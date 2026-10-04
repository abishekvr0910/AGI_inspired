"""Hermetic unit tests for platform sandboxing, POSIX containment, and cloud secrets."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))

import platform_sandbox
from platform_sandbox import (
    PlatformInfo,
    PlatformSandboxError,
    PosixContainedProcess,
    PosixJobHandle,
    detect_platform,
    read_mounted_secret,
    sanitize_worker_environment,
    spawn_posix_worker,
)
import secrets


class PlatformSandboxTests(unittest.TestCase):
    def test_detect_platform_real_and_mocked(self):
        info = detect_platform()
        self.assertIsInstance(info, PlatformInfo)
        self.assertIn(info.system, ("win32", "linux", "darwin"))
        if sys.platform == "win32":
            self.assertTrue(info.is_windows)
            self.assertEqual(info.containment_backend, "windows_job_object")

        # Mock Linux container environment
        with patch("sys.platform", "linux"), patch("pathlib.Path.exists") as mock_exists:
            mock_exists.side_effect = lambda p=None: True  # /.dockerenv exists
            lin_info = detect_platform()
            self.assertTrue(lin_info.is_linux)
            self.assertTrue(lin_info.is_container)
            self.assertEqual(lin_info.containment_backend, "container_posix_session")

        # Mock Linux with cgroups v2
        with patch("sys.platform", "linux"), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("os.access", return_value=True):
            cg_info = detect_platform()
            self.assertTrue(cg_info.is_linux)
            self.assertTrue(cg_info.has_cgroups_v2)
            self.assertEqual(cg_info.containment_backend, "linux_cgroup_v2")

    def test_sanitize_worker_environment_windows_and_posix(self):
        with tempfile.TemporaryDirectory() as td:
            worker_home = Path(td)
            base_env = {
                "HARNESS_WORKER_HOME": str(worker_home),
                "PATH": "/usr/bin:/bin",
                "WINDIR": "C:\\Windows",
                "SYSTEMROOT": "C:\\Windows",
                "LANG": "en_US.UTF-8",
                "SECRET_LEAK_VAR": "super_secret_dont_leak",
            }
            auth = {
                "OPENAI_API_KEY": "sk-authorized-test-token",
                "CUSTOM_TOKEN": "custom-auth-token-xyz",
            }

            # 1. Windows platform sanitization
            win_info = PlatformInfo(
                system="win32", is_windows=True, is_linux=False, is_darwin=False,
                is_container=False, has_cgroups_v2=False, cgroup_root=None,
                containment_backend="windows_job_object",
            )
            win_env = sanitize_worker_environment(base_env, auth, platform_info=win_info)
            self.assertIn("WINDIR", win_env)
            self.assertIn("SYSTEMROOT", win_env)
            self.assertNotIn("SECRET_LEAK_VAR", win_env)
            self.assertEqual(win_env["OPENAI_API_KEY"], "sk-authorized-test-token")
            self.assertEqual(win_env["HOME"], str(worker_home))
            self.assertEqual(win_env["PYTHONNOUSERSITE"], "1")

            # 2. POSIX platform sanitization
            posix_info = PlatformInfo(
                system="linux", is_windows=False, is_linux=True, is_darwin=False,
                is_container=False, has_cgroups_v2=False, cgroup_root=None,
                containment_backend="posix_process_group",
            )
            posix_env = sanitize_worker_environment(base_env, auth, platform_info=posix_info)
            self.assertIn("PATH", posix_env)
            self.assertIn("LANG", posix_env)
            self.assertNotIn("SECRET_LEAK_VAR", posix_env)
            self.assertEqual(posix_env["OPENAI_API_KEY"], "sk-authorized-test-token")
            self.assertEqual(posix_env["TMPDIR"], str(worker_home))

            # 3. Validation: missing worker home raises
            with self.assertRaises(PlatformSandboxError):
                sanitize_worker_environment({}, auth, platform_info=posix_info)

            # 4. Validation: illegal auth variable raises
            with self.assertRaises(PlatformSandboxError):
                sanitize_worker_environment(
                    base_env, {"INVALID_VAR_NAME": "val"}, platform_info=posix_info)

    def test_read_mounted_secret_and_secrets_integration(self):
        with tempfile.TemporaryDirectory() as td:
            secret_dir = Path(td)
            (secret_dir / "openai_api_key").write_text("sk-cloud-secret-token-999\n", encoding="utf-8")
            (secret_dir / "anthropic").write_text("claude-secret-mounted-val\n", encoding="utf-8")

            # Direct read from mounted directory
            self.assertEqual(read_mounted_secret("openai", custom_mount=secret_dir), "sk-cloud-secret-token-999")
            self.assertEqual(read_mounted_secret("anthropic", custom_mount=secret_dir), "claude-secret-mounted-val")
            self.assertIsNone(read_mounted_secret("unknown_provider", custom_mount=secret_dir))

            # Integration with orchestrator/secrets.py via AGI_SECRETS_DIR
            with patch.dict(os.environ, {"AGI_SECRETS_DIR": str(secret_dir), "OPENAI_API_KEY": ""}):
                with patch("secrets._win32cred", None):
                    key = secrets.get_api_key("openai")
                    self.assertEqual(key, "sk-cloud-secret-token-999")
                    has_key = secrets.vault_or_manager_has_api_key("openai")
                    self.assertTrue(has_key)

    def test_posix_contained_process_lifecycle(self):
        # Test model-free test guard on forbidden executables
        with patch.dict(os.environ, {"AGI_LIVE_EXECUTION_ALLOWED": "0"}):
            with self.assertRaises(PlatformSandboxError):
                spawn_posix_worker(["/usr/bin/ollama", "serve"], None, {})

        # Test spawning a contained python echo process
        script = "import sys; print('SANDBOX_ALIVE', flush=True); sys.exit(0)"
        proc = spawn_posix_worker(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            env={"PATH": os.environ.get("PATH", "")},
        )
        self.assertIsInstance(proc, PosixContainedProcess)
        self.assertIsInstance(proc.job_handle, PosixJobHandle)
        code = proc.wait(timeout=10)
        self.assertEqual(code, 0)
        out = proc.stdout.read().decode("utf-8")
        self.assertIn("SANDBOX_ALIVE", out)
        proc.close()

    def test_posix_contained_process_kill(self):
        # Test terminating a long-running process
        script = "import time; time.sleep(60)"
        proc = spawn_posix_worker(
            [sys.executable, "-c", script],
            cwd=str(ROOT),
            env={"PATH": os.environ.get("PATH", "")},
        )
        self.assertIsNone(proc.poll())
        proc.kill()
        proc.wait(timeout=5)
        self.assertIsNotNone(proc.returncode)
        proc.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

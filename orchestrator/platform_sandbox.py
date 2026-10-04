"""Platform abstraction layer for process sandboxing, containment, and secrets.

Provides cross-platform parity between Windows (Win32 Job Objects, Restricted
Tokens, and Windows Credential Manager) and Linux/POSIX/Cloud-Native environments
(POSIX process group sessions, cgroups v2, and container volume-mounted secrets).

No elevation or unrestricted fallbacks: fail-closed containment is guaranteed
on all supported operating systems.
"""
from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]


class PlatformSandboxError(RuntimeError):
    """The platform containment contract could not be established."""


@dataclass(frozen=True)
class PlatformInfo:
    """Operating system and container environment capabilities."""
    system: str
    is_windows: bool
    is_linux: bool
    is_darwin: bool
    is_container: bool
    has_cgroups_v2: bool
    cgroup_root: Path | None
    containment_backend: str


def detect_platform() -> PlatformInfo:
    """Detect current operating system and container virtualization layer."""
    sys_name = sys.platform
    is_win = sys_name == "win32"
    is_lin = sys_name.startswith("linux")
    is_mac = sys_name == "darwin"

    # Container detection: Docker .dockerenv, K8s serviceaccount, or container env var
    is_container = False
    if Path("/.dockerenv").exists():
        is_container = True
    elif Path("/run/secrets/kubernetes.io").exists() or Path("/var/run/secrets/kubernetes.io").exists():
        is_container = True
    elif os.environ.get("CONTAINER", "").lower() in ("docker", "podman", "containerd", "oci"):
        is_container = True

    # Linux cgroups v2 detection
    has_cgroup2 = False
    cgroup_root = None
    if is_lin:
        cg_path = Path("/sys/fs/cgroup")
        controllers = cg_path / "cgroup.controllers"
        if controllers.is_file():
            has_cgroup2 = True
            cgroup_root = cg_path

    if is_win:
        backend = "windows_job_object"
    elif has_cgroup2 and os.access(cgroup_root, os.W_OK):
        backend = "linux_cgroup_v2"
    elif is_container:
        backend = "container_posix_session"
    else:
        backend = "posix_process_group"

    return PlatformInfo(
        system=sys_name,
        is_windows=is_win,
        is_linux=is_lin,
        is_darwin=is_mac,
        is_container=is_container,
        has_cgroups_v2=has_cgroup2,
        cgroup_root=cgroup_root,
        containment_backend=backend,
    )


# ── Cross-Platform Worker Environment ────────────────────────────────────────

WINDOWS_ALLOWED_ENV = {
    "SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
    "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
}

POSIX_ALLOWED_ENV = {
    "PATH", "LANG", "LC_ALL", "SHELL", "TERM", "USER", "LOGNAME",
    "HOSTNAME", "PWD", "LD_LIBRARY_PATH", "SSL_CERT_FILE", "SSL_CERT_DIR",
}


def sanitize_worker_environment(
    base: dict[str, str],
    authentication: dict[str, str],
    platform_info: PlatformInfo | None = None,
) -> dict[str, str]:
    """Filter environment variables to enforce fail-closed credential isolation."""
    info = platform_info or detect_platform()
    home = base.get("HARNESS_WORKER_HOME", "")
    if not home or not Path(home).is_absolute() or not Path(home).is_dir():
        raise PlatformSandboxError("dedicated_HARNESS_WORKER_HOME_required")

    allowed = WINDOWS_ALLOWED_ENV if info.is_windows else POSIX_ALLOWED_ENV
    env = {k: v for k, v in base.items() if (k.upper() in allowed if info.is_windows else k in allowed)}

    # Standard sandbox paths
    env.update({
        "HOME": home,
        "USERPROFILE": home,
        "TEMP": home,
        "TMP": home,
        "TMPDIR": home,
        "PYTHONIOENCODING": "utf-8",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    })

    # Only declared authentication variables ending in _API_KEY or _TOKEN cross
    for name, value in authentication.items():
        if not name.isidentifier() or not name.upper().endswith(("_API_KEY", "_TOKEN")):
            raise PlatformSandboxError("unsupported_worker_authentication_variable")
        env[name] = value

    return env


# ── POSIX Process Containment ────────────────────────────────────────────────

class PosixJobHandle:
    """Manages process group and optional cgroup v2 lifecycle for POSIX processes."""

    def __init__(self, pid: int, pgid: int, cgroup_dir: Path | None = None):
        self.pid = pid
        self.pgid = pgid
        self.cgroup_dir = cgroup_dir
        self._terminated = False

    def terminate(self, exit_code: int = 75) -> None:
        """Terminate entire process group tree fail-closed."""
        if self._terminated:
            return
        self._terminated = True

        # 1. cgroup v2 kill if present
        if self.cgroup_dir and (self.cgroup_dir / "cgroup.kill").is_file():
            try:
                (self.cgroup_dir / "cgroup.kill").write_text("1", encoding="ascii")
            except OSError:
                pass

        # 2. Process group termination via SIGTERM, followed by SIGKILL
        if self.pgid > 0:
            if hasattr(os, "killpg"):
                try:
                    os.killpg(self.pgid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    os.killpg(self.pgid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
            elif hasattr(os, "kill"):
                try:
                    os.kill(self.pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    os.kill(self.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                except (ProcessLookupError, PermissionError):
                    pass

    def close(self) -> None:
        """Clean up cgroup directory if allocated."""
        if self.cgroup_dir and self.cgroup_dir.is_dir():
            try:
                self.cgroup_dir.rmdir()
            except OSError:
                pass


class PosixContainedProcess:
    """Restricted native process adapter mirroring RestrictedProcess contract."""

    def __init__(self, popen_proc: subprocess.Popen, job_handle: PosixJobHandle):
        self._proc = popen_proc
        self.pid = popen_proc.pid
        self.args = popen_proc.args
        self.stdin = popen_proc.stdin
        self.stdout = popen_proc.stdout
        self.stderr = popen_proc.stderr
        self.job_handle = job_handle
        self.returncode = None

    def wait(self, timeout: float | None = None) -> int:
        try:
            self.returncode = self._proc.wait(timeout=timeout)
            return self.returncode
        except subprocess.TimeoutExpired:
            raise

    def poll(self) -> int | None:
        self.returncode = self._proc.poll()
        return self.returncode

    def kill(self) -> None:
        self.job_handle.terminate()
        try:
            self._proc.kill()
        except OSError:
            pass

    def close(self) -> None:
        for stream in (self.stdin, self.stdout, self.stderr):
            if stream and not stream.closed:
                try:
                    stream.close()
                except Exception:
                    pass
        self.job_handle.close()


def spawn_posix_worker(
    command: list[str],
    cwd: str | Path | None,
    env: dict[str, str],
    cgroup_scope: str | None = None,
) -> PosixContainedProcess:
    """Spawn a research worker inside an isolated POSIX process group and optional cgroup."""
    if not command or not Path(command[0]).is_absolute() or env is None:
        raise PlatformSandboxError("absolute_worker_executable_and_explicit_environment_required")
    if any(not key or "=" in key or "\0" in key or "\0" in value for key, value in env.items()):
        raise PlatformSandboxError("invalid_worker_environment_block")

    if os.environ.get("AGI_LIVE_EXECUTION_ALLOWED") == "0":
        forbidden = {
            "hermes", "hermes.exe", "ollama", "ollama.exe", "controlled_hermes.py",
            "batch_runner.py", "run_task.py", "onboarding_autonomy.py", "run_daily.py",
        }
        if any(Path(arg).name.lower() in forbidden for arg in command):
            raise PlatformSandboxError("live_worker_blocked_in_model_free_test")

    # Optional cgroup v2 setup
    cg_dir = None
    if cgroup_scope and Path("/sys/fs/cgroup").is_dir():
        candidate_cg = Path("/sys/fs/cgroup") / f"agi_{cgroup_scope}"
        try:
            candidate_cg.mkdir(parents=True, exist_ok=True)
            cg_dir = candidate_cg
        except OSError:
            cg_dir = None

    proc = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,  # Creates a distinct POSIX process group with PGID == PID
    )

    # Attach to cgroup if available
    if cg_dir and (cg_dir / "cgroup.procs").is_file():
        try:
            (cg_dir / "cgroup.procs").write_text(str(proc.pid), encoding="ascii")
        except OSError:
            pass

    job_handle = PosixJobHandle(pid=proc.pid, pgid=proc.pid, cgroup_dir=cg_dir)
    return PosixContainedProcess(proc, job_handle)


# ── Cloud-Native Secret Volume Discovery ─────────────────────────────────────

STANDARD_SECRET_MOUNTS = [
    Path("/var/run/secrets/agi"),
    Path("/run/secrets"),
    Path("/etc/secrets"),
]


def read_mounted_secret(provider: str, custom_mount: Path | str | None = None) -> str | None:
    """Search container-mounted secret files (Kubernetes / Docker secrets).

    Looks for exact provider name file or environment variable equivalent.
    Never raises on missing files or permissions; returns None fail-closed.
    """
    normalized = provider.strip().lower()
    targets = [normalized, normalized.replace("-", "_")]
    env_keys = {
        "byteplus_coding": "ark_api_key",
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "typesafe": "typesafe_api_key",
    }
    if normalized in env_keys:
        targets.append(env_keys[normalized])

    search_dirs: list[Path] = []
    if custom_mount:
        search_dirs.append(Path(custom_mount))
    env_secret_dir = os.environ.get("AGI_SECRETS_DIR")
    if env_secret_dir:
        search_dirs.append(Path(env_secret_dir))
    search_dirs.extend(STANDARD_SECRET_MOUNTS)

    for s_dir in search_dirs:
        if not s_dir.is_dir():
            continue
        for target in targets:
            secret_file = s_dir / target
            if secret_file.is_file():
                try:
                    val = secret_file.read_text(encoding="utf-8").strip()
                    if val:
                        return val
                except OSError:
                    continue
    return None

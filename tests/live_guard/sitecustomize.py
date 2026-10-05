"""Fail closed if a non-live test attempts model, network, or mission execution."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import subprocess

if os.environ.get("AGI_LIVE_EXECUTION_ALLOWED") != "1":
    _real_popen = subprocess.Popen
    _blocked_scripts = {"batch_runner.py", "run_task.py", "controlled_hermes.py",
                        "onboarding_autonomy.py", "run_daily.py"}

    def _items(args) -> list[str]:
        if isinstance(args, (str, bytes)):
            return [os.fsdecode(args)]
        return [os.fsdecode(item) for item in args]

    def _live_command(args) -> str | None:
        for item in _items(args):
            name = Path(item).name.lower()
            if name in {"hermes", "hermes.exe", "ollama", "ollama.exe"} or name in _blocked_scripts:
                return name
        return None

    class GuardedPopen(_real_popen):
        def __init__(self, args, *pargs, **kwargs):
            blocked = _live_command(args)
            if blocked:
                raise RuntimeError(f"LIVE PATH BLOCKED in {os.environ.get('AGI_TEST_TIER', 'default')} "
                                   f"test tier: attempted {blocked}")
            super().__init__(args, *pargs, **kwargs)

    _real_connect = socket.socket.connect

    def _blocked_connect(self, address):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and address[1] != 11434:
            return _real_connect(self, address)
        raise RuntimeError(f"LIVE NETWORK BLOCKED in {os.environ.get('AGI_TEST_TIER', 'default')} "
                           f"test tier: attempted {address!r}")

    _real_create_connection = socket.create_connection

    def _blocked_create_connection(address, *args, **kwargs):
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"} and address[1] != 11434:
            return _real_create_connection(address, *args, **kwargs)
        raise RuntimeError(f"LIVE NETWORK BLOCKED in {os.environ.get('AGI_TEST_TIER', 'default')} "
                           f"test tier: attempted {address!r}")

    subprocess.Popen = GuardedPopen
    socket.socket.connect = _blocked_connect
    socket.create_connection = _blocked_create_connection

    try:
        import win32cred  # type: ignore[import-untyped]
        _real_cred_write = win32cred.CredWrite

        def _guarded_cred_write(credential, flags=0):
            target = credential.get("TargetName", "") if isinstance(credential, dict) else ""
            if "operator_key" in str(target).lower():
                raise RuntimeError(
                    f"CREDENTIAL STORE WRITE BLOCKED in {os.environ.get('AGI_TEST_TIER', 'default')} "
                    f"test tier: attempted {target}"
                )
            return _real_cred_write(credential, flags)

        win32cred.CredWrite = _guarded_cred_write
    except (ImportError, Exception):
        pass

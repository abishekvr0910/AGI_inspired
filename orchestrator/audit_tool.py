"""Audit Retention, Replica Verification & Attestation Tooling.

Non-provisioning operator helper commands implementing Stage 6 requirements of
docs/HARNESS_COMPLETION_DIRECTIVE_2026-10-05.md:
  1. Evidence collection and replica chain verification (UNC & S3 WORM backends)
  2. Restore verification (validating trajectory artifact SHA-256 with dry-run support)
  3. Egress boundary attestation validation (Ed25519 signature, TTL, policy claims)

All commands are idempotent, non-mutating by default (--dry-run), strictly redact
secrets, and fail closed on tampered or missing historical artifacts.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))

import audit_replication
import egress_policy

logger = logging.getLogger(__name__)

GENESIS_HASH = "GENESIS"


def mask_secret(value: Optional[str], visible_prefix: int = 4, visible_suffix: int = 2) -> str:
    """Safely redact secret tokens and access keys from operator logs/output."""
    if not value or not str(value).strip():
        return "<not-configured>"
    s = str(value).strip()
    if len(s) <= visible_prefix + visible_suffix:
        return "********"
    return f"{s[:visible_prefix]}***{s[-visible_suffix:]}"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# 1. Evidence Collection & Chain Verification
# ---------------------------------------------------------------------------

def collect_evidence(
    config_path: Path = audit_replication.CONFIG_PATH,
    environment: Optional[dict[str, str]] = None,
    now: Optional[datetime] = None,
    s3_client: Any = None,
    verify_checkpoint: Optional[Callable[[str], dict[str, Any] | None]] = None,
    signing_state: Optional[Callable[[], dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Inspect off-machine audit configuration and verify remote retention chain.

    Read-only, non-mutating evidence collection covering UNC and S3 backends.
    Redacts all credentials in output.
    """
    env = os.environ if environment is None else environment
    backend = str(env.get("HARNESS_AUDIT_BACKEND") or "").strip().lower() or "unc"
    enforce_env = str(env.get("HARNESS_AUDIT_ENFORCE") or "").strip()
    enforcement_requested = enforce_env == "1"

    current_ts = now or datetime.now(timezone.utc)

    if backend == "s3":
        try:
            import s3_audit_replication
            s3_cfg = s3_audit_replication.load_s3_config_from_env(env)
            state = s3_audit_replication.s3_audit_state(
                environment=env,
                verify_checkpoint=verify_checkpoint,
                signing_state=signing_state,
                now=current_ts,
            )
            redacted_config = {
                "backend": "s3",
                "bucket": s3_cfg.bucket,
                "endpoint_url": s3_cfg.endpoint_url or "<default-aws>",
                "region_name": s3_cfg.region_name,
                "access_key_id": mask_secret(s3_cfg.access_key_id),
                "secret_access_key": "********" if s3_cfg.secret_access_key else "<not-configured>",
                "retention_mode": s3_cfg.retention_mode,
                "retention_days": s3_cfg.retention_days,
                "minimum_retention_days": s3_cfg.minimum_retention_days,
                "checkpoint_max_age_hours": s3_cfg.checkpoint_max_age_hours,
            }
            return {
                "ok": state.get("ok") is True,
                "backend": "s3",
                "enforcement_requested": enforcement_requested,
                "config": redacted_config,
                "replica_accessible": state.get("error") != "s3_client_unavailable",
                "checkpoint_count": state.get("checkpoints", 0),
                "latest": state.get("latest"),
                "fresh": state.get("fresh", False),
                "artifact_ok": state.get("artifact_ok", False),
                "truncation_detected": state.get("truncation_detected", False),
                "retention_floor_ok": state.get("retention_floor_ok", False),
                "retention_floor_days": state.get("retention_floor_days", 0.0),
                "minimum_retention_days": s3_cfg.minimum_retention_days,
                "immutability_guarantee": state.get("immutability_guarantee", "storage_object_lock_compliance"),
                "error": state.get("error"),
            }
        except Exception as exc:
            return {
                "ok": False,
                "backend": "s3",
                "enforcement_requested": enforcement_requested,
                "config": {"backend": "s3"},
                "replica_accessible": False,
                "checkpoint_count": 0,
                "latest": None,
                "fresh": False,
                "artifact_ok": False,
                "truncation_detected": False,
                "retention_floor_ok": False,
                "retention_floor_days": 0.0,
                "minimum_retention_days": 0,
                "immutability_guarantee": "none",
                "error": f"s3_config_error:{type(exc).__name__}:{exc}",
            }

    # UNC / Local Share Backend
    try:
        unc_cfg = audit_replication.load_config(config_path)
        enforcement_requested = audit_replication.enforcement_requested(unc_cfg, env)
    except Exception as exc:
        return {
            "ok": False,
            "backend": "unc",
            "enforcement_requested": enforcement_requested,
            "config": {},
            "replica_accessible": False,
            "checkpoint_count": 0,
            "latest": None,
            "fresh": False,
            "artifact_ok": False,
            "truncation_detected": False,
            "retention_floor_ok": False,
            "retention_floor_days": 0.0,
            "minimum_retention_days": 0,
            "immutability_guarantee": "none",
            "error": f"unc_config_error:{type(exc).__name__}:{exc}",
        }

    raw_root = str(env.get(unc_cfg.root_environment_variable) or "").strip()
    root_configured = bool(raw_root)
    root_is_unc = raw_root.startswith("\\\\")
    root_path = Path(raw_root) if root_configured else None
    root_accessible = root_path.is_dir() if root_path else False

    redacted_config = {
        "backend": "unc",
        "replica_root": raw_root or "<not-configured>",
        "require_unc": unc_cfg.require_unc,
        "is_unc": root_is_unc,
        "root_accessible": root_accessible,
        "artifact_subdirectory": unc_cfg.artifact_subdirectory,
        "checkpoint_filename": unc_cfg.checkpoint_filename,
        "checkpoint_max_age_hours": unc_cfg.checkpoint_max_age_hours,
        "minimum_retention_days": unc_cfg.minimum_retention_days,
        "enforcement_env_var": unc_cfg.enforcement_environment_variable,
    }

    state = audit_replication.audit_state(
        config_path=config_path,
        environment=env,
        verify_checkpoint=verify_checkpoint,
        signing_state=signing_state,
        now=current_ts,
    )

    return {
        "ok": state.get("ok") is True,
        "backend": "unc",
        "enforcement_requested": enforcement_requested,
        "config": redacted_config,
        "replica_accessible": root_accessible,
        "checkpoint_count": state.get("checkpoints", 0),
        "latest": state.get("latest"),
        "fresh": state.get("fresh", False),
        "artifact_ok": state.get("artifact_ok", False),
        "truncation_detected": state.get("truncation_detected", False),
        "retention_floor_ok": state.get("retention_floor_ok", False),
        "retention_floor_days": state.get("retention_floor_days", 0.0),
        "minimum_retention_days": unc_cfg.minimum_retention_days,
        "immutability_guarantee": state.get("immutability_guarantee", "detection_only_storage_worm_required"),
        "error": state.get("error"),
    }


# ---------------------------------------------------------------------------
# 2. Restore Verification (Dry-Run & Content Validation)
# ---------------------------------------------------------------------------

def verify_restore(
    task_id: Optional[int] = None,
    checkpoint_hash: Optional[str] = None,
    target_dir: Optional[Path] = None,
    dry_run: bool = True,
    config_path: Path = audit_replication.CONFIG_PATH,
    environment: Optional[dict[str, str]] = None,
    s3_client: Any = None,
    verify_checkpoint: Optional[Callable[[str], dict[str, Any] | None]] = None,
) -> dict[str, Any]:
    """Verify that a replicated trajectory artifact can be retrieved and validated.

    In dry_run mode (default), verifies artifact readability and SHA-256 digest
    match without mutating the filesystem.
    In restore mode, writes the verified trajectory to target_dir with atomic
    commit and path containment enforcement.
    """
    env = os.environ if environment is None else environment
    backend = str(env.get("HARNESS_AUDIT_BACKEND") or "").strip().lower() or "unc"

    if verify_checkpoint is None:
        import audit_signing
        verify_checkpoint = audit_signing.verify_checkpoint

    if backend == "s3":
        import s3_audit_replication
        s3_cfg = s3_audit_replication.load_s3_config_from_env(env)
        client = s3_client or s3_audit_replication.get_s3_client(s3_cfg)

        chain = s3_audit_replication.verify_s3_checkpoint_chain(
            client, s3_cfg, verify_checkpoint, verify_artifacts=False
        )
        if not chain.get("ok"):
            return {
                "ok": False,
                "error": f"remote_checkpoint_invalid:{chain.get('error')}",
                "backend": "s3",
            }
        checkpoints = chain.get("checkpoints") or []
        if not checkpoints:
            return {"ok": False, "error": "no_checkpoints_found", "backend": "s3"}

        target_cp = _find_target_checkpoint(checkpoints, task_id, checkpoint_hash)
        if target_cp is None:
            return {"ok": False, "error": "target_checkpoint_not_found", "backend": "s3"}

        rel_path = target_cp["artifact_relative_path"]
        expected_digest = target_cp["trajectory_sha256"]
        expected_bytes = target_cp.get("source_bytes")

        try:
            resp = client.get_object(Bucket=s3_cfg.bucket, Key=rel_path)
            content_bytes = resp["Body"].read()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"s3_download_failed:{type(exc).__name__}:{exc}",
                "backend": "s3",
                "key": rel_path,
            }

        actual_digest = _sha256_bytes(content_bytes)
        if actual_digest != expected_digest:
            return {
                "ok": False,
                "error": "artifact_hash_mismatch",
                "backend": "s3",
                "expected_digest": expected_digest,
                "actual_digest": actual_digest,
            }

        if dry_run:
            return {
                "ok": True,
                "dry_run": True,
                "backend": "s3",
                "task_id": target_cp.get("task_id"),
                "checkpoint_hash": target_cp.get("checkpoint_hash"),
                "artifact_path": rel_path,
                "bytes": len(content_bytes),
                "sha256": actual_digest,
                "verified": True,
            }

        if target_dir is None:
            return {"ok": False, "error": "target_dir_required_for_restore", "backend": "s3"}

        dest = _safe_target_path(target_dir, rel_path, target_cp.get("task_id"))
        _write_atomic(dest, content_bytes)

        return {
            "ok": True,
            "dry_run": False,
            "backend": "s3",
            "task_id": target_cp.get("task_id"),
            "checkpoint_hash": target_cp.get("checkpoint_hash"),
            "restored_path": str(dest),
            "bytes": len(content_bytes),
            "sha256": actual_digest,
            "verified": True,
        }

    # UNC Backend
    unc_cfg = audit_replication.load_config(config_path)
    try:
        root = audit_replication._replica_root(unc_cfg, env)
    except Exception as exc:
        return {"ok": False, "error": f"replica_root_error:{exc}", "backend": "unc"}

    cp_path = audit_replication._checkpoint_path(root, unc_cfg)
    chain = audit_replication.verify_checkpoint_chain(
        cp_path, unc_cfg, verify_checkpoint, replica_root=root
    )
    if not chain.get("ok"):
        return {
            "ok": False,
            "error": f"remote_checkpoint_invalid:{chain.get('error')}",
            "backend": "unc",
        }
    checkpoints = chain.get("checkpoints") or []
    if not checkpoints:
        return {"ok": False, "error": "no_checkpoints_found", "backend": "unc"}

    target_cp = _find_target_checkpoint(checkpoints, task_id, checkpoint_hash)
    if target_cp is None:
        return {"ok": False, "error": "target_checkpoint_not_found", "backend": "unc"}

    rel_path = target_cp["artifact_relative_path"]
    expected_digest = target_cp["trajectory_sha256"]
    artifact_file = root / rel_path

    if not artifact_file.is_file():
        return {
            "ok": False,
            "error": "replica_artifact_missing",
            "backend": "unc",
            "artifact_path": str(artifact_file),
        }

    actual_digest = _sha256_file(artifact_file)
    if actual_digest != expected_digest:
        return {
            "ok": False,
            "error": "artifact_hash_mismatch",
            "backend": "unc",
            "expected_digest": expected_digest,
            "actual_digest": actual_digest,
        }

    file_size = artifact_file.stat().st_size

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "backend": "unc",
            "task_id": target_cp.get("task_id"),
            "checkpoint_hash": target_cp.get("checkpoint_hash"),
            "artifact_path": str(artifact_file),
            "bytes": file_size,
            "sha256": actual_digest,
            "verified": True,
        }

    if target_dir is None:
        return {"ok": False, "error": "target_dir_required_for_restore", "backend": "unc"}

    dest = _safe_target_path(target_dir, rel_path, target_cp.get("task_id"))
    content_bytes = artifact_file.read_bytes()
    _write_atomic(dest, content_bytes)

    return {
        "ok": True,
        "dry_run": False,
        "backend": "unc",
        "task_id": target_cp.get("task_id"),
        "checkpoint_hash": target_cp.get("checkpoint_hash"),
        "restored_path": str(dest),
        "bytes": file_size,
        "sha256": actual_digest,
        "verified": True,
    }


def _find_target_checkpoint(
    checkpoints: list[dict[str, Any]],
    task_id: Optional[int],
    checkpoint_hash: Optional[str],
) -> Optional[dict[str, Any]]:
    if checkpoint_hash:
        for cp in reversed(checkpoints):
            if cp.get("checkpoint_hash") == checkpoint_hash:
                return cp
        return None
    if task_id is not None:
        for cp in reversed(checkpoints):
            if cp.get("task_id") == task_id:
                return cp
        return None
    # Default to latest checkpoint
    return checkpoints[-1] if checkpoints else None


def _safe_target_path(target_dir: Path, rel_path: str, task_id: Optional[int]) -> Path:
    """Enforce directory containment and compute safe destination path."""
    dest_dir = target_dir.resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = Path(rel_path).name
    if not filename or ".." in filename:
        filename = f"task{task_id or 'unknown'}.trajectory.jsonl"
    dest = (dest_dir / filename).resolve()
    # Path containment check: ensure dest is strictly within dest_dir
    try:
        dest.relative_to(dest_dir)
    except ValueError:
        raise ValueError(f"Path traversal detected: {dest} is outside {dest_dir}")
    return dest


def _write_atomic(dest: Path, content: bytes) -> None:
    tmp = dest.with_name(f"{dest.name}.tmp.{os.getpid()}")
    try:
        tmp.write_bytes(content)
        tmp.replace(dest)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 3. Egress Boundary Attestation Validation
# ---------------------------------------------------------------------------

def validate_attestation(
    token_path: Optional[Path] = None,
    policy_path: Path = egress_policy.POLICY_PATH,
    environment: Optional[dict[str, str]] = None,
    now: Optional[datetime] = None,
    verify_token: Optional[Callable[[str], dict[str, Any] | None]] = None,
) -> dict[str, Any]:
    """Validate the signed egress boundary attestation token with granular TTL details."""
    try:
        policy = egress_policy.load_policy(policy_path)
    except Exception as exc:
        return {"ok": False, "error": f"policy_load_failed:{exc}"}

    env = os.environ if environment is None else environment
    if token_path is None:
        raw_env = str(env.get(policy.attestation_env) or "").strip()
        if raw_env:
            path = Path(raw_env)
        else:
            path = policy_path.resolve().parents[1] / ".harness" / "egress_attestation.signed"
    else:
        path = token_path

    if not path.is_file():
        return {
            "ok": False,
            "error": "attestation_file_missing",
            "token_path": str(path),
            "policy_digest": policy.digest,
        }

    try:
        raw_token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return {
            "ok": False,
            "error": f"attestation_unreadable:{type(exc).__name__}",
            "token_path": str(path),
            "policy_digest": policy.digest,
        }

    if verify_token is None:
        try:
            import operator_auth
            verify_token = operator_auth.verify_marker
        except Exception:
            return {
                "ok": False,
                "error": "operator_verifier_unavailable",
                "token_path": str(path),
                "policy_digest": policy.digest,
            }

    payload = verify_token(raw_token)
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "error": "attestation_untrusted_signature",
            "token_path": str(path),
            "policy_digest": policy.digest,
        }

    issued_at = _parse_timestamp(payload.get("issued_at"))
    current = now or datetime.now(timezone.utc)

    if issued_at is None:
        age_hours = 0.0
        ttl_remaining = 0.0
        is_expired = True
    else:
        age_delta = current - issued_at
        age_hours = round(age_delta.total_seconds() / 3600.0, 2)
        ttl_remaining = round(max(0.0, policy.max_age_hours - age_hours), 2)
        is_expired = age_hours > policy.max_age_hours or issued_at > current

    present_evidence = payload.get("evidence")
    evidence_list = sorted(present_evidence) if isinstance(present_evidence, list) else []
    missing_evidence = sorted(list(policy.required_evidence - set(evidence_list)))

    claims = payload.get("claims") or {}
    claims_ok = egress_policy._claims_complete(payload, policy)
    endpoint = payload.get("broker_endpoint")
    endpoint_ok = endpoint == f"{policy.host}:{policy.port}"
    policy_digest_ok = payload.get("policy_sha256") == policy.digest
    purpose_ok = payload.get("purpose") == policy.attestation_purpose

    ok = (
        purpose_ok
        and policy_digest_ok
        and not is_expired
        and endpoint_ok
        and not missing_evidence
        and claims_ok
    )

    error = None
    if not ok:
        if is_expired:
            error = "attestation_expired"
        elif not policy_digest_ok:
            error = "policy_digest_mismatch"
        elif not endpoint_ok:
            error = "broker_endpoint_mismatch"
        elif missing_evidence:
            error = f"missing_evidence:{','.join(missing_evidence)}"
        elif not claims_ok:
            error = "claims_incomplete"
        else:
            error = "attestation_invalid"

    return {
        "ok": ok,
        "token_path": str(path),
        "policy_digest": policy.digest,
        "broker_endpoint": f"{policy.host}:{policy.port}",
        "issued_at": issued_at.isoformat() if issued_at else None,
        "age_hours": age_hours,
        "max_age_hours": policy.max_age_hours,
        "ttl_hours_remaining": ttl_remaining,
        "is_expired": is_expired,
        "evidence": evidence_list,
        "missing_evidence": missing_evidence,
        "claims": sorted(claims.keys()) if isinstance(claims, dict) else [],
        "error": error,
    }


# ---------------------------------------------------------------------------
# 4. Human-Readable Renderers
# ---------------------------------------------------------------------------

def render_evidence(data: dict[str, Any]) -> str:
    lines = ["=== OFF-MACHINE AUDIT RETENTION STATUS ==="]
    backend = data.get("backend", "unknown").upper()
    lines.append(f"Backend: {backend}")
    enforced = "ENABLED (HARNESS_AUDIT_ENFORCE=1)" if data.get("enforcement_requested") else "DISABLED (enforcement not requested)"
    lines.append(f"Enforcement: {enforced}")

    cfg = data.get("config") or {}
    if backend == "S3":
        lines.append(f"Bucket: {cfg.get('bucket')} (region={cfg.get('region_name')})")
        lines.append(f"Endpoint: {cfg.get('endpoint_url')}")
        lines.append(f"Access Key: {cfg.get('access_key_id')}")
        lines.append(f"Retention Mode: {cfg.get('retention_mode')} ({cfg.get('retention_days')} days)")
    else:
        lines.append(f"Replica Root: {cfg.get('replica_root')} (UNC={cfg.get('is_unc')}, Accessible={cfg.get('root_accessible')})")
        lines.append(f"Max Age: {cfg.get('checkpoint_max_age_hours')}h | Retention Floor: {cfg.get('minimum_retention_days')} days")

    lines.append("------------------------------------------")
    mark = "PASS" if data.get("ok") else "FAIL"
    lines.append(f"[{mark}] Integrity Status:")
    lines.append(f"  • Checkpoint Count: {data.get('checkpoint_count')}")
    lines.append(f"  • Latest Checkpoint: {data.get('latest')}")
    lines.append(f"  • Freshness (<24h): {'YES' if data.get('fresh') else 'NO'}")
    lines.append(f"  • Artifact Digest Verification: {'ALL MATCH' if data.get('artifact_ok') else 'INVALID/MISSING'}")
    lines.append(f"  • Truncation Detected: {'YES (TAMPERED)' if data.get('truncation_detected') else 'NO'}")
    lines.append(f"  • Retention Floor: {data.get('retention_floor_days'):.1f} days (min: {data.get('minimum_retention_days')} days)")
    lines.append(f"  • Immutability: {data.get('immutability_guarantee')}")
    if data.get("error"):
        lines.append(f"  • Error: {data.get('error')}")
    return "\n".join(lines)


def render_restore(data: dict[str, Any]) -> str:
    lines = ["=== AUDIT TRAJECTORY RESTORE VERIFICATION ==="]
    mark = "PASS" if data.get("ok") else "FAIL"
    mode = "DRY-RUN (read-only verification)" if data.get("dry_run") else "RESTORED TO DISK"
    lines.append(f"[{mark}] Mode: {mode}")
    if data.get("ok"):
        lines.append(f"  • Task ID: {data.get('task_id')}")
        lines.append(f"  • Checkpoint Hash: {data.get('checkpoint_hash')}")
        lines.append(f"  • SHA-256 Digest: {data.get('sha256')}")
        lines.append(f"  • Content Size: {data.get('bytes')} bytes")
        if data.get("dry_run"):
            lines.append(f"  • Verified Artifact: {data.get('artifact_path')}")
        else:
            lines.append(f"  • Restored File: {data.get('restored_path')}")
    else:
        lines.append(f"  • Error: {data.get('error')}")
    return "\n".join(lines)


def render_attestation(data: dict[str, Any]) -> str:
    lines = ["=== EGRESS BOUNDARY ATTESTATION STATUS ==="]
    mark = "PASS" if data.get("ok") else "FAIL"
    lines.append(f"[{mark}] Attestation Token: {data.get('token_path')}")
    lines.append(f"  • Broker Endpoint: {data.get('broker_endpoint')}")
    lines.append(f"  • Policy SHA-256: {data.get('policy_digest')}")
    lines.append(f"  • Issued At: {data.get('issued_at')}")
    lines.append(f"  • Token Age: {data.get('age_hours')}h / {data.get('max_age_hours')}h max")
    lines.append(f"  • TTL Remaining: {data.get('ttl_hours_remaining')}h")
    lines.append(f"  • Expired: {'YES' if data.get('is_expired') else 'NO'}")
    lines.append(f"  • Evidence: {', '.join(data.get('evidence') or [])}")
    if data.get("missing_evidence"):
        lines.append(f"  • Missing Evidence: {', '.join(data.get('missing_evidence'))}")
    if data.get("error"):
        lines.append(f"  • Error: {data.get('error')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. CLI Entry Point
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.audit_tool",
        description="Audit retention evidence collection, replica verification, and restore tooling.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_status = sub.add_parser("status", help="Inspect off-machine audit retention configuration and status")
    p_status.add_argument("--json", action="store_true", help="Output in machine-readable JSON")

    p_restore = sub.add_parser("restore", help="Verify or restore a replicated trajectory artifact")
    p_restore.add_argument("--task-id", type=int, help="Task ID to restore/verify")
    p_restore.add_argument("--checkpoint-hash", help="Specific checkpoint hash to restore/verify")
    p_restore.add_argument("--target-dir", type=Path, help="Target destination directory for actual file restore")
    p_restore.add_argument("--dry-run", action="store_true", default=True, help="Verify digest only without writing (default)")
    p_restore.add_argument("--write", action="store_true", help="Actually write verified file to --target-dir")
    p_restore.add_argument("--json", action="store_true", help="Output in machine-readable JSON")

    p_attest = sub.add_parser("attestation", help="Validate signed worker egress boundary attestation")
    p_attest.add_argument("--token-path", type=Path, help="Path to attestation token file")
    p_attest.add_argument("--json", action="store_true", help="Output in machine-readable JSON")

    args = parser.parse_args(argv)

    if args.subcommand == "status":
        res = collect_evidence()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(render_evidence(res))
        return 0 if res.get("ok") else 1

    if args.subcommand == "restore":
        dry_run = not args.write
        res = verify_restore(
            task_id=args.task_id,
            checkpoint_hash=args.checkpoint_hash,
            target_dir=args.target_dir,
            dry_run=dry_run,
        )
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(render_restore(res))
        return 0 if res.get("ok") else 1

    if args.subcommand == "attestation":
        res = validate_attestation(token_path=args.token_path)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(render_attestation(res))
        return 0 if res.get("ok") else 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

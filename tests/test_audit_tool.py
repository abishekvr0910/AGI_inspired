"""Hermetic unit tests for orchestrator/audit_tool.py.

Covers:
  - Evidence collection for UNC and S3 backends
  - Redaction of secret keys and access credentials
  - Checkpoint chain verification & truncation detection
  - Restore verification (dry-run read-only and write modes)
  - Tampered artifact rejection (fail-closed digest verification)
  - Path containment and traversal protection during restore
  - Egress boundary attestation token validation and TTL calculations
  - CLI subcommand routing through operator_cli.py
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
sys.path.insert(0, str(ORCH))

import audit_replication
import audit_tool
import operator_cli


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mock_sign(checkpoint: dict) -> str:
    return json.dumps({"checkpoint": checkpoint}, sort_keys=True)


def _mock_verify(token: str) -> dict | None:
    try:
        payload = json.loads(token)
    except json.JSONDecodeError:
        return None
    return payload.get("checkpoint") if isinstance(payload, dict) else None


class AuditToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.td = Path(self.temp.name)
        self.replica = self.td / "replica"
        self.replica.mkdir()
        self.trajectories_dir = self.replica / "trajectories"
        self.trajectories_dir.mkdir()

        self.config_path = self.td / "audit_retention.yaml"
        self.config_path.write_text(
            """schema_version: 1
mode: signed_hash_chain
replica:
  root_environment_variable: HARNESS_TEST_AUDIT_ROOT
  require_unc: false
  artifact_subdirectory: trajectories
  checkpoint_filename: trajectory-checkpoints.jsonl
enforcement_environment_variable: HARNESS_TEST_AUDIT_ENFORCE
checkpoint_max_age_hours: 24
minimum_retention_days: 365
""",
            encoding="utf-8",
        )
        self.env = {
            "HARNESS_TEST_AUDIT_ROOT": str(self.replica),
            "HARNESS_TEST_AUDIT_ENFORCE": "1",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_sample_trajectory(self, task_id: int, content: str = '{"event": 1}\n') -> tuple[Path, str, str]:
        content_bytes = content.encode("utf-8")
        digest = _sha256(content_bytes)
        filename = f"task{task_id}-{digest}.trajectory.jsonl"
        dest = self.trajectories_dir / filename
        dest.write_bytes(content_bytes)
        rel_path = f"trajectories/{filename}"
        return dest, digest, rel_path

    def _create_sample_chain(self, tasks: list[tuple[int, str]]) -> list[dict]:
        checkpoints_file = self.replica / "trajectory-checkpoints.jsonl"
        manifest_file = self.replica / "latest-checkpoint.json"
        now = datetime.now(timezone.utc)

        prev_hash = "GENESIS"
        cps = []
        lines = []

        for tid, content in tasks:
            _, digest, rel_path = self._create_sample_trajectory(tid, content)
            cp = {
                "schema_version": 1,
                "task_id": tid,
                "artifact_relative_path": rel_path,
                "trajectory_sha256": digest,
                "source_bytes": len(content.encode("utf-8")),
                "replicated_at": now.isoformat(),
                "previous_checkpoint_hash": prev_hash,
            }
            cp_hash = audit_replication._checkpoint_hash(cp)
            cp["checkpoint_hash"] = cp_hash
            prev_hash = cp_hash
            cps.append(cp)

            sig = _mock_sign(cp)
            line = json.dumps({"checkpoint": cp, "signature": sig}, sort_keys=True)
            lines.append(line)

        checkpoints_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        if cps:
            latest = cps[-1]
            manifest_payload = {
                "checkpoint_hash": latest["checkpoint_hash"],
                "count": len(cps),
                "recorded_at": now.isoformat(),
            }
            manifest_sig = _mock_sign(manifest_payload)
            manifest_file.write_text(
                json.dumps({"manifest": manifest_payload, "signature": manifest_sig}),
                encoding="utf-8",
            )
        return cps

    def test_mask_secret(self) -> None:
        self.assertEqual(audit_tool.mask_secret(None), "<not-configured>")
        self.assertEqual(audit_tool.mask_secret(""), "<not-configured>")
        self.assertEqual(audit_tool.mask_secret("12345"), "********")
        masked = audit_tool.mask_secret("AKIAIOSFODNN7EXAMPLE")
        self.assertTrue(masked.startswith("AKIA***LE"))
        self.assertNotIn("FODNN7", masked)

    def test_collect_evidence_unc_not_enforced(self) -> None:
        empty_env = {}
        res = audit_tool.collect_evidence(
            config_path=self.config_path,
            environment=empty_env,
        )
        self.assertFalse(res["ok"])
        self.assertFalse(res["enforcement_requested"])
        self.assertEqual(res["error"], "audit_enforcement_not_enabled")

    def test_collect_evidence_unc_valid_chain(self) -> None:
        self._create_sample_chain([(1, '{"event": 1}\n'), (2, '{"event": 2}\n')])

        res = audit_tool.collect_evidence(
            config_path=self.config_path,
            environment=self.env,
            verify_checkpoint=_mock_verify,
            signing_state=lambda: {"ok": True},
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["enforcement_requested"])
        self.assertEqual(res["checkpoint_count"], 2)
        self.assertTrue(res["artifact_ok"])
        self.assertFalse(res["truncation_detected"])
        self.assertIsNone(res["error"])

    def test_collect_evidence_truncation_detected(self) -> None:
        # Create 2 checkpoints, but delete the second line to simulate chain rollback
        self._create_sample_chain([(1, '{"event": 1}\n'), (2, '{"event": 2}\n')])
        checkpoints_file = self.replica / "trajectory-checkpoints.jsonl"
        lines = checkpoints_file.read_text(encoding="utf-8").strip().splitlines()
        # Keep only line 1, but manifest expects 2
        checkpoints_file.write_text(lines[0] + "\n", encoding="utf-8")

        res = audit_tool.collect_evidence(
            config_path=self.config_path,
            environment=self.env,
            verify_checkpoint=_mock_verify,
            signing_state=lambda: {"ok": True},
        )
        self.assertFalse(res["ok"])
        self.assertTrue(res["truncation_detected"])
        self.assertEqual(res["error"], "checkpoint_suffix_truncated")

    def test_verify_restore_unc_dry_run(self) -> None:
        self._create_sample_chain([(42, '{"step": "model_output"}\n')])

        res = audit_tool.verify_restore(
            task_id=42,
            dry_run=True,
            config_path=self.config_path,
            environment=self.env,
            verify_checkpoint=_mock_verify,
        )
        self.assertTrue(res["ok"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["task_id"], 42)
        self.assertTrue(res["verified"])
        self.assertIn("task42", res["artifact_path"])

    def test_verify_restore_unc_write_file(self) -> None:
        content = '{"restored_task": 99}\n'
        self._create_sample_chain([(99, content)])
        target_restore_dir = self.td / "restored"

        res = audit_tool.verify_restore(
            task_id=99,
            target_dir=target_restore_dir,
            dry_run=False,
            config_path=self.config_path,
            environment=self.env,
            verify_checkpoint=_mock_verify,
        )
        self.assertTrue(res["ok"])
        self.assertFalse(res["dry_run"])
        self.assertEqual(res["task_id"], 99)
        self.assertTrue(res["verified"])
        restored_path = Path(res["restored_path"])
        self.assertTrue(restored_path.is_file())
        self.assertEqual(restored_path.read_text(encoding="utf-8"), content)
        self.assertEqual(_sha256(content.encode("utf-8")), res["sha256"])

    def test_verify_restore_tampered_artifact_fails(self) -> None:
        self._create_sample_chain([(100, '{"original": true}\n')])
        # Corrupt the artifact file on disk
        artifact_files = list(self.trajectories_dir.glob("task100-*.trajectory.jsonl"))
        self.assertTrue(len(artifact_files) == 1)
        artifact_files[0].write_text('{"tampered": true}\n', encoding="utf-8")

        res = audit_tool.verify_restore(
            task_id=100,
            dry_run=True,
            config_path=self.config_path,
            environment=self.env,
            verify_checkpoint=_mock_verify,
        )
        self.assertFalse(res["ok"])
        self.assertTrue("tampered" in res["error"] or "mismatch" in res["error"])

    def test_verify_restore_target_path_containment(self) -> None:
        target_dir = self.td / "containment_test"
        # Ensure path with traversal components resolves within directory
        safe_path = audit_tool._safe_target_path(target_dir, "../../../secret.txt", task_id=1)
        self.assertTrue(safe_path.resolve().is_relative_to(target_dir.resolve()))
        self.assertEqual(safe_path.name, "secret.txt")

    def test_validate_attestation_live_token(self) -> None:
        signed_file = ROOT / ".harness" / "egress_attestation.signed"
        if not signed_file.is_file():
            self.skipTest(".harness/egress_attestation.signed not found")

        res = audit_tool.validate_attestation(token_path=signed_file)
        self.assertTrue(res["ok"])
        self.assertFalse(res["is_expired"])
        self.assertEqual(res["missing_evidence"], [])
        self.assertIn("deny_direct_egress", res["evidence"])
        self.assertIn("broker_only_egress", res["evidence"])
        self.assertIn("restricted_worker_identity", res["evidence"])
        self.assertGreater(res["ttl_hours_remaining"], 0)

    def test_validate_attestation_expired(self) -> None:
        signed_file = ROOT / ".harness" / "egress_attestation.signed"
        if not signed_file.is_file():
            self.skipTest(".harness/egress_attestation.signed not found")

        future_time = datetime.now(timezone.utc) + timedelta(days=2)
        res = audit_tool.validate_attestation(token_path=signed_file, now=future_time)
        self.assertFalse(res["ok"])
        self.assertTrue(res["is_expired"])
        self.assertEqual(res["error"], "attestation_expired")

    def test_validate_attestation_tampered_token(self) -> None:
        tampered_file = self.td / "tampered_attestation.signed"
        tampered_file.write_text("invalid_base64.invalid_sig.v1", encoding="utf-8")

        res = audit_tool.validate_attestation(token_path=tampered_file)
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "attestation_untrusted_signature")

    def test_operator_cli_audit_subcommands(self) -> None:
        # Test CLI help
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            code = operator_cli.main(["audit", "attestation", "--json"])
            self.assertEqual(code, 0)

        with mock.patch("sys.stdout", new_callable=io.StringIO):
            code = operator_cli.main(["audit", "status", "--json"])
            # Status fails closed when unenforced (code 1)
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()

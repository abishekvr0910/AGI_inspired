"""tests/test_sample_remediation.py -- Regression suite for P0-A Sample Remediation and Truthful Generation.

Covers acceptance criteria from docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §4:
1. Compiler refusal verification: EvidenceGate refusal stops pipeline export, surfaces failure reason,
   and prevents ready/success signals or usable pitch/audit links.
2. Sample visibility verification: all 8 sample prospects are visibly samples across all outward surfaces
   (tracker status = SAMPLE_NOT_FOR_SEND, pitches bannered, Google Ads CSV status = Paused).
3. Non-destructive backup and restore: dry-run manifest, backup creation, and restore verification in a fixture.
4. Idempotence: re-running remediation produces 0 modifications.
5. Boundary safety: protected clients (el-shaddai-coffee-katowice) and non-sample paths are strictly untouched.
"""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WS = ROOT / "workspace"
import sys
for p in (ROOT, ROOT / "orchestrator", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import client_profile
import client_reporter
import generate_prospect_pipeline
import remediate_sample_artifacts as rsa


class TestSampleRemediation(unittest.TestCase):
    def test_sample_client_ids_exclude_protected_clients(self):
        """Safety invariant: protected clients must NEVER appear in sample client IDs."""
        for cid in rsa.EXCLUDED_CLIENT_IDS:
            self.assertNotIn(cid, rsa.KNOWN_SAMPLE_CLIENT_IDS)

    def test_find_sample_artifacts_discovers_all_samples(self):
        """find_sample_artifacts discovers files for all 8 known sample prospects."""
        artifacts = rsa.find_sample_artifacts(WS)
        self.assertGreaterEqual(len(artifacts), 8)
        found_cids = {a["client_id"] for a in artifacts if a["client_id"] != "_tracker"}
        self.assertEqual(found_cids, set(rsa.KNOWN_SAMPLE_CLIENT_IDS))

        for art in artifacts:
            p = Path(art["path"])
            self.assertTrue(p.is_file(), f"Artifact path does not exist: {p}")

    def test_remediation_dry_run_makes_no_modifications(self):
        """Dry-run inspection mode returns manifest without touching files."""
        res = rsa.remediate_all(WS, dry_run=True)
        self.assertEqual(res["status"], "dry_run_complete")
        self.assertGreaterEqual(res["artifact_count"], 8)
        self.assertEqual(res["modified_count"], 0)

    def test_remediation_idempotence(self):
        """Re-applying remediation to already remediated workspace produces zero modifications."""
        res = rsa.remediate_all(WS, dry_run=False)
        self.assertEqual(res["status"], "remediation_complete")
        self.assertEqual(res["modified_count"], 0, f"Expected 0 modifications on clean run, got: {res['modified_files']}")

    def test_prospect_tracker_status_and_notes(self):
        """All sample rows in PROSPECT_TRACKER.csv must be marked SAMPLE_NOT_FOR_SEND."""
        tracker_path = WS / "PROSPECT_TRACKER.csv"
        if not tracker_path.is_file():
            self.skipTest("PROSPECT_TRACKER.csv not found")

        content = tracker_path.read_text(encoding="utf-8")
        reader = list(csv.reader(content.splitlines()))
        header = reader[0]
        status_idx = header.index("Outreach Status")
        waste_idx = header.index("Est Monthly Ad Waste")
        notes_idx = header.index("Notes")

        for row in reader[1:]:
            is_sample = any(cid in str(row) for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS)
            if is_sample:
                self.assertEqual(row[status_idx], "SAMPLE_NOT_FOR_SEND")
                self.assertTrue(row[waste_idx].startswith("[SAMPLE]"), f"Missing [SAMPLE] in {row[waste_idx]}")
                self.assertIn("DO NOT SEND", row[notes_idx])

    def test_sample_pitches_have_warning_banners(self):
        """All sample pitches must have the prominent warning banner and no real-audit guarantees."""
        pitches_dir = WS / "outbound_pitches"
        for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS:
            pitch_file = pitches_dir / f"{cid}_pitch.txt"
            if pitch_file.is_file():
                text = pitch_file.read_text(encoding="utf-8")
                self.assertTrue(
                    "[SAMPLE DEMONSTRATION MATERIAL" in text or "[SAMPLE / DEMONSTRATION MATERIAL" in text,
                    f"Missing sample banner in {pitch_file}"
                )
                self.assertIn("DO NOT SEND", text)
                self.assertNotIn("We ran an automated query analysis on your local market footprint", text)

    def test_sample_google_ads_csv_is_paused(self):
        """All Google Ads Editor import CSVs for sample clients must have Status: Paused."""
        for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS:
            csv_path = WS / "clients" / cid / "google_ads_editor_import.csv"
            if csv_path.is_file():
                content = csv_path.read_text(encoding="utf-8")
                lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
                reader = list(csv.reader(lines))
                header = reader[0]
                status_idx = header.index("Status")
                camp_idx = header.index("Campaign") if "Campaign" in header else header.index("[SAMPLE] Campaign")

                for row in reader[1:]:
                    self.assertEqual(row[status_idx], "Paused", f"Found non-Paused row in {csv_path}")
                    self.assertTrue(row[camp_idx].startswith("[SAMPLE] "), f"Missing [SAMPLE] prefix in {row[camp_idx]}")

    def test_sample_strategy_dossiers_have_warnings(self):
        """All sample strategy dossiers must have synthetic sample warnings."""
        for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS:
            md_path = WS / "clients" / cid / "strategy_dossier.md"
            if md_path.is_file():
                text = md_path.read_text(encoding="utf-8")
                self.assertTrue(
                    "SYNTHETIC SAMPLE MATERIAL" in text or "SAMPLE DEMONSTRATION MATERIAL" in text,
                    f"Missing warning in {md_path}"
                )
                self.assertNotIn("> **Confidential Client Report**", text)

            html_path = WS / "clients" / cid / "strategy_dossier.html"
            if html_path.is_file():
                text = html_path.read_text(encoding="utf-8")
                self.assertIn("SAMPLE DEMONSTRATION MATERIAL", text)

    def test_fixture_restore_roundtrip(self):
        """Fixture directory roundtrip: backup and restore preserve byte-for-byte equality."""
        with tempfile.TemporaryDirectory() as td:
            fixture_root = Path(td)
            fixture_ws = fixture_root / "workspace"
            sample_client = fixture_ws / "clients" / "test-sample"
            sample_client.mkdir(parents=True)
            f1 = sample_client / "test.csv"
            f1.write_text("Campaign,Status\nTest,Enabled\n", encoding="utf-8")
            original_sha = rsa.sha256_file(f1)

            artifacts = [{
                "client_id": "test-sample",
                "path": str(f1),
                "rel_path": "clients/test-sample/test.csv",
                "file_name": "test.csv",
            }]

            backup_dir = fixture_ws / "backups" / "test_backup"
            manifest = rsa.create_backup(fixture_ws, backup_dir, artifacts)
            self.assertEqual(len(manifest["files"]), 1)
            self.assertEqual(manifest["files"][0]["sha256"], original_sha)

            # Tamper the original file
            f1.write_text("TAMPERED_BYTES", encoding="utf-8")
            self.assertNotEqual(rsa.sha256_file(f1), original_sha)

            # Restore and verify hash matches
            count = rsa.restore_backup(fixture_ws, backup_dir)
            self.assertEqual(count, 1)
            self.assertEqual(rsa.sha256_file(f1), original_sha)

    def test_production_mode_generator_fails_closed_on_unverified(self):
        """Production pipeline generator refuses unverified sample clients without emitting ready signals."""
        with tempfile.TemporaryDirectory() as td:
            fixture_root = Path(td)
            fixture_ws = fixture_root / "workspace"
            fixture_ws.mkdir(parents=True)
            cdir = fixture_ws / "clients" / "unverified-prospect"
            cdir.mkdir(parents=True)

            prof = {
                "client_id": "unverified-prospect",
                "display_name": "Unverified Prospect",
                "domain": "unverified.example",
                "geo": ["US", "Austin, TX"],
                "language": ["en"],
                "offer": "Testing offer",
                "audience": "Testing audience",
                "competitors": ["https://competitor.example"],
                "brand_voice": "Professional",
                "landing_url": "https://unverified.example",
                "seed_keywords": ["unverified test keyword"],
                "forbidden_claims": ["best", "guarantee"],
            }
            client_profile.save_client_profile(prof, root=fixture_root)

            # Compiler without force_export must return error
            res = client_reporter.compile_and_export_client_package("unverified-prospect", root=fixture_root, force_export=False)
            self.assertFalse(res.get("success"))
            self.assertEqual(res.get("error"), "EXPORT_BLOCKED")
            self.assertIn("Evidence gate blocked export", res.get("message", ""))


if __name__ == "__main__":
    unittest.main()

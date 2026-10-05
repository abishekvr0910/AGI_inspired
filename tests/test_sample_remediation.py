"""tests/test_sample_remediation.py -- Regression suite for P0-A Sample Remediation and Truthful Generation.

Covers acceptance criteria from docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §4 and Codex findings (R1, R8):
1. Compiler refusal verification: EvidenceGate refusal stops pipeline export, surfaces failure reason,
   and prevents ready/success signals or usable pitch/audit links.
2. Sample visibility verification: all 8 sample prospects are visibly samples across all outward surfaces
   (tracker status = SAMPLE_NOT_FOR_SEND, pitches bannered, Google Ads CSV status = Paused).
3. Non-destructive backup and restore: baseline preservation across repeated runs (R8).
4. Path traversal protection: restore rejects path traversal attempts in backup manifests (R8).
5. Idempotence: re-running remediation produces 0 modifications.
6. Boundary safety: protected clients (el-shaddai-coffee-katowice) and non-sample paths are strictly untouched.
7. Pure fixture isolation: 100% of mutations occur inside temporary directory; production workspace is untouched (R1).
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WS_PROD = ROOT / "workspace"
for p in (ROOT, ROOT / "orchestrator", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import client_profile
import client_reporter
import generate_prospect_pipeline
import remediate_sample_artifacts as rsa


def _snapshot_dir(dir_path: Path) -> dict[str, str]:
    """Record SHA256 hashes of critical production client/tracker files."""
    snapshot = {}
    if not dir_path.is_dir():
        return snapshot
    tracker = dir_path / "PROSPECT_TRACKER.csv"
    if tracker.is_file():
        snapshot["PROSPECT_TRACKER.csv"] = rsa.sha256_file(tracker)
    for sub in ("clients", "outbound_pitches"):
        sdir = dir_path / sub
        if sdir.is_dir():
            for p in sdir.rglob("*"):
                if p.is_file():
                    try:
                        snapshot[str(p.relative_to(dir_path))] = rsa.sha256_file(p)
                    except Exception:
                        pass
    return snapshot


class TestSampleRemediation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Snapshot production workspace to verify zero mutation (R1)
        cls.prod_snapshot_before = _snapshot_dir(WS_PROD)

        # 2. Build a fully synthetic temporary workspace for all remediation tests (R1)
        cls._tmp = tempfile.TemporaryDirectory(prefix="agi_test_remediation_")
        cls.tmp_root = Path(cls._tmp.name)
        cls.WS = cls.tmp_root / "workspace"
        cls.WS.mkdir(parents=True)

        # Create synthetic client directories and files for all 8 sample prospects
        for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS:
            cdir = cls.WS / "clients" / cid
            cdir.mkdir(parents=True)

            # Raw un-remediated Google Ads Editor CSV with Enabled rows
            csv_path = cdir / "google_ads_editor_import.csv"
            csv_path.write_text(
                "Campaign,Ad Group,Keyword,Criterion Type,Status\n"
                f"{cid.title()} - Search - Core,General,services,Broad,Enabled\n",
                encoding="utf-8",
            )

            # Raw strategy dossier
            md_path = cdir / "strategy_dossier.md"
            md_path.write_text(
                f"# Executive Strategy Dossier: {cid.title()}\n\n> **Confidential Client Report**\n",
                encoding="utf-8",
            )
            html_path = cdir / "strategy_dossier.html"
            html_path.write_text(
                f"<html><body><h1>Executive Strategy Dossier: {cid.title()}</h1></body></html>",
                encoding="utf-8",
            )

        # Synthetic outbound pitches
        pitches_dir = cls.WS / "outbound_pitches"
        pitches_dir.mkdir(parents=True)
        for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS:
            pitch_file = pitches_dir / f"{cid}_pitch.txt"
            pitch_file.write_text(
                f"Subject: PPC Audit for {cid}\n\n"
                "We ran an automated query analysis on your local market footprint and noticed search ads routinely matching to queries like:\n"
                "- cheap competitors\n- scam reviews\n"
                "ESTIMATED AD WASTE DETECTED: $4,500/mo\n"
                "it should instantly eliminate an estimated waste.\n",
                encoding="utf-8",
            )

        # Synthetic PROSPECT_TRACKER.csv with full production schema
        tracker_path = cls.WS / "PROSPECT_TRACKER.csv"
        rows = [
            ["Company Name", "Vertical", "Market/City", "Contact Name", "Role", "Email", "Phone", "Website", "Est Monthly Ad Waste", "Audit Dossier Path", "Google Ads CSV Path", "Outbound Pitch Path", "Outreach Status", "First Touch Date", "Follow-up Date", "Notes"],
        ]
        for cid in rsa.KNOWN_SAMPLE_CLIENT_IDS:
            rows.append([
                cid.title(), "Commercial Services", "Austin, TX", "Test Contact", "Owner", f"contact@{cid}.example", "555-0100", f"https://{cid}.example", "$4,500/mo",
                f"workspace/clients/{cid}/strategy_dossier.html", f"workspace/clients/{cid}/google_ads_editor_import.csv", f"workspace/outbound_pitches/{cid}_pitch.txt",
                "Ready to Send", "", "", "Initial test prospect"
            ])
        # Protected client
        rows.append([
            "El Shaddai Coffee", "Specialty Coffee", "Katowice, PL", "Owner", "Head Roaster", "contact@elshaddai.example", "555-0200", "https://elshaddaicoffee.pl", "None",
            "workspace/clients/el-shaddai-coffee-katowice/strategy_dossier.html", "workspace/clients/el-shaddai-coffee-katowice/google_ads_editor_import.csv", "",
            "Consented Candidate", "", "", "Production client"
        ])

        with open(tracker_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        # Synthetic protected client el-shaddai-coffee-katowice
        prot_dir = cls.WS / "clients" / "el-shaddai-coffee-katowice"
        prot_dir.mkdir(parents=True)
        (prot_dir / "profile.json").write_text(
            json.dumps({"client_id": "el-shaddai-coffee-katowice", "display_name": "El Shaddai Indian Coffee"}),
            encoding="utf-8",
        )

        # Remediate cls.WS once so all verification assertions inspect remediated state
        rsa.remediate_all(cls.WS, dry_run=False)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

        # Invariant verification: production workspace must NOT have been mutated (R1)
        prod_snapshot_after = _snapshot_dir(WS_PROD)
        if prod_snapshot_after != cls.prod_snapshot_before:
            diff_keys = set(prod_snapshot_after.keys()) ^ set(cls.prod_snapshot_before.keys())
            for k in set(prod_snapshot_after.keys()) & set(cls.prod_snapshot_before.keys()):
                if prod_snapshot_after[k] != cls.prod_snapshot_before[k]:
                    diff_keys.add(k)
            raise AssertionError(f"R1 VIOLATION: Production workspace was mutated during test run! Modified: {diff_keys}")

    def test_sample_client_ids_exclude_protected_clients(self):
        """Safety invariant: protected clients must NEVER appear in sample client IDs."""
        for cid in rsa.EXCLUDED_CLIENT_IDS:
            self.assertNotIn(cid, rsa.KNOWN_SAMPLE_CLIENT_IDS)

    def test_find_sample_artifacts_discovers_all_samples(self):
        """find_sample_artifacts discovers files for all 8 known sample prospects."""
        artifacts = rsa.find_sample_artifacts(self.WS)
        self.assertGreaterEqual(len(artifacts), 8)
        found_cids = {a["client_id"] for a in artifacts if a["client_id"] != "_tracker"}
        self.assertEqual(found_cids, set(rsa.KNOWN_SAMPLE_CLIENT_IDS))

        for art in artifacts:
            p = Path(art["path"])
            self.assertTrue(p.is_file(), f"Artifact path does not exist: {p}")

    def test_remediation_dry_run_makes_no_modifications(self):
        """Dry-run inspection mode returns manifest without touching files."""
        res = rsa.remediate_all(self.WS, dry_run=True)
        self.assertEqual(res["status"], "dry_run_complete")
        self.assertGreaterEqual(res["artifact_count"], 8)
        self.assertEqual(res["modified_count"], 0)

    def test_remediation_execution_and_idempotence(self):
        """Remediates synthetic workspace, verifies markings, and proves idempotence on second pass."""
        with tempfile.TemporaryDirectory() as td:
            fixture_ws = Path(td) / "workspace"
            sample_dir = fixture_ws / "clients" / "texas-premier-roofing"
            sample_dir.mkdir(parents=True)
            (sample_dir / "google_ads_editor_import.csv").write_text("Campaign,Status\nTexas,Enabled\n", encoding="utf-8")
            # 1. First execution modifies files
            res1 = rsa.remediate_all(fixture_ws, dry_run=False)
            self.assertEqual(res1["status"], "remediation_complete")
            self.assertGreater(res1["modified_count"], 0)

            # 2. Second execution produces zero modifications (idempotence)
            res2 = rsa.remediate_all(fixture_ws, dry_run=False)
            self.assertEqual(res2["status"], "remediation_complete")
            self.assertEqual(res2["modified_count"], 0, f"Expected 0 modifications on second pass, got: {res2['modified_files']}")

    def test_prospect_tracker_status_and_notes(self):
        """All sample rows in PROSPECT_TRACKER.csv must be marked SAMPLE_NOT_FOR_SEND."""
        tracker_path = self.WS / "PROSPECT_TRACKER.csv"
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
            elif "el-shaddai-coffee-katowice" in str(row):
                self.assertEqual(row[status_idx], "Consented Candidate")
                self.assertEqual(row[waste_idx], "None")

    def test_sample_pitches_have_warning_banners(self):
        """All sample pitches must have the prominent warning banner and no real-audit guarantees."""
        pitches_dir = self.WS / "outbound_pitches"
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
            csv_path = self.WS / "clients" / cid / "google_ads_editor_import.csv"
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
            md_path = self.WS / "clients" / cid / "strategy_dossier.md"
            if md_path.is_file():
                text = md_path.read_text(encoding="utf-8")
                self.assertTrue(
                    "SYNTHETIC SAMPLE MATERIAL" in text or "SAMPLE DEMONSTRATION MATERIAL" in text,
                    f"Missing warning in {md_path}"
                )
                self.assertNotIn("> **Confidential Client Report**", text)

            html_path = self.WS / "clients" / cid / "strategy_dossier.html"
            if html_path.is_file():
                text = html_path.read_text(encoding="utf-8")
                self.assertIn("SAMPLE DEMONSTRATION MATERIAL", text)

    def test_repeated_remediation_preserves_rollback_baseline(self):
        """R8: Two remediation runs followed by restore returns the original baseline, not modified state."""
        with tempfile.TemporaryDirectory() as td:
            fixture_ws = Path(td) / "workspace"
            sample_client = fixture_ws / "clients" / "texas-premier-roofing"
            sample_client.mkdir(parents=True)
            csv_file = sample_client / "google_ads_editor_import.csv"
            # Original baseline: Status is Enabled
            csv_file.write_text("Campaign,Status\nOriginal Campaign,Enabled\n", encoding="utf-8")
            original_sha = rsa.sha256_file(csv_file)

            backup_dir = fixture_ws / "backups" / "samples_pre_remediation_20261004"

            # Pass 1: Remediate (creates backup baseline and pauses CSV)
            res1 = rsa.remediate_all(fixture_ws, dry_run=False, backup_dir=backup_dir)
            self.assertEqual(res1["modified_count"], 1)
            self.assertIn("Paused", csv_file.read_text(encoding="utf-8"))

            # Pass 2: Remediate again (0 modifications; MUST NOT overwrite backup baseline)
            res2 = rsa.remediate_all(fixture_ws, dry_run=False, backup_dir=backup_dir)
            self.assertEqual(res2["modified_count"], 0)

            # Restore backup: must restore the ORIGINAL Enabled baseline!
            rsa.restore_backup(fixture_ws, backup_dir)

            restored_text = csv_file.read_text(encoding="utf-8")
            self.assertIn("Enabled", restored_text, "R8 Failure: Restore returned modified file, not original baseline!")
            self.assertEqual(rsa.sha256_file(csv_file), original_sha)

    def test_restore_rejects_path_traversal_manifest(self):
        """R8: restore_backup validates root containment and rejects path traversal targets."""
        with tempfile.TemporaryDirectory() as td:
            fixture_ws = Path(td) / "workspace"
            backup_dir = fixture_ws / "backups" / "test_backup"
            backup_dir.mkdir(parents=True)

            # Create an evil manifest attempting to write outside workspace
            evil_manifest = {
                "created_at": "2026-10-04T12:00:00Z",
                "workspace_root": str(fixture_ws.resolve()),
                "backup_dir": str(backup_dir.resolve()),
                "files": [
                    {
                        "client_id": "test",
                        "rel_path": "../../../evil.txt",
                        "sha256": "fake",
                    }
                ],
            }
            (backup_dir / "manifest.json").write_text(json.dumps(evil_manifest), encoding="utf-8")
            (backup_dir / "evil.txt").write_text("malicious content", encoding="utf-8")

            with self.assertRaises(ValueError) as cm:
                rsa.restore_backup(fixture_ws, backup_dir)
            self.assertIn("Path traversal detected", str(cm.exception))

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

            res = client_reporter.compile_and_export_client_package("unverified-prospect", root=fixture_root, force_export=False)
            self.assertFalse(res.get("success"))
            self.assertEqual(res.get("error"), "EXPORT_BLOCKED")
            self.assertIn("Evidence gate blocked export", res.get("message", ""))


if __name__ == "__main__":
    unittest.main()

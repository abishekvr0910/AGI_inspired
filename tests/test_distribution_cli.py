"""Test suite for Distribution Engine CLI Dispatcher (orchestrator/distribution.py).

Validates:
1. --list-templates displays all 5 registered templates.
2. --list-clients accurately lists client profiles in workspace/clients/.
3. --dry-run formats specification and criteria without database mutation.
4. Admitted dispatch creates task row and valid Step.DISPATCH attestation record carrying client_id.
5. dispatch_all_templates dispatches all 5 templates in sequence.
6. Zero-spend containment (3 probes: no ads SDK, no write/mutate symbols, no ad hosts).
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
TESTS = ROOT / "tests"
for p in (ROOT, ORCH, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import operator_auth
import attestation_chain as chain
import client_profile
import distribution

SAMPLE_PROFILE = {
    "client_id": "apex-roofing",
    "display_name": "Apex Commercial Roofing",
    "domain": "commercial roofing austin",
    "geo": ["US", "Austin-TX"],
    "language": ["en"],
    "offer": "Commercial roof inspection, TPO membrane installation, and storm leak emergency repair",
    "audience": "Facility directors, commercial property managers, building owners",
    "competitors": ["https://austin-roof-pros.example", "https://central-tx-roofs.example"],
    "brand_voice": "Authoritative, industrial, prompt, transparent warranties",
    "landing_url": "https://apex-roofing.example/commercial",
    "seed_keywords": ["commercial roofer austin", "tpo roofing contractors", "commercial roof leak repair"],
    "forbidden_claims": ["100% free lifetime roof replacement", "lowest price in North America"],
}


class DistributionCLITests(unittest.TestCase):
    def setUp(self):
        self.keys = operator_auth._generate_keypair()
        self.patcher = patch.object(operator_auth, "_load_keypair", return_value=self.keys)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_list_templates(self):
        """--list-templates outputs all 7 registered templates."""
        out = io.StringIO()
        with patch("sys.stdout", out):
            code = distribution.main(["--list-templates", "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out.getvalue())
        self.assertEqual(
            set(data.keys()),
            {
                "keyword_research",
                "competitive_serp",
                "ad_copy_variants",
                "seo_content_brief",
                "landing_page_recco",
                "negative_keyword_harvest",
                "audience_pain_point_research",
            },
        )

    def test_list_clients(self):
        """list_client_profiles and --list-clients enumerate client profiles correctly."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            clients = client_profile.list_client_profiles(root=temp_root)
            self.assertEqual(clients, ["apex-roofing"])

            out = io.StringIO()
            with patch("sys.stdout", out):
                code = distribution.main(["--list-clients", "--json", "--root", str(temp_root)])
            self.assertEqual(code, 0)
            json_clients = json.loads(out.getvalue())
            self.assertIn("apex-roofing", json_clients)

    def test_dry_run_preview(self):
        """--dry-run generates spec and pass_criteria without database mutation."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)

            res = distribution.dispatch_distribution_task(
                "apex-roofing",
                "ad_copy_variants",
                dry_run=True,
                root=temp_root,
            )

            self.assertTrue(res["dry_run"])
            self.assertEqual(res["client_id"], "apex-roofing")
            self.assertIn("Apex Commercial Roofing", res["spec"])
            self.assertIn("headlines <= 30 characters", res["pass_criteria"])
            self.assertIn("100% free lifetime roof replacement", res["pass_criteria"])

    def test_unknown_template_raises(self):
        """dispatch_distribution_task raises ValueError on unregistered template."""
        with self.assertRaises(ValueError) as ctx:
            distribution.dispatch_distribution_task("apex-roofing", "invalid_template", dry_run=True)
        self.assertIn("unknown distribution template", str(ctx.exception))

    def test_missing_client_profile_error(self):
        """dispatch_distribution_task raises ValueError on non-existent client."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            with self.assertRaises(ValueError) as ctx:
                distribution.dispatch_distribution_task("nonexistent", "keyword_research", dry_run=True, root=temp_root)
            self.assertIn("client profile not found", str(ctx.exception))

    def test_cli_main_dry_run(self):
        """CLI main with --dry-run returns exit code 0 and json result."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            out = io.StringIO()
            with patch("sys.stdout", out):
                code = distribution.main([
                    "--client", "apex-roofing",
                    "--template", "keyword_research",
                    "--dry-run",
                    "--json",
                    "--root", str(temp_root),
                ])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertTrue(data["dry_run"])
            self.assertEqual(data["client_id"], "apex-roofing")
            self.assertIn("Grounded keyword research", data["spec"])

    def test_cli_main_admitted_dispatch(self):
        """CLI main without --dry-run queues task and records attestation step."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            (temp_root / "runs").mkdir()
            ledger_dir = temp_root / "ledger"
            ledger_dir.mkdir()
            db_path = ledger_dir / "ledger.db"

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "CREATE TABLE tasks (task_id INTEGER PRIMARY KEY, mission_id TEXT, "
                    "spec TEXT, pass_criteria TEXT, status TEXT, run_id TEXT, "
                    "attempt_count INTEGER DEFAULT 0, started_at TEXT, finished_at TEXT, "
                    "model_used TEXT, lease_expires_at TEXT, owner_pid INTEGER, "
                    "owner_process_start_id TEXT, artifacts TEXT, cost_usd REAL, "
                    "tokens_in INTEGER, tokens_out INTEGER, critic_verdict TEXT, "
                    "critic_notes TEXT, interventions TEXT, intervention_types TEXT)"
                )
                conn.commit()
            finally:
                conn.close()

            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            out = io.StringIO()
            with patch("sys.stdout", out):
                code = distribution.main([
                    "--client", "apex-roofing",
                    "--template", "ad_copy_variants",
                    "--json",
                    "--root", str(temp_root),
                ])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertFalse(data["dry_run"])
            self.assertEqual(data["task_id"], 1)
            self.assertEqual(data["status"], "queued")

            # Verify chain has genuine Step.DISPATCH
            payloads = chain.read_payloads(temp_root / "runs", 1)
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["step"], chain.Step.DISPATCH.value)
            self.assertEqual(payloads[0]["claims"]["client_id"], "apex-roofing")

    def test_admitted_task_dispatch(self):
        """Admitted dispatch writes to ledger and appends signed Step.DISPATCH."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            runs = temp_root / "runs"
            runs.mkdir()
            ledger_dir = temp_root / "ledger"
            ledger_dir.mkdir()
            db_path = ledger_dir / "ledger.db"

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "CREATE TABLE tasks (task_id INTEGER PRIMARY KEY, mission_id TEXT, "
                    "spec TEXT, pass_criteria TEXT, status TEXT, run_id TEXT, "
                    "attempt_count INTEGER DEFAULT 0, started_at TEXT, finished_at TEXT, "
                    "model_used TEXT, lease_expires_at TEXT, owner_pid INTEGER, "
                    "owner_process_start_id TEXT, artifacts TEXT, cost_usd REAL, "
                    "tokens_in INTEGER, tokens_out INTEGER, critic_verdict TEXT, "
                    "critic_notes TEXT, interventions TEXT, intervention_types TEXT)"
                )
                conn.commit()
            finally:
                conn.close()

            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)

            # Exercise canonical default paths under root=temp_root
            res = distribution.dispatch_distribution_task(
                "apex-roofing",
                "competitive_serp",
                dry_run=False,
                root=temp_root,
            )

            self.assertFalse(res["dry_run"])
            self.assertEqual(res["task_id"], 1)
            self.assertEqual(res["mission_id"], "distribution")
            self.assertEqual(res["status"], "queued")

            # Verify chain has genuine Step.DISPATCH carrying client_id
            payloads = chain.read_payloads(runs, 1)
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["step"], chain.Step.DISPATCH.value)
            self.assertEqual(payloads[0]["claims"]["client_id"], "apex-roofing")
            self.assertEqual(payloads[0]["claims"]["mission_id"], "distribution")

    def test_dispatch_all_templates(self):
        """dispatch_all_templates queues all 5 templates sequentially."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            runs = temp_root / "runs"
            runs.mkdir()
            ledger_dir = temp_root / "ledger"
            ledger_dir.mkdir()
            db_path = ledger_dir / "ledger.db"

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    "CREATE TABLE tasks (task_id INTEGER PRIMARY KEY, mission_id TEXT, "
                    "spec TEXT, pass_criteria TEXT, status TEXT, run_id TEXT, "
                    "attempt_count INTEGER DEFAULT 0, started_at TEXT, finished_at TEXT, "
                    "model_used TEXT, lease_expires_at TEXT, owner_pid INTEGER, "
                    "owner_process_start_id TEXT, artifacts TEXT, cost_usd REAL, "
                    "tokens_in INTEGER, tokens_out INTEGER, critic_verdict TEXT, "
                    "critic_notes TEXT, interventions TEXT, intervention_types TEXT)"
                )
                conn.commit()
            finally:
                conn.close()

            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)

            results = distribution.dispatch_all_templates(
                "apex-roofing",
                dry_run=False,
                root=temp_root,
            )

            self.assertEqual(len(results), 7)
            task_ids = [r["task_id"] for r in results]
            self.assertEqual(task_ids, [1, 2, 3, 4, 5, 6, 7])
            templates_dispatched = [r["template"] for r in results]
            self.assertEqual(
                templates_dispatched,
                [
                    "keyword_research",
                    "competitive_serp",
                    "ad_copy_variants",
                    "seo_content_brief",
                    "landing_page_recco",
                    "negative_keyword_harvest",
                    "audience_pain_point_research",
                ],
            )

            # Verify all 7 have DSSE DISPATCH records with client_id
            for tid in range(1, 8):
                payloads = chain.read_payloads(runs, tid)
                self.assertEqual(len(payloads), 1)
                self.assertEqual(payloads[0]["claims"]["client_id"], "apex-roofing")

    def test_zero_spend_containment_three_probes(self):
        """3-probe test passes across all orchestrator files and CLI tests."""
        sdk_forbidden = [
            "import " + "googleads",
            "from google" + ".ads",
            "from google" + "_ads",
            "googleads" + ".client",
            "from " + "googleads",
        ]
        sdk_pattern = re.compile(r"|".join(re.escape(p) for p in sdk_forbidden))

        mutate_forbidden = [
            "Campaign" + "Service",
            "AdGroup" + "Service",
            "Budget" + "Service",
            "mutate_" + "campaigns",
            "mutate_" + "ad_groups",
            "create_" + "campaign",
            "create_" + "ad_group",
            r"place.{0,8}bid",
            "ads." + "googleapis.com",
        ]
        mutate_pattern = re.compile(r"|".join(mutate_forbidden))

        py_files = list((ROOT / "orchestrator").rglob("*.py"))
        test_files = [
            ROOT / "tests" / "test_distribution_keyword_research.py",
            ROOT / "tests" / "test_distribution_templates.py",
            ROOT / "tests" / "test_distribution_cli.py",
        ]

        for f in py_files:
            content = f.read_text(encoding="utf-8", errors="ignore")
            m_sdk = sdk_pattern.search(content)
            self.assertIsNone(m_sdk, f"Probe 1 violation in {f}: matches SDK pattern {m_sdk}")

            m_mut = mutate_pattern.search(content)
            self.assertIsNone(m_mut, f"Probe 2 violation in {f}: matches mutate pattern {m_mut}")

        for tf in test_files:
            if tf.exists():
                content = tf.read_text(encoding="utf-8", errors="ignore")
                m_sdk = sdk_pattern.search(content)
                self.assertIsNone(m_sdk, f"Probe 1 violation in {tf}: matches SDK pattern {m_sdk}")

        egress_policy_yaml = (ROOT / "config" / "egress_policy.yaml").read_text(encoding="utf-8")
        ad_host_keywords = ["googleads", "ads.google", "bingads", "ads.yahoo", "ads.tiktok", "adservice"]
        for kw in ad_host_keywords:
            self.assertNotIn(kw, egress_policy_yaml, f"Probe 3 violation: ad platform {kw} found in egress policy")


if __name__ == "__main__":
    unittest.main()

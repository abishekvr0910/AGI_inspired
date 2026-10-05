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

    def test_auto_pipeline_execution(self):
        """--auto-pipeline dispatches all 7 research tasks and compiles campaign package."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            db_path = temp_root / "ledger.db"
            runs = temp_root / "runs"
            runs.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, spec TEXT, pass_criteria TEXT, "
                "status TEXT, worker_engine TEXT, run_id TEXT, created_at TEXT, updated_at TEXT)"
            )
            conn.commit()
            conn.close()

            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)

            # Create verified evidence record for test client (bypass evidence gate)
            import evidence_gate
            gate = evidence_gate.EvidenceGate(root=temp_root)
            from evidence_gate import ProspectVerification, VerificationStatus, EvidenceRecord, ClaimType
            from datetime import datetime
            now = datetime.utcnow().isoformat() + "Z"
            v = ProspectVerification(
                client_id="apex-roofing",
                company_name="Apex Commercial Roofing",
                status=VerificationStatus.VERIFIED,
                approved_for_export=True,
            )
            v.add_evidence(EvidenceRecord(ClaimType.CONTACT, "contact_name", "operator", now, "test", now, verified=True))
            v.add_evidence(EvidenceRecord(ClaimType.CONTACT, "contact_email", "operator", now, "test", now, verified=True))
            v.add_evidence(EvidenceRecord(ClaimType.CONTACT, "contact_role", "operator", now, "test", now, verified=True))
            v.add_evidence(EvidenceRecord(ClaimType.COMPANY, "company_name", "operator", now, "test", now, verified=True))
            v.add_evidence(EvidenceRecord(ClaimType.COMPANY, "website", "operator", now, "test", now, verified=True))
            v.add_evidence(EvidenceRecord(ClaimType.COMPANY, "city", "operator", now, "test", now, verified=True))
            v.add_evidence(EvidenceRecord(ClaimType.WASTE_ESTIMATE, "est_monthly_leak", "operator", now, "test", now, verified=True))
            gate.create_or_update(v)

            out = io.StringIO()
            with patch("sys.stdout", out):
                code = distribution.main([
                    "--client", "apex-roofing",
                    "--auto-pipeline",
                    "--dry-run",
                    "--json",
                    "--root", str(temp_root),
                    "--db-path", str(db_path),
                    "--runs-dir", str(runs),
                ])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["pipeline"], "auto")
            self.assertEqual(len(data["dispatch_results"]), 7)
            self.assertIn("campaign_package", data)
            pkg = data["campaign_package"]
            self.assertTrue(pkg["success"])
            self.assertEqual(pkg["client_id"], "apex-roofing")
            self.assertTrue(Path(pkg["csv_path"]).is_file())
            self.assertTrue(Path(pkg["dossier_md_path"]).is_file())
            self.assertTrue(Path(pkg["dossier_html_path"]).is_file())

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

    def test_pilot_dry_run_dispatches_exact_held_out_tasks(self):
        """--pilot preview dispatches exactly the 4 held-out tasks and enforces bounds."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)
            pilot_spec = {
                "pilot_id": "test-pilot-001",
                "client_id": "apex-roofing",
                "live_execution_authorized": False,
                "held_out_task_manifest": [
                    {"template": "keyword_research", "held_out": True},
                    {"template": "negative_keyword_harvest", "held_out": True},
                    {"template": "ad_copy_variants", "held_out": True},
                    {"template": "competitive_serp", "held_out": True},
                ],
                "budget_and_resource_bounds": {
                    "max_total_tokens": 100000,
                    "max_cost_usd": 1.00,
                },
            }
            spec_file = pilots_dir / "test_pilot.json"
            spec_file.write_text(json.dumps(pilot_spec), encoding="utf-8")

            out = io.StringIO()
            with patch("sys.stdout", out):
                code = distribution.main([
                    "--pilot", str(spec_file),
                    "--dry-run",
                    "--json",
                    "--root", str(temp_root),
                ])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertTrue(data["success"])
            self.assertEqual(data["pilot_id"], "test-pilot-001")
            self.assertEqual(data["client_id"], "apex-roofing")
            self.assertEqual(data["status"], "dry_run_preview")
            self.assertEqual(data["tasks_dispatched"], 4)
            self.assertEqual(
                data["held_out_templates"],
                ["keyword_research", "negative_keyword_harvest", "ad_copy_variants", "competitive_serp"],
            )
            for r in data["results"]:
                self.assertTrue(r["dry_run"])
                self.assertTrue(r["held_out"])

    def test_pilot_live_execution_refusal_when_unauthorized(self):
        """Attempting live pilot execution when live_execution_authorized=False fails closed."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)
            pilot_spec = {
                "pilot_id": "unauthorized-pilot",
                "client_id": "apex-roofing",
                "live_execution_authorized": False,
                "held_out_task_manifest": [
                    {"template": "keyword_research", "held_out": True},
                ],
                "budget_and_resource_bounds": {"max_total_tokens": 50000, "max_cost_usd": 0.50},
            }
            spec_file = pilots_dir / "unauthorized.json"
            spec_file.write_text(json.dumps(pilot_spec), encoding="utf-8")

            err = io.StringIO()
            with patch("sys.stderr", err):
                code = distribution.main([
                    "--pilot", str(spec_file),
                    "--json",
                    "--root", str(temp_root),
                ])
            self.assertEqual(code, 1)
            err_data = json.loads(err.getvalue())
            self.assertIn("PILOT_ADMISSION_BLOCKED", err_data["error"])
            self.assertIn("live_execution_authorized=False", err_data["error"])

    def test_pilot_token_budget_cap_exceeded_refusal(self):
        """Pilot dispatch fails closed when estimated token demand exceeds bounds."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)
            pilot_spec = {
                "pilot_id": "budget-exceeded-pilot",
                "client_id": "apex-roofing",
                "live_execution_authorized": False,
                "held_out_task_manifest": [
                    {"template": "keyword_research", "held_out": True},
                    {"template": "competitive_serp", "held_out": True},
                ],
                "budget_and_resource_bounds": {"max_total_tokens": 1000, "max_cost_usd": 0.01},
            }
            spec_file = pilots_dir / "budget_exceeded.json"
            spec_file.write_text(json.dumps(pilot_spec), encoding="utf-8")

            err = io.StringIO()
            with patch("sys.stderr", err):
                code = distribution.main([
                    "--pilot", str(spec_file),
                    "--dry-run",
                    "--json",
                    "--root", str(temp_root),
                ])
            self.assertEqual(code, 1)
            err_data = json.loads(err.getvalue())
            self.assertIn("exceeds pilot max_total_tokens", err_data["error"])

    def test_pilot_string_boolean_false_blocks_admission(self):
        """RR2: String 'false' in live_execution_authorized is strictly evaluated as False, blocking live dispatch."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)
            pilot_spec = {
                "pilot_id": "string-false-pilot",
                "client_id": "apex-roofing",
                "live_execution_authorized": "false",  # STRING 'false', truthy in naive Python
                "held_out_task_manifest": [
                    {"template": "keyword_research", "held_out": True},
                ],
                "budget_and_resource_bounds": {"max_total_tokens": 50000, "max_cost_usd": 0.50},
            }
            spec_file = pilots_dir / "str_false.json"
            spec_file.write_text(json.dumps(pilot_spec), encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                distribution.validate_and_dispatch_pilot(str(spec_file), dry_run=False, root=temp_root)
            self.assertIn("PILOT_ADMISSION_BLOCKED", str(ctx.exception))
            self.assertIn("live_execution_authorized=False", str(ctx.exception))

    def test_pilot_zero_cost_bound_rejected(self):
        """RR2: Pilot bounds with max_cost_usd=0 or max_total_tokens=0 fail closed at admission."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)

            # max_cost_usd = 0
            pilot_spec_zero_cost = {
                "pilot_id": "zero-cost-pilot",
                "client_id": "apex-roofing",
                "live_execution_authorized": False,
                "held_out_task_manifest": [
                    {"template": "keyword_research", "held_out": True},
                ],
                "budget_and_resource_bounds": {"max_total_tokens": 50000, "max_cost_usd": 0},
            }
            spec_file = pilots_dir / "zero_cost.json"
            spec_file.write_text(json.dumps(pilot_spec_zero_cost), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                distribution.validate_and_dispatch_pilot(str(spec_file), dry_run=True, root=temp_root)
            self.assertIn("max_cost_usd bound must be > 0", str(ctx.exception))

    def test_pilot_propagates_budget_kwargs_and_frozen_constraints(self):
        """RR2: Pilot dispatch propagates allocated budgets and frozen task specs to each admitted task."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)

            pilot_spec = {
                "pilot_id": "budget-prop-pilot",
                "client_id": "apex-roofing",
                "live_execution_authorized": False,
                "held_out_task_manifest": [
                    {
                        "template": "keyword_research",
                        "held_out": True,
                        "description": "Commercial roofing search queries",
                        "prohibited_archetypes": ["dental implants", "hvac"],
                    },
                ],
                "budget_and_resource_bounds": {"max_total_tokens": 60000, "max_cost_usd": 0.80},
            }
            spec_file = pilots_dir / "budget_prop.json"
            spec_file.write_text(json.dumps(pilot_spec), encoding="utf-8")

            res = distribution.validate_and_dispatch_pilot(str(spec_file), dry_run=True, root=temp_root)
            self.assertTrue(res["success"])
            self.assertEqual(len(res["results"]), 1)
            task_res = res["results"][0]
            self.assertEqual(task_res["allocated_budget_usd"], 0.80)
            self.assertEqual(task_res["allocated_tokens"], 60000)
            self.assertEqual(task_res["budget_enforcement"], "hard_stop")
            self.assertIsNotNone(task_res["frozen_spec"])
            self.assertIn("dental implants", task_res["spec"])


    def test_pilot_subcent_budget_allocation_no_inflation(self):
        """RR2: Pilot dispatch with sub-cent budget (e.g. $0.005 across 4 tasks) does NOT inflate to $0.04."""
        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            client_profile.save_client_profile(SAMPLE_PROFILE, root=temp_root)
            pilots_dir = temp_root / "workspace" / "pilots"
            pilots_dir.mkdir(parents=True, exist_ok=True)

            pilot_spec = {
                "pilot_id": "subcent-pilot",
                "client_id": "apex-roofing",
                "live_execution_authorized": False,
                "held_out_task_manifest": [
                    {"template": "keyword_research", "held_out": True},
                    {"template": "competitive_serp", "held_out": True},
                    {"template": "ad_copy_variants", "held_out": True},
                    {"template": "seo_content_brief", "held_out": True},
                ],
                "budget_and_resource_bounds": {"max_total_tokens": 100000, "max_cost_usd": 0.005},
            }
            spec_file = pilots_dir / "subcent_pilot.json"
            spec_file.write_text(json.dumps(pilot_spec), encoding="utf-8")

            res = distribution.validate_and_dispatch_pilot(str(spec_file), dry_run=True, root=temp_root)
            self.assertTrue(res["success"])
            self.assertEqual(len(res["results"]), 4)
            per_task_budgets = [r["allocated_budget_usd"] for r in res["results"]]
            self.assertEqual(per_task_budgets, [0.00125, 0.00125, 0.00125, 0.00125])
            self.assertAlmostEqual(sum(per_task_budgets), 0.005, places=5)
            # Assert NONE of them were inflated to $0.01
            for b in per_task_budgets:
                self.assertLess(b, 0.01)

    def test_shared_runtime_budget_exhaustion(self):
        """RR2: Shared budget controller enforces hard stop across multiple tasks under a shared pilot ID."""
        from budget_controller import BudgetController, BudgetExhaustedError

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()

            # Controller 1 for Task 101 under shared pilot "pilot-alpha" with total cap $0.005
            ctrl_1 = BudgetController(
                runs_dir=runs_dir,
                task_id=101,
                max_budget_usd=0.005,
                budget_enforcement="hard_stop",
                shared_budget_id="pilot-alpha",
                shared_max_budget_usd=0.005,
            )

            # Task 101 reserves for worker and reconciles $0.004 spent
            res1 = ctrl_1.reserve("worker", "openai/gpt-4o", prompt_text="research prompt")
            ctrl_1.reconcile(res1, actual_cost_usd=0.004, actual_tokens=1000)

            # Controller 2 for Task 102 under same shared pilot "pilot-alpha"
            ctrl_2 = BudgetController(
                runs_dir=runs_dir,
                task_id=102,
                max_budget_usd=0.005,
                budget_enforcement="hard_stop",
                shared_budget_id="pilot-alpha",
                shared_max_budget_usd=0.005,
            )

            # Task 102 attempts to reserve $0.002, but only $0.001 remains in the $0.005 pool
            with self.assertRaises(BudgetExhaustedError) as ctx:
                ctrl_2.reserve("worker", "openai/gpt-4o", prompt_text="second research prompt")
            self.assertIn("remaining shared budget", str(ctx.exception))

    def test_corrupt_shared_budget_fails_closed(self):
        """Corrupt or tampered shared budget JSON fails closed with BudgetExhaustedError (Finding 1)."""
        from budget_controller import BudgetController, BudgetExhaustedError

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            budgets_dir = runs_dir / "budgets"
            budgets_dir.mkdir(parents=True)
            shared_id = "cohort-corrupt-001"
            budget_file = budgets_dir / f"{shared_id}.json"
            # Write invalid/corrupt JSON
            budget_file.write_text("{corrupt json file content without closing brace", encoding="utf-8")

            ctrl = BudgetController(
                runs_dir=runs_dir,
                task_id=201,
                max_tokens=10000,
                budget_enforcement="hard_stop",
                shared_budget_id=shared_id,
                shared_max_tokens=10000,
            )

            # Attempting to reserve must fail closed, NOT reset available capacity
            with self.assertRaises(BudgetExhaustedError) as ctx:
                ctrl.reserve("worker", "openai/gpt-4o", prompt_text="hello world")
            self.assertIn("BUDGET_CORRUPTED", str(ctx.exception))

    def test_native_worker_blocks_second_model_call_when_budget_cap_exceeded(self):
        """Native agent loop enforces budget per turn and halts BEFORE the second model call on overrun (Finding 1)."""
        from budget_controller import BudgetController, BudgetExhaustedError
        from native_worker import run_native_research_turn

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()

            # 4,000 token cap
            ctrl = BudgetController(
                runs_dir=runs_dir,
                task_id=301,
                max_tokens=4000,
                budget_enforcement="hard_stop",
            )

            call_count = 0

            def fake_caller(messages, tools):
                nonlocal call_count
                call_count += 1
                # Return tool call demanding next turn, consuming 4,000 in + 1,000 out (5,000 total)
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_abc",
                                "type": "function",
                                "function": {
                                    "name": "web_search",
                                    "arguments": json.dumps({"query": "solar energy"}),
                                },
                            }
                        ],
                    },
                    "input_tokens": 4000,
                    "output_tokens": 1000,
                }

            # Run turn with custom_caller under model-free test environment with mocked tool execution
            with patch("native_worker.pause_engaged", return_value=False), \
                 patch("native_worker.execute_web_search", return_value=[{"title": "mock", "url": "https://example.com", "snippet": "mock snippet"}]), \
                 patch("native_worker.execute_web_fetch", return_value={"url": "https://example.com", "text": "mock text", "classification": "OK"}):
                with self.assertRaises(BudgetExhaustedError) as ctx:
                    run_native_research_turn(
                        prompt="Research solar panels in Nevada",
                        model_cfg={"provider": "mock", "model": "mock-model"},
                        budget_ctrl=ctrl,
                        custom_caller=fake_caller,
                        max_turns=5,
                    )

            # Exactly ONE call made, second call was blocked before execution
            self.assertEqual(call_count, 1)
            self.assertIn("Budget exhausted before turn 1", str(ctx.exception))
            # Spent tokens recorded accurately
            self.assertEqual(ctrl.task_spent_tokens, 5000)

    def test_c2_1100_tokens_spend_deduplication_and_repeated_settlement(self):
        """C2: 1,100-token native call plus settlement records exactly 1,100 in task and shared spend, even after repeated settlement."""
        import uuid
        from budget_controller import BudgetController, BudgetExhaustedError

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()
            shared_id = f"shared_c2_{uuid.uuid4().hex[:8]}"

            ctrl = BudgetController(
                runs_dir=runs_dir,
                task_id=401,
                max_tokens=5000,
                shared_budget_id=shared_id,
                shared_max_tokens=10000,
                budget_enforcement="hard_stop",
            )

            res_id = ctrl.reserve("worker", "openai/gpt-4o", prompt_text="research prompt")
            # Intermediate turn spend records 1,100 tokens
            ctrl.record_turn_spend(turn_tokens=1100, turn_usd=0.003, reservation_id=res_id)
            self.assertEqual(ctrl.task_spent_tokens, 1100)

            # Reconcile settlement
            ctrl.reconcile(res_id, actual_cost_usd=0.003, actual_tokens=1100)
            self.assertEqual(ctrl.task_spent_tokens, 1100)

            shared_data = ctrl._read_shared()
            self.assertEqual(shared_data["spent_tokens"], 1100)

            # Repeated settlement is idempotent and does NOT double-charge
            ctrl.reconcile(res_id, actual_cost_usd=0.003, actual_tokens=1100)
            self.assertEqual(ctrl.task_spent_tokens, 1100)
            shared_data2 = ctrl._read_shared()
            self.assertEqual(shared_data2["spent_tokens"], 1100)

    def test_c2_reservation_equals_available_cap_owner_can_use_competitor_blocked(self):
        """C2: When reservation equals available cap, the owner can use it while competing calls are blocked."""
        from budget_controller import BudgetController, BudgetExhaustedError

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()

            ctrl = BudgetController(
                runs_dir=runs_dir,
                task_id=402,
                max_tokens=2000,
                budget_enforcement="hard_stop",
            )

            # Reserve exactly 2,000 tokens for R1
            res_r1 = ctrl.reserve("worker", "openai/gpt-4o", estimated_tokens=2000)
            # R1 owner has remaining tokens matching capacity
            rem_r1 = ctrl.remaining_task_tokens(reservation_id=res_r1)
            self.assertEqual(rem_r1, 2000)

            # Competing call has 0 remaining tokens
            rem_other = ctrl.remaining_task_tokens(reservation_id=None)
            self.assertEqual(rem_other, 0)

            # Competing reservation attempt is refused
            with self.assertRaises(BudgetExhaustedError):
                ctrl.reserve("critic", "openai/gpt-4o", estimated_tokens=100)

    def test_c2_requested_call_cannot_fit_maximum_refused_before_dispatch(self):
        """C2: Requested call that cannot fit 4,000-token maximum is refused before dispatch."""
        from budget_controller import BudgetController, BudgetExhaustedError

        with tempfile.TemporaryDirectory() as td:
            runs_dir = Path(td) / "runs"
            runs_dir.mkdir()

            ctrl = BudgetController(
                runs_dir=runs_dir,
                task_id=403,
                max_tokens=4000,
                budget_enforcement="hard_stop",
            )

            # Attempt to reserve with prompt demanding > 4,000 tokens
            huge_prompt = "word " * 5000  # ~5000 tokens input alone
            with self.assertRaises(BudgetExhaustedError) as ctx:
                ctrl.reserve("worker", "openai/gpt-4o", prompt_text=huge_prompt)
            self.assertIn("exceeds remaining task tokens", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

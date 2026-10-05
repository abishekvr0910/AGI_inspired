"""tests/test_vertical_slice.py — Stage 4 Model-Free Vertical-Slice Acceptance Suite.

Validates the full product assembly line model-free per docs/HARNESS_COMPLETION_DIRECTIVE_2026-10-05.md § Stage 4:
1. Admission & Queueing -> Dispatch & Budget Reservation -> Research Worker ->
   Missing-Evidence Preflight Detection -> Research Notebook Direction Block Injection ->
   Repair Turn -> Critic Evaluation -> Deliverable Persistence & Cost Accounting ->
   Cryptographic Ed25519 Human Review Token -> Verified Campaign Export & Copy Purity ->
   Audit & Fitness Consumers.
2. Negative & Denial Tests:
   - Deliverable mutation on disk breaks review token binding (C4 fail-closed).
   - Incomplete / unverified copy in verified export mode refuses boilerplate (copy purity).
   - Over-cap budget demand refuses dispatch before execution.
   - Global ESTOP engagement halts worker execution immediately.
   - Unified Hermes and Native worker invocation ABI contract validation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
for p in (ROOT, ORCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import attestation_chain as chain
from budget_controller import BudgetController, BudgetExhaustedError
import campaign_builder
import cost_accounting
from deliverable_preflight import PreflightReport
import execution
import ledger
import operator_auth
from research_notebook import Notebook
import runtime_context as rc
import task_runner


class TestStage4VerticalSlice(unittest.TestCase):
    """End-to-end model-free simulation exercising the entire product assembly line."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory(prefix="agi_stage4_")
        self.temp_root = Path(self.td.name)
        self.runs_dir = self.temp_root / "runs"
        self.runs_dir.mkdir(parents=True)
        self.workspace_dir = self.temp_root / "workspace" / "solar"
        self.workspace_dir.mkdir(parents=True)
        self.db_path = self.temp_root / "ledger.db"

        # Initialize real SQLite schema from canonical ledger/schema.sql
        schema_sql = (ROOT / "ledger" / "schema.sql").read_text(encoding="utf-8")
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(schema_sql)

        # Ephemeral Ed25519 operator keypair for hermetic review token signing
        self.ephemeral_keys = operator_auth._generate_keypair()

        # Patch environment and paths to disposable test root
        self.patches = [
            patch.object(rc, "ROOT", self.temp_root),
            patch.object(rc, "RUNS", self.runs_dir),
            patch.object(ledger, "LEDGER_DB", self.db_path),
            patch.object(operator_auth, "_store_keypair", side_effect=AssertionError("Host key store write attempted")),
            patch.object(operator_auth, "_load_keypair", return_value=self.ephemeral_keys),
            patch.dict(os.environ, {"AGI_TEST_TIER": "integration", "HERMES_HOME": str(self.temp_root)}),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        import gc
        gc.collect()
        try:
            self.td.cleanup()
        except Exception:
            pass

    def test_01_full_assembly_line_native_worker_and_repair(self):
        """Full product pipeline: admission -> research -> preflight repair -> critic -> artifact -> signed review -> export -> audit."""
        tid = 101
        spec = "Research commercial solar installation contractors in Nevada with active state contractor licenses"
        pass_criteria = "At least two licensed commercial contractors with verified license numbers and sources"

        # 1. ADMISSION & QUEUEING
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, mission_id, spec, pass_criteria, status, created_at) "
                "VALUES (?, ?, ?, ?, 'queued', datetime('now'))",
                (tid, "001-solar", spec, pass_criteria),
            )

        # Pre-seed DSSE DISPATCH step so DSSE attestation chain binds
        chain.append_step(self.runs_dir, chain.Step.DISPATCH, tid, 1, {
            "worker_engine": "native",
            "max_budget_usd": 2.00,
            "max_tokens": 10000,
            "budget_enforcement": "hard_stop",
            "client_id": "solar-pros-nv",
        })

        # 2. DISPATCH & MODEL-FREE EXECUTION WITH REPAIR
        # Turn 1: Initial research produces a draft with 1 dead source and 1 live source -> preflight intercepts
        # Turn 2: Repair turn uses Notebook direction block, retrieves 2 verified contractor licenses -> passes
        source_alive_1 = {"url": "https://nv-contractors.example/solar1", "http_status": 200, "classification": "OK",
                          "reachable_on_host": True, "worker_policy_permitted": True, "error": None}
        source_alive_2 = {"url": "https://nv-contractors.example/solar2", "http_status": 200, "classification": "OK",
                          "reachable_on_host": True, "worker_policy_permitted": True, "error": None}
        source_dead = {"url": "https://dead-solar.example/404", "http_status": 404, "classification": "DEAD",
                       "reachable_on_host": False, "worker_policy_permitted": True, "error": "Not Found"}

        reports = [
            # First attempt fails preflight due to dead URL
            PreflightReport(
                passed=False,
                dead_urls=[source_dead],
                schema_issues=["Dead URL detected: https://dead-solar.example/404"],
                repair_feedback="Remove dead URL and find replacement commercial solar license",
                verified_sources=[source_alive_1],
            ),
            # Repair attempt passes preflight with 2 verified sources
            PreflightReport(
                passed=True,
                dead_urls=[],
                schema_issues=[],
                repair_feedback="",
                verified_sources=[source_alive_1, source_alive_2],
            ),
        ]

        worker_calls = 0
        def fake_worker(prompt, cfg, usage_path, **kwargs):
            nonlocal worker_calls
            worker_calls += 1
            if worker_calls == 1:
                # Initial draft citing dead link
                content = (
                    "# Nevada Commercial Solar Contractors\n\n"
                    "- Nevada Sun Pro: Active License NV-SOL-9912. Source: [NV Contractors](https://nv-contractors.example/solar1)\n"
                    "- Ghost Solar: Source: [Defunct Link](https://dead-solar.example/404)\n"
                )
            else:
                # Repaired draft citing 2 verified live links
                self.assertIn("RESEARCH NOTEBOOK", prompt)
                content = (
                    "# Nevada Commercial Solar Contractors\n\n"
                    "- Nevada Sun Pro: Active License NV-SOL-9912. Source: [NV Contractors](https://nv-contractors.example/solar1)\n"
                    "- Silver State Solar: Active License NV-SOL-8841. Source: [NV Contractors](https://nv-contractors.example/solar2)\n"
                )
            return (
                content,
                {"input_tokens": 500, "output_tokens": 200, "cost_usd": 0.0035, "is_invoice": True},
                {"provider": "openai", "model": "gpt-4o"},
                False,
            )

        with patch("task_runner.deliverable_preflight.run_preflight", side_effect=reports), \
             patch("task_runner.citecheck.verify", return_value=[source_alive_1, source_alive_2]), \
             patch("task_runner.evaluation.run_critic", return_value=("pass", "Pass: 2 commercial contractor licenses verified")), \
             patch("task_runner.evaluation.extract_facts", return_value=0), \
             patch("task_runner.execution.worker_with_failover", side_effect=fake_worker), \
             patch("egress_policy.snapshot_egress_policy", return_value={"policy_digest": "p_snap", "allowlisted_hosts": []}), \
             patch("task_runner.policy.token_budget_breached", return_value=False), \
             patch("task_runner.policy.deny_list_scan", return_value=[]):

            mission_dict = {
                "id": "001-solar",
                "body": "## Objective\nResearch commercial solar installation contractors in Nevada\n## \n",
                "frontmatter": {"mission_id": "001-solar"},
                "seeds": ["solar_nv_seed"],
            }
            context = task_runner._TaskContext(
                tid=tid,
                mission=mission_dict,
                roles={"worker": {"provider": "openai", "model": "gpt-4o"},
                       "critic": {"provider": "ollama", "model": "qwen2.5:7b"},
                       "manager": {"provider": "ollama", "model": "qwen2.5:7b"}},
                row={"task_id": tid, "spec": spec, "pass_criteria": pass_criteria, "attempt_count": 0, "client_id": "solar-pros-nv"},
            )
            result = task_runner._run_research_task(context)
            self.assertEqual(result, "done")

        # 3. VERIFY PERSISTENCE & RUNNER ARTIFACTS
        self.assertEqual(worker_calls, 2)  # 1 initial + 1 repair
        notebook = Notebook.load(self.runs_dir / f"task{tid}_research_notebook.json")
        self.assertIsNotNone(notebook)
        self.assertEqual(notebook.attempts_seen, 2)

        # Verify structured attempt cost files
        cost_a1_file = self.runs_dir / f"task{tid}_a1_cost.json"
        self.assertTrue(cost_a1_file.is_file())
        c1 = json.loads(cost_a1_file.read_text())
        # Attempt 1: worker + repair + critic ($0.0035 + $0.0035 = $0.0070 worker+repair)
        self.assertAlmostEqual(c1["cost_usd"], 0.0070, places=4)

        # Verify task deliverable exists on disk
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (tid,)).fetchone()
            self.assertEqual(row["status"], "done")
            self.assertEqual(row["critic_verdict"], "pass")
            artifacts = json.loads(row["artifacts"]) if row["artifacts"] else []
            self.assertTrue(len(artifacts) > 0)
            deliverable_rel = artifacts[0]

        deliverable_path = self.temp_root / deliverable_rel
        self.assertTrue(deliverable_path.is_file())
        deliverable_bytes = deliverable_path.read_bytes()
        deliverable_sha = hashlib.sha256(deliverable_bytes).hexdigest()

        # 4. OPERATOR HUMAN REVIEW & C4 ARTIFACT DIGEST BINDING
        # Generate authentic operator review token bound to deliverable SHA-256
        review_token = operator_auth.create_operator_review(
            task_id=tid,
            artifact_sha256=deliverable_sha,
            verdict="pass",
            notes="State licensing verified on NV portal",
        )
        annotated_notes = f"{row['critic_notes']}\n[OPERATOR_REVIEW_TOKEN: {review_token}]"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE tasks SET human_verdict = 'pass', critic_notes = ? WHERE task_id = ?", (annotated_notes, tid))

        # 5. COMMERCIAL CAMPAIGN EXPORT & COPY PURITY
        # Compile verified campaign from approved deliverable facts
        client_prof = {
            "client_id": "solar-pros-nv",
            "display_name": "Nevada Solar Pros",
            "domain": "commercial solar nevada",
            "geo": ["US", "Nevada"],
            "language": ["en"],
            "offer": "Commercial Solar Power Installation",
            "landing_url": "https://nv-solarpros.example",
            "forbidden_claims": ["100% free guaranteed", "#1 cheapest solar"],
        }
        kw_research = [
            {"keyword": "commercial solar nevada", "theme": "Commercial Solar"},
            {"keyword": "nevada solar installation", "theme": "Installation"},
        ]
        neg_harvest = [{"keyword": "residential"}, {"keyword": "diy"}, {"keyword": "jobs"}, {"keyword": "cheap"}]
        ad_copies = [
            {
                "headlines": ["Nevada Commercial Solar", "Licensed Solar Installers", "Cut Commercial Energy Cost"],
                "descriptions": ["Nevada state licensed commercial solar installations. Free commercial site assessment.",
                                "Custom commercial solar installations for Nevada businesses. Inquire today."],
                "landing_url": "https://nv-solarpros.example",
            }
        ]

        campaign = campaign_builder.build_campaign_from_research(
            client_profile=client_prof,
            keywords=kw_research,
            negatives=neg_harvest,
            ad_copies=ad_copies,
            verified_for_export=True,  # STRICT VERIFIED MODE (C5 copy purity)
        )
        csv_path = self.temp_root / "campaign_export.csv"
        campaign_builder.export_google_ads_editor_csv(campaign, csv_path)
        csv_text = csv_path.read_text(encoding="utf-8")
        self.assertIn("Nevada Commercial Solar", csv_text)
        self.assertIn("Licensed Solar Installers", csv_text)
        self.assertIn("Commercial Solar", csv_text)
        # Verify copy purity: synthetic default headlines are NOT injected into verified CSV
        self.assertNotIn("Official Website", csv_text)
        self.assertNotIn("Contact Our Team", csv_text)
        # Verify default export campaign is paused
        self.assertIn("Paused", csv_text)

        # 6. AUDIT & FITNESS CONSUMERS
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Cost audit sums actual attempt costs
            cost_audit = cost_accounting.audit_ledger_costs(conn, runs_dir=self.runs_dir)
            self.assertEqual(cost_audit["breakdown"]["measured_invoice_tasks"], 1)
            self.assertAlmostEqual(cost_audit["reconciled_cost"]["measured_invoice_usd"], 0.0070, places=4)

            # Human review audit validates operator token
            verdict_audit = cost_accounting.audit_human_verdicts(conn, root=self.temp_root)
            self.assertEqual(verdict_audit["operator_independent"]["count"], 1)
            self.assertEqual(verdict_audit["operator_independent"]["pass"], 1)
            self.assertEqual(verdict_audit["operator_independent"]["fail"], 0)
            self.assertEqual(verdict_audit["ai_performed_checks"]["count"], 0)

            # Weekly fitness computes independent accuracy bound to artifact digest
            fit = ledger.weekly_fitness()
            self.assertEqual(fit["tasks_attempted"], 1)
            self.assertEqual(fit["spot_checked_independent"], 1)
            self.assertEqual(fit["independent_accuracy"], 1.0)
            self.assertEqual(fit["cost_known_tasks"], 1)

        # 7. DSSE ATTESTATION CHAIN VALIDATION
        statements = chain.load(chain.chain_path(self.runs_dir, tid))
        self.assertGreaterEqual(len(statements), 4)  # DISPATCH, WORKER, PREFLIGHT, CRITIC
        valid, err = chain.verify_chain(statements)
        self.assertTrue(valid)
        self.assertIsNone(err)

    def test_02_negative_case_deliverable_tampering_breaks_review_binding(self):
        """C4: Modifying deliverable content on disk causes audit and fitness to fail closed."""
        tid = 102
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, mission_id, spec, pass_criteria, status, created_at) "
                "VALUES (?, ?, 'spec', 'pass', 'done', datetime('now'))",
                (tid, "m1"),
            )

        # Write genuine deliverable
        deliv_file = self.workspace_dir / "deliverable_102.md"
        deliv_file.write_text("Genuine licensed contractor report")
        art_sha = hashlib.sha256(deliv_file.read_bytes()).hexdigest()

        token = operator_auth.create_operator_review(
            task_id=tid,
            artifact_sha256=art_sha,
            verdict="pass",
            notes="Genuine review",
        )
        notes = f"Pass\n[OPERATOR_REVIEW_TOKEN: {token}]"
        rel_art = str(deliv_file.relative_to(self.temp_root))
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tasks SET status='done', human_verdict='pass', critic_notes=?, artifacts=? WHERE task_id=?",
                (notes, json.dumps([rel_art]), tid),
            )

        # Initial check: passes as independent review
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            audit = cost_accounting.audit_human_verdicts(conn, root=self.temp_root)
            self.assertEqual(audit["operator_independent"]["count"], 1)

        # Tamper deliverable content on disk
        deliv_file.write_text("TAMPERED deliverable content replacing genuine facts")

        # After tampering: audit and weekly_fitness fail closed (0 independent reviews)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            audit_tampered = cost_accounting.audit_human_verdicts(conn, root=self.temp_root)
            self.assertEqual(audit_tampered["operator_independent"]["count"], 0)

            fit_tampered = ledger.weekly_fitness()
            self.assertEqual(fit_tampered["spot_checked_independent"], 0)
            self.assertIsNone(fit_tampered["independent_accuracy"])

    def test_03_negative_case_budget_exhaustion_blocks_call_before_dispatch(self):
        """C2: Budget demand exceeding task cap halts runner before LLM dispatch."""
        tid = 103
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, mission_id, spec, pass_criteria, status, created_at) "
                "VALUES (?, ?, 'spec', 'pass', 'queued', datetime('now'))",
                (tid, "m1"),
            )

        # Seed DISPATCH step with small 2,000-token cap
        chain.append_step(self.runs_dir, chain.Step.DISPATCH, tid, 1, {
            "worker_engine": "native",
            "max_tokens": 2000,
            "max_budget_usd": 0.05,
            "budget_enforcement": "hard_stop",
        })

        # Giant prompt demanding > 3,000 tokens
        giant_prompt = "research solar " * 2000

        called = False
        def fake_worker(*args, **kwargs):
            nonlocal called
            called = True
            return "output", {}, {}, False

        with patch("task_runner.execution.worker_with_failover", side_effect=fake_worker):
            mission_dict = {
                "id": "m1",
                "body": "## Objective\nResearch solar objective\n## \n",
                "frontmatter": {"mission_id": "m1"},
                "seeds": ["m1_seed"],
            }
            context = task_runner._TaskContext(
                tid=tid,
                mission=mission_dict,
                roles={"worker": {"provider": "openai", "model": "gpt-4o"},
                       "critic": {"provider": "openai", "model": "gpt-4o"},
                       "manager": {"provider": "openai", "model": "gpt-4o"}},
                row={"task_id": tid, "spec": giant_prompt, "pass_criteria": "pass", "attempt_count": 0},
            )
            result = task_runner._run_research_task(context)

            # Execution blocked before worker dispatch
            self.assertEqual(result, "budget_skip")
            self.assertFalse(called)

            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (tid,)).fetchone()
                self.assertEqual(row["status"], "quota_wait")
                self.assertIn("budget check blocked execution", row["critic_notes"])

    def test_04_negative_case_estop_halts_model_execution_immediately(self):
        """ESTOP = True halts model execution immediately."""
        from execution_pause import pause_engaged
        with patch("execution_pause.pause_engaged", return_value=True):
            with self.assertRaises(RuntimeError) as ctx:
                execution.hermes_worker("prompt", {"provider": "openai", "model": "gpt-4o"}, self.runs_dir / "u.json")
            self.assertIn("ESTOP is engaged", str(ctx.exception))

            with self.assertRaises(RuntimeError) as ctx2:
                execution.native_worker("prompt", {"provider": "openai", "model": "gpt-4o"}, self.runs_dir / "u.json")
            self.assertIn("ESTOP is engaged", str(ctx2.exception))

    def test_05_unified_engine_invocation_contract(self):
        """C1: Unified Hermes and Native worker invocation contract accepts budget_ctrl, res_id, and kwargs."""
        ctrl = BudgetController(runs_dir=self.runs_dir, task_id=105, max_tokens=5000, budget_enforcement="hard_stop")
        res_id = ctrl.reserve("worker", "openai/gpt-4o", prompt_text="hello")

        # Native worker accepts unified contract
        with patch("native_worker.run_native_research_turn", return_value=("native done", {"input_tokens": 100, "output_tokens": 50})), \
             patch("execution.pause_engaged", return_value=False):
            out, usage = execution.native_worker(
                prompt="Research prompt",
                model_cfg={"provider": "openai", "model": "gpt-4o"},
                usage_path=self.runs_dir / "task105_u.json",
                budget_ctrl=ctrl,
                res_id=res_id,
                enforce_active_research=True,
            )
            self.assertEqual(out, "native done")
            self.assertEqual(usage["input_tokens"], 100)


if __name__ == "__main__":
    unittest.main()

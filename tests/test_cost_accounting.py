"""tests/test_cost_accounting.py — Unit regression tests for Honest Outcome and Cost Measurement (P1-E).

Validates acceptance criteria from docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §8:
- Unknown cost never displays or counts as free ($0.00).
- Local compute (Ollama) is explicitly identified with CostBasis.LOCAL_COMPUTE.
- Standard rate cards accurately price cloud models (e.g. OpenAI, BytePlus).
- Measured invoice takes precedence over rate estimation.
- AI-performed checks (F28) are strictly separated from independent operator accuracy.
- Cohort manifests partition historical canaries and infra failures from fresh work.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
for p in (ROOT, ORCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cost_accounting
from cost_accounting import CostBasis, TaskCost, calculate_task_cost, is_genuine_operator_review


class TestCostAccounting(unittest.TestCase):
    """Test cost provenance, rate estimation, verdict auditing, and cohort partitioning."""

    def test_01_unknown_cost_never_displays_as_free(self):
        """Unknown cost returns None and displays 'Unknown (Unpriced)', never '$0.00'."""
        cost = calculate_task_cost(model_used="exotic-unpriced-model/v1", tokens_in=5000, tokens_out=1000)
        self.assertIsNone(cost.cost_usd)
        self.assertEqual(cost.basis, CostBasis.UNKNOWN)
        self.assertNotEqual(cost.formatted, "$0.00")
        self.assertIn("Unknown", cost.formatted)

    def test_02_local_compute_has_explicit_provenance(self):
        """Local models (Ollama) report $0.00 marginal cloud invoice with LOCAL_COMPUTE basis."""
        cost = calculate_task_cost(model_used="ollama/qwen2.5-coder", tokens_in=10000, tokens_out=2500)
        self.assertEqual(cost.cost_usd, 0.0)
        self.assertEqual(cost.basis, CostBasis.LOCAL_COMPUTE)
        self.assertIn("Local Compute", cost.formatted)
        self.assertEqual(cost.input_cost_usd, 0.0)

    def test_03_published_rate_card_calculation(self):
        """Tokens are accurately priced according to 2026 rate card for cloud models."""
        # openai/gpt-4o: $2.50 in / $10.00 out per 1M tokens
        # 10,000 input = 0.01M * 2.50 = $0.025
        # 2,000 output = 0.002M * 10.00 = $0.020
        # Total = $0.045
        cost = calculate_task_cost(model_used="openai/gpt-4o", tokens_in=10000, tokens_out=2000)
        self.assertIsNotNone(cost.cost_usd)
        self.assertAlmostEqual(cost.cost_usd, 0.045, places=5)
        self.assertEqual(cost.basis, CostBasis.ESTIMATED_TOKEN_RATE)
        self.assertAlmostEqual(cost.input_cost_usd, 0.025, places=5)
        self.assertAlmostEqual(cost.output_cost_usd, 0.020, places=5)
        self.assertEqual(cost.formatted, "$0.0450")

    def test_04_measured_invoice_priority(self):
        """Raw provider invoice cost takes priority ONLY when is_invoice is explicitly True (RR4)."""
        # When is_invoice is True:
        cost_inv = calculate_task_cost(
            model_used="openai/gpt-4o",
            tokens_in=10000,
            tokens_out=2000,
            raw_cost_usd=0.0385,
            is_invoice=True,
        )
        self.assertEqual(cost_inv.cost_usd, 0.0385)
        self.assertEqual(cost_inv.basis, CostBasis.MEASURED_INVOICE)

        # When is_invoice is omitted (None): does NOT assume invoice, falls back to token rate
        cost_no_inv = calculate_task_cost(
            model_used="openai/gpt-4o",
            tokens_in=10000,
            tokens_out=2000,
            raw_cost_usd=0.0385,
        )
        self.assertEqual(cost_no_inv.cost_usd, 0.045)
        self.assertEqual(cost_no_inv.basis, CostBasis.ESTIMATED_TOKEN_RATE)

    def test_05_verdict_audit_strictly_separates_ai_checks(self):
        """AI-performed reviews (F28 marker) must not count toward independent operator accuracy."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE tasks (
                task_id INTEGER PRIMARY KEY,
                mission_id TEXT,
                critic_verdict TEXT,
                human_verdict TEXT,
                critic_notes TEXT
            )
        """)
        # 1. Genuine operator pass (with affirmative signature)
        conn.execute("INSERT INTO tasks VALUES (1, 'M1', 'pass', 'pass', '| HUMAN(operator): OPERATOR-VERIFIED verified citations and landing page')")
        # 2. Genuine operator fail (with affirmative signature)
        conn.execute("INSERT INTO tasks VALUES (2, 'M1', 'fail', 'fail', '| HUMAN(operator): OPERATOR-VERIFIED broken links and hallucinated rates')")
        # 3. AI-performed pass (F28)
        conn.execute("INSERT INTO tasks VALUES (3, 'M1', 'pass', 'pass', '| HUMAN(operator): AI-PERFORMED CHECK by claude session')")
        # 4. AI-performed fail (F28)
        conn.execute("INSERT INTO tasks VALUES (4, 'M1', 'fail', 'fail', '| HUMAN(operator): AI-PERFORMED CHECK (not operator)')")
        # 5. Ambiguous note without affirmative signature (unknown provenance)
        conn.execute("INSERT INTO tasks VALUES (5, 'M1', 'pass', 'pass', '| HUMAN(operator): looks good')")
        # 6. Missing note without affirmative signature (unknown provenance)
        conn.execute("INSERT INTO tasks VALUES (6, 'M1', 'fail', 'fail', NULL)")

        audit = cost_accounting.audit_human_verdicts(conn, allow_legacy_text=True)

        self.assertEqual(audit["total_recorded_verdicts"], 6)
        self.assertEqual(audit["operator_independent"]["count"], 2)
        self.assertEqual(audit["operator_independent"]["pass"], 1)
        self.assertEqual(audit["operator_independent"]["fail"], 1)
        self.assertEqual(audit["operator_independent"]["accuracy"], 0.5)

        self.assertEqual(audit["ai_performed_checks"]["count"], 2)
        self.assertEqual(audit["ai_performed_checks"]["pass"], 1)
        self.assertEqual(audit["ai_performed_checks"]["fail"], 1)
        self.assertEqual(audit["ai_performed_checks"]["accuracy"], 0.5)

        self.assertEqual(audit["unknown_provenance"]["count"], 2)
        self.assertEqual(audit["unknown_provenance"]["pass"], 1)
        self.assertEqual(audit["unknown_provenance"]["fail"], 1)
        self.assertEqual(audit["unknown_provenance"]["accuracy"], 0.5)

    def test_06_cohort_manifest_partitions_workloads(self):
        """Canaries, infra failures, and client missions are partitioned into disjoint cohorts."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE tasks (
                task_id INTEGER PRIMARY KEY,
                mission_id TEXT,
                status TEXT,
                critic_verdict TEXT,
                human_verdict TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL
            )
        """)
        conn.execute("INSERT INTO tasks VALUES (1, 'canaries', 'done', 'pass', 'pass', 100, 50, 0.0)")
        conn.execute("INSERT INTO tasks VALUES (2, 'kw_research_roofing', 'done', 'pass', NULL, 500, 200, 0.01)")
        conn.execute("INSERT INTO tasks VALUES (3, 'proto_ablation', 'infra_failed', NULL, NULL, 0, 0, 0.0)")
        conn.execute("INSERT INTO tasks VALUES (50, 'legacy_ablation', 'done', 'pass', NULL, 200, 100, 0.0)")

        manifest = cost_accounting.build_cohort_manifest(conn)
        cohorts = manifest["cohorts"]

        self.assertEqual(cohorts["canaries"]["total_tasks"], 1)
        self.assertEqual(cohorts["commercial_distribution"]["total_tasks"], 1)
        self.assertEqual(cohorts["infra_failures"]["total_tasks"], 1)
        self.assertEqual(cohorts["historical_prototypes"]["total_tasks"], 1)

    def test_07_ledger_cost_audit_reconciles_tokens_honestly(self):
        """audit_ledger_costs accurately categorizes tasks without treating unpriced as $0."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE tasks (
                task_id INTEGER PRIMARY KEY,
                mission_id TEXT,
                model_used TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                status TEXT
            )
        """)
        conn.execute("INSERT INTO tasks VALUES (1, 'M1', 'ollama/qwen2.5-coder', 1000, 500, 0.0, 'done')")
        conn.execute("INSERT INTO tasks VALUES (2, 'M2', 'openai/gpt-4o', 10000, 2000, 0.0, 'done')")
        conn.execute("INSERT INTO tasks VALUES (3, 'M3', 'unpriced_custom_worker', 3000, 1000, 0.0, 'done')")
        conn.execute("INSERT INTO tasks VALUES (4, 'M4', 'none/smoke', 0, 0, 0.0, 'infra_failed')")

        audit = cost_accounting.audit_ledger_costs(conn)
        self.assertEqual(audit["total_tasks"], 4)
        self.assertEqual(audit["breakdown"]["local_compute_tasks"], 2)  # ollama + none/smoke
        self.assertEqual(audit["breakdown"]["estimated_rate_tasks"], 1) # gpt-4o
        self.assertEqual(audit["breakdown"]["unknown_cost_tasks"], 1)   # unpriced_custom_worker
        # $0.045 from openai/gpt-4o
        self.assertAlmostEqual(audit["reconciled_cost"]["estimated_rate_usd"], 0.045, places=4)

    def test_08_bare_model_name_resolution(self):
        """Bare model name 'gpt-4o' resolves to 'openai/gpt-4o' and prices correctly (R6)."""
        cost = calculate_task_cost(model_used="gpt-4o", tokens_in=10000, tokens_out=2000)
        self.assertIsNotNone(cost.cost_usd)
        self.assertAlmostEqual(cost.cost_usd, 0.045, places=5)
        self.assertEqual(cost.basis, CostBasis.ESTIMATED_TOKEN_RATE)

    def test_09_cloud_ollama_model_excluded_from_local_compute(self):
        """Models with :cloud tag in Ollama are not local compute and never priced at $0.00 (R6)."""
        cost = calculate_task_cost(model_used="ollama/glm-5.2:cloud", tokens_in=5000, tokens_out=1000)
        self.assertNotEqual(cost.basis, CostBasis.LOCAL_COMPUTE)
        self.assertIsNone(cost.cost_usd)
        self.assertIn("Unknown", cost.formatted)

    def test_10_unknown_cost_persists_sqlite_null_and_zero_cost_efficiency(self):
        """finish_task with cost_usd=None persists SQLite NULL and weekly_fitness awards 0% efficiency credit (R6)."""
        import tempfile
        from unittest.mock import patch
        import ledger

        td = tempfile.TemporaryDirectory()
        try:
            db_path = Path(td.name) / "test_ledger.db"
            schema_file = ROOT / "ledger" / "schema.sql"
            with sqlite3.connect(db_path) as dst:
                dst.executescript(schema_file.read_text(encoding="utf-8"))

            with patch.object(ledger, "LEDGER_DB", db_path):
                # 1. Queue a task: verify cost_usd defaults to NULL
                tid = ledger.queue_task("mission_test", "Test Task", "Pass criteria")
                with ledger._conn() as c:
                    row = c.execute("SELECT cost_usd FROM tasks WHERE task_id=?", (tid,)).fetchone()
                    self.assertIsNone(row["cost_usd"])

                # 2. Finish task with cost_usd=None: verify NULL is persisted directly (R6)
                ledger.start_task(tid, "mock_model")
                ledger.finish_task(tid, artifacts={}, status="done", cost_usd=None, tokens_in=100, tokens_out=50)
                with ledger._conn() as c:
                    row = c.execute("SELECT cost_usd FROM tasks WHERE task_id=?", (tid,)).fetchone()
                    self.assertIsNone(row["cost_usd"])

                # 3. Verify weekly_fitness reports cost_known_tasks=0, cost_unknown_tasks=1, cost_efficiency=0.0
                fit = ledger.weekly_fitness()
                self.assertEqual(fit["cost_known_tasks"], 0)
                self.assertEqual(fit["cost_unknown_tasks"], 1)
                self.assertEqual(fit["cost_efficiency"], 0.0)
        finally:
            import gc
            gc.collect()
            try:
                td.cleanup()
            except Exception:
                pass

    def test_11_negative_phrases_rejected_in_human_review_provenance(self):
        """RR5: Phrases containing negative review markers strictly return False."""
        self.assertFalse(is_genuine_operator_review("Not reviewed by operator"))
        self.assertFalse(is_genuine_operator_review("No human operator has reviewed this"))
        self.assertFalse(is_genuine_operator_review("by Claude session (not operator)"))
        self.assertFalse(is_genuine_operator_review("AI-PERFORMED CHECK (2026-07-30)"))
        self.assertFalse(is_genuine_operator_review("OPERATOR-VERIFIED: false"))
        self.assertFalse(is_genuine_operator_review("The operator personally has not inspected this report."))
        self.assertFalse(is_genuine_operator_review(""))
        self.assertFalse(is_genuine_operator_review(None))

        # Legacy unsigned text without cryptographic token remains unknown (False)
        self.assertFalse(is_genuine_operator_review("OPERATOR-VERIFIED: Checked domain and contacts"))
        self.assertFalse(is_genuine_operator_review("Verification performed by the operator with their own eyes"))
        self.assertFalse(is_genuine_operator_review("Transcribed at the operator's explicit direction"))

    def test_12_mixed_known_and_unknown_costs_scale_cost_efficiency(self):
        """RR4: Unknown costs scale cost_efficiency down rather than awarding 100% credit."""
        import tempfile
        from unittest.mock import patch
        import ledger

        td = tempfile.TemporaryDirectory()
        try:
            db_path = Path(td.name) / "test_ledger_mixed.db"
            schema_file = ROOT / "ledger" / "schema.sql"
            with sqlite3.connect(db_path) as dst:
                dst.executescript(schema_file.read_text(encoding="utf-8"))

            with patch.object(ledger, "LEDGER_DB", db_path):
                # Task 1: Known cost $0.05
                t1 = ledger.queue_task("m1", "Task 1", "Criteria 1")
                ledger.start_task(t1, "openai/gpt-4o")
                ledger.finish_task(t1, artifacts={}, status="done", cost_usd=0.05, tokens_in=1000, tokens_out=500)

                # Task 2: Unknown cost None
                t2 = ledger.queue_task("m2", "Task 2", "Criteria 2")
                ledger.start_task(t2, "unpriced_model")
                ledger.finish_task(t2, artifacts={}, status="done", cost_usd=None, tokens_in=5000, tokens_out=2000)

                fit = ledger.weekly_fitness()
                self.assertEqual(fit["cost_known_tasks"], 1)
                self.assertEqual(fit["cost_unknown_tasks"], 1)
                # With 50% cost coverage, cost_efficiency cannot be 1.0; it scales by coverage (0.5)
                self.assertLessEqual(fit["cost_efficiency"], 0.5)
        finally:
            import gc
            gc.collect()
            try:
                td.cleanup()
            except Exception:
                pass

    def test_13_structured_operator_token_authentication(self):
        """RR5: Cryptographic operator review tokens authenticate genuine human reviews bound to task & sha."""
        from unittest.mock import patch
        import operator_auth

        ephemeral_keys = operator_auth._generate_keypair()

        # Deny real host credential store writes and supply ephemeral keys
        with patch.object(operator_auth, "_store_keypair", side_effect=AssertionError("Host key store write attempted in test")), \
             patch.object(operator_auth, "_load_keypair", return_value=ephemeral_keys):

            art_dir = Path(tempfile.mkdtemp())
            art42 = art_dir / "art42.md"
            art42.write_text("Deliverable 42 content")
            sha42 = hashlib.sha256(art42.read_bytes()).hexdigest()

            art43 = art_dir / "art43.md"
            art43.write_text("Deliverable 43 content")
            sha43 = hashlib.sha256(art43.read_bytes()).hexdigest()

            token_pass = operator_auth.create_operator_review(
                task_id=42,
                artifact_sha256=sha42,
                verdict="pass",
                notes="Manually audited phone and email on client site",
            )
            note_pass = f"VERDICT: pass\n[OPERATOR_REVIEW_TOKEN: {token_pass}]"

            # Matching task and sha passes authentication
            self.assertTrue(is_genuine_operator_review(note_pass, task_id=42, artifact_sha256=sha42))
            # Mismatched task fails
            self.assertFalse(is_genuine_operator_review(note_pass, task_id=99, artifact_sha256=sha42))
            # Mismatched artifact sha fails
            self.assertFalse(is_genuine_operator_review(note_pass, task_id=42, artifact_sha256="wrongsha"))

            # Genuine signed failure token is authentic and bound
            token_fail = operator_auth.create_operator_review(
                task_id=43,
                artifact_sha256=sha43,
                verdict="fail",
                notes="Phone number on website does not answer",
            )
            note_fail = f"VERDICT: fail\n[OPERATOR_REVIEW_TOKEN: {token_fail}]"
            self.assertTrue(is_genuine_operator_review(note_fail, task_id=43, artifact_sha256=sha43))
            self.assertFalse(is_genuine_operator_review(note_fail, task_id=43, artifact_sha256="wrongsha"))

            # Test audit_human_verdicts with bound tokens, replayed token rejection, and signed failures
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.execute("""
                CREATE TABLE tasks (
                    task_id INTEGER PRIMARY KEY,
                    mission_id TEXT,
                    critic_verdict TEXT,
                    human_verdict TEXT,
                    critic_notes TEXT,
                    artifacts TEXT
                )
            """)
            # Row 1: Valid signed pass for task 42 bound to art42
            conn.execute("INSERT INTO tasks VALUES (42, 'm1', 'pass', 'pass', ?, ?)", (note_pass, json.dumps([str(art42)])))
            # Row 2: Replayed token (token for task 42 put on task 99)
            conn.execute("INSERT INTO tasks VALUES (99, 'm1', 'pass', 'pass', ?, ?)", (note_pass, json.dumps([str(art42)])))
            # Row 3: Valid signed fail for task 43 bound to art43
            conn.execute("INSERT INTO tasks VALUES (43, 'm1', 'fail', 'fail', ?, ?)", (note_fail, json.dumps([str(art43)])))

            audit = cost_accounting.audit_human_verdicts(conn)
            op = audit["operator_independent"]
            self.assertEqual(op["count"], 2)  # Task 42 (pass) and Task 43 (fail); task 99 rejected as unknown
            self.assertEqual(op["pass"], 1)
            self.assertEqual(op["fail"], 1)
            self.assertEqual(op["accuracy"], 0.5)  # 1 pass out of 2 genuine reviews = 50%
            self.assertEqual(audit["unknown_provenance"]["count"], 1)  # Task 99 replayed token categorized as unknown

            # C4 test: Mutate art42 on disk -> task 42 fails closed and is rejected as unverified
            art42.write_text("TAMPERED deliverable content!")
            audit_tampered = cost_accounting.audit_human_verdicts(conn)
            op_tampered = audit_tampered["operator_independent"]
            self.assertEqual(op_tampered["count"], 1)  # Task 42 rejected; only Task 43 remains
            self.assertEqual(op_tampered["pass"], 0)
            self.assertEqual(op_tampered["fail"], 1)
            self.assertEqual(op_tampered["accuracy"], 0.0)

            # C4 test: Delete art43 on disk -> missing artifact fails closed
            art43.unlink()
            audit_missing = cost_accounting.audit_human_verdicts(conn)
            self.assertEqual(audit_missing["operator_independent"]["count"], 0)

        # Assert missing-key behavior without provisioning
        with patch.object(operator_auth, "_store_keypair", side_effect=AssertionError("Host key store write attempted in test")), \
             patch.object(operator_auth, "_load_keypair", return_value=None):
            self.assertFalse(is_genuine_operator_review(note_pass, task_id=42, artifact_sha256="abcdef1234567890"))
            self.assertIsNone(operator_auth.verify_marker(token_pass))

    def test_14_combine_task_costs_and_ledger_invoice_roundtrip(self):
        """RR4: Multi-role cost composition and ledger roundtrip of measured invoice and estimated basis."""
        # 1. Multi-role combination: worker rate card + critic local compute
        w_cost = calculate_task_cost("openai/gpt-4o", 10000, 2000)
        c_cost = calculate_task_cost("ollama/llama3.2", 2000, 500)
        combined = cost_accounting.combine_task_costs([w_cost, c_cost])
        self.assertEqual(combined.basis, CostBasis.ESTIMATED_TOKEN_RATE)
        self.assertEqual(combined.cost_usd, w_cost.cost_usd)
        self.assertEqual(len(combined.provenance["role_breakdowns"]), 2)

        # 2. Unknown role cost propagates unknown status
        u_cost = calculate_task_cost("unpriced_model_xyz", 5000, 1000)
        combined_u = cost_accounting.combine_task_costs([w_cost, u_cost])
        self.assertEqual(combined_u.basis, CostBasis.UNKNOWN)
        self.assertIsNone(combined_u.cost_usd)

        # 3. Ledger roundtrip preserving measured invoice basis via critic_notes
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE tasks (
                task_id INTEGER PRIMARY KEY,
                mission_id TEXT,
                model_used TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                status TEXT,
                critic_notes TEXT
            )
        """)
        conn.execute("INSERT INTO tasks VALUES (1, 'M1', 'openai/gpt-4o', 10000, 2000, 9.25, 'done', 'Audit passed\n[COST_BASIS: measured_invoice]')")
        audit = cost_accounting.audit_ledger_costs(conn)
        self.assertEqual(audit["breakdown"]["measured_invoice_tasks"], 1)
        self.assertEqual(audit["reconciled_cost"]["measured_invoice_usd"], 9.25)

        # 4. Multi-role combined cost roundtrip: worker gpt-4o + critic gpt-4o-mini ($0.003605)
        # 1000 in / 100 out gpt-4o: $0.0035; 500 in / 50 out gpt-4o-mini: $0.000105 -> Total $0.003605
        w_cost2 = calculate_task_cost("openai/gpt-4o", 1000, 100)
        c_cost2 = calculate_task_cost("openai/gpt-4o-mini", 500, 50)
        comb2 = cost_accounting.combine_task_costs([w_cost2, c_cost2])
        self.assertEqual(comb2.cost_usd, 0.003605)

        conn2 = sqlite3.connect(":memory:")
        conn2.row_factory = sqlite3.Row
        conn2.execute("""
            CREATE TABLE tasks (
                task_id INTEGER PRIMARY KEY,
                mission_id TEXT,
                model_used TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                status TEXT,
                critic_notes TEXT
            )
        """)
        conn2.execute(
            "INSERT INTO tasks VALUES (2, 'M2', 'openai/gpt-4o', 1500, 150, 0.003605, 'done', 'Audit passed\n[COST_BASIS: estimated_token_rate]')"
        )
        audit2 = cost_accounting.audit_ledger_costs(conn2)
        self.assertEqual(audit2["breakdown"]["estimated_rate_tasks"], 1)
        # Must audit at exactly $0.003605, NOT single-model recalculated $0.0053
        self.assertEqual(audit2["reconciled_cost"]["estimated_rate_usd"], 0.003605)

    def test_15_weekly_fitness_authenticates_signed_reviews_and_rejects_replays(self):
        """RR5: weekly_fitness binds tokens to task_id and recognizes both signed passes and failures."""
        import tempfile
        from unittest.mock import patch
        import ledger
        import operator_auth

        ephemeral_keys = operator_auth._generate_keypair()

        with patch.object(operator_auth, "_store_keypair", side_effect=AssertionError("Host key store write attempted in test")), \
             patch.object(operator_auth, "_load_keypair", return_value=ephemeral_keys):

            td = tempfile.TemporaryDirectory()
            try:
                db_path = Path(td.name) / "test_ledger_reviews.db"
                schema_file = ROOT / "ledger" / "schema.sql"
                with sqlite3.connect(db_path) as dst:
                    dst.executescript(schema_file.read_text(encoding="utf-8"))

                with patch.object(ledger, "LEDGER_DB", db_path):
                    # Deliverables on disk
                    art42 = Path(td.name) / "t42.md"
                    art42.write_text("Deliverable 42 content")
                    sha42 = hashlib.sha256(art42.read_bytes()).hexdigest()

                    art43 = Path(td.name) / "t43.md"
                    art43.write_text("Deliverable 43 content")
                    sha43 = hashlib.sha256(art43.read_bytes()).hexdigest()

                    # Task 42: genuine signed pass
                    t42 = ledger.queue_task("m1", "Task 42", "Criteria")
                    token_pass = operator_auth.create_operator_review(
                        task_id=t42,
                        artifact_sha256=sha42,
                        verdict="pass",
                        notes="Pass review",
                    )
                    note_pass = f"VERDICT: pass\n[OPERATOR_REVIEW_TOKEN: {token_pass}]"
                    ledger.start_task(t42, "openai/gpt-4o")
                    ledger.finish_task(t42, artifacts=[str(art42)], status="done", critic_notes=note_pass)

                    # Task 43: genuine signed fail
                    t43 = ledger.queue_task("m1", "Task 43", "Criteria")
                    token_fail = operator_auth.create_operator_review(
                        task_id=t43,
                        artifact_sha256=sha43,
                        verdict="fail",
                        notes="Fail review",
                    )
                    note_fail = f"VERDICT: fail\n[OPERATOR_REVIEW_TOKEN: {token_fail}]"
                    ledger.start_task(t43, "openai/gpt-4o")
                    ledger.finish_task(t43, artifacts=[str(art43)], status="done", critic_notes=note_fail)

                    # Task 99: replayed token from task 42
                    t99 = ledger.queue_task("m1", "Task 99", "Criteria")
                    ledger.start_task(t99, "openai/gpt-4o")
                    ledger.finish_task(t99, artifacts=[str(art42)], status="done", critic_notes=note_pass)

                    with sqlite3.connect(db_path) as conn:
                        conn.execute("UPDATE tasks SET human_verdict = 'pass' WHERE task_id = ?", (t42,))
                        conn.execute("UPDATE tasks SET human_verdict = 'fail' WHERE task_id = ?", (t43,))
                        conn.execute("UPDATE tasks SET human_verdict = 'pass' WHERE task_id = ?", (t99,))

                    fit = ledger.weekly_fitness()
                    # 3 tasks attempted, but Task 99 is rejected because task_id does not match token
                    # 2 genuine independent reviews: 1 pass (Task 42) + 1 fail (Task 43)
                    self.assertEqual(fit["tasks_attempted"], 3)
                    self.assertEqual(fit["spot_checked_independent"], 2)
                    self.assertEqual(fit["independent_accuracy"], 0.5)  # 1 pass out of 2 genuine reviews = 50%, NOT 100%!

                    # C4 test: Mutate art42 on disk -> weekly_fitness rejects drifted deliverable
                    art42.write_text("TAMPERED deliverable content!")
                    fit_tampered = ledger.weekly_fitness()
                    self.assertEqual(fit_tampered["spot_checked_independent"], 1)  # Only task 43 valid
                    self.assertEqual(fit_tampered["independent_accuracy"], 0.0)  # Only task 43 (fail) is independent
            finally:
                import gc
                gc.collect()
                try:
                    td.cleanup()
                except Exception:
                    pass

    def test_17_attempt_cost_accumulation_and_audit(self):
        """C3: Attempt costs do not sum exponentially, repair is not double-charged, and audit sums all attempts."""
        td = tempfile.TemporaryDirectory()
        try:
            runs_dir = Path(td.name) / "runs"
            runs_dir.mkdir(parents=True, exist_ok=True)

            worker_cost = TaskCost(
                cost_usd=0.0035,
                basis=CostBasis.MEASURED_INVOICE,
                provenance={"role": "worker"},
            )
            repair_cost = TaskCost(
                cost_usd=0.0035,
                basis=CostBasis.MEASURED_INVOICE,
                provenance={"role": "repair"},
            )
            critic_cost = TaskCost(
                cost_usd=0.0,
                basis=CostBasis.LOCAL_COMPUTE,
                provenance={"role": "critic"},
            )

            # Test 1: Worker + repair combined cost is exactly $0.0070 without double counting
            wr_combined = cost_accounting.combine_task_costs([worker_cost, repair_cost, critic_cost])
            self.assertEqual(wr_combined.cost_usd, 0.007)

            # Test 2: Simulate 3 attempts storing discrete attempt spend
            # Attempt 1
            a1_cost = cost_accounting.combine_task_costs([worker_cost, critic_cost])
            (runs_dir / "task1_a1_cost.json").write_text(json.dumps(a1_cost.to_dict()))
            total_1 = cost_accounting.combine_task_costs([a1_cost])
            (runs_dir / "task1_cost.json").write_text(json.dumps(total_1.to_dict()))

            # Attempt 2
            a2_cost = cost_accounting.combine_task_costs([worker_cost, critic_cost])
            (runs_dir / "task1_a2_cost.json").write_text(json.dumps(a2_cost.to_dict()))
            total_2 = cost_accounting.combine_task_costs([a1_cost, a2_cost])
            (runs_dir / "task1_cost.json").write_text(json.dumps(total_2.to_dict()))

            # Attempt 3
            a3_cost = cost_accounting.combine_task_costs([worker_cost, critic_cost])
            (runs_dir / "task1_a3_cost.json").write_text(json.dumps(a3_cost.to_dict()))
            total_3 = cost_accounting.combine_task_costs([a1_cost, a2_cost, a3_cost])
            (runs_dir / "task1_cost.json").write_text(json.dumps(total_3.to_dict()))

            # Verify discrete attempt files each store $0.0035, NOT cumulative ($0.0035, $0.007, $0.014)
            c1 = TaskCost.from_dict(json.loads((runs_dir / "task1_a1_cost.json").read_text()))
            c2 = TaskCost.from_dict(json.loads((runs_dir / "task1_a2_cost.json").read_text()))
            c3 = TaskCost.from_dict(json.loads((runs_dir / "task1_a3_cost.json").read_text()))
            self.assertEqual(c1.cost_usd, 0.0035)
            self.assertEqual(c2.cost_usd, 0.0035)
            self.assertEqual(c3.cost_usd, 0.0035)
            self.assertEqual(total_3.cost_usd, 0.0105)

            # Test 3: audit_ledger_costs reports $0.0105 from runs_dir
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.execute("CREATE TABLE tasks (task_id INTEGER, mission_id TEXT, model_used TEXT, tokens_in INT, tokens_out INT, cost_usd REAL, status TEXT, critic_notes TEXT)")
            conn.execute("INSERT INTO tasks VALUES (1, 'm1', 'openai/gpt-4o', 100, 100, 0.0105, 'done', '[cost_basis: measured_invoice]')")

            audit = cost_accounting.audit_ledger_costs(conn, runs_dir=runs_dir)
            self.assertEqual(audit["breakdown"]["measured_invoice_tasks"], 1)
            self.assertEqual(audit["reconciled_cost"]["measured_invoice_usd"], 0.0105)

            # Test 4: If task1_cost.json is absent, audit sums all attempt files
            (runs_dir / "task1_cost.json").unlink()
            audit2 = cost_accounting.audit_ledger_costs(conn, runs_dir=runs_dir)
            self.assertEqual(audit2["breakdown"]["measured_invoice_tasks"], 1)
            self.assertEqual(audit2["reconciled_cost"]["measured_invoice_usd"], 0.0105)
        finally:
            td.cleanup()


if __name__ == "__main__":
    unittest.main()

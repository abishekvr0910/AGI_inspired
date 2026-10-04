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

import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
for p in (ROOT, ORCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import cost_accounting
from cost_accounting import CostBasis, TaskCost, calculate_task_cost


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
        """Raw provider invoice cost takes priority over token rate estimation."""
        cost = calculate_task_cost(
            model_used="openai/gpt-4o",
            tokens_in=10000,
            tokens_out=2000,
            raw_cost_usd=0.0385,
        )
        self.assertEqual(cost.cost_usd, 0.0385)
        self.assertEqual(cost.basis, CostBasis.MEASURED_INVOICE)

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
        # 1. Genuine operator pass
        conn.execute("INSERT INTO tasks VALUES (1, 'M1', 'pass', 'pass', '| HUMAN(operator): verified citations and landing page')")
        # 2. Genuine operator fail
        conn.execute("INSERT INTO tasks VALUES (2, 'M1', 'fail', 'fail', '| HUMAN(operator): broken links and hallucinated rates')")
        # 3. AI-performed pass (F28)
        conn.execute("INSERT INTO tasks VALUES (3, 'M1', 'pass', 'pass', '| HUMAN(operator): AI-PERFORMED CHECK by claude session')")
        # 4. AI-performed fail (F28)
        conn.execute("INSERT INTO tasks VALUES (4, 'M1', 'fail', 'fail', '| HUMAN(operator): AI-PERFORMED CHECK (not operator)')")

        audit = cost_accounting.audit_human_verdicts(conn)

        self.assertEqual(audit["total_recorded_verdicts"], 4)
        self.assertEqual(audit["operator_independent"]["count"], 2)
        self.assertEqual(audit["operator_independent"]["pass"], 1)
        self.assertEqual(audit["operator_independent"]["fail"], 1)
        self.assertEqual(audit["operator_independent"]["accuracy"], 0.5)

        self.assertEqual(audit["ai_performed_checks"]["count"], 2)
        self.assertEqual(audit["ai_performed_checks"]["pass"], 1)
        self.assertEqual(audit["ai_performed_checks"]["fail"], 1)
        self.assertEqual(audit["ai_performed_checks"]["accuracy"], 0.5)

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


if __name__ == "__main__":
    unittest.main()

"""Empirical Hypothesis Test Suite: Deep-Loop Re-Search (H-DEEP-LOOP-01).

Validates the core architectural hypothesis that the Deep-Loop Re-Search upgrade
eliminates "one-shot repair amnesia" in the AGI_like harness.

Hypothesis Structure:
- H1: Mechanical Deficit Classification & Banner Injection
- H2: Native Worker Zero-Tool Interception & Mandatory Tool Re-Prompt
- H3: End-to-End Task Runner Auto-Repair Recovery with Active Tool Invocation
- H4: Full Trajectory, Research Notebook, and DSSE Attestation Accounting Integrity
"""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator", ROOT / "tests"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import attestation_chain as chain
import deliverable_preflight
from deliverable_preflight import PreflightReport, build_repair_prompt, requires_active_research
import native_worker
import operator_auth
from research_notebook import Notebook
import task_runner as runner
from v1_test_support import context, runner_fixture, source, worker_result


class DeepLoopHypothesisTests(unittest.TestCase):
    def setUp(self):
        self.keys = operator_auth._generate_keypair()
        self.auth_patch = patch.object(operator_auth, "_load_keypair", return_value=self.keys)
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)

    def test_hypothesis_h1_mechanical_deficit_classification(self):
        """H1: Preflight correctly classifies research vs formatting deficits and gates the re-search banner."""
        # 1. Dead URL deficit -> True
        rep_dead = PreflightReport(passed=False, dead_urls=[{"url": "https://broken.example/404", "http_status": 404}])
        self.assertTrue(requires_active_research(rep_dead), "Dead URL must trigger active research")

        # 2. Insufficient verified sources -> True
        rep_insuf = PreflightReport(
            passed=False,
            schema_issues=["Insufficient verified sources: found 0 OK citations, minimum 2"]
        )
        self.assertTrue(requires_active_research(rep_insuf), "Insufficient sources must trigger active research")

        # 3. Spec declared source count deficit -> True
        rep_count = PreflightReport(
            passed=False,
            schema_issues=["Insufficient source count: deliverable cites 1 sources, spec requires at least 3."]
        )
        self.assertTrue(requires_active_research(rep_count), "Spec source deficit must trigger active research")

        # 4. Pure formatting deficit (e.g. comparison table missing) -> False
        rep_fmt = PreflightReport(
            passed=False,
            schema_issues=["Specification requires a comparison table/matrix, but no valid markdown table was found."]
        )
        self.assertFalse(requires_active_research(rep_fmt), "Pure formatting deficit must NOT trigger active research")

        # 5. Banner injection gating
        prompt_with_research = build_repair_prompt("Mission Base", "Draft", "Feedback", requires_research=True)
        self.assertIn("MANDATORY ACTIVE RE-SEARCH REQUIRED:", prompt_with_research)
        self.assertIn("Do NOT attempt to solve this deficit by reformatting existing text", prompt_with_research)

        prompt_without_research = build_repair_prompt("Mission Base", "Draft", "Feedback", requires_research=False)
        self.assertNotIn("MANDATORY ACTIVE RE-SEARCH REQUIRED:", prompt_without_research)

    def test_hypothesis_h2_native_worker_zero_tool_interception(self):
        """H2: Under enforce_active_research=True, turn 0 zero-tool completions are rejected and re-prompted."""
        messages_received = []

        def mock_caller(messages, tools):
            messages_received.append(list(messages))
            if len(messages_received) == 1:
                # Turn 0: Model attempts one-shot answer from memory without tools
                return {
                    "message": {
                        "role": "assistant",
                        "content": "Premature answer without executing any web tools."
                    },
                    "input_tokens": 60,
                    "output_tokens": 15,
                }
            elif len(messages_received) == 2:
                # Turn 1: Model complies with mandatory re-prompt user message and invokes web_search
                return {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_search_1",
                            "type": "function",
                            "function": {
                                "name": "web_search",
                                "arguments": json.dumps({"query": "verified high-ticket dental ICP"})
                            }
                        }]
                    },
                    "input_tokens": 110,
                    "output_tokens": 25,
                }
            else:
                # Turn 2: Model writes final deliverable grounded in the search result
                return {
                    "message": {
                        "role": "assistant",
                        "content": (
                            "# Verified Dental ICP\n\n"
                            "Grounded finding: All-on-4 implants cost $25k-$50k per arch.\n"
                            "Source: [Metro Dental](https://metro-dental.example/pricing) retrieved 2026-10-02.\n"
                        )
                    },
                    "input_tokens": 140,
                    "output_tokens": 40,
                }

        search_mock = [{"title": "Metro Dental Pricing", "url": "https://metro-dental.example/pricing", "snippet": "Pricing $25k-$50k"}]

        with patch("native_worker.execute_web_search", return_value=search_mock):
            with patch("native_worker.pause_engaged", return_value=False):
                deliv, usage = native_worker.run_native_research_turn(
                    prompt="Research dental pricing.",
                    model_cfg={"provider": "mock"},
                    custom_caller=mock_caller,
                    enforce_active_research=True,
                )

                # Assert that exactly 3 turns occurred (intercepted -> searched -> completed)
                self.assertEqual(len(messages_received), 3, "Turn 0 must be intercepted and re-prompted")
                # Assert turn 1 contained the re-prompt user message
                turn1_msgs = messages_received[1]
                self.assertTrue(any(
                    m.get("role") == "user" and "MANDATORY REQUIREMENT" in m.get("content", "")
                    for m in turn1_msgs
                ), "Model must receive mandatory active research directive")
                # Assert final deliverable cites the retrieved source
                self.assertIn("https://metro-dental.example/pricing", deliv)
                self.assertEqual(usage["tool_calls_executed"], 1)

    def test_hypothesis_h3_and_h4_end_to_end_deep_loop_recovery_and_accounting(self):
        """H3 & H4: End-to-end task runner detects research deficit, enforces active repair, and records full DSSE audit chain."""
        draft1_fail = (
            "# Market Analysis: Prompt Platforms\n\n"
            "This report details prompt platforms.\n"
            "Source: [Dead Resource](https://dead-broken.example/missing-page) reported.\n"
            + ("Detailed paragraph of text to pass minimum character length bounds.\n" * 5)
        )

        draft2_clean = (
            "# Market Analysis: Prompt Platforms\n\n"
            "| Platform | Tier | Monthly Price | Retrieval Date | Confidence |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            "| PromptBase | Pro | $9.99 | 2026-10-02 | 3 |\n\n"
            "Sources:\n"
            "- https://alive-verified.example/pricing [Retrieved 2026-10-02, Confidence: high]\n"
            + ("Detailed paragraph of verified findings.\n" * 5)
        )

        calls = []

        def tracked_worker(prompt, worker_cfg, usage_path, log_prefix="", **kw):
            calls.append({
                "prompt": prompt,
                "kw": kw,
                "usage_path": usage_path,
            })
            if usage_path:
                Path(usage_path).write_text(
                    json.dumps({
                        "input_tokens": 50,
                        "output_tokens": 20,
                        "total_tokens": 70,
                        "api_calls": 1,
                        "tool_calls_executed": 1 if len(calls) > 1 else 0
                    }) + "\n",
                    encoding="utf-8"
                )
            if len(calls) == 1:
                return worker_result(draft1_fail)
            return worker_result(draft2_clean)

        with runner_fixture(tracked_worker) as (_, runs, stack):
            # Seed DSSE Dispatch step
            chain.append_step(runs, chain.Step.DISPATCH, 1, 1, {"worker_engine": "native"})

            # Preflight behavior: Attempt 1 fails with dead URL, Repair 1 passes with clean source
            reports = [
                PreflightReport(
                    passed=False,
                    dead_urls=[{"url": "https://dead-broken.example/missing-page", "http_status": 404}],
                    schema_issues=["Dead Citation URLs: https://dead-broken.example/missing-page"],
                    repair_feedback="Dead Citation: https://dead-broken.example/missing-page is 404.",
                    verified_sources=[],
                ),
                PreflightReport(
                    passed=True,
                    dead_urls=[],
                    schema_issues=[],
                    repair_feedback=None,
                    verified_sources=[source("https://alive-verified.example/pricing", 200)],
                ),
            ]
            stack.enter_context(patch.object(runner.deliverable_preflight, "run_preflight", side_effect=reports))
            stack.enter_context(patch.object(runner.citecheck, "verify", return_value=[source("https://alive-verified.example/pricing", 200)]))
            stack.enter_context(patch.object(runner.evaluation, "run_critic", return_value=("pass", "Verified clean deliverable with live sources")))
            stack.enter_context(patch.object(runner.evaluation, "RUNS", runs))
            stack.enter_context(patch.object(runner.evaluation, "extract_facts", return_value=5))

            # Run task through task runner
            task_ctx = context(tid=1, spec="Research prompt platforms with active sources.")
            status = runner._run_research_task(task_ctx)

            # --- H3 Validations ---
            self.assertEqual(status, "done", "Task must successfully recover to done status")
            self.assertEqual(len(calls), 2, "Task runner must execute exactly Attempt 1 + Repair 1")

            # Verify Attempt 1 had no enforce_active_research requirement
            self.assertFalse(calls[0]["kw"].get("enforce_active_research", False))

            # Verify Repair 1 specifically received enforce_active_research=True
            self.assertTrue(calls[1]["kw"].get("enforce_active_research"), "Repair call MUST receive enforce_active_research=True")

            # Verify Repair 1 prompt contained the mandatory research banner
            self.assertIn("MANDATORY ACTIVE RE-SEARCH REQUIRED:", calls[1]["prompt"])

            # --- H4 Validations (Accounting & Audit Integrity) ---
            # 1. Research notebook persisted both dead URL attempt and clean replacement
            notebook_path = runs / "task1_research_notebook.json"
            self.assertTrue(notebook_path.is_file(), "Notebook must be persisted")
            nb = Notebook.load(notebook_path)
            self.assertEqual(nb.attempts_seen, 2, "Notebook must record 2 attempts")
            dead_urls = [s.url for s in nb.dead_sources]
            self.assertIn("https://dead-broken.example/missing-page", dead_urls)

            # 2. Repair usage file persisted
            repair_usage_file = runs / "task1_a1_worker_repair_1.usage.json"
            self.assertTrue(repair_usage_file.is_file(), "Repair usage file must be saved")
            repair_usage = json.loads(repair_usage_file.read_text(encoding="utf-8"))
            self.assertEqual(repair_usage["policy_digest"], "fixture")

            # 3. Aggregated mission usage file reflects accumulated tokens
            mission_usage_file = runs / "task1_mission.usage.json"
            self.assertTrue(mission_usage_file.is_file(), "Mission usage file must be saved")
            mission_usage = json.loads(mission_usage_file.read_text(encoding="utf-8"))
            self.assertGreater(mission_usage.get("total_tokens", 0), 0)

            # 4. DSSE Cryptographic Chain unbroken and fully valid
            chain_file = chain.chain_path(runs, 1)
            self.assertTrue(chain_file.is_file(), "DSSE attestation chain file must exist")
            statements = chain.load(chain_file)
            self.assertGreaterEqual(len(statements), 6, "Chain must have at least 6 steps")

            # Validate steps in order: DISPATCH -> WORKER(a1) -> PREFLIGHT(a1) -> WORKER(repair1) -> PREFLIGHT(repair1) -> CRITIC -> DELIVERABLE
            payloads = chain.read_payloads(runs, 1)
            step_names = [p["step"] for p in payloads]
            self.assertEqual(step_names[0], chain.Step.DISPATCH.value)
            self.assertEqual(step_names[1], chain.Step.WORKER.value)
            self.assertEqual(step_names[2], chain.Step.PREFLIGHT.value)
            self.assertEqual(step_names[3], chain.Step.WORKER.value)
            self.assertEqual(step_names[4], chain.Step.PREFLIGHT.value)
            self.assertEqual(step_names[5], chain.Step.CRITIC.value)
            self.assertEqual(step_names[6], chain.Step.DELIVERABLE.value)

            # Validate cryptographic verification
            valid, err = chain.verify_chain(statements)
            self.assertTrue(valid, f"DSSE chain must verify cryptographically: {err}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

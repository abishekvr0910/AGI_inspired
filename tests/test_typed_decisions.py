"""Unit tests for orchestrator/typed_decisions.py — Typed Decision Interface.

Verifies:
1. NoulDecision, ChoiceDecision, ScoreDecision data classes and validation.
2. DeterministicRubricBackend produces correct, deterministic results.
3. JevBackend fails closed at dispatch unless all local safety gates pass.
4. DecisionBackend protocol compliance.
5. All backends satisfy the protocol contract.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import typed_decisions as td


class TestDecisionDataClasses(unittest.TestCase):
    """Validates decision result dataclasses and their invariants."""

    def test_noul_decision_valid(self):
        d = td.NoulDecision(probability=0.975, outcome=True, confidence=0.95)
        self.assertTrue(d.outcome)
        self.assertEqual(d.probability, 0.975)
        self.assertEqual(d.noul, 0.975)
        self.assertEqual(d.confidence, 0.95)
        self.assertEqual(d.backend, "deterministic")

    def test_noul_decision_invalid_probability(self):
        with self.assertRaises(ValueError):
            td.NoulDecision(probability=1.5)
        with self.assertRaises(ValueError):
            td.NoulDecision(probability=-0.1)

    def test_noul_decision_invalid_confidence(self):
        with self.assertRaises(ValueError):
            td.NoulDecision(outcome=True, confidence=1.5)
        with self.assertRaises(ValueError):
            td.NoulDecision(outcome=False, confidence=-0.1)

    def test_noul_decision_rejects_contradictory_values(self):
        """Contradictory outcome or confidence must be rejected with ValueError."""
        # Low probability cannot produce True outcome
        with self.assertRaises(ValueError):
            td.NoulDecision(probability=0.1, outcome=True)
        # High probability cannot produce False outcome
        with self.assertRaises(ValueError):
            td.NoulDecision(probability=0.9, outcome=False)
        # Near uncertainty (p=0.5) cannot claim high confidence
        with self.assertRaises(ValueError):
            td.NoulDecision(probability=0.5, confidence=0.95)

    def test_choice_decision_valid(self):
        d = td.ChoiceDecision(
            selected="billing",
            allowed_choices=("billing", "technical", "sales"),
            distribution={"billing": 0.8, "technical": 0.15, "sales": 0.05},
            confidence=0.9,
        )
        self.assertEqual(d.selected, "billing")
        self.assertAlmostEqual(sum(d.distribution.values()), 1.0, places=2)

    def test_choice_decision_invalid_selection(self):
        with self.assertRaises(ValueError):
            td.ChoiceDecision(
                selected="unknown",
                allowed_choices=("billing", "technical"),
            )

    def test_choice_decision_invalid_distribution(self):
        with self.assertRaises(ValueError):
            td.ChoiceDecision(
                selected="billing",
                allowed_choices=("billing", "technical"),
                distribution={"billing": 0.5, "technical": 0.2},  # sums to 0.7
            )

    def test_score_decision_valid(self):
        d = td.ScoreDecision(score=85.0, min_score=0.0, max_score=100.0, confidence=0.95)
        self.assertEqual(d.score, 85.0)
        self.assertEqual(d.confidence, 0.95)

    def test_score_decision_out_of_bounds(self):
        with self.assertRaises(ValueError):
            td.ScoreDecision(score=105.0, max_score=100.0)
        with self.assertRaises(ValueError):
            td.ScoreDecision(score=-5.0, min_score=0.0)

    def test_frozen_dataclasses(self):
        d = td.NoulDecision(outcome=True, confidence=0.95)
        with self.assertRaises(AttributeError):
            d.outcome = False  # type: ignore[misc]


class TestDeterministicRubricBackend(unittest.TestCase):
    """Validates the zero-spend deterministic backend."""

    def setUp(self):
        self.backend = td.DeterministicRubricBackend()

    def test_backend_id(self):
        self.assertEqual(self.backend.backend_id, "deterministic_rubric")

    def test_protocol_compliance(self):
        self.assertIsInstance(self.backend, td.DecisionBackend)

    def test_decide_noul_high_score(self):
        result = self.backend.decide_noul({"score": 95, "threshold": 75})
        self.assertIsInstance(result, td.NoulDecision)
        self.assertTrue(result.outcome)
        self.assertEqual(result.confidence, 0.95)
        self.assertGreater(result.latency_ms, 0)

    def test_decide_noul_low_score(self):
        result = self.backend.decide_noul({"score": 40, "threshold": 75})
        self.assertFalse(result.outcome)
        self.assertEqual(result.confidence, 0.95)

    def test_decide_noul_near_threshold(self):
        result = self.backend.decide_noul({"score": 73, "threshold": 75})
        self.assertFalse(result.outcome)
        self.assertEqual(result.confidence, 0.70)

    def test_decide_choice_dental(self):
        choices = ("broad_match_non_converting", "residential_spillage",
                   "residential_ac_drainage", "unfiltered_broad_match")
        result = self.backend.decide_choice({"vertical": "Dental Implants"}, choices)
        self.assertIsInstance(result, td.ChoiceDecision)
        self.assertEqual(result.selected, "broad_match_non_converting")
        self.assertEqual(result.distribution["broad_match_non_converting"], 1.0)
        self.assertAlmostEqual(sum(result.distribution.values()), 1.0)

    def test_decide_choice_roofing(self):
        choices = ("broad_match_non_converting", "residential_spillage",
                   "residential_ac_drainage", "unfiltered_broad_match")
        result = self.backend.decide_choice({"vertical": "Commercial Roofing"}, choices)
        self.assertEqual(result.selected, "residential_spillage")

    def test_decide_choice_unknown_vertical(self):
        choices = ("broad_match_non_converting", "residential_spillage",
                   "residential_ac_drainage", "unfiltered_broad_match")
        result = self.backend.decide_choice({"vertical": "Solar Panels"}, choices)
        self.assertEqual(result.selected, "unfiltered_broad_match")

    def test_decide_score_high_ticket(self):
        result = self.backend.decide_score({
            "vertical": "Dental Implants",
            "role": "Founder",
            "waste_str": "$22,000/mo",
            "email": "drpatel@dental.com",
        })
        self.assertIsInstance(result, td.ScoreDecision)
        self.assertGreaterEqual(result.score, 90)
        self.assertLessEqual(result.score, 100)
        self.assertEqual(result.confidence, 0.95)

    def test_decide_score_low_ticket(self):
        result = self.backend.decide_score({
            "vertical": "General Cleaning",
            "role": "Intern",
            "waste_str": "$0/mo",
            "email": "",
        })
        self.assertLess(result.score, 60)
        self.assertEqual(result.confidence, 0.65)

    def test_decide_score_deterministic(self):
        """Same inputs must produce identical outputs (determinism invariant)."""
        ctx = {"vertical": "Commercial HVAC", "role": "Owner", "waste_str": "$15,000/mo", "email": "a@b.com"}
        r1 = self.backend.decide_score(ctx)
        r2 = self.backend.decide_score(ctx)
        self.assertEqual(r1.score, r2.score)
        self.assertEqual(r1.confidence, r2.confidence)


class TestJevBackend(unittest.TestCase):
    """Exercises the guarded TypeSafe client with an injected, network-free transport."""

    @staticmethod
    def _response(status, payload=None, headers=None):
        body = json.dumps(payload or {}).encode("utf-8")
        return td._JevHttpResponse(status, body, headers or {})

    def _backend(self, responses, *, estop=False, boundary_ok=True, sleeps=None, events=None):
        policy = replace(
            __import__("egress_policy").load_policy(),
            allowed_hosts=frozenset({"api.typesafe.ai"}),
        )
        pending = list(responses)
        calls = []

        def transport(endpoint, headers, body, timeout, proxy):
            calls.append((endpoint, headers, body, timeout, proxy))
            if not pending:
                raise AssertionError("unexpected additional transport call")
            item = pending.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        def credential_resolver():
            if events is not None:
                events.append("credential")
            return "secret-test-value"

        backend = td.JevBackend(
            transport=transport,
            credential_resolver=credential_resolver,
            estop_check=lambda: estop,
            policy_loader=lambda: policy,
            boundary_check=lambda: {
                "ok": boundary_ok,
                "policy_digest": policy.digest,
            },
            sleeper=(sleeps.append if sleeps is not None else lambda _delay: None),
        )
        return backend, calls

    def test_endpoint_is_pinned_to_official_https_api(self):
        for endpoint in (
            "http://api.typesafe.ai/v1/systemone",
            "https://attacker.example/v1/systemone",
            "https://api.typesafe.ai/v1/systemone?redirect=https://attacker.example",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaises(td.JevBackendNotConfigured):
                td.JevBackend(api_endpoint=endpoint)

    def test_builtin_transport_forces_loopback_proxy_without_environment_bypass(self):
        captured = {}

        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"{}"

        class FakeOpener:
            def open(self, request, timeout):
                captured["request"] = request
                captured["timeout"] = timeout
                return FakeResponse()

        with patch.object(td.urllib.request, "build_opener", return_value=FakeOpener()) as build:
            result = td._stdlib_http_transport(
                "https://api.typesafe.ai/v1/systemone",
                {"Authorization": "Bearer test-only"}, b"{}", 3.0,
                "http://127.0.0.1:8787",
            )
        request = captured["request"]
        self.assertEqual(result.status, 200)
        self.assertEqual(request.full_url, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(request.host, "127.0.0.1:8787")
        self.assertEqual(request._tunnel_host, "api.typesafe.ai")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
        self.assertEqual(captured["timeout"], 3.0)
        self.assertIsInstance(build.call_args.args[0], td.urllib.request.ProxyHandler)
        self.assertEqual(build.call_args.args[0].proxies, {})

    def test_builtin_transport_rejects_non_loopback_proxy(self):
        with self.assertRaisesRegex(td.JevBackendError, "proxy_not_loopback"):
            td._stdlib_http_transport(
                "https://api.typesafe.ai/v1/systemone", {}, b"{}", 1.0,
                "http://proxy.example:8080",
            )

    def test_estop_blocks_before_policy_credentials_or_transport(self):
        events = []
        policy = __import__("egress_policy").load_policy()
        backend = td.JevBackend(
            transport=lambda *args: events.append("transport"),
            credential_resolver=lambda: events.append("credential"),
            estop_check=lambda: True,
            policy_loader=lambda: events.append("policy") or policy,
            boundary_check=lambda: events.append("boundary") or {"ok": True},
        )
        with self.assertRaisesRegex(td.JevBackendNotConfigured, "estop_engaged"):
            backend.decide_noul({"score": 90, "threshold": 75})
        self.assertEqual(events, [])

    def test_non_allowlisted_host_blocks_before_credential_access(self):
        events = []
        backend = td.JevBackend(
            transport=lambda *args: events.append("transport"),
            credential_resolver=lambda: events.append("credential"),
            estop_check=lambda: False,
            policy_loader=__import__("egress_policy").load_policy,
            boundary_check=lambda: events.append("boundary") or {"ok": True},
        )
        with self.assertRaisesRegex(td.JevBackendNotConfigured, "host_not_allowlisted"):
            backend.decide_noul({"score": 90, "threshold": 75})
        self.assertEqual(events, [])

    def test_signed_boundary_is_required_before_credential_access(self):
        events = []
        policy = replace(
            __import__("egress_policy").load_policy(),
            allowed_hosts=frozenset({"api.typesafe.ai"}),
        )
        backend = td.JevBackend(
            transport=lambda *args: events.append("transport"),
            credential_resolver=lambda: events.append("credential"),
            estop_check=lambda: False,
            policy_loader=lambda: policy,
            boundary_check=lambda: {"ok": False, "policy_digest": policy.digest},
        )
        with self.assertRaisesRegex(td.JevBackendNotConfigured, "boundary_unverified"):
            backend.decide_noul({"score": 90, "threshold": 75})
        self.assertEqual(events, [])

    def test_noul_post_uses_official_shape_and_excludes_contact_data(self):
        backend, calls = self._backend([self._response(200, {"answers": {
            "decision": {"type": "noul", "noul": 0.88},
        }})])
        decision = backend.decide_noul({
            "score": 88, "threshold": 75, "email": "owner@acme.com",
            "company": "Acme Co", "notes": "visit https://acme.com/contact",
            "vertical": "acme.com", "role": "Founder", "waste_str": "$15,000/mo",
        })
        self.assertAlmostEqual(decision.noul, 0.88)
        self.assertEqual(decision.backend, "jev_typesafe")
        endpoint, headers, raw_body, _timeout, proxy = calls[0]
        body = json.loads(raw_body.decode("utf-8"))
        self.assertEqual(endpoint, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(proxy, "http://127.0.0.1:8787")
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(body["questions"]["decision"]["type"], "noul")
        self.assertEqual(body["state"], {
            "score": 88, "threshold": 75, "role": "Founder", "waste_str": "$15,000/mo",
        })
        self.assertTrue(headers["Authorization"].startswith("Bearer "))
        self.assertNotIn("owner@acme.com", raw_body.decode("utf-8"))
        self.assertEqual(headers["User-Agent"], "AGI_like-Harness/1.0")
        self.assertNotIn("secret-test-value", repr(backend))

    def test_choice_answer_distribution_is_validated(self):
        backend, calls = self._backend([self._response(200, {"answers": {
            "decision": {
                "type": "choice", "choice": "b",
                "probabilities": {"a": 0.2, "b": 0.8}, "confidence": 0.8,
            },
        }})])
        result = backend.decide_choice({"vertical": "HVAC"}, ("a", "b"))
        self.assertEqual(result.selected, "b")
        self.assertAlmostEqual(sum(result.distribution.values()), 1.0)
        request = json.loads(calls[0][2].decode("utf-8"))
        self.assertEqual(request["questions"]["decision"]["criteria"], {"a": None, "b": None})

    def test_choice_rejects_invalid_probability_distribution(self):
        backend, _calls = self._backend([self._response(200, {"answers": {
            "decision": {
                "type": "choice", "choice": "a",
                "probabilities": {"a": 0.2, "b": 0.2}, "confidence": 0.8,
            },
        }})])
        with self.assertRaisesRegex(td.JevBackendError, "probability_distribution"):
            backend.decide_choice({"vertical": "HVAC"}, ("a", "b"))

    def test_score_maps_vendor_zero_to_nine_scale_to_requested_bounds(self):
        probabilities = {str(i): (1.0 if i == 4 else 0.0) for i in range(10)}
        backend, calls = self._backend([self._response(200, {"answers": {
            "decision": {
                "type": "score", "score": 4.5, "probabilities": probabilities,
                "confidence": 0.9,
            },
        }})])
        result = backend.decide_score({"vertical": "Dental", "role": "Owner"}, 10, 90)
        self.assertAlmostEqual(result.score, 50.0)
        self.assertEqual((result.min_score, result.max_score), (10.0, 90.0))
        request = json.loads(calls[0][2].decode("utf-8"))
        self.assertEqual(len(request["questions"]["decision"]["criteria"]), 10)

    def test_rate_limit_retries_with_bounded_delay_and_rechecks_gate(self):
        sleeps = []
        backend, calls = self._backend([
            td._JevHttpResponse(429, b"{}", {"retry-after": "0.25"}),
            self._response(200, {"answers": {"decision": {"type": "noul", "noul": 0.5}}}),
        ], sleeps=sleeps)
        backend.decide_noul({"score": 60, "threshold": 75})
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [0.5])

    def test_http_error_fails_without_leaking_body_or_retry(self):
        backend, calls = self._backend([
            td._JevHttpResponse(401, b"secret-test-value invalid key details"),
        ])
        with self.assertRaisesRegex(td.JevBackendError, "http_error:401") as cm:
            backend.decide_noul({"score": 60, "threshold": 75})
        self.assertNotIn("secret-test-value", str(cm.exception))
        self.assertEqual(len(calls), 1)

    def test_missing_credential_fails_after_safety_preflight_and_before_transport(self):
        policy = replace(
            __import__("egress_policy").load_policy(),
            allowed_hosts=frozenset({"api.typesafe.ai"}),
        )
        events = []
        backend = td.JevBackend(
            credential_resolver=lambda: None,
            estop_check=lambda: False,
            policy_loader=lambda: policy,
            boundary_check=lambda: {"ok": True, "policy_digest": policy.digest},
            transport=lambda *args: events.append("transport"),
        )
        with self.assertRaisesRegex(td.JevBackendNotConfigured, "api_key_missing"):
            backend.decide_noul({"score": 90, "threshold": 75})
        self.assertEqual(events, [])

    def test_injected_transport_is_never_reported_as_live_http(self):
        backend, _calls = self._backend([self._response(200, {"answers": {
            "decision": {"type": "noul", "noul": 0.8},
        }})])
        self.assertFalse(backend.live_transport_enabled)
        backend.decide_noul({"score": 90, "threshold": 75})
        self.assertEqual(backend.requests_dispatched, 0)
        self.assertEqual(backend.transport_attempts, 1)

    def test_builtin_transport_is_marked_as_live_only_after_all_gates(self):
        backend = td.JevBackend()
        self.assertTrue(backend.live_transport_enabled)
        self.assertEqual(backend.requests_dispatched, 0)

    def test_old_placeholder_constructor_is_not_a_credential_interface(self):
        with self.assertRaises(td.JevBackendNotConfigured) as cm:
            td.JevBackend(api_endpoint="placeholder://", credential_resolver=lambda: "ignored")
        self.assertEqual(str(cm.exception), "jev_endpoint_not_permitted")


class TestGetDefaultBackend(unittest.TestCase):
    def test_returns_deterministic_backend(self):
        backend = td.get_default_backend()
        self.assertIsInstance(backend, td.DeterministicRubricBackend)
        self.assertEqual(backend.backend_id, "deterministic_rubric")


if __name__ == "__main__":
    unittest.main()

"""Unit tests for TypeSafe AI Lead Generation & ICP Evaluation Engine (scripts/evaluate_leads_typesafe.py).

Verifies:
1. ICP fit scoring rubric (0-100 bounds, commercial ticket threshold, calibrated confidence).
2. Waste vector categorization into TypeSafe 'Choice' decision primitives.
3. TypeSafe 'Noul' Boolean qualification primitive.
4. Commercial Evidence Gate enforcement (blocks unverified sample exports).
5. Pipeline execution, sorting determinism, and 100% hermetic execution with isolated gate fixtures.
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator", ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import evaluate_leads_typesafe as elt
import evidence_gate
import typed_decisions


import contextlib
import io
import os
import shutil
import uuid
from unittest.mock import patch


def _safe_cleanup(target):
    try:
        if hasattr(target, "cleanup"):
            try:
                target.cleanup()
            except Exception:
                pass
            if hasattr(target, "_finalizer") and target._finalizer is not None:
                try:
                    target._finalizer.detach()
                except Exception:
                    pass
        elif target:
            def _on_err(func, path, exc_info):
                try:
                    import stat
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                except Exception:
                    pass
            shutil.rmtree(str(target), ignore_errors=True, onerror=_on_err)
    except Exception:
        pass


@contextlib.contextmanager
def _make_temp_dir():
    """Robust temporary directory allocator that actively verifies writability,
    with an automatic in-memory virtual directory fallback for restricted sandboxes."""
    # 1. Exhaustive list of physical candidate directories
    candidates = [
        None,
        Path(tempfile.gettempdir()) if tempfile.gettempdir() else None,
        Path(os.environ["TEMP"]) if "TEMP" in os.environ else None,
        Path(os.environ["TMP"]) if "TMP" in os.environ else None,
        Path(os.environ["TMPDIR"]) if "TMPDIR" in os.environ else None,
        Path(os.environ["LOCALAPPDATA"]) / "Temp" if "LOCALAPPDATA" in os.environ else None,
        Path(os.environ["USERPROFILE"]) / "AppData" / "Local" / "Temp" if "USERPROFILE" in os.environ else None,
        Path.home() / ".tmp" if Path.home().exists() else None,
        ROOT / ".tmp",
        ROOT / "runs" / "_test_tmp",
        ROOT / "workspace" / "_test_tmp",
        Path.cwd() / "_test_tmp",
    ]

    seen = set()
    for candidate in candidates:
        if candidate is None:
            td = None
            try:
                try:
                    td = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
                except TypeError:
                    td = tempfile.TemporaryDirectory()
                probe = Path(td.name) / ".write_probe"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink(missing_ok=True)
            except (PermissionError, OSError, Exception):
                if td is not None:
                    _safe_cleanup(td)
                continue

            try:
                yield td.name
            finally:
                _safe_cleanup(td)
            return

        cand_str = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if cand_str in seen:
            continue
        seen.add(cand_str)

        d = None
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            d = candidate / f"eval_tmp_{uuid.uuid4().hex[:8]}"
            d.mkdir(parents=True, exist_ok=False)
            probe = d / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except (PermissionError, OSError, Exception):
            if d is not None:
                _safe_cleanup(d)
            continue

        try:
            yield str(d)
        finally:
            _safe_cleanup(d)
        return

    # 2. Seamless In-Memory Virtual Fallback (Active when physical filesystem writes are denied)
    marker = f"virtual_eval_tmp_{uuid.uuid4().hex}"
    virtual_fs: dict[str, str] = {}

    class VirtualTextFile(io.StringIO):
        def __init__(self, path_str: str, mode_str: str):
            super().__init__()
            self.path_str = path_str
            self.mode_str = mode_str
            if "r" in mode_str:
                super().write(virtual_fs.get(path_str, ""))
                super().seek(0)

        def close(self):
            if "w" in self.mode_str or "a" in self.mode_str:
                virtual_fs[self.path_str] = self.getvalue()
            super().close()

    orig_open = open
    def mock_open(file, mode="r", *args, **kwargs):
        sfile = str(file)
        if marker in sfile:
            return VirtualTextFile(sfile, mode)
        return orig_open(file, mode, *args, **kwargs)

    orig_mkdir = Path.mkdir
    def mock_mkdir(self, *args, **kwargs):
        if marker in str(self):
            return None
        return orig_mkdir(self, *args, **kwargs)

    orig_is_file = Path.is_file
    def mock_is_file(self):
        if marker in str(self):
            return str(self) in virtual_fs
        return orig_is_file(self)

    orig_exists = Path.exists
    def mock_exists(self):
        if marker in str(self):
            return str(self) in virtual_fs or any(k.startswith(str(self)) for k in virtual_fs)
        return orig_exists(self)

    orig_read_text = Path.read_text
    def mock_read_text(self, *args, **kwargs):
        if marker in str(self):
            if str(self) not in virtual_fs:
                raise FileNotFoundError(str(self))
            return virtual_fs[str(self)]
        return orig_read_text(self, *args, **kwargs)

    orig_write_text = Path.write_text
    def mock_write_text(self, data, *args, **kwargs):
        if marker in str(self):
            virtual_fs[str(self)] = str(data)
            return len(data)
        return orig_write_text(self, data, *args, **kwargs)

    orig_read_bytes = Path.read_bytes
    def mock_read_bytes(self):
        if marker in str(self):
            if str(self) not in virtual_fs:
                raise FileNotFoundError(str(self))
            return virtual_fs[str(self)].encode("utf-8")
        return orig_read_bytes(self)

    orig_unlink = Path.unlink
    def mock_unlink(self, missing_ok=False):
        if marker in str(self):
            virtual_fs.pop(str(self), None)
            return None
        return orig_unlink(self, missing_ok=missing_ok)

    with patch("builtins.open", mock_open), \
         patch.object(Path, "mkdir", mock_mkdir), \
         patch.object(Path, "is_file", mock_is_file), \
         patch.object(Path, "exists", mock_exists), \
         patch.object(Path, "read_text", mock_read_text), \
         patch.object(Path, "write_text", mock_write_text), \
         patch.object(Path, "read_bytes", mock_read_bytes), \
         patch.object(Path, "unlink", mock_unlink):
        yield str(ROOT / marker)


class TestTypeSafeLeadEvaluator(unittest.TestCase):
    def test_score_icp_fit_high_ticket(self):
        """High-ticket vertical + executive role + high waste + valid email should score >= 90 with 0.95 confidence."""
        score, fit, conf = elt.score_icp_fit(
            vertical="Dental Implants",
            role="Chief Surgeon & Founder",
            waste_str="$18,200/mo",
            email="drpatel@illinoisimplants.com"
        )
        self.assertGreaterEqual(score, 90)
        self.assertLessEqual(score, 100)
        self.assertTrue(fit)
        self.assertEqual(conf, 0.95)

    def test_score_icp_fit_missing_email_confidence(self):
        """Missing or invalid email should lower confidence from 0.95 to 0.85."""
        score, fit, conf = elt.score_icp_fit(
            vertical="Dental Implants",
            role="Chief Surgeon & Founder",
            waste_str="$18,200/mo",
            email=""
        )
        self.assertGreaterEqual(score, 90)
        self.assertTrue(fit)
        self.assertEqual(conf, 0.85)

    def test_score_icp_fit_low_ticket_or_generic(self):
        """Unknown vertical + generic role + no contact should score lower with 0.65 baseline confidence."""
        score, fit, conf = elt.score_icp_fit(
            vertical="General Cleaning",
            role="Intern",
            waste_str="$0/mo",
            email=""
        )
        self.assertLess(score, 60)
        self.assertFalse(fit)
        self.assertGreaterEqual(score, 0)
        self.assertEqual(conf, 0.65)  # has_role True, but missing both contact and waste -> 0.65
        # Completely empty role and contact
        score_empty, fit_empty, conf_empty = elt.score_icp_fit(
            vertical="General Cleaning",
            role="",
            waste_str="$0/mo",
            email=""
        )
        self.assertEqual(conf_empty, 0.65)

    def test_classify_waste_vector_choices(self):
        """Waste vectors must map to discrete non-empty TypeSafe Choice categories."""
        v_dental = elt.classify_waste_vector("Dental Implants", "")
        self.assertIn("Free Clinics", v_dental)

        v_roofing = elt.classify_waste_vector("Commercial Roofing", "")
        self.assertIn("Residential Shingle", v_roofing)

        v_hvac = elt.classify_waste_vector("Commercial HVAC", "")
        self.assertIn("Residential AC", v_hvac)

        v_fallback = elt.classify_waste_vector("Solar Panels", "")
        self.assertEqual(v_fallback, "Unfiltered Broad Match Leakage")

    def test_evaluate_prospects_hermetic_fixture(self):
        """Pipeline evaluation produces valid, ranked leads with hermetic EvidenceGate isolation."""
        fixture_rows = [
            {
                "Company Name": "Alpha Commercial Roofing",
                "Vertical": "Commercial Roofing",
                "Market/City": "Dallas, TX",
                "Contact Name": "Marcus Vance",
                "Role": "Owner",
                "Email": "mvance@alpharoofing.com",
                "Phone": "(214) 555-0192",
                "Website": "https://www.alpharoofing.com",
                "Est Monthly Ad Waste": "$12,400/mo",
                "Audit Dossier Path": "workspace/clients/alpha-roofing/strategy_dossier.html",
                "Google Ads CSV Path": "",
                "Outbound Pitch Path": "workspace/outbound_pitches/alpha_pitch.txt",
                "Outreach Status": "Ready to Send",
                "First Touch Date": "",
                "Follow-up Date": "",
                "Notes": ""
            },
            {
                "Company Name": "Beta Dental Implants",
                "Vertical": "Dental Implants",
                "Market/City": "Chicago, IL",
                "Contact Name": "Dr. Arthur Patel",
                "Role": "Founder",
                "Email": "drpatel@betadental.com",
                "Phone": "(312) 555-0138",
                "Website": "https://www.betadental.com",
                "Est Monthly Ad Waste": "$22,000/mo",
                "Audit Dossier Path": "workspace/clients/beta-dental/strategy_dossier.html",
                "Google Ads CSV Path": "",
                "Outbound Pitch Path": "workspace/outbound_pitches/beta_pitch.txt",
                "Outreach Status": "Ready to Send",
                "First Touch Date": "",
                "Follow-up Date": "",
                "Notes": ""
            }
        ]

        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "test_prospects.csv"
            with open(tmp_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(fixture_rows[0].keys()))
                writer.writeheader()
                writer.writerows(fixture_rows)

            isolated_gate = evidence_gate.EvidenceGate(root=tmp_root)
            leads = elt.evaluate_prospects(csv_path=tmp_csv, gate=isolated_gate)
            self.assertEqual(len(leads), 2)

            # Must be sorted descending by ICP fit score
            scores = [l.icp_fit_score for l in leads]
            self.assertEqual(scores, sorted(scores, reverse=True))

            # Beta Dental has higher waste ($22k vs $12.4k) and scores 98 vs 95
            self.assertEqual(leads[0].company_name, "Beta Dental Implants")
            self.assertEqual(leads[0].confidence, 0.95)
            self.assertTrue(leads[0].commercial_ticket_fit)  # TypeSafe Noul primitive
            self.assertEqual(leads[1].company_name, "Alpha Commercial Roofing")
            self.assertEqual(leads[1].confidence, 0.95)
            self.assertTrue(leads[1].commercial_ticket_fit)

            for l in leads:
                self.assertGreaterEqual(l.icp_fit_score, 0)
                self.assertLessEqual(l.icp_fit_score, 100)
                # Unregistered / unverified client in isolated gate must block export
                self.assertFalse(l.can_export_outbound)
                self.assertIn("EVIDENCE_HOLD", l.routing_action)

    def test_evaluate_prospects_verified_export_flow(self):
        """When a prospect is legitimately verified and approved in EvidenceGate, export is permitted."""
        fixture_rows = [
            {
                "Company Name": "Verified Industrial Roofing",
                "Vertical": "Commercial Roofing",
                "Market/City": "Austin, TX",
                "Contact Name": "Jane Doe",
                "Role": "President",
                "Email": "jane@verifiedroofing.com",
                "Phone": "(512) 555-0100",
                "Website": "https://www.verifiedroofing.com",
                "Est Monthly Ad Waste": "$15,000/mo",
                "Audit Dossier Path": "workspace/clients/verified-roofing/strategy_dossier.html",
                "Google Ads CSV Path": "",
                "Outbound Pitch Path": "",
                "Outreach Status": "Ready to Send",
                "First Touch Date": "",
                "Follow-up Date": "",
                "Notes": ""
            }
        ]

        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "verified_prospect.csv"
            with open(tmp_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(fixture_rows[0].keys()))
                writer.writeheader()
                writer.writerows(fixture_rows)

            isolated_gate = evidence_gate.EvidenceGate(root=tmp_root)
            # Register prospect as fully verified and approved
            pv = evidence_gate.ProspectVerification(
                client_id="verified-roofing",
                company_name="Verified Industrial Roofing",
                status=evidence_gate.VerificationStatus.VERIFIED,
                approved_for_export=True,
            )
            # Add required evidence records
            for ctype, field_val in [
                (evidence_gate.ClaimType.CONTACT, "contact_name"),
                (evidence_gate.ClaimType.CONTACT, "contact_email"),
                (evidence_gate.ClaimType.CONTACT, "contact_role"),
                (evidence_gate.ClaimType.COMPANY, "company_name"),
                (evidence_gate.ClaimType.COMPANY, "website"),
                (evidence_gate.ClaimType.COMPANY, "city"),
                (evidence_gate.ClaimType.WASTE_ESTIMATE, "est_monthly_leak"),
            ]:
                pv.add_evidence(evidence_gate.EvidenceRecord(
                    claim_type=ctype,
                    claim_value=field_val,
                    source="operator_verified",
                    source_date="2026-09-26",
                    reviewer="operator",
                    reviewer_date="2026-09-26",
                    verified=True
                ))
            isolated_gate.create_or_update(pv)

            leads = elt.evaluate_prospects(csv_path=tmp_csv, gate=isolated_gate)
            self.assertEqual(len(leads), 1)
            lead = leads[0]
            self.assertEqual(lead.verification_status, "verified")
            self.assertTrue(lead.can_export_outbound)
            self.assertIn("PRIORITY_OUTBOUND", lead.routing_action)

    def test_evaluate_prospects_injected_backend(self):
        """Pipeline operates seamlessly with an injected DecisionBackend protocol implementation."""
        fixture_rows = [
            {
                "Company Name": "Omega HVAC Solutions",
                "Vertical": "Commercial HVAC",
                "Market/City": "Phoenix, AZ",
                "Contact Name": "Tom Miller",
                "Role": "President",
                "Email": "tom@omegahvac.com",
                "Phone": "(602) 555-0199",
                "Website": "https://www.omegahvac.com",
                "Est Monthly Ad Waste": "$16,500/mo",
                "Audit Dossier Path": "",
                "Google Ads CSV Path": "",
                "Outbound Pitch Path": "",
                "Outreach Status": "Ready to Send",
                "First Touch Date": "",
                "Follow-up Date": "",
                "Notes": ""
            }
        ]
        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "injected_test.csv"
            with open(tmp_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(fixture_rows[0].keys()))
                writer.writeheader()
                writer.writerows(fixture_rows)

            isolated_gate = evidence_gate.EvidenceGate(root=tmp_root)
            backend = typed_decisions.DeterministicRubricBackend()
            leads = elt.evaluate_prospects(csv_path=tmp_csv, gate=isolated_gate, backend=backend)
            self.assertEqual(len(leads), 1)
            lead = leads[0]
            self.assertGreaterEqual(lead.icp_fit_score, 85)
            self.assertTrue(lead.commercial_ticket_fit)
            self.assertEqual(lead.confidence, 0.95)
            # Unverified in gate must still hold export
            self.assertFalse(lead.can_export_outbound)
            self.assertIn("EVIDENCE_HOLD", lead.routing_action)

    def test_evidence_gate_strict_precedence_over_model_decision(self):
        """Model decisions (even 100/100 score and high-ticket fit) CAN NEVER authorize export without EvidenceGate approval."""
        class MockOverlyOptimisticBackend:
            @property
            def backend_id(self) -> str:
                return "mock_hyper_optimistic"

            def decide_noul(self, context: dict) -> typed_decisions.NoulDecision:
                return typed_decisions.NoulDecision(outcome=True, confidence=1.0, backend=self.backend_id)

            def decide_choice(self, context: dict, allowed_choices: tuple[str, ...]) -> typed_decisions.ChoiceDecision:
                return typed_decisions.ChoiceDecision(selected=allowed_choices[0], allowed_choices=allowed_choices, confidence=1.0, backend=self.backend_id)

            def decide_score(self, context: dict, min_score: float = 0.0, max_score: float = 100.0) -> typed_decisions.ScoreDecision:
                return typed_decisions.ScoreDecision(score=100.0, confidence=1.0, backend=self.backend_id)

        fixture_rows = [
            {
                "Company Name": "Unverified HyperFit Inc",
                "Vertical": "Commercial Roofing",
                "Market/City": "Denver, CO",
                "Contact Name": "CEO",
                "Role": "Chief Executive",
                "Email": "ceo@hyperfit.com",
                "Phone": "(303) 555-0100",
                "Website": "https://www.hyperfit.com",
                "Est Monthly Ad Waste": "$50,000/mo",
                "Audit Dossier Path": "",
                "Google Ads CSV Path": "",
                "Outbound Pitch Path": "",
                "Outreach Status": "Ready to Send",
                "First Touch Date": "",
                "Follow-up Date": "",
                "Notes": ""
            }
        ]
        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "precedence_test.csv"
            with open(tmp_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(fixture_rows[0].keys()))
                writer.writeheader()
                writer.writerows(fixture_rows)

            isolated_gate = evidence_gate.EvidenceGate(root=tmp_root)
            leads = elt.evaluate_prospects(csv_path=tmp_csv, gate=isolated_gate, backend=MockOverlyOptimisticBackend())
            self.assertEqual(len(leads), 1)
            lead = leads[0]
            # Model says perfect score
            self.assertEqual(lead.icp_fit_score, 100)
            self.assertTrue(lead.commercial_ticket_fit)
            # BUT EvidenceGate strictly blocks outbound export
            self.assertFalse(lead.can_export_outbound)
            self.assertIn("EVIDENCE_HOLD", lead.routing_action)
            self.assertEqual(lead.verification_status, "unregistered")

    def test_unconfigured_jev_backend_fails_closed(self):
        """Unsupported endpoints are rejected before a credential or transport can be used."""
        with self.assertRaisesRegex(typed_decisions.JevBackendNotConfigured, "endpoint_not_permitted"):
            typed_decisions.JevBackend(api_endpoint="placeholder")

    def test_benchmark_runner_deterministic(self):
        """Benchmark runner executes cleanly against deterministic baseline and records distributions."""
        fixture_rows = [
            {
                "Company Name": "Benchmark HVAC Co",
                "Vertical": "Commercial HVAC",
                "Market/City": "Phoenix, AZ",
                "Contact Name": "Tom Miller",
                "Role": "President",
                "Email": "tom@benchmarkhvac.com",
                "Phone": "(602) 555-0199",
                "Website": "https://www.benchmarkhvac.com",
                "Est Monthly Ad Waste": "$16,500/mo",
                "Audit Dossier Path": "",
                "Google Ads CSV Path": "",
                "Outbound Pitch Path": "",
                "Outreach Status": "Ready to Send",
                "First Touch Date": "",
                "Follow-up Date": "",
                "Notes": ""
            }
        ]
        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "bench_test.csv"
            tmp_out = tmp_root / "bench_result.json"
            with open(tmp_csv, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(fixture_rows[0].keys()))
                writer.writeheader()
                writer.writerows(fixture_rows)

            res = elt.run_benchmark(csv_path=tmp_csv, samples=5, backend_type="deterministic", output_path=tmp_out)
            self.assertEqual(res["status"], "COMPLETED_LOCAL_BASELINE")
            self.assertEqual(res["field_type"], "locally_measured")
            self.assertIn("not RFC 2606-sanitized", res["dataset"]["provenance"])
            self.assertEqual(res["total_decision_calls"], 15)  # 1 prospect * 5 samples * 3 primitives
            self.assertEqual(res["schema_error_count"], 0)
            self.assertTrue(tmp_out.is_file())

    def test_benchmark_runner_jev_unconfigured(self):
        """Default ESTOP causes the live benchmark to record an honest, unrun result."""
        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "bench_test.csv"
            tmp_out = tmp_root / "bench_jev.json"
            with open(tmp_csv, mode="w", newline="", encoding="utf-8") as f:
                f.write("Company Name,Vertical,Role,Est Monthly Ad Waste,Email\nTest Co,Commercial Roofing,Owner,$10000,a@b.com\n")

            res = elt.run_benchmark(csv_path=tmp_csv, samples=5, backend_type="jev", output_path=tmp_out)
            self.assertEqual(res["status"], "JEV_LIVE_MEASUREMENT_NOT_RUN")
            self.assertEqual(res["field_type"], "unrun")
            self.assertIn("estop_engaged", res["reason"].lower())
            self.assertEqual(res["requests_dispatched"], 0)
            self.assertIn("not RFC 2606-sanitized", res["dataset"]["provenance"])
            self.assertTrue(tmp_out.is_file())

    def test_benchmark_runner_jev_mock_transport_flow(self):
        """The live report path works with a mocked client and never uses the network."""
        fixture = "Company Name,Vertical,Role,Est Monthly Ad Waste,Email\nTest Co,Commercial Roofing,Owner,$10000,owner@not-example.com\n"
        with _make_temp_dir() as tmpdir:
            tmp_root = Path(tmpdir)
            tmp_csv = tmp_root / "bench_test.csv"
            tmp_out = tmp_root / "bench_jev.json"
            tmp_csv.write_text(fixture, encoding="utf-8")

            class MockJevBackend:
                backend_id = "jev_typesafe"
                live_transport_enabled = False
                requests_dispatched = 0
                transport_attempts = 3

                def decide_score(self, context):
                    return typed_decisions.ScoreDecision(score=82, confidence=0.9, backend=self.backend_id)

                def decide_noul(self, context):
                    return typed_decisions.NoulDecision(probability=0.9, backend=self.backend_id)

                def decide_choice(self, context, allowed_choices):
                    return typed_decisions.ChoiceDecision(
                        selected=allowed_choices[0], allowed_choices=allowed_choices,
                        confidence=0.8, backend=self.backend_id,
                    )

            with patch.object(elt.typed_decisions, "JevBackend", MockJevBackend):
                res = elt.run_benchmark(
                    csv_path=tmp_csv, backend_type="jev", output_path=tmp_out,
                )
            self.assertEqual(res["status"], "JEV_MOCK_MEASUREMENT_COMPLETED")
            self.assertEqual(res["field_type"], "mock_measured")
            self.assertEqual(res["decision_calls_requested"], 3)
            self.assertEqual(res["completed_decision_calls"], 3)
            self.assertEqual(res["requests_dispatched"], 0)
            self.assertEqual(res["transport_attempts"], 3)
            self.assertIn("no external HTTP request", res["reason"])
            self.assertNotIn("owner@not-example.com", tmp_out.read_text(encoding="utf-8"))

    def test_virtual_fallback_allocation(self):
        """Simulate a restricted token environment where physical filesystem access raises PermissionError,
        verifying that _make_temp_dir() engages the virtual in-memory directory fallback seamlessly."""
        with patch("tempfile.TemporaryDirectory", side_effect=PermissionError("Denied by token")), \
             patch("pathlib.Path.mkdir", side_effect=PermissionError("Denied by token")):
            with _make_temp_dir() as vdir:
                self.assertIn("virtual_eval_tmp_", vdir)
                vpath = Path(vdir) / "test_file.txt"
                vpath.write_text("hermetic content", encoding="utf-8")
                self.assertTrue(vpath.is_file())
                self.assertEqual(vpath.read_text(encoding="utf-8"), "hermetic content")

    def test_virtual_fallback_when_probe_fails(self):
        """Simulate an environment where directory creation succeeds but the write probe fails
        (e.g., read-only filesystem or restricted DACL on directory contents),
        verifying that candidate temp dirs are safely cleaned up and fallback engages without traces."""
        orig_write_text = Path.write_text

        def mock_write_text(self, *args, **kwargs):
            if self.name == ".write_probe":
                raise PermissionError("Write probe denied by token DACL")
            return orig_write_text(self, *args, **kwargs)

        with patch.object(Path, "write_text", side_effect=mock_write_text, autospec=True):
            with _make_temp_dir() as vdir:
                self.assertIn("virtual_eval_tmp_", vdir)
                vpath = Path(vdir) / "test_file.txt"
                vpath.write_text("probe-failure recovery content", encoding="utf-8")
                self.assertTrue(vpath.is_file())
                self.assertEqual(vpath.read_text(encoding="utf-8"), "probe-failure recovery content")


if __name__ == "__main__":
    unittest.main()

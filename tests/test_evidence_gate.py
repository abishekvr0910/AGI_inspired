"""tests/test_evidence_gate.py — Comprehensive regression suite for P0-B Evidence & Complete Client Packages.

Acceptance criteria from docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §5:
1. Coffee profile rejection: el-shaddai-coffee-katowice with no research is rejected for client-ready export,
   listing missing research sections; visibly marked internal draft is allowed.
2. Empty fields & placeholder values fail closed: empty source, reviewer, dates, or bare field names as values.
3. Waste estimate optionality: packages with no savings claim are permitted without forcing fake figures;
   waste claims require an authorized account extract reference.
4. Content hash invalidation: post-approval profile or deliverable mutations invalidate approval and fail closed.
5. Factual boilerplate removal: contractor claims (licensed & bonded, emergency service, free estimates)
   are never injected into generic copy; language-appropriate copy is used.
6. Default paused status: all exported campaigns (sample, draft, and verified) default strictly to Paused.
7. Positive fixture: complete approved evidence produces useful, sector-appropriate MD, HTML, and paused CSV.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
for p in (ROOT, ORCH):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import campaign_builder
import client_reporter
import evidence_gate
from evidence_gate import (
    ClaimType,
    EvidenceGate,
    EvidenceRecord,
    ProspectVerification,
    VerificationStatus,
    create_sample_verification,
    verify_client_package_export,
)


class TestEvidenceGateHardening(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        self.gate = EvidenceGate(root=self.tmp_root)

        self.valid_profile = {
            "client_id": "apex-solar",
            "display_name": "Apex Solar Solutions",
            "domain": "solar energy systems",
            "geo": ["US", "Denver-CO"],
            "language": ["en"],
            "offer": "Residential and commercial rooftop solar installation",
            "audience": "Homeowners and commercial property owners looking to reduce utility bills",
            "competitors": ["https://competitor.example"],
            "brand_voice": "Authoritative, sustainable, transparent",
            "landing_url": "https://apex-solar.example",
            "seed_keywords": ["solar panels denver", "rooftop solar installation"],
            "forbidden_claims": ["free solar guaranteed", "zero bill guaranteed"],
        }

        self.complete_deliverables = {
            "keyword_research": (
                "| Keyword | Intent | Funnel Stage | Rationale | Source URL |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
                "| denver solar panel installation | commercial | conversion | High intent local buyer | https://example.com/s1 |\n"
                "| cost of rooftop solar colorado | informational | consideration | Research stage | https://example.com/s2 |\n"
            ),
            "negative_keyword_harvest": (
                "| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n"
                "| free solar program scam | phrase | irrelevant | Searchers looking for government subsidies | https://example.com/s3 |\n"
                "| diy solar panel kit | exact | out_of_scope | Non-installation buyers | https://example.com/s4 |\n"
            ),
            "ad_copy_variants": (
                "| Format | Component | Copy Text | Characters | CTA | Source / Rationale |\n"
                "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
                "| RSA | Headline | Apex Solar Solutions | 20 | Explore | Brand anchor |\n"
                "| RSA | Headline | Denver Rooftop Solar Pros | 25 | Inquire | Local authority |\n"
                "| RSA | Headline | Lower Your Utility Bills | 24 | Learn More | Core benefit |\n"
                "| RSA | Description | Invest in high-efficiency rooftop solar for your Denver property. Contact our team. | 83 | Contact Us | Primary value prop |\n"
                "| RSA | Description | Custom solar designs engineered for Colorado weather. Browse our solutions online. | 82 | Explore | Authority description |\n"
            ),
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _create_valid_verified_prospect(self, client_id: str = "apex-solar") -> ProspectVerification:
        v = ProspectVerification(
            client_id=client_id,
            company_name="Apex Solar Solutions",
            status=VerificationStatus.VERIFIED,
            approved_for_export=True,
        )
        now = "2026-10-04T12:00:00Z"
        identity_fields = [
            (ClaimType.CONTACT, "contact_name", "Sarah Jenkins", "operator_provided"),
            (ClaimType.CONTACT, "contact_email", "s.jenkins@apex-solar.example", "corporate_registry"),
            (ClaimType.CONTACT, "contact_role", "VP Commercial Operations", "corporate_registry"),
            (ClaimType.COMPANY, "company_name", "Apex Solar Solutions", "state_filing"),
            (ClaimType.COMPANY, "website", "https://apex-solar.example", "dns_whois_verified"),
            (ClaimType.COMPANY, "city", "Denver", "state_filing"),
        ]
        for ctype, fname, cval, src in identity_fields:
            v.add_evidence(EvidenceRecord(
                claim_type=ctype,
                field_name=fname,
                claim_value=cval,
                source=src,
                source_date=now,
                reviewer="auditor_lead",
                reviewer_date=now,
                notes="Verified in state filing",
                verified=True,
            ))
        return v

    def test_coffee_client_rejected_for_client_export_due_to_incomplete_research(self):
        """el-shaddai-coffee-katowice with no research is rejected for client export, listing missing sections."""
        res = client_reporter.compile_and_export_client_package("el-shaddai-coffee-katowice")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"], "EXPORT_BLOCKED")
        self.assertIn("Incomplete research sections", res["message"])
        self.assertIn("keyword_research missing", res["message"])

    def test_coffee_client_allows_visibly_marked_internal_draft(self):
        """el-shaddai-coffee-katowice allows an internal draft when allow_draft=True with clear warnings."""
        res = client_reporter.compile_and_export_client_package("el-shaddai-coffee-katowice", allow_draft=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["is_draft"])
        self.assertEqual(res["verification_status"], "draft")

        # Dossier must contain prominent internal draft warning
        md_text = Path(res["dossier_md_path"]).read_text(encoding="utf-8")
        self.assertIn("[INTERNAL DRAFT]", md_text)
        self.assertIn("⚠ INTERNAL DRAFT — INCOMPLETE RESEARCH — NOT FOR CLIENT USE", md_text)

        # Ads CSV must be Paused and prefixed [DRAFT]
        csv_text = Path(res["csv_path"]).read_text(encoding="utf-8")
        self.assertIn("[DRAFT] ", csv_text)
        self.assertNotIn("Licensed & Bonded Pros", csv_text)
        self.assertNotIn("24/7 Emergency Service", csv_text)
        # All rows must be Paused
        lines = [l for l in csv_text.splitlines() if l.strip() and not l.startswith("#")]
        reader = list(csv.reader(lines))
        status_idx = reader[0].index("Status")
        for row in reader[1:]:
            self.assertEqual(row[status_idx], "Paused")

    def test_empty_or_placeholder_claim_values_fail_closed(self):
        """Empty source, reviewer, dates, or bare field names as values fail verification."""
        v = self._create_valid_verified_prospect()
        # Corrupt one record with empty reviewer
        v.evidence[0].reviewer = ""
        self.gate.create_or_update(v)

        can_export, reason = self.gate.can_export_prospect("apex-solar", deliverables=self.complete_deliverables)
        self.assertFalse(can_export)
        self.assertIn("Reviewer cannot be empty", reason)

        # Corrupt with bare field name placeholder as claim value
        v.evidence[0].reviewer = "auditor"
        v.evidence[0].claim_value = v.evidence[0].field_name  # e.g. "contact_name"
        self.gate.create_or_update(v)

        can_export, reason = self.gate.can_export_prospect("apex-solar", deliverables=self.complete_deliverables)
        self.assertFalse(can_export)
        self.assertIn("cannot be identical to field name", reason)

    def test_unsupported_waste_estimate_fails_closed(self):
        """Waste estimate with generic operator estimate fails closed; authorized export passes."""
        v = self._create_valid_verified_prospect()
        now = "2026-10-04T12:00:00Z"

        # Add unsupported waste estimate
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.WASTE_ESTIMATE,
            field_name="est_monthly_leak",
            claim_value="$3,500/mo",
            source="operator_estimate",  # Generic estimate without extract
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        self.gate.create_or_update(v)

        can_export, reason = self.gate.can_export_prospect("apex-solar", deliverables=self.complete_deliverables)
        self.assertFalse(can_export)
        self.assertIn("Waste estimate claim requires an authorized account extract", reason)

        # Fix with authorized extract
        v.evidence[-1].source = "authorized_google_ads_export_2026_q3"
        self.gate.create_or_update(v)
        can_export, reason = self.gate.can_export_prospect("apex-solar", deliverables=self.complete_deliverables)
        self.assertTrue(can_export)
        self.assertIsNone(reason)

    def test_omitted_waste_estimate_is_permitted(self):
        """Packages with no savings claim are permitted without forcing fake waste figures."""
        v = self._create_valid_verified_prospect()
        # Ensure zero waste records exist
        self.assertFalse(any(e.claim_type == ClaimType.WASTE_ESTIMATE for e in v.evidence))
        self.gate.create_or_update(v)

        can_export, reason = self.gate.can_export_prospect("apex-solar", deliverables=self.complete_deliverables)
        self.assertTrue(can_export)
        self.assertIsNone(reason)

    def test_content_drift_invalidates_approval(self):
        """Mutating profile or deliverables after approval invalidates export approval."""
        v = self._create_valid_verified_prospect()
        self.gate.create_or_update(v)

        ok, msg = self.gate.verify_prospect_for_export(
            "apex-solar",
            reviewer="compliance_lead",
            profile=self.valid_profile,
            deliverables=self.complete_deliverables,
        )
        self.assertTrue(ok)

        # Export succeeds with matching profile and deliverables
        can_export, reason = self.gate.can_export_prospect(
            "apex-solar", profile=self.valid_profile, deliverables=self.complete_deliverables
        )
        self.assertTrue(can_export)

        # Mutate profile (e.g. changing landing_url or offer)
        mutated_profile = dict(self.valid_profile)
        mutated_profile["landing_url"] = "https://hijacked.example"
        can_export, reason = self.gate.can_export_prospect(
            "apex-solar", profile=mutated_profile, deliverables=self.complete_deliverables
        )
        self.assertFalse(can_export)
        self.assertIn("Approved content drift", reason)

        # Mutate deliverables
        mutated_delivs = dict(self.complete_deliverables)
        mutated_delivs["keyword_research"] = "corrupted table"
        can_export, reason = self.gate.can_export_prospect(
            "apex-solar", profile=self.valid_profile, deliverables=mutated_delivs
        )
        self.assertFalse(can_export)
        self.assertIn("Approved content drift", reason)

    def test_campaign_builder_removes_contractor_boilerplate_and_uses_language(self):
        """Generic contractor claims are never injected; Polish profile produces Polish copy."""
        pl_profile = {
            "client_id": "test-coffee",
            "display_name": "Kawiarnia Testowa",
            "domain": "palarnia kawy",
            "geo": ["PL", "Warszawa"],
            "language": ["pl"],
            "offer": "Kawa speciality",
            "landing_url": "https://kawa.example",
            "seed_keywords": ["kawa speciality warszawa"],
            "forbidden_claims": [],
        }

        campaign = campaign_builder.build_campaign_from_research(
            client_profile=pl_profile,
            keywords=[{"keyword": "kawa ziarnista", "theme": "Kawa", "intent": "commercial"}],
            verified_for_export=True,
        )

        all_headlines = []
        all_descriptions = []
        for ag in campaign.ad_groups:
            for ad in ag.ads:
                all_headlines.extend(ad.headlines)
                all_descriptions.extend(ad.descriptions)

        headlines_str = " ".join(all_headlines)
        descriptions_str = " ".join(all_descriptions)

        # Forbidden contractor claims
        for bad in ["Licensed & Bonded Pros", "24/7 Emergency Service", "Free On-Site Estimates", "Decades of Experience"]:
            self.assertNotIn(bad, headlines_str)
            self.assertNotIn(bad, descriptions_str)

        # Polish language neutral defaults present
        self.assertIn("Oficjalna Strona", headlines_str)
        self.assertIn("Poznaj Nasza Oferte", headlines_str)

    def test_positive_fixture_complete_approved_export(self):
        """Complete approved evidence produces verified MD, HTML, and paused CSV."""
        cdir = self.tmp_root / "workspace" / "clients" / "apex-solar"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "profile.json").write_text(json.dumps(self.valid_profile), encoding="utf-8")
        for k, v in self.complete_deliverables.items():
            (cdir / f"{k}.md").write_text(v, encoding="utf-8")

        v = self._create_valid_verified_prospect()
        self.gate.create_or_update(v)
        self.gate.verify_prospect_for_export(
            "apex-solar",
            reviewer="auditor_lead",
            profile=self.valid_profile,
            deliverables=self.complete_deliverables,
        )

        res = client_reporter.compile_and_export_client_package("apex-solar", root=self.tmp_root)
        self.assertTrue(res["success"])
        self.assertFalse(res["is_draft"])
        self.assertEqual(res["verification_status"], "verified")

        # Verify dossier has confidential report tag and no draft/sample warnings
        md_text = Path(res["dossier_md_path"]).read_text(encoding="utf-8")
        self.assertIn("# Executive Strategy & Distribution Audit: Apex Solar Solutions", md_text)
        self.assertIn("Confidential Client Report", md_text)
        self.assertNotIn("[INTERNAL DRAFT]", md_text)
        self.assertNotIn("[SAMPLE]", md_text)

        # Verify CSV has Status: Paused and no sample prefix
        csv_text = Path(res["csv_path"]).read_text(encoding="utf-8")
        self.assertNotIn("SAMPLE_", csv_text)
        self.assertNotIn("[DRAFT]", csv_text)
        lines = [l for l in csv_text.splitlines() if l.strip() and not l.startswith("#")]
        reader = list(csv.reader(lines))
        status_idx = reader[0].index("Status")
        for row in reader[1:]:
            self.assertEqual(row[status_idx], "Paused")


if __name__ == "__main__":
    unittest.main()

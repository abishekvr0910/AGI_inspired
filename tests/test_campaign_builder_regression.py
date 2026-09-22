"""Regression tests for campaign_builder.py fixes (forbidden claims, headline count, export gate)."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
TESTS = ROOT / "tests"
for p in (ROOT, ORCH, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import campaign_builder


class CampaignBuilderRegressionTests(unittest.TestCase):
    """Tests that verify the campaign_builder fixes work correctly."""

    def setUp(self) -> None:
        self.profile = {
            "client_id": "test-client",
            "display_name": "Test Company",
            "domain": "test domain",
            "geo": ["US", "Test City"],
            "language": ["en"],
            "offer": "Test offer",
            "audience": "Test audience",
            "competitors": ["https://competitor.example"],
            "brand_voice": "Professional",
            "landing_url": "https://test.example",
            "seed_keywords": ["test keyword"],
            "forbidden_claims": ["certified", "insured", "guaranteed", "satisfaction guaranteed"],
        }
        self.keywords = [
            {"keyword": "test service", "theme": "test", "intent": "commercial"},
            {"keyword": "best test service", "theme": "test", "intent": "commercial"},
        ]

    def test_forbidden_claims_filtered_from_defaults(self):
        """Default headlines/descriptions with forbidden claims are filtered out."""
        campaign = campaign_builder.build_campaign_from_research(
            client_profile=self.profile,
            keywords=self.keywords,
            verified_for_export=True,
        )
        
        # Check that no forbidden claims appear in any ad
        for ag in campaign.ad_groups:
            for ad in ag.ads:
                for h in ad.headlines:
                    h_lower = h.lower()
                    self.assertNotIn("certified", h_lower)
                    self.assertNotIn("insured", h_lower)
                    self.assertNotIn("guaranteed", h_lower)
                    self.assertNotIn("satisfaction guaranteed", h_lower)
                for d in ad.descriptions:
                    d_lower = d.lower()
                    self.assertNotIn("certified", d_lower)
                    self.assertNotIn("insured", d_lower)
                    self.assertNotIn("guaranteed", d_lower)
                    self.assertNotIn("satisfaction guaranteed", d_lower)

    def test_forbidden_claims_filtered_from_custom_ad_copies(self):
        """Custom ad copies with forbidden claims are filtered out."""
        custom_ad_copies = [{
            "headlines": [
                "Test Company",
                "Certified & Insured Pros",  # Should be filtered
                "Guaranteed Results",         # Should be filtered
            ],
            "descriptions": [
                "Satisfaction guaranteed on every project.",  # Should be filtered
                "Quality service you can trust.",
            ],
        }]
        
        campaign = campaign_builder.build_campaign_from_research(
            client_profile=self.profile,
            keywords=self.keywords,
            ad_copies=custom_ad_copies,
            verified_for_export=True,
        )
        
        for ag in campaign.ad_groups:
            for ad in ag.ads:
                for h in ad.headlines:
                    h_lower = h.lower()
                    self.assertNotIn("certified", h_lower)
                    self.assertNotIn("insured", h_lower)
                    self.assertNotIn("guaranteed", h_lower)
                for d in ad.descriptions:
                    d_lower = d.lower()
                    self.assertNotIn("satisfaction guaranteed", d_lower)

    def test_headline_count_reaches_15(self):
        """Campaign generates 15 headlines for Excellent Ad Strength."""
        campaign = campaign_builder.build_campaign_from_research(
            client_profile=self.profile,
            keywords=self.keywords,
            verified_for_export=True,
        )
        
        for ag in campaign.ad_groups:
            for ad in ag.ads:
                # Should have 15 headlines (MAX_RSA_HEADLINES)
                self.assertEqual(len(ad.headlines), 15, f"Expected 15 headlines, got {len(ad.headlines)}: {ad.headlines}")
                # Should have 4 descriptions (MAX_RSA_DESCRIPTIONS)
                self.assertEqual(len(ad.descriptions), 4)

    def test_csv_export_has_15_headline_columns(self):
        """CSV export has 15 headline columns and 4 description columns."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_path = tmp / "test_campaign.csv"
            
            campaign = campaign_builder.build_campaign_from_research(
                client_profile=self.profile,
                keywords=self.keywords,
                verified_for_export=True,
            )
            campaign_builder.export_google_ads_editor_csv(campaign, csv_path)
            
            # Read CSV and verify headers
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)
            
            # Verify headline columns
            headline_cols = [h for h in headers if h.startswith("Headline")]
            self.assertEqual(len(headline_cols), 15, f"Expected 15 Headline columns, got {len(headline_cols)}: {headline_cols}")
            
            # Verify description columns
            desc_cols = [h for h in headers if h.startswith("Description")]
            self.assertEqual(len(desc_cols), 4, f"Expected 4 Description columns, got {len(desc_cols)}: {desc_cols}")

    def test_sample_campaign_has_sample_prefix(self):
        """Non-verified campaigns get SAMPLE_ prefix in CSV."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_path = tmp / "test_campaign.csv"
            
            campaign = campaign_builder.build_campaign_from_research(
                client_profile=self.profile,
                keywords=self.keywords,
                verified_for_export=False,  # Sample mode
            )
            campaign_builder.export_google_ads_editor_csv(campaign, csv_path)
            
            csv_text = csv_path.read_text(encoding="utf-8")
            # Should have SAMPLE_ prefix
            self.assertIn("SAMPLE_", csv_text)
            # Should have warning comment row
            self.assertIn("SAMPLE CAMPAIGN - NOT VERIFIED FOR CLIENT USE", csv_text)

    def test_verified_campaign_no_sample_prefix(self):
        """Verified campaigns do NOT get SAMPLE_ prefix."""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            csv_path = tmp / "test_campaign.csv"
            
            campaign = campaign_builder.build_campaign_from_research(
                client_profile=self.profile,
                keywords=self.keywords,
                verified_for_export=True,
            )
            campaign_builder.export_google_ads_editor_csv(campaign, csv_path)
            
            csv_text = csv_path.read_text(encoding="utf-8")
            # Should NOT have SAMPLE_ prefix
            self.assertNotIn("SAMPLE_", csv_text)
            # Should NOT have warning comment row
            self.assertNotIn("SAMPLE CAMPAIGN", csv_text)

    def test_filter_forbidden_claims_function(self):
        """filter_forbidden_claims correctly filters headlines and descriptions."""
        headlines = [
            "Test Company",
            "Certified & Insured Pros",
            "Guaranteed Results",
            "Transparent Pricing",
        ]
        descriptions = [
            "Satisfaction guaranteed on every project.",
            "Quality service you can trust.",
            "100% money back guarantee.",
        ]
        
        clean_h, clean_d = campaign_builder.filter_forbidden_claims(
            headlines, descriptions, ["certified", "insured", "guaranteed"]
        )
        
        # "Test Company" and "Transparent Pricing" should remain
        self.assertIn("Test Company", clean_h)
        self.assertIn("Transparent Pricing", clean_h)
        # Forbidden ones should be removed
        self.assertNotIn("Certified & Insured Pros", clean_h)
        self.assertNotIn("Guaranteed Results", clean_h)
        
        # Descriptions
        self.assertIn("Quality service you can trust.", clean_d)
        self.assertNotIn("Satisfaction guaranteed on every project.", clean_d)
        self.assertNotIn("100% money back guarantee.", clean_d)


class EvidenceGateTests(unittest.TestCase):
    """Tests for the commercial evidence gate."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_root = Path(self._tmp.name)
        sys.path.insert(0, str(ORCH))
        import evidence_gate
        self.gate = evidence_gate.EvidenceGate(root=self.tmp_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sample_verification_blocks_export(self):
        """SAMPLE status verifications block export."""
        from evidence_gate import create_sample_verification
        v = create_sample_verification("test-client", "Test Company")
        self.gate.create_or_update(v)
        
        can_export, reason = self.gate.can_export_prospect("test-client")
        self.assertFalse(can_export)
        self.assertIn("Sample material", reason)

    def test_unverified_verification_blocks_export(self):
        """UNVERIFIED status blocks export."""
        from evidence_gate import ProspectVerification, VerificationStatus
        v = ProspectVerification(client_id="test-client", company_name="Test Company", status=VerificationStatus.UNVERIFIED)
        self.gate.create_or_update(v)
        
        can_export, reason = self.gate.can_export_prospect("test-client")
        self.assertFalse(can_export)
        self.assertIn("Unverified prospect", reason)

    def test_verified_with_evidence_allows_export(self):
        """VERIFIED status with all required evidence and approval allows export."""
        from evidence_gate import ProspectVerification, VerificationStatus, EvidenceRecord, ClaimType
        from datetime import datetime
        
        v = ProspectVerification(
            client_id="test-client",
            company_name="Test Company",
            status=VerificationStatus.VERIFIED,
            approved_for_export=True,
        )
        # Add required evidence
        now = datetime.utcnow().isoformat() + "Z"
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.CONTACT,
            claim_value="contact_name",
            source="operator_provided",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.CONTACT,
            claim_value="contact_email",
            source="operator_provided",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.CONTACT,
            claim_value="contact_role",
            source="operator_provided",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.COMPANY,
            claim_value="company_name",
            source="operator_provided",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.COMPANY,
            claim_value="website",
            source="operator_provided",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.COMPANY,
            claim_value="city",
            source="operator_provided",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        v.add_evidence(EvidenceRecord(
            claim_type=ClaimType.WASTE_ESTIMATE,
            claim_value="est_monthly_leak",
            source="authorized_account_export",
            source_date=now,
            reviewer="operator",
            reviewer_date=now,
            verified=True,
        ))
        self.gate.create_or_update(v)
        
        can_export, reason = self.gate.can_export_prospect("test-client")
        self.assertTrue(can_export)
        self.assertIsNone(reason)

    def test_missing_evidence_blocks_export(self):
        """VERIFIED status but missing required evidence blocks export."""
        from evidence_gate import ProspectVerification, VerificationStatus
        v = ProspectVerification(
            client_id="test-client",
            company_name="Test Company",
            status=VerificationStatus.VERIFIED,
            approved_for_export=True,
        )
        self.gate.create_or_update(v)
        
        can_export, reason = self.gate.can_export_prospect("test-client")
        self.assertFalse(can_export)
        self.assertIn("Missing verified evidence", reason)

    def test_relabel_all_as_samples(self):
        """relabel_all_as_samples marks all verifications as SAMPLE."""
        from evidence_gate import create_sample_verification, ProspectVerification, VerificationStatus
        
        # Create mix of statuses
        v1 = create_sample_verification("client1", "Client 1")
        v2 = ProspectVerification(client_id="client2", company_name="Client 2", status=VerificationStatus.UNVERIFIED)
        v3 = ProspectVerification(client_id="client3", company_name="Client 3", status=VerificationStatus.VERIFIED, approved_for_export=True)
        
        self.gate.create_or_update(v1)
        self.gate.create_or_update(v2)
        self.gate.create_or_update(v3)
        
        count = self.gate.relabel_all_as_samples()
        self.assertEqual(count, 2)  # v2 and v3 changed
        
        # All should now be SAMPLE
        for cid in ["client1", "client2", "client3"]:
            v = self.gate.get(cid)
            self.assertEqual(v.status, VerificationStatus.SAMPLE)
            self.assertFalse(v.approved_for_export)


if __name__ == "__main__":
    unittest.main()
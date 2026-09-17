"""Distribution Engine Phase 2 Unit Test Suite.

Validates:
1. negative_keyword_harvest template function (arms preflight, match types, categories, waste rationale).
2. audience_pain_point_research template function (arms preflight, emotional triggers, ad hooks, proof).
3. campaign_builder structure compiler (STAG ad groups, Exact/Phrase match pairs, RSA ads, negatives).
4. campaign_builder JSON and Google Ads Editor CSV exporters.
5. CLI distribution integration across all 7 research templates.
6. Zero-spend 3-probe containment invariant.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re
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

from research_templates import (
    generate_negative_keyword_harvest_task,
    generate_audience_pain_point_research_task,
)
import campaign_builder
import distribution

SAMPLE_PROFILE = {
    "client_id": "apex-roofing",
    "display_name": "Apex Commercial Roofing",
    "domain": "commercial roofing",
    "geo": ["US", "Austin-TX"],
    "language": ["en"],
    "offer": "Commercial TPO and metal roof replacement and preventive maintenance",
    "audience": "Facility managers and commercial property owners in Central Texas",
    "competitors": ["https://austin-roof-pros.example", "https://central-tx-roofing.example"],
    "brand_voice": "Authoritative, technical, transparent, dependable",
    "landing_url": "https://apex-commercial-roofing.example/services",
    "seed_keywords": ["commercial roofing austin", "tpo roof replacement", "commercial roof repair"],
    "forbidden_claims": ["cheapest roofer in Texas", "100% free lifetime warranty"],
}


class DistributionPhase2Tests(unittest.TestCase):
    def test_negative_keyword_harvest_template(self):
        """negative_keyword_harvest generates spec and criteria arming negative exclusion checks."""
        spec, criteria = generate_negative_keyword_harvest_task(
            SAMPLE_PROFILE,
            seed_input={
                "target_keyword": "tpo commercial roofing",
                "excluded_services": ["residential shingle repair", "diy roof patches"],
            },
        )

        # Spec assertions
        self.assertIn("Apex Commercial Roofing", spec)
        self.assertIn("apex-roofing", spec)
        self.assertIn("tpo commercial roofing", spec)
        self.assertIn("residential shingle repair", spec)
        self.assertIn("diy roof patches", spec)
        self.assertIn("irrelevant_intent", spec)
        self.assertIn("career_or_education", spec)
        self.assertIn("out_of_scope_service", spec)
        self.assertIn("competitor_brand", spec)

        # Criteria assertions
        self.assertIn("| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |", criteria)
        self.assertIn("Match type must be one of: exact, phrase, broad.", criteria)
        self.assertIn("Category must be one of: irrelevant_intent, career_or_education, out_of_scope_service, competitor_brand.", criteria)
        self.assertIn("At least 2 distinct independent sources cited.", criteria)
        self.assertIn("### Sources Attempted", criteria)
        self.assertIn("not publicly disclosed", criteria)
        self.assertIn("cheapest roofer in Texas", criteria)

    def test_audience_pain_point_research_template(self):
        """audience_pain_point_research generates spec and criteria arming pain point & ad hook checks."""
        spec, criteria = generate_audience_pain_point_research_task(
            SAMPLE_PROFILE,
            seed_input={"target_keyword": "commercial roof maintenance"},
        )

        # Spec assertions
        self.assertIn("Apex Commercial Roofing", spec)
        self.assertIn("commercial roof maintenance", spec)
        self.assertIn("Facility managers and commercial property owners", spec)
        self.assertIn("Authoritative, technical, transparent, dependable", spec)
        self.assertIn("https://austin-roof-pros.example", spec)

        # Criteria assertions
        self.assertIn("| Pain Point / Objection | Emotional Trigger | Recommended Ad Hook | Proof Required | Source URL |", criteria)
        self.assertIn("At least 2 distinct independent sources cited.", criteria)
        self.assertIn("### Sources Attempted", criteria)
        self.assertIn("not publicly disclosed", criteria)
        self.assertIn("No unsubstantiated superlative claims", criteria)
        self.assertIn("100% free lifetime warranty", criteria)

    def test_campaign_builder_structure(self):
        """build_campaign_from_research compiles positive/negative research into STAGs and RSAs."""
        keywords_data = [
            {"keyword": "commercial tpo roofing", "intent": "commercial", "theme": "TPO Roofing"},
            {"keyword": "flat roof repair austin", "intent": "transactional", "theme": "Flat Roof Repair"},
        ]
        ad_copies = [
            {
                "headlines": ["Apex Commercial Roofing", "TPO Roofing Specialists", "Call For Fast Inspection"],
                "descriptions": ["Austin's certified commercial roofing contractors. 20-year warranty on all TPO installations."],
                "landing_url": "https://apex-commercial-roofing.example/services",
            }
        ]
        negatives_data = [
            {"keyword": "free roofing", "match_type": "Exact"},
            {"keyword": "diy roof repair", "match_type": "Phrase"},
            {"keyword": "jobs", "match_type": "Broad"},
        ]

        campaign = campaign_builder.build_campaign_from_research(
            SAMPLE_PROFILE,
            keywords=keywords_data,
            ad_copies=ad_copies,
            negatives=negatives_data,
            daily_budget=75.0,
        )

        self.assertEqual(campaign.client_id, "apex-roofing")
        self.assertEqual(campaign.daily_budget, 75.0)
        self.assertEqual(len(campaign.campaign_negatives), 3)

        # Check negative formatting
        formatted_negs = [n.formatted_text() for n in campaign.campaign_negatives]
        self.assertIn("[free roofing]", formatted_negs)
        self.assertIn('"diy roof repair"', formatted_negs)
        self.assertIn("jobs", formatted_negs)

        # Check Ad Groups
        self.assertEqual(len(campaign.ad_groups), 2)
        ag_names = [ag.name for ag in campaign.ad_groups]
        self.assertIn("Tpo Roofing", ag_names)
        self.assertIn("Flat Roof Repair", ag_names)

        # Check positive keywords within Ad Group (both Exact and Phrase generated)
        tpo_ag = next(ag for ag in campaign.ad_groups if ag.name == "Tpo Roofing")
        kw_formatted = [k.formatted_text() for k in tpo_ag.keywords]
        self.assertIn("[commercial tpo roofing]", kw_formatted)
        self.assertIn('"commercial tpo roofing"', kw_formatted)

        # Check RSA ad attachment
        self.assertEqual(len(tpo_ag.ads), 1)
        rsa = tpo_ag.ads[0]
        self.assertEqual(rsa.validate(), [])  # No validation errors
        self.assertIn("Apex Commercial Roofing", rsa.headlines)
        self.assertIn("TPO Roofing Specialists", rsa.headlines)

    def test_campaign_builder_exporters(self):
        """campaign_builder exports valid JSON and Google Ads Editor bulk CSV."""
        keywords_data = [
            {"keyword": "commercial roof coatings", "theme": "Roof Coatings"},
        ]
        negatives_data = [
            {"keyword": "cheap", "match_type": "Phrase"},
        ]

        campaign = campaign_builder.build_campaign_from_research(
            SAMPLE_PROFILE,
            keywords=keywords_data,
            negatives=negatives_data,
        )

        with tempfile.TemporaryDirectory() as td:
            temp_root = Path(td)
            json_path = temp_root / "campaign.json"
            csv_path = temp_root / "campaign_editor.csv"

            # 1. Test JSON export
            res_json = campaign_builder.export_campaign_json(campaign, json_path)
            self.assertTrue(res_json.is_file())
            data = json.loads(res_json.read_text(encoding="utf-8"))
            self.assertEqual(data["client_id"], "apex-roofing")
            self.assertEqual(data["stats"]["total_keywords"], 2)  # Exact + Phrase
            self.assertEqual(data["stats"]["total_negatives"], 1)

            # 2. Test Google Ads Editor CSV export
            res_csv = campaign_builder.export_google_ads_editor_csv(campaign, csv_path)
            self.assertTrue(res_csv.is_file())

            with open(res_csv, "r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)

            headers = rows[0]
            self.assertEqual(headers[0], "Campaign")
            self.assertEqual(headers[1], "Ad Group")
            self.assertEqual(headers[2], "Keyword")
            self.assertEqual(headers[3], "Criterion Type")

            # Check campaign negative row
            neg_row = next(r for r in rows[1:] if "cheap" in r[2])
            self.assertEqual(neg_row[1], "")  # Empty ad group for campaign-level negative
            self.assertEqual(neg_row[3], "Negative Phrase")

            # Check keyword rows
            kw_exact_row = next(r for r in rows[1:] if r[2] == "commercial roof coatings" and r[3] == "Exact")
            self.assertEqual(kw_exact_row[1], "Roof Coatings")

            # Check RSA ad row
            ad_row = next(r for r in rows[1:] if r[1] == "Roof Coatings" and r[2] == "")
            self.assertIn("Apex Commercial Roofing", ad_row[4])  # Headline 1

    def test_distribution_cli_all_seven_templates(self):
        """distribution.py TEMPLATES contains all 7 templates and dry-run dispatches cleanly."""
        self.assertEqual(len(distribution.TEMPLATES), 7)
        expected = [
            "keyword_research",
            "competitive_serp",
            "ad_copy_variants",
            "seo_content_brief",
            "landing_page_recco",
            "negative_keyword_harvest",
            "audience_pain_point_research",
        ]
        for name in expected:
            self.assertIn(name, distribution.TEMPLATES)

        # Test dry-run dispatch for both new Phase 2 templates
        with patch("client_profile.load_client_profile", return_value=SAMPLE_PROFILE):
            res_neg = distribution.dispatch_distribution_task(
                "apex-roofing",
                "negative_keyword_harvest",
                dry_run=True,
            )
            self.assertTrue(res_neg["dry_run"])
            self.assertIn("Budget Waste Rationale", res_neg["pass_criteria"])

            res_pain = distribution.dispatch_distribution_task(
                "apex-roofing",
                "audience_pain_point_research",
                dry_run=True,
            )
            self.assertTrue(res_pain["dry_run"])
            self.assertIn("Recommended Ad Hook", res_pain["pass_criteria"])

    def test_zero_spend_containment_three_probes(self):
        """Phase 2 components satisfy zero-spend 3-probe containment invariant."""
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

        files_to_check = [
            ROOT / "orchestrator" / "campaign_builder.py",
            ROOT / "orchestrator" / "research_templates" / "negative_keyword_harvest.py",
            ROOT / "orchestrator" / "research_templates" / "audience_pain_point_research.py",
        ]

        for f in files_to_check:
            content = f.read_text(encoding="utf-8")
            self.assertIsNone(sdk_pattern.search(content), f"Probe 1 violation in {f.name}")
            self.assertIsNone(mutate_pattern.search(content), f"Probe 2 violation in {f.name}")

        egress_yaml = (ROOT / "config" / "egress_policy.yaml").read_text(encoding="utf-8")
        ad_host_keywords = ["googleads", "ads.google", "bingads", "ads.yahoo", "ads.tiktok", "adservice"]
        for kw in ad_host_keywords:
            self.assertNotIn(kw, egress_yaml, f"Probe 3 violation: {kw} in egress policy")


if __name__ == "__main__":
    unittest.main()

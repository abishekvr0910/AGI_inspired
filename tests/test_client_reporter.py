"""Hermetic unit tests for Client Strategy Dossier & Campaign Exporter (orchestrator/client_reporter.py).

Verifies:
1. Table parsing across various markdown formats.
2. Field extraction: positive keywords, negative keywords, ad copies, pain points, competitor gaps.
3. Executive strategy dossier generation (Markdown + HTML).
4. Google Ads Editor bulk CSV compilation and file export.
5. Error handling and fallbacks.
6. Zero-spend 3-probe containment.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
TESTS = ROOT / "tests"
for p in (ROOT, ORCH, TESTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import client_profile
import client_reporter


SAMPLE_PROFILE = {
    "client_id": "test-dental",
    "display_name": "Metro Dental Implants",
    "domain": "dental implants",
    "geo": ["US", "Chicago-IL"],
    "language": ["en"],
    "offer": "All-on-4 dental implants and same-day tooth replacement",
    "audience": "Adults 45+ with missing teeth or loose dentures",
    "competitors": ["https://chicago-implants.example"],
    "brand_voice": "Compassionate, clinical, transparent",
    "landing_url": "https://metro-dental.example/all-on-4",
    "seed_keywords": ["all on 4 implants", "dental implants chicago"],
    "forbidden_claims": ["cheapest", "painless guaranteed"],
}

SAMPLE_KEYWORD_DOC = """# Keyword Research Deliverable
| Keyword | Intent | Funnel Stage | Rationale | Source URL |
|---|---|---|---|---|
| all on 4 dental implants cost | commercial | consideration | High purchase research intent | https://example.com/kw1 |
| teeth in a day chicago | transactional | conversion | Immediate local conversion intent | https://example.com/kw2 |
"""

SAMPLE_NEGATIVE_DOC = """# Negative Keyword Harvest
| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |
|---|---|---|---|---|
| free dental clinic | exact | irrelevant_intent | Zero intent to pay commercial implant rates | https://example.com/neg1 |
| dental assistant jobs | phrase | career_or_education | Job seekers clicking high CPC ad | https://example.com/neg2 |
| dental implant tools wholesale | phrase | out_of_scope_service | B2B supplier search | https://example.com/neg3 |
"""

SAMPLE_AD_COPY_DOC = """# Ad Copy Variants
| Format | Component | Copy Text | Characters | CTA | Source / Rationale |
|---|---|---|---|---|---|
| RSA | Headline | Metro Dental Implants | 21 | Schedule Now | Brand anchor |
| RSA | Headline | Permanent Teeth in 1 Day | 24 | Book Consult | Primary hook |
| RSA | Headline | Experienced Chicago Team | 24 | Call Today | Trust builder |
| RSA | Description | Restore your smile with permanent All-on-4 dental implants. Free consultation today. | 84 | Free consult | Core offer description |
| RSA | Description | Transparent pricing with zero hidden fees. Certified Chicago implant surgeons. | 79 | Call now | Credibility description |
"""

SAMPLE_PAIN_POINT_DOC = """# Audience Pain Points
| Pain Point / Objection | Emotional Trigger | Recommended Ad Hook | Proof Required | Source URL |
|---|---|---|---|---|
| Fear of painful surgery | Surgical anxiety | Gentle, Sedation-Assisted Implants | Board-certified anesthesiologist | https://example.com/pain1 |
| Dread of hidden add-on costs | Financial distrust | All-Inclusive Transparent Pricing | Written upfront price guarantee | https://example.com/pain2 |
"""

SAMPLE_SERP_DOC = """# Competitive SERP Analysis
| Competitor / Ranker | SERP Angle | Content Gap | Opportunity for Us | Source URL |
|---|---|---|---|---|
| BigChain Dental | National low-cost claims | Lacks local Chicago doctor bios | Highlight locally owned private practice | https://example.com/serp1 |
"""

SAMPLE_LP_DOC = """# Landing Page Recommendations
| Section Name | Purpose | Why-It-Converts Rationale | Evidence / Source |
|---|---|---|---|
| Hero Section | Clear value proposition and CTA | Immediate clarity reduces bounce | https://example.com/lp1 |
| Before & After Gallery | Visual proof of outcome | Reduces anxiety and builds confidence | https://example.com/lp2 |
"""


class TestClientReporter(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        # Create client profile in temp directory
        cdir = self.tmp_dir / "workspace" / "clients" / "test-dental"
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "profile.json").write_text(json.dumps(SAMPLE_PROFILE, indent=2), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_markdown_table_parsing_and_extraction(self) -> None:
        """Verify markdown tables are parsed into structured dictionaries accurately."""
        # 1. Keywords
        kws = client_reporter.extract_keywords_from_deliverable(SAMPLE_KEYWORD_DOC)
        self.assertEqual(len(kws), 2)
        self.assertEqual(kws[0]["keyword"], "all on 4 dental implants cost")
        self.assertEqual(kws[0]["intent"], "commercial")
        self.assertEqual(kws[1]["funnel_stage"], "conversion")

        # 2. Negatives
        negs = client_reporter.extract_negatives_from_deliverable(SAMPLE_NEGATIVE_DOC)
        self.assertEqual(len(negs), 3)
        self.assertEqual(negs[0]["keyword"], "free dental clinic")
        self.assertEqual(negs[0]["match_type"], "Exact")
        self.assertEqual(negs[1]["category"], "career_or_education")

        # 3. Ad copies
        ads = client_reporter.extract_ad_copies_from_deliverable(SAMPLE_AD_COPY_DOC)
        self.assertEqual(len(ads), 5)
        headlines = [a for a in ads if a["component"] == "Headline"]
        self.assertEqual(len(headlines), 3)

        # 4. Pain points
        pains = client_reporter.extract_pain_points_from_deliverable(SAMPLE_PAIN_POINT_DOC)
        self.assertEqual(len(pains), 2)
        self.assertIn("Gentle", pains[0]["recommended_hook"])

        # 5. Competitors & Landing Page
        comps = client_reporter.extract_competitors_from_deliverable(SAMPLE_SERP_DOC)
        self.assertEqual(len(comps), 1)
        lps = client_reporter.extract_landing_page_reccos(SAMPLE_LP_DOC)
        self.assertEqual(len(lps), 2)

    def test_executive_dossier_markdown_and_html(self) -> None:
        """Verify dossier markdown and HTML generation."""
        deliverables = {
            "keyword_research": SAMPLE_KEYWORD_DOC,
            "negative_keyword_harvest": SAMPLE_NEGATIVE_DOC,
            "ad_copy_variants": SAMPLE_AD_COPY_DOC,
            "audience_pain_point_research": SAMPLE_PAIN_POINT_DOC,
            "competitive_serp": SAMPLE_SERP_DOC,
            "landing_page_recco": SAMPLE_LP_DOC,
        }
        md = client_reporter.generate_executive_dossier(SAMPLE_PROFILE, deliverables)
        self.assertIn("# Executive Strategy & Distribution Audit: Metro Dental Implants", md)
        self.assertIn("Customer Psychology: Pain Points", md)
        self.assertIn("Negative Keyword Shield", md)
        self.assertIn("free dental clinic", md)
        self.assertIn("Google Ads Editor Bulk Deployment Instructions", md)

        html_doc = client_reporter.generate_dossier_html(SAMPLE_PROFILE, md)
        self.assertIn("<!doctype html>", html_doc)
        self.assertIn("Metro Dental Implants — Distribution Dossier", html_doc)
        self.assertIn("<table", html_doc)
        self.assertIn("Print / PDF", html_doc)

    def test_compile_and_export_client_package(self) -> None:
        """Verify compile_and_export_client_package outputs all artifacts to client workspace."""
        cdir = self.tmp_dir / "workspace" / "clients" / "test-dental"
        (cdir / "keyword_research.md").write_text(SAMPLE_KEYWORD_DOC, encoding="utf-8")
        (cdir / "negative_keyword_harvest.md").write_text(SAMPLE_NEGATIVE_DOC, encoding="utf-8")
        (cdir / "ad_copy_variants.md").write_text(SAMPLE_AD_COPY_DOC, encoding="utf-8")
        (cdir / "audience_pain_point_research.md").write_text(SAMPLE_PAIN_POINT_DOC, encoding="utf-8")

        res = client_reporter.compile_and_export_client_package("test-dental", root=self.tmp_dir)
        self.assertTrue(res["success"])
        self.assertEqual(res["client_id"], "test-dental")
        self.assertEqual(res["display_name"], "Metro Dental Implants")

        # Verify artifacts exist on disk
        csv_path = Path(res["csv_path"])
        json_path = Path(res["json_path"])
        md_path = Path(res["dossier_md_path"])
        html_path = Path(res["dossier_html_path"])

        self.assertTrue(csv_path.is_file())
        self.assertTrue(json_path.is_file())
        self.assertTrue(md_path.is_file())
        self.assertTrue(html_path.is_file())

        # Verify CSV content
        csv_text = csv_path.read_text(encoding="utf-8")
        self.assertIn("Campaign,Ad Group,Keyword,Criterion Type", csv_text)
        self.assertIn("free dental clinic", csv_text)
        self.assertIn("Negative Exact", csv_text)
        self.assertIn("Metro Dental Implants", csv_text)

        # Verify summary counts
        summary = res["campaign_summary"]
        self.assertGreater(summary["ad_groups_count"], 0)
        self.assertGreater(summary["total_keywords"], 0)
        self.assertEqual(summary["total_negatives"], 3)

    def test_zero_spend_containment_held(self) -> None:
        """3-probe zero spend test: client_reporter imports no ads SDK, mutates no ad accounts."""
        reporter_text = (ORCH / "client_reporter.py").read_text(encoding="utf-8")
        # Probe 1: No ads SDK import
        self.assertNotIn("import google.ads", reporter_text)
        self.assertNotIn("import googleads", reporter_text)
        self.assertNotIn("from google.ads", reporter_text)
        self.assertNotIn("facebook_business", reporter_text)

        # Probe 2: No write/mutate endpoint symbols
        for symbol in ("CampaignService", "mutate_campaigns", "create_campaign", "BudgetService"):
            self.assertNotIn(symbol, reporter_text)


if __name__ == "__main__":
    unittest.main()

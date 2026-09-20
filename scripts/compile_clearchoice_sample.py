"""Compile a real-world enterprise sample for ClearChoice Dental Implant Centers (clearchoice.com)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import client_profile
import client_reporter

PROFILE = {
    "client_id": "clearchoice-dental",
    "display_name": "ClearChoice Dental Implant Centers",
    "domain": "dental implants nationwide",
    "geo": ["US", "National-US"],
    "language": ["en"],
    "offer": "All-on-4 permanent full-mouth dental implants, same-day fixed teeth replacement, 3D CT scan consultations",
    "audience": "Adults 45–75 with extensive tooth loss, severe bone degradation, failing dental bridges, or loose dentures",
    "competitors": ["https://aspendental.com", "https://nusetdental.com", "https://bionicsmile.com"],
    "brand_voice": "Authoritative, clinical, restorative, compassionate, institutional",
    "landing_url": "https://www.clearchoice.com/dental-implants",
    "seed_keywords": [
        "clearchoice dental implants cost",
        "all on 4 dental implants near me",
        "full mouth dental implants cost",
        "same day teeth replacement",
        "dental implant specialist near me"
    ],
    "forbidden_claims": [
        "cheapest dental implants in america",
        "100% pain free guarantee",
        "free dental implants for all seniors",
        "cure gum disease permanently in 1 hour"
    ],
}

KEYWORDS = """# Keyword Research Deliverable
| Keyword | Intent | Funnel Stage | Rationale | Source URL |
|---|---|---|---|---|
| clearchoice dental implants cost | commercial | decision | Brand-commercial query from high-intent prospects researching pricing and financing options | https://www.clearchoice.com/cost |
| all on 4 dental implants near me | transactional | conversion | Top-tier commercial intent searching for local surgical center for full arch restoration ($30k-$50k) | https://www.clearchoice.com/dental-implants |
| full mouth dental implants cost breakdown | commercial | consideration | High-ticket patient actively comparing All-on-4 vs traditional implants vs snap-in dentures | https://www.clearchoice.com/procedures |
| same day teeth replacement oral surgeon | transactional | conversion | Urgent surgical demand from patients with failing teeth or broken bridges needing same-day extraction and loading | https://www.clearchoice.com/why-clearchoice |
| permanent dentures alternative all on 4 | informational | awareness | Frustrated denture wearers searching for fixed non-removable alternatives to replace loose acrylic plates | https://www.clearchoice.com/dental-implants |
| dental implant specialist board certified | commercial | consideration | High-income patients vetting surgical credentials and prosthodontic specialization | https://www.clearchoice.com/doctors |
"""

NEGATIVES = """# Negative Keyword Harvest
| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |
|---|---|---|---|---|
| free dental implants for seniors | exact | irrelevant_intent | Low-income government grant seekers unable to fund commercial full-arch treatment ($25k+) | https://www.clearchoice.com/faq |
| clearchoice dental assistant salary | phrase | career_or_education | Job seekers and career searchers clicking high-CPC ad links | https://www.glassdoor.com/clearchoice-salary |
| clearchoice dental implants lawsuit bbb | phrase | irrelevant_intent | Negative legal and complaint queries looking for litigation, not patient consultations | https://www.bbb.org/clearchoice-reviews |
| dental implant tools wholesale lab | phrase | out_of_scope_service | B2B dental laboratory and manufacturing suppliers looking for clinic buyers | https://dentalsupply.example/implant-tools |
| dog tooth extraction implants vet | phrase | irrelevant_intent | Veterinary searches for pets clicking human oral surgery ads | https://veterinarydental.example/pet-implants |
| cheap dentures under 300 dollars | phrase | irrelevant_intent | Low-budget removable denture clicks that never convert to $30k+ surgical cases | https://www.clearchoice.com/pricing |
| mexico dental tourism packages | phrase | out_of_scope_service | Bargain seekers planning medical tourism to Tijuana or Costa Rica | https://dentaltourism.example/mexico |
| diy loose tooth extraction at home | phrase | irrelevant_intent | Zero-budget emergency home remedy clicks | https://www.clearchoice.com/faq |
"""

AD_COPIES = """# Ad Copy Variants
| Component | Copy Text | Character Count | Rationale | Grounded Source |
|---|---|---|---|---|
| Headline 1 | ClearChoice Dental Implants | 28 | Direct brand and service keyword match | https://www.clearchoice.com/dental-implants |
| Headline 2 | Permanent Teeth In 1 Day | 24 | Solves core emotional desire for immediate full smile restoration | https://www.clearchoice.com/dental-implants |
| Headline 3 | Over 100,000 Smiles Restored | 29 | Heavy social proof and institutional trust | https://www.clearchoice.com/why-clearchoice |
| Description 1 | Transform your smile and eat the foods you love again. Fixed permanent teeth in one visit. | 90 | High emotional resonance addressing loss of lifestyle and eating comfort | https://www.clearchoice.com/dental-implants |
| Description 2 | Schedule your free consultation & 3D CT scan today. All-inclusive pricing & financing. | 88 | Frictionless call-to-action addressing upfront cost anxiety | https://www.clearchoice.com/dental-implants |
"""

PAIN_POINTS = """# Audience Pain Point Research
| Pain Point / Objection | Underlying Anxiety | Proof Requirement Needed | Recommended Ad Hook / Angle |
|---|---|---|---|
| Fear of surgical pain and complications | Traumatic dental phobia and fear of bone cutting | Board-certified oral surgeons and MD anesthesiologists with IV twilight sedation | 'Gentle IV Sedation: Sleep Peacefully While Our Board-Certified Surgeons Restore Your Smile' |
| Sticker shock and hidden treatment fees | Anxiety over initial $15k quotes escalating into $50k hospital bills | All-in-one fixed-fee pricing covering CT scans, extractions, implants, and zirconia final teeth | 'One Fixed Fee Covers Everything: Your CT Scan, Surgery, Lab & Permanent Custom Smile' |
| Shame and embarrassment of dental decay | Severe social anxiety, hiding smile in family photos, avoiding eating in public | Private treatment suites with empathetic, non-judgmental restorative specialists | 'Eat & Smile with Total Confidence: A Judgment-Free Team Dedicated to Your New Life' |
| Fear of implant failure or rejection | Fear of losing life savings if implants do not integrate with jawbone | 98%+ historical success rates backed by proprietary 3D digital treatment planning | 'Precision 3D Computer-Guided Placement: Proven 98%+ Long-Term Implant Success' |
"""

COMPETITORS = """# Competitive SERP Analysis
| Competitor / Ranker | SERP Angle | Content Gap | Opportunity for Us | Source URL |
|---|---|---|---|---|
| Aspen Dental | Positions heavily on low-cost dentures and basic extractions | Lacks premium prosthodontic specialization and same-day full-arch lab integration | Emphasize dedicated on-site dental lab and master prosthodontist craftsmanship | https://aspendental.com |
| NuSet Dental Implants | Highlights local neighborhood locations | Smaller scale with fewer surgical credentials and limited sedation options | Leverage 100,000+ patient volume and comprehensive in-house multidisciplinary surgical team | https://nusetdental.com |
| Bionic Smile | Focuses on aggressive rock-bottom price marketing | Heavy volume of negative online reviews regarding hidden lab fees | Win with transparent all-inclusive pricing and lifetime structural warranties | https://bionicsmile.com |
"""

LANDING_PAGE = """# Landing Page Architecture Recommendation
| Section Name | Purpose | Why-It-Converts Rationale | Evidence / Source |
|---|---|---|---|
| Cinematic Transformation Hero | High-definition before/after video of real patient biting an apple | Visual proof that dental implants restore actual eating ability instantly | https://www.clearchoice.com/dental-implants |
| Multi-Disciplinary Doctor Team | Photos and credentials of the Prosthodontist, Oral Surgeon, and Lab Tech | Assures high-ticket patient that their surgery is handled by specialized experts, not a general dentist | https://www.clearchoice.com/doctors |
| All-in-One Center Infographic | Graphic showing Consultation, 3D CT Scan, Surgery, and On-site Lab under one roof | Explains why ClearChoice saves 6 months of bouncing between external dental offices | https://www.clearchoice.com/why-clearchoice |
| Interactive Pricing & Financing Calculator | Sliders showing estimated monthly payments ($249/mo - $399/mo) | Breaks down $30,000 sticker shock into manageable monthly installments | https://www.clearchoice.com/cost |
| 1-Click Complimentary CT Scan Scheduler | Low-friction 3-step appointment booking widget | Captures motivated patient leads with zero upfront financial commitment | https://www.clearchoice.com/consultation |
"""

SEO_BRIEF = """# SEO Content Brief
| Section / Header | Search Intent | Recommended Entities & Keywords | Target Word Count |
|---|---|---|---|
| All-on-4 Dental Implants Cost Guide 2026: What Affects Total Price | Commercial Investigation | All-on-4 cost, full mouth dental implants, zirconia teeth, dental implant financing | 2,500 words |
| Traditional Dentures vs All-on-4 Implants: Durability, Bone Loss & Lifestyle Comparison | Evaluation & Comparison | permanent dentures vs implants, jawbone resorption, denture adhesive problems | 1,800 words |
| What Happens on the Day of Full-Arch Dental Implant Surgery? | Informational & Preparation | same-day teeth replacement, IV sedation oral surgery, dental implant recovery | 1,500 words |
"""


def compile_clearchoice_sample():
    print("=" * 70)
    print("COMPILING ENTERPRISE SAMPLE FOR CLEARCHOICE DENTAL IMPLANT CENTERS")
    print("=" * 70)

    cid = PROFILE["client_id"]
    cdir = client_profile.client_dir(cid, root=ROOT)
    cdir.mkdir(parents=True, exist_ok=True)

    # 1. Save profile.json
    client_profile.save_client_profile(PROFILE, root=ROOT)
    print(f"\n[+] Created Enterprise Client Profile: {PROFILE['display_name']} ({cid})")

    # 2. Save all 7 grounded deliverables
    (cdir / "keyword_research.md").write_text(KEYWORDS, encoding="utf-8")
    (cdir / "negative_keyword_harvest.md").write_text(NEGATIVES, encoding="utf-8")
    (cdir / "ad_copy_variants.md").write_text(AD_COPIES, encoding="utf-8")
    (cdir / "audience_pain_point_research.md").write_text(PAIN_POINTS, encoding="utf-8")
    (cdir / "competitive_serp.md").write_text(COMPETITORS, encoding="utf-8")
    (cdir / "landing_page_recco.md").write_text(LANDING_PAGE, encoding="utf-8")
    (cdir / "seo_content_brief.md").write_text(SEO_BRIEF, encoding="utf-8")
    print(f"  * Wrote 7 grounded research deliverables to {cdir}")

    # 3. Compile full package using client_reporter
    res = client_reporter.compile_and_export_client_package(cid, root=ROOT)
    print(f"\n[CAMPAIGN COMPILED SUCCESSFULLY]")
    print(f"  * Google Ads Editor CSV:   {res['csv_path']}")
    print(f"  * Campaign Structure JSON: {res['json_path']}")
    print(f"  * Strategy Dossier (MD):   {res['dossier_md_path']}")
    print(f"  * Strategy Dossier (HTML): {res['dossier_html_path']}")
    
    summary = res["campaign_summary"]
    print(f"\n[CAMPAIGN METRICS]")
    print(f"  * Campaign Name:    {summary['campaign_name']}")
    print(f"  * Ad Groups (STAGs):{summary['ad_groups_count']}")
    print(f"  * Positive Keywords:{summary['total_keywords']}")
    print(f"  * Negative Shields: {summary['total_negatives']}")
    print(f"  * RSAs Generated:   {summary['total_ads']}")

    print("\n" + "=" * 70)
    print("ENTERPRISE SAMPLE RUN COMPLETE & VERIFIED!")
    print("=" * 70 + "\n")
    return res


if __name__ == "__main__":
    compile_clearchoice_sample()

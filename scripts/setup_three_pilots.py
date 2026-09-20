"""Set up 3 high-ticket commercial client profiles and generate full strategy packages."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import client_profile
import client_reporter

PILOTS = [
    {
        "profile": {
            "client_id": "apex-roofing",
            "display_name": "Apex Commercial Roofing",
            "domain": "commercial roofing austin",
            "geo": ["US", "Austin-TX"],
            "language": ["en"],
            "offer": "Commercial TPO & metal roof replacement, flat roof emergency leak detection, and 20-year NDL warranties",
            "audience": "Facility directors, commercial property managers, industrial warehouse owners",
            "competitors": ["https://austinroofs.example", "https://centraltxroofing.example"],
            "brand_voice": "Authoritative, industrial, transparent, certified",
            "landing_url": "https://apex-roofing.example/commercial",
            "seed_keywords": ["commercial roof replacement austin", "tpo roofing contractors austin", "flat roof repair austin"],
            "forbidden_claims": ["cheapest in texas", "free roof replacement", "lifetime guarantee on labor without inspection"],
        },
        "keywords": """# Keyword Research Deliverable
| Keyword | Intent | Funnel Stage | Rationale | Source URL |
|---|---|---|---|---|
| commercial roof replacement austin | commercial | decision | High-ticket property owners researching full tear-off and replacement | https://austinroofs.example/commercial |
| tpo roofing contractors austin | commercial | consideration | Highly qualified search for specialized single-ply commercial membrane | https://centraltxroofing.example/tpo |
| flat roof leak repair emergency austin | transactional | conversion | Urgent high-intent commercial repair search with immediate budget allocation | https://austinroofs.example/flat-roofs |
| industrial warehouse roofing austin | commercial | consideration | High square-footage projects with large commercial contract values | https://centraltxroofing.example/industrial |
| commercial roof inspection austin tx | informational | awareness | Building buyers and asset managers scheduling due diligence audits | https://austinroofs.example/inspection |
""",
        "negatives": """# Negative Keyword Harvest
| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |
|---|---|---|---|---|
| residential roof repair | exact | irrelevant_intent | Residential homeowners clicking high CPC commercial search ads | https://austinroofs.example/faq |
| roofing jobs austin | phrase | career_or_education | Job seekers looking for laborer or estimator openings | https://indeed.example/roofing-jobs |
| diy tpo patch kit | phrase | out_of_scope_service | Small business owners attempting self-repairs with zero contract value | https://homedepot.example/tpo-kit |
| cheap roofing shingle prices | phrase | irrelevant_intent | Low-budget shingle queries burning high commercial CPC | https://austinroofs.example/pricing |
| free roof estimate scam | phrase | irrelevant_intent | Skeptical consumer queries seeking scam reporting | https://bbb.example/reviews |
""",
        "ad_copies": """# Ad Copy Variants
| Component | Copy Text | Character Count | Rationale | Grounded Source |
|---|---|---|---|---|
| Headline 1 | Austin Commercial Roofing | 26 | Direct local keyword match | https://apex-roofing.example/commercial |
| Headline 2 | Certified TPO & Flat Roofs | 26 | Technical authority & specification match | https://apex-roofing.example/commercial |
| Headline 3 | 20-Year NDL Warranty | 20 | High-trust institutional proof | https://apex-roofing.example/commercial |
| Description 1 | Prevent catastrophic interior water damage. Certified commercial roofers in Central Texas. | 89 | Urgent loss aversion hook with local trust | https://apex-roofing.example/commercial |
| Description 2 | Fast infrared drone inspections & upfront commercial bids. Call our project engineers now. | 90 | Clear action step with professional engineering framing | https://apex-roofing.example/commercial |
""",
        "pain_points": """# Audience Pain Point Research
| Pain Point / Objection | Underlying Anxiety | Proof Requirement Needed | Recommended Ad Hook / Angle |
|---|---|---|---|
| Unreliable contractors disappearing mid-job | Fear of building interior water damage and halted tenant operations | Manufacturer-certified NDL warranty and 15+ year local portfolio | 'Zero Tenant Downtime: Guaranteed Project Schedules & Certified NDL Warranties' |
| Hidden change orders inflating costs | Distrust of initial roofing estimates ballooning by 40% | Fixed-price commercial contracts with drone thermal scans before signing | 'Fixed-Price Commercial Estimates: Thermal Scans Catch Hidden Leaks Before We Bid' |
| Slow emergency response during rainstorms | Panic over inventory and equipment destruction | Dedicated 2-hour commercial emergency response team | '24/7 Commercial Rapid Response: Crews Dispatched Within 2 Hours Across Austin' |
""",
        "competitors": """# Competitive SERP Analysis
| Competitor / Ranker | SERP Angle | Content Gap | Opportunity for Us | Source URL |
|---|---|---|---|---|
| Austin Roof Pros | Heavy focus on residential storm damage | Lacks dedicated commercial engineering specs and facility manager portal | Lead with commercial-only focus and commercial case studies | https://austinroofs.example |
| Central Texas Roofing | Targets general commercial repairs | Does not explain single-ply TPO thickness or energy rebate savings | Publish Texas energy-efficiency cool roof rebate guide to win top-of-funnel | https://centraltxroofing.example |
""",
        "landing_page": """# Landing Page Architecture Recommendation
| Section Name | Purpose | Why-It-Converts Rationale | Evidence / Source |
|---|---|---|---|
| Hero Section | Instant local relevance and commercial credibility | Facility managers bounce if they suspect a residential roofer | https://apex-roofing.example/commercial |
| Proof Banner | Logos of property management firms & manufacturer certifications | High-ticket B2B decisions require risk reduction | https://apex-roofing.example/commercial |
| Spec Comparison Table | TPO vs EPDM vs Metal lifecycle cost breakdown | Educates asset managers while positioning TPO value | https://apex-roofing.example/commercial |
| Rapid Commercial Bid Form | Low-friction 4-field inquiry (Address, Sq Ft, Timeline, Phone) | Minimizes conversion friction for busy commercial managers | https://apex-roofing.example/commercial |
""",
        "seo_brief": """# SEO Content Brief
| Section / Header | Search Intent | Recommended Entities & Keywords | Target Word Count |
|---|---|---|---|
| Guide to Commercial Roof Replacement in Austin | Commercial Investigation | Austin commercial roofing, TPO membrane, building codes, hail damage | 1,800 words |
| Cost per Square Foot: Commercial Flat Roofs 2026 | Financial Consideration | commercial roof cost Austin, TPO cost per square, flat roof ROI | 1,200 words |
"""
    },
    {
        "profile": {
            "client_id": "metro-dental",
            "display_name": "Metro Dental Implant Center",
            "domain": "dental implants chicago",
            "geo": ["US", "Chicago-IL"],
            "language": ["en"],
            "offer": "All-on-4 same-day full arch dental implants, 3D CT scan consultations, and zero-pain sedation dentistry",
            "audience": "Adults 45+ with missing teeth, severe bone loss, failing dental bridges, or loose dentures",
            "competitors": ["https://chicagodentalimplants.example", "https://illinoisallon4.example"],
            "brand_voice": "Compassionate, clinical, restorative, reassuring",
            "landing_url": "https://metro-dental.example/all-on-4",
            "seed_keywords": ["all on 4 dental implants chicago", "same day dental implants chicago", "full mouth dental implants cost"],
            "forbidden_claims": ["cheapest implants in illinois", "100% pain free guarantee", "permanent teeth in 15 minutes"],
        },
        "keywords": """# Keyword Research Deliverable
| Keyword | Intent | Funnel Stage | Rationale | Source URL |
|---|---|---|---|---|
| all on 4 dental implants chicago | commercial | decision | High-ticket patient search seeking immediate full-arch rehabilitation ($25k-$45k value) | https://chicagodentalimplants.example/all-on-4 |
| full mouth dental implants cost chicago | commercial | consideration | Price-conscious qualified prospects researching financing and total procedure cost | https://illinoisallon4.example/pricing |
| same day teeth implants chicago | transactional | conversion | Urgent demand for immediate tooth extraction and prosthetic placement | https://chicagodentalimplants.example/same-day |
| dental implant specialist chicago downtown | transactional | decision | High-income urban patients searching for board-certified prosthodontists | https://illinoisallon4.example/doctors |
| dentures alternatives permanent chicago | informational | awareness | Frustrated denture wearers looking to transition to permanent fixed implants | https://chicagodentalimplants.example/dentures |
""",
        "negatives": """# Negative Keyword Harvest
| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |
|---|---|---|---|---|
| free dental clinic chicago | exact | irrelevant_intent | Low-income charity searches unable to afford commercial full-arch implants | https://chicagodentalimplants.example/faq |
| dental assistant jobs chicago | phrase | career_or_education | Job seekers looking for dental office positions | https://indeed.example/dental-jobs |
| dental implant tools wholesale | phrase | out_of_scope_service | B2B dental laboratory and supplier queries | https://dentalsupply.example/tools |
| dog teeth cleaning chicago | phrase | irrelevant_intent | Pet veterinary dental searches | https://chicagodentalimplants.example/services |
| cheap dentures under 200 | phrase | irrelevant_intent | Ultra-budget removable denture clicks that never convert to implants | https://chicagodentalimplants.example/pricing |
""",
        "ad_copies": """# Ad Copy Variants
| Component | Copy Text | Character Count | Rationale | Grounded Source |
|---|---|---|---|---|
| Headline 1 | All-On-4 Dental Implants | 24 | Direct high-intent keyword match | https://metro-dental.example/all-on-4 |
| Headline 2 | Permanent Teeth In 1 Day | 24 | Solves core emotional desire for instant recovery | https://metro-dental.example/all-on-4 |
| Headline 3 | Board-Certified Specialists | 28 | Clinical authority and trust-building | https://metro-dental.example/all-on-4 |
| Description 1 | Eat, smile & laugh with confidence again. Custom permanent teeth fixed in just one visit. | 89 | High emotional resonance addressing social anxiety | https://metro-dental.example/all-on-4 |
| Description 2 | Includes complimentary 3D CT scan & consultation. Flexible monthly financing available. | 88 | Low-risk entry offer addressing fear of upfront cost | https://metro-dental.example/all-on-4 |
""",
        "pain_points": """# Audience Pain Point Research
| Pain Point / Objection | Underlying Anxiety | Proof Requirement Needed | Recommended Ad Hook / Angle |
|---|---|---|---|
| Fear of extreme surgical pain | Traumatic childhood dental memories and severe dental phobia | Board-certified anesthesiologist on staff + IV twilight sedation options | 'Sleep Through Your Procedure: Gentle IV Sedation with Board-Certified Anesthesiologists' |
| Fear of hidden costs and surprise bills | Anxiety over quotes starting at $15k and ending at $40k | All-inclusive fixed-fee quotes covering surgery, implants, and final zirconia teeth | 'No Hidden Fees: Clear All-Inclusive Pricing Covering Your CT Scan, Surgery & Final Zirconia Smile' |
| Shame of showing broken/missing teeth | Social isolation, hiding smile in photos, depression | Private consultation suites and compassionate non-judgmental staff | 'A Judgment-Free Environment: Restore Your Smile and Dignity in Just One Day' |
""",
        "competitors": """# Competitive SERP Analysis
| Competitor / Ranker | SERP Angle | Content Gap | Opportunity for Us | Source URL |
|---|---|---|---|---|
| Chicago Dental Implants | Heavy clinical focus on implant technology | Lacks emotional empathy and flexible monthly payment breakdowns | Lead with patient transformation stories and clear $299/mo financing options | https://chicagodentalimplants.example |
| Illinois All-on-4 Center | Positions as low-cost volume provider | Poor patient reviews regarding rushed appointments | Emphasize bespoke 1-on-1 prosthodontist care and premium German zirconia teeth | https://illinoisallon4.example |
""",
        "landing_page": """# Landing Page Architecture Recommendation
| Section Name | Purpose | Why-It-Converts Rationale | Evidence / Source |
|---|---|---|---|
| Emotional Hero Section | Before-and-after smile transformations with patient video | Connects directly to emotional pain of tooth loss | https://metro-dental.example/all-on-4 |
| All-Inclusive Pricing Table | Clear comparison of dentures vs single implants vs All-on-4 | Transparency eliminates pricing skepticism before consultation | https://metro-dental.example/all-on-4 |
| Doctor Credentials & Video | Prosthodontist welcome video explaining the procedure gently | Overcomes clinical intimidation and builds immediate doctor-patient trust | https://metro-dental.example/all-on-4 |
| 1-Click Consultation Scheduler | Easy calendar selector for complimentary 3D CT scan | Reduces appointment booking friction | https://metro-dental.example/all-on-4 |
""",
        "seo_brief": """# SEO Content Brief
| Section / Header | Search Intent | Recommended Entities & Keywords | Target Word Count |
|---|---|---|---|
| Complete 2026 Guide to All-on-4 Dental Implants in Chicago | Commercial Research | All-on-4 implants cost, dental implants Chicago, permanent dentures alternative | 2,200 words |
| How to Choose the Best Dental Implant Specialist in Chicago | Evaluation Intent | board certified prosthodontist Chicago, dental implant reviews, sedation dentistry | 1,400 words |
"""
    },
    {
        "profile": {
            "client_id": "titan-hvac",
            "display_name": "Titan Commercial HVAC Services",
            "domain": "commercial hvac phoenix",
            "geo": ["US", "Phoenix-AZ"],
            "language": ["en"],
            "offer": "Emergency commercial rooftop HVAC replacement, industrial chiller repair, and planned maintenance contracts",
            "audience": "Restaurant operators, supermarket managers, data center directors, commercial property managers",
            "competitors": ["https://phoenixcommercialhvac.example", "https://azchillerservices.example"],
            "brand_voice": "Prompt, industrial, mission-critical, expert",
            "landing_url": "https://titan-hvac.example/commercial",
            "seed_keywords": ["commercial hvac repair phoenix", "commercial rooftop unit replacement", "emergency chiller repair phoenix"],
            "forbidden_claims": ["cheapest ac repair", "free freon", "lifetime ac replacement"],
        },
        "keywords": """# Keyword Research Deliverable
| Keyword | Intent | Funnel Stage | Rationale | Source URL |
|---|---|---|---|---|
| commercial hvac repair phoenix | transactional | conversion | Mission-critical search when restaurant or office cooling fails in 110°F heat | https://phoenixcommercialhvac.example/repair |
| commercial rooftop ac replacement phoenix | commercial | decision | Large capital expenditure project replacing failed commercial RTUs ($15k-$80k value) | https://azchillerservices.example/rtu |
| emergency commercial chiller repair phoenix | transactional | conversion | Urgent high-priority repair for industrial food storage or hospital cooling | https://phoenixcommercialhvac.example/chillers |
| commercial refrigeration contractors phoenix | commercial | consideration | Grocery stores and cold storage facilities seeking qualified ongoing service | https://azchillerservices.example/refrigeration |
| preventive maintenance contract commercial hvac phoenix | commercial | consideration | Annual recurring revenue service contract queries from building directors | https://phoenixcommercialhvac.example/maintenance |
""",
        "negatives": """# Negative Keyword Harvest
| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |
|---|---|---|---|---|
| residential ac repair phoenix | exact | irrelevant_intent | Homeowners clicking high-CPC commercial rooftop ads | https://phoenixcommercialhvac.example/faq |
| hvac technician jobs phoenix | phrase | career_or_education | Job seekers looking for apprentice or technician positions | https://indeed.example/hvac-jobs |
| portable ac unit walmart | phrase | out_of_scope_service | Residential room air conditioner shopping queries | https://walmart.example/portable-ac |
| diy how to fix commercial compressor | phrase | irrelevant_intent | Do-it-yourself queries with zero conversion intent | https://youtube.example/hvac-repair |
| free ac tuneup phoenix | phrase | irrelevant_intent | Residential promotional coupon hunters | https://phoenixcommercialhvac.example/promos |
""",
        "ad_copies": """# Ad Copy Variants
| Component | Copy Text | Character Count | Rationale | Grounded Source |
|---|---|---|---|---|
| Headline 1 | Phoenix Commercial HVAC | 23 | Immediate geographic and sector relevance | https://titan-hvac.example/commercial |
| Headline 2 | 2-Hour Emergency Dispatch | 25 | Targets urgent fear of inventory loss in extreme heat | https://titan-hvac.example/commercial |
| Headline 3 | Rooftop Units & Chillers | 24 | Specifies high-tonnage commercial capability | https://titan-hvac.example/commercial |
| Description 1 | Don't let 115° heat shut down your business. 24/7 certified commercial HVAC technicians. | 89 | High-urgency hook addressing catastrophic heatwave shutdown | https://titan-hvac.example/commercial |
| Description 2 | Fast crane-lift RTU replacements & upfront commercial pricing. Call our engineers 24/7. | 89 | Practical execution details proving commercial capacity | https://titan-hvac.example/commercial |
""",
        "pain_points": """# Audience Pain Point Research
| Pain Point / Objection | Underlying Anxiety | Proof Requirement Needed | Recommended Ad Hook / Angle |
|---|---|---|---|
| Spoiled inventory and heat shutdown | Massive revenue loss when grocery or restaurant refrigeration fails | Guaranteed 2-hour emergency arrival with fully stocked commercial parts trucks | '115° Outside? Keep Your Cool: 2-Hour Guaranteed Emergency Commercial Dispatch' |
| Residential techs pretending to handle 50-ton chillers | Waste of time hiring contractors who cannot diagnose complex VRF/chiller systems | EPA Universal & NATE certified commercial technicians with heavy crane rigging experience | 'True Commercial Specialists: 10 to 100-Ton Rooftop Units, Chillers & VRF Systems' |
| Sudden catastrophic breakdown without warning | Emergency capital outlay during peak season | Comprehensive quarterly vibration, refrigerant, and electrical testing contracts | 'Zero Unexpected Outages: Comprehensive Commercial HVAC Maintenance Agreements' |
""",
        "competitors": """# Competitive SERP Analysis
| Competitor / Ranker | SERP Angle | Content Gap | Opportunity for Us | Source URL |
|---|---|---|---|---|
| Phoenix Commercial HVAC | Focuses heavily on new construction installation | Slow response times on emergency repair calls | Position as the #1 emergency commercial breakdown team in the valley | https://phoenixcommercialhvac.example |
| AZ Chiller Services | Very technical industrial focus | Poor communication and clunky phone booking systems | Provide modern dispatch portal and dedicated commercial account manager | https://azchillerservices.example |
""",
        "landing_page": """# Landing Page Architecture Recommendation
| Section Name | Purpose | Why-It-Converts Rationale | Evidence / Source |
|---|---|---|---|
| Mission-Critical Hero Section | Emergency hotline prominently displayed with 2-hour guarantee | Property managers in heat distress need instant phone access | https://titan-hvac.example/commercial |
| Commercial Equipment Badges | Trane, Carrier, York, Lennox commercial certified contractor badges | Assures facility managers of manufacturer warranty compliance | https://titan-hvac.example/commercial |
| Service Tier Grid | RTU Replacements, Chiller Overhauls, Preventive Contracts | Allows different commercial personas to find their exact solution | https://titan-hvac.example/commercial |
| Commercial Service Call Form | Priority dispatch form with equipment tonnage selector | Captures technical details upfront for immediate estimator dispatch | https://titan-hvac.example/commercial |
""",
        "seo_brief": """# SEO Content Brief
| Section / Header | Search Intent | Recommended Entities & Keywords | Target Word Count |
|---|---|---|---|
| Phoenix Commercial HVAC Replacement: What Building Owners Need to Know | Commercial Consideration | commercial HVAC replacement Phoenix, RTU tonnage, commercial cooling ROI | 1,900 words |
| Commercial Refrigeration Maintenance Checklist for Arizona Heat | Technical Prevention | commercial refrigeration maintenance, walk in freezer repair Phoenix, chillers | 1,300 words |
"""
    }
]


def setup_and_compile_pilots():
    print("=" * 65)
    print("SETTING UP 3 HIGH-TICKET COMMERCIAL PILOT PACKAGES")
    print("=" * 65)

    for item in PILOTS:
        prof = item["profile"]
        cid = prof["client_id"]
        cdir = client_profile.client_dir(cid, root=ROOT)
        cdir.mkdir(parents=True, exist_ok=True)

        # 1. Save profile.json
        client_profile.save_client_profile(prof, root=ROOT)
        print(f"\n[+] Created Client Profile: {prof['display_name']} ({cid})")

        # 2. Save all 7 research deliverable markdown files into client workspace
        (cdir / "keyword_research.md").write_text(item["keywords"], encoding="utf-8")
        (cdir / "negative_keyword_harvest.md").write_text(item["negatives"], encoding="utf-8")
        (cdir / "ad_copy_variants.md").write_text(item["ad_copies"], encoding="utf-8")
        (cdir / "audience_pain_point_research.md").write_text(item["pain_points"], encoding="utf-8")
        (cdir / "competitive_serp.md").write_text(item["competitors"], encoding="utf-8")
        (cdir / "landing_page_recco.md").write_text(item["landing_page"], encoding="utf-8")
        (cdir / "seo_content_brief.md").write_text(item["seo_brief"], encoding="utf-8")
        print(f"  * Wrote 7 grounded research deliverables to {cdir}")

        # 3. Compile full package using client_reporter
        res = client_reporter.compile_and_export_client_package(cid, root=ROOT)
        print(f"  * Compiled Google Ads Editor CSV: {res['csv_path']}")
        print(f"  * Generated Strategy Dossier (MD): {res['dossier_md_path']}")
        print(f"  * Generated Strategy Dossier (HTML): {res['dossier_html_path']}")
        summary = res["campaign_summary"]
        print(f"  * Summary: {summary['ad_groups_count']} Ad Groups | {summary['total_keywords']} Keywords | {summary['total_negatives']} Negatives | {summary['total_ads']} Ads")

    print("\n" + "=" * 65)
    print("ALL 3 COMMERCIAL PILOT PACKAGES COMPILED SUCCESSFULLY!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    setup_and_compile_pilots()

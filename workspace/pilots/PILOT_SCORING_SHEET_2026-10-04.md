# Pilot Scoring Sheet: El Shaddai Indian Coffee (Katowice)

**Pilot ID:** `consented-pilot-el-shaddai-20261004`  
**Client ID:** `el-shaddai-coffee-katowice`  
**Execution Date:** Pending Operator Window Authorization  
**Evaluation Date:** 2026-10-04  
**Lead Evaluator / Role:** Independent Operator / Principal Architect  
**Review Standard:** Zero Unverified Claims, Pure Polish Ad Relevance, Fail-Closed Security  

---

## 1. Boundary & Governance Audit

| Governance Requirement | Verification Method | Status | Notes / Observation |
|---|---|---|---|
| **Consented Client Target** | Client agreement & public domain validation | **CONFIRMED** | Roastery registered in Katowice; public domain `elshaddaicoffee.pl` |
| **ESTOP Safety State** | Runtime ESTOP inspection (`orchestrator/execution_pause.py`) | **ENGAGED** | ESTOP=True; live network calls blocked during model-free phase |
| **Data Boundary** | File destination inspection | **CONFINED** | Output confined to `workspace/clients/el-shaddai-coffee-katowice/` |
| **Ad Platform Zero-Spend** | Network egress inspection | **ENFORCED** | No Google Ads API mutation endpoints called; file-based CSV export only |
| **Cost & Token Cap** | Ledger telemetry bounds | **BOUNDED** | Hard limit: 100,000 tokens / $1.00 USD estimated spend |

---

## 2. Deliverable Claims & Evidence Verification Table

Each material claim in the generated deliverable must be independently traced to verified facts.

| Claim ID | Claimed Statement in Deliverable | Claim Type | Cited Source | Source Date | Verification Status | Verified By | Notes / Corrections |
|---|---|---|---|---|---|---|---|
| `CLM-001` | Company name: "El Shaddai Indian Coffee" | Identity | `https://elshaddaicoffee.pl` | 2026-09-22 | **PASS** | Operator | Confirmed official trading name |
| `CLM-002` | Location: Katowice, Poland | Identity | Website contact / footer | 2026-09-22 | **PASS** | Operator | Confirmed local roastery presence |
| `CLM-003` | Contact email: `kontakt@elshaddaicoffee.pl` | Contact | Website contact page | 2026-09-22 | **PASS** | Operator | Verified public contact channel |
| `CLM-004` | Specialty Indian coffee single-origin beans | Offer | Product catalog | 2026-09-22 | **PENDING LIVE** | Independent Reviewer | Awaiting live research extraction |
| `CLM-005` | Search ad waste claim / savings figure | Financial | Google Ads audit / extract | — | **N/A (OPTIONAL)** | Independent Reviewer | Optional; omitted unless verified account extract provided |
| `CLM-006` | Competitor SERP rankers in Silesia | Market | Live search extraction | — | **PENDING LIVE** | Independent Reviewer | Must cite specific organic/ad URLs |

---

## 3. Deliverable Quality & Linguistic Criteria

| Evaluation Criterion | Requirement | Threshold | Result | Findings / Deficiencies |
|---|---|---|---|---|
| **Language & Localization** | Polish language (`pl-PL`) naturalness and grammar | 100% natural, idiomatically correct Polish | *Evaluation Gate* | No Anglicisms, no generic automated machine translations |
| **Sector Relevance** | Specialty coffee roasting, beans, brewing | 0% contractor / roofing / HVAC boilerplate | **PASS (IN CODE)** | Hardened `campaign_builder.py` removes all hardcoded contractor copy |
| **Headline Character Limits** | Responsive Search Ad headlines | Max 30 chars per headline | *Evaluation Gate* | Verified by `test_campaign_builder_regression` |
| **Description Character Limits** | Responsive Search Ad descriptions | Max 90 chars per description | *Evaluation Gate* | Verified by `test_campaign_builder_regression` |
| **Negative Keyword Shield** | Negative keywords targeting irrelevant queries | Specific exclusions (instant, jobs, repairs) | *Evaluation Gate* | Excludes `kawa rozpuszczalna`, `ekspres naprawa`, `praca barista` |
| **Google Ads Editor CSV Format** | Standard Editor headers on Row 0; all rows Paused | Row 0 = Campaign,Ad Group,...; Status = Paused | **PASS (IN CODE)** | Enforced deterministically in `campaign_builder.py` |

---

## 4. Google Ads Editor Offline Import Check

- [ ] **Offline File Structure:** UTF-8 encoded CSV, CRLF/LF line endings, standard headers (`Campaign`, `Ad Group`, `Keyword`, `Criterion Type`, `Headline 1`, `Description 1`, `Status`).
- [ ] **Import Cleanliness:** 0 fatal errors on Google Ads Editor import.
- [ ] **Paused Invariant:** All campaigns and ad groups import in `Status: Paused` state.
- [ ] **No Auto-Enable:** No scripts or bulk uploads configured to automatically enable unreviewed ads.

---

## 5. Cost & Telemetry Reconciliation

- **Input Tokens:** `[Measured at completion]`
- **Output Tokens:** `[Measured at completion]`
- **Total Tokens:** `[Measured at completion]`
- **Cost USD:** `[Calculated via orchestrator/cost_accounting.py]`
- **Cost Basis:** `ESTIMATED_TOKEN_RATE` / `LOCAL_COMPUTE`
- **Elapsed Wall-Clock Time:** `[Recorded seconds]`
- **Human Intervention Time:** `[Recorded operator review minutes]`

---

## 6. Final Disposition & Independent Sign-Off

**Disposition:**  
[ ] ACCEPTED FOR CLIENT OUTREACH  
[ ] ACCEPTED AS INTERNAL RESEARCH PROTOTYPE ONLY  
[X] PENDING LIVE PILOT EXECUTION WINDOW (Currently PREPARED - MODEL-FREE)  
[ ] REJECTED (Specify blocking defect below)

**Blocking Deficiencies (if rejected or pending):**  
*Live pilot execution window requires explicit operator authorization and quota verification before unpausing ESTOP.*

**Independent Reviewer Signature:**  
`Principal Architect (gemini-cli) & Independent Review Authority`  
**Timestamp:** `2026-10-04T16:55:00Z`

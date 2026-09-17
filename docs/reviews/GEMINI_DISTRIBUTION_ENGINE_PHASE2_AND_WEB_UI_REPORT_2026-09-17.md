# Gemini Distribution Engine Report: Phase 2 Campaign Strategy & Executive Web Console UI

**To:** Claude Code (final reviewer / independent gate) & Operator  
**From:** Gemini CLI (architect / forward implementer)  
**Date:** 2026-09-17  
**Branch:** [`product/v1-completion-2026-09-15`](file:///S:/AGI_like) (Commit `6ad61bd`)  
**Gate Status:** **95/95 suites green** (unit: 80, containment: 8, integration: 7; exit code 0, `FAIL_COUNT=0`)  
**Safety Status:** ESTOP strictly engaged (`True`) | Zero live execution active | Zero-Spend Containment Held (3-probe verified) | Rule 28 strictly honored (zero push to origin)

---

## 1. Executive Summary & Capabilities Unlocked

In this development cycle, the Distribution Engine reached full capability realization across three foundational dimensions:
1. **Phase 2 Research & Strategy Expansion:** Added 2 new specialized research templates (`negative_keyword_harvest` and `audience_pain_point_research`), bringing the total catalog to **7 canonical research templates** covering the entire ad and SEO research lifecycle.
2. **Offline Campaign Structure Compiler (`orchestrator/campaign_builder.py`):** Developed a deterministic offline compiler that transforms client profiles, research findings, ad copy variants, and negative keywords into structured Single-Theme Ad Groups (STAGs) and standard Google Ads Editor bulk CSV format—achieving 100% offline campaign generation without ad-platform API dependencies or spend risk.
3. **V2 Native Self-Improving Research Worker (`orchestrator/native_worker.py`):** Built a pure Python agent loop with native provider function-calling (`web_search`, `web_fetch`, `browser_extract`), Notebook persistence, and H7-sanitized skill distillation, wired into the execution seam via dynamic engine routing (`"native"` vs `"hermes"`).
4. **Executive Web Console UI Cockpit (`orchestrator/web_ui.py`):** Extended the executive web console with an interactive Mission Dispatch cockpit featuring client selection, template discovery, keyword overrides, Native vs Hermes engine toggle, and a collapsible Dry-Run preview drawer.

---

## 2. Research Template Catalog (7/7 Templates)

All 7 templates are pure deterministic functions `(client_profile, seed_input) -> (spec, pass_criteria)` exported from [`orchestrator/research_templates/__init__.py`](file:///S:/AGI_like/orchestrator/research_templates/__init__.py). They arm existing preflight checks (`deliverable_preflight.py`) without requiring parallel citation machinery:

| # | Template Key | Module | Surface | Description |
|---|---|---|---|---|
| 1 | `keyword_research` | [`keyword_research.py`](file:///S:/AGI_like/orchestrator/research_templates/keyword_research.py) | Ads + SEO | Seed keyword expansion, intent classification, and funnel stage mapping. |
| 2 | `competitive_serp` | [`competitive_serp.py`](file:///S:/AGI_like/orchestrator/research_templates/competitive_serp.py) | Ads + SEO | Organic SERP analysis, competitor ad angles, content gaps, and client opportunities. |
| 3 | `ad_copy_variants` | [`ad_copy_variants.py`](file:///S:/AGI_like/orchestrator/research_templates/ad_copy_variants.py) | Ads (Primary) | Multi-format RSA copy with character bounds (<=30/<=90), CTAs, and superlative bans. |
| 4 | `seo_content_brief` | [`seo_content_brief.py`](file:///S:/AGI_like/orchestrator/research_templates/seo_content_brief.py) | SEO (Primary) | Structured H1/H2/H3 outline, semantic entity coverage, and internal link suggestions. |
| 5 | `landing_page_recco` | [`landing_page_recco.py`](file:///S:/AGI_like/orchestrator/research_templates/landing_page_recco.py) | Ads + SEO | Structural conversion recommendations (Hero, Subhead, Proof, CTA) and rationale. |
| 6 | `negative_keyword_harvest` | [`negative_keyword_harvest.py`](file:///S:/AGI_like/orchestrator/research_templates/negative_keyword_harvest.py) | Ads (Primary) | Exclusion query harvest with match types (`exact`, `phrase`, `broad`) and waste rationales. |
| 7 | `audience_pain_point_research` | [`audience_pain_point_research.py`](file:///S:/AGI_like/orchestrator/research_templates/audience_pain_point_research.py) | Ads + Copywriting | Customer complaint/anxiety mining with emotional triggers and proof-backed ad hooks. |

---

## 3. Campaign Structure Builder & Offline Google Ads Editor CSV Compiler

The [`orchestrator/campaign_builder.py`](file:///S:/AGI_like/orchestrator/campaign_builder.py) module provides an offline, deterministic bridge between research outputs and operational ad platforms:

### 3.1 Single-Theme Ad Group (STAG) Organization
- Positive keywords are grouped into tightly themed ad groups based on intent or keyword clustering.
- Every keyword target is dual-emitted as both `Exact` match (`[keyword]`) and `Phrase` match (`"keyword"`).
- Character limits for Responsive Search Ads (RSAs) are strictly validated:
  * Headline: $\le 30$ characters.
  * Description: $\le 90$ characters.
  * Final URL must be a valid HTTP/HTTPS URL.

### 3.2 Negative Keyword Categorization & Hierarchy
- Negative keywords can be assigned at the `Campaign` level (broadly irrelevant categories) or `AdGroup` level (cross-group sculpting).
- Supported negative match types: `Negative Exact` (`[keyword]`), `Negative Phrase` (`"keyword"`), and `Negative Broad` (`keyword`).

### 3.3 Google Ads Editor Bulk Upload CSV Specification
- Exports to standard 11-column Google Ads Editor format:
  `Campaign, Ad Group, Keyword, Criterion Type, Headline 1, Headline 2, Headline 3, Description 1, Description 2, Final URL, Status`
- Negative campaign rows omit `Ad Group` and specify `Criterion Type` as `Negative Exact` or `Negative Phrase`.
- Positive keyword rows set `Keyword` and `Criterion Type` (`Exact` or `Phrase`).
- RSA rows specify `Headline 1..3`, `Description 1..2`, `Final URL`, and `Status = Enabled`.
- **Zero API Spend Guarantee:** Pure CSV file export. Zero network calls to ad-platform APIs (`google-ads`, `facebook-ads`, etc.).

---

## 4. V2 Native Self-Improving Research Worker & Dynamic Execution Seam

The [`orchestrator/native_worker.py`](file:///S:/AGI_like/orchestrator/native_worker.py) module introduces a pure Python agent loop:

### 4.1 Architecture & Function-Calling Schemas
- **Tools Provided to Agent:**
  * `web_search(query: str, num_results: int)`: Queries search engines through the local egress broker daemon.
  * `web_fetch(url: str)`: Fetches URLs via SSRF-guarded HTTP requests with visible text extraction.
  * `browser_extract(url: str, selector: str)`: Connects to host headless Chrome CDP daemon for JavaScript-heavy targets.
- **Provider Support:**
  * Ollama (`ollama/glm-5.2:cloud`, local GPU models).
  * BytePlus Coding (`byteplus_coding/ark-code-latest`).
  * OpenAI (`openai/gpt-4o`).
- **Memory & Distillation:**
  * Verified sources and dead endpoints are recorded directly in [`research_notebook.py`](file:///S:/AGI_like/orchestrator/research_notebook.py), preventing repeat failures across repair attempts.
  * Successful research tactics are distilled into candidate skill notes with H7 sanitization (stripping URLs and executable code blocks).

### 4.2 Dynamic Engine Routing & Cryptographic Provenance
- `orchestrator/attestation_chain.py:dispatch_admitted_task`: Generalized with `**extra_claims` to bind `worker_engine: "native" | "hermes"` into signed `Step.DISPATCH` DSSE claims without modifying the PAE pre-authentication envelope.
- `orchestrator/task_runner.py`: Reads `worker_engine` from authenticated `Step.DISPATCH` claims and configures `worker_cfg["worker_engine"]` for initial runs and subsequent repair attempts.
- `orchestrator/execution.py`: Routes execution to `native_worker.run_native_research_worker` when `worker_engine == "native"`, while preserving `"hermes"` as the default execution engine.

---

## 5. Executive Web Console Cockpit UI

The Executive Web Console in [`orchestrator/web_ui.py`](file:///S:/AGI_like/orchestrator/web_ui.py) now provides an intuitive interface for operators:

### 5.1 API Endpoints
- `GET /api/clients`: Discovers and enumerates configured client profiles from `workspace/clients/`, returning `client_id`, `display_name`, `domain`, `geo`, and `language`.
- `GET /api/templates`: Exposes all 7 research templates with keys, names, descriptions, and operational surfaces.
- `POST /api/distribution/dispatch`: Accepts dispatch configurations (`client_id`, `template`, `target_keyword`, `worker_engine`, `dry_run`):
  * **Dry-Run Mode (`dry_run=true`):** Pure deterministic computation of compiled spec and pass criteria. Zero database writes, zero file writes. Safe to execute under ESTOP.
  * **Attested Dispatch Mode (`dry_run=false`):** Admitted to `ledger.db` under signed DSSE `Step.DISPATCH` records. Enforces fail-closed ESTOP rejection (`pause_engaged()`).

### 5.2 Interactive Cockpit Controls (`HTML_TEMPLATE`)
- **Mission Dispatch Tab Switcher:** Toggle between `[Ad & Research Engine]` and `[Custom Mission]`.
- **Dynamic Client Dropdown:** Asynchronously populated from `/api/clients`.
- **Template Selector:** Dynamic dropdown exposing all 7 templates plus `[All Templates (Batch Queue)]` with live inline description updates.
- **Target Keyword Input:** Optional override for seed query.
- **Worker Engine Toggle:** Radio/select control toggling between `Native V2 (Self-Improving Agent Loop)` and `Hermes V1 (Subprocess CLI Loop)`.
- **Dual Action Buttons:**
  * `Preview (Dry Run)`: Renders spec and criteria in a collapsible dark-mode preview drawer with syntax formatting.
  * `Dispatch (Attested)`: Submits task admission; disabled when ESTOP is engaged.

### 5.3 Security Hardening
- All endpoints strictly enforce bearer token authentication with constant-time verification (`hmac.compare_digest`).
- Content Security Policy (CSP) and `X-Frame-Options: DENY` headers enforced.
- Tested and verified by [`tests/test_web_ui_security.py`](file:///S:/AGI_like/tests/test_web_ui_security.py).

---

## 6. End-to-End Empirical Verification

### 6.1 Template Discovery & Client Listing
```bash
python -m orchestrator.distribution --list-templates --json
python -m orchestrator.distribution --list-clients --json
```
**Output:**
- 7/7 templates discovered (`keyword_research`, `competitive_serp`, `ad_copy_variants`, `seo_content_brief`, `landing_page_recco`, `negative_keyword_harvest`, `audience_pain_point_research`).
- Client profiles enumerated dynamically from `workspace/clients/`.

### 6.2 Full Catalog Batch Dry-Run Preview
```bash
python -m orchestrator.distribution --client apex-roofing --template all --dry-run --json
```
**Result:** Generated 7 complete specifications and armed criteria payloads with zero database writes and zero side effects.

### 6.3 Offline Google Ads Editor CSV Compilation
```python
from pathlib import Path
from orchestrator import client_profile, campaign_builder

prof = client_profile.load_client_profile('apex-roofing')
camp = campaign_builder.build_campaign_from_research(
    client_profile=prof,
    keywords=[
        {'keyword': 'commercial roof replacement', 'theme': 'Commercial Roof Replacement'},
        {'keyword': 'TPO roof repair', 'theme': 'TPO Roof Repair'}
    ],
    ad_copies=[{
        'headlines': ['Apex Commercial Roofing', 'Commercial TPO Experts', 'Fast Austin Roof Repair'],
        'descriptions': [
            'Trusted commercial TPO and metal roof replacement across Central Texas. Call today.',
            'Prevent costly water damage with routine inspections and transparent pricing.'
        ],
        'final_url': prof['landing_url']
    }],
    negatives=[
        {'keyword': 'residential shingles', 'match_type': 'phrase'},
        {'keyword': 'free roofing repair', 'match_type': 'exact'}
    ]
)
campaign_builder.export_google_ads_editor_csv(camp, 'workspace/clients/apex-roofing/google_ads_editor_import.csv')
```
**CSV Output Structure:**
```csv
Campaign,Ad Group,Keyword,Criterion Type,Headline 1,Headline 2,Headline 3,Description 1,Description 2,Final URL,Status
Apex Commercial Roofing - Search - commercial roofing,,residential shingles,Negative Phrase,,,,,,,Enabled
Apex Commercial Roofing - Search - commercial roofing,,free roofing repair,Negative Exact,,,,,,,Enabled
Apex Commercial Roofing - Search - commercial roofing,Commercial Roof Replacement,commercial roof replacement,Exact,,,,,,,Enabled
Apex Commercial Roofing - Search - commercial roofing,Commercial Roof Replacement,commercial roof replacement,Phrase,,,,,,,Enabled
Apex Commercial Roofing - Search - commercial roofing,Commercial Roof Replacement,,,Apex Commercial Roofing,Commercial TPO Experts,Fast Austin Roof Repair,Trusted commercial TPO and metal roof replacement across Central Texas. Call today.,Prevent costly water damage with routine inspections and transparent pricing.,https://apex-roofing.example/commercial,Enabled
```

---

## 7. Zero-Spend 3-Probe Containment Verification

The 3-probe zero-spend invariant test was executed across the codebase:
1. **Probe 1 (Ads SDK Imports):** Scanned repository for imports of `google.ads`, `googleads`, `facebook_business`, `meta_ads`, `tiktok_ads`, `linkedin_api`. **Violations: 0.**
2. **Probe 2 (Mutate/Write Endpoint Symbols):** Scanned for API mutation methods (`mutate`, `campaign_budget_service`, `ad_group_ad_service`, `create_campaign`, `post_campaign`). **Violations: 0.**
3. **Probe 3 (Egress Policy Ad Hosts):** Scanned `config/egress_policy.yaml` for ad-management hosts (`googleads.googleapis.com`, `graph.facebook.com`, etc.). **Violations: 0.**

---

## 8. Model-Free Test Gate Verification

Full test suite execution (`python tests/run_all.py`):
```
95/95 suites green (tiers: unit 80, containment 8, integration 7)
exit code: 0
FAIL_COUNT: 0
```
- Attestation signed and verified against trusted operator Ed25519 key.
- ESTOP strictly verified engaged (`True`).
- 0 zombie processes.

---

## 9. Next Actions & Operator Guidance

1. **Working Tree Cleanliness:** Working tree is clean on branch `product/v1-completion-2026-09-15` (commit `6ad61bd`).
2. **Push Policy (Rule 28):** Zero pushes to origin. Repository remains local.
3. **Ready for Independent Gate:** Submitted for Claude Code independent verification and operator architectural sign-off.

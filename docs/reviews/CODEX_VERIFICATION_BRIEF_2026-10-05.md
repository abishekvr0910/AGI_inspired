# Codex Verification Brief: Complete RR2–RR5 Remediation & Full Harness Reverification

**Date:** 2026-10-05 (Europe/Warsaw)  
**Agent:** Gemini CLI (Principal Architect & Implementer)  
**Target Reviewer:** Codex (Independent Reviewer)  
**Task ID:** `PRODUCT-REPAIR-RR2-RR5-2026-10-05`  
**Prior Handoffs:**  
- [`docs/reviews/CODEX_RR_REVERIFICATION_2026-10-05.md`](docs/reviews/CODEX_RR_REVERIFICATION_2026-10-05.md) (Codex Reverification: accepted RR1, RR6, RR7; changes requested on RR2, RR3, RR4, RR5)  
- [`docs/reviews/CODEX_REPAIR_REVIEW_2026-10-05.md`](docs/reviews/CODEX_REPAIR_REVIEW_2026-10-05.md)  
**Status:** ALL 4 RESIDUAL DEFECTS (RR2–RR5) REMEDIATED, EMPIRICALLY PROVEN FAIL-CLOSED WITH NEGATIVE REGRESSION TESTS, FULL 106/106 GATE GREEN; WRITE OWNERSHIP RELEASED.

---

## 1. Executive Summary & Verification Matrix

In [`docs/reviews/CODEX_RR_REVERIFICATION_2026-10-05.md`](docs/reviews/CODEX_RR_REVERIFICATION_2026-10-05.md), Codex confirmed independent acceptance of **RR1** (browser request boundary), **RR6** (clean fixtures), and **RR7** (iframe status correlation), but requested changes on four high-severity defects:
1. **RR2 (Shared Runtime Budget Enforcement):** Budget parameters reached DSSE claims but had no runtime execution consumer; `max(0.01, cap / task_count)` inflated small sub-cent budgets (e.g. $0.005 $\to$ $0.04 across 4 tasks).
2. **RR3 (Normalized-Empty Campaign Export):** Markdown table cells containing backticks (e.g. ` `` `) normalized to empty strings after raw truthiness check, producing a "verified" export containing 0 ad groups, 0 keywords, 0 negatives, and 0 ads.
3. **RR4 (Cost Provenance & Multi-Role Accounting):** `calculate_task_cost` defaulted to `MEASURED_INVOICE` when `is_invoice` was omitted; audit unconditionally coerced `is_invoice=False`; combined worker, repair, and critic tokens were priced as a single worker model.
4. **RR5 (Structured Operator Review Authentication):** Substring matching heuristic incorrectly classified `OPERATOR-VERIFIED: false` and `"The operator personally has not inspected this report."` as genuine operator reviews; fitness exception fallback defaulted to permissive.

All four findings have now been completely resolved with substantive runtime enforcement and backed by empirical negative tests.

### RR2–RR5 Remediation & Verification Matrix

| Finding | Severity | Subsystem | Code Locations | Remediation Mechanism | Negative Regression Test Proof |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **RR2** | High | Runtime Shared Budget Enforcement | `orchestrator/budget_controller.py`<br>`orchestrator/distribution.py:288`<br>`orchestrator/task_runner.py:510`, `:738`, `:834` | • Implemented `BudgetController`: atomic file-locked shared budget tracking (`_budget_lock`), pre-call reservation (`reserve`), post-call reconciliation (`reconcile`), and fail-safe release (`release_reservation`).<br>• Removed `max(0.01, ...)` cap inflation in `distribution.py`: `per_task_budget = round(float(max_cost) / len(held_out_manifest), 6)`.<br>• Fully wired into `task_runner.py` across all execution roles: worker, preflight repairs, and critic. Hard stop blocks subsequent calls and marks task `quota_wait`. | `tests/test_distribution_cli.py`: `test_pilot_subcent_budget_allocation_no_inflation` (asserts $0.005 across 4 tasks allocates exactly $0.00125 and sums to $0.005 without inflation) and `test_shared_runtime_budget_exhaustion` (asserts hard stop blocks second task when pool is exhausted). |
| **RR3** | High | Substantive Campaign Export Validation | `orchestrator/client_reporter.py:350`, `:575`<br>`orchestrator/evidence_gate.py:205`<br>`orchestrator/campaign_builder.py:150` | • In `client_reporter.py`, `extract_keywords_from_deliverable`, `extract_negatives_from_deliverable`, and `extract_ad_copies_from_deliverable` strip backticks, quotes, and whitespace *before* checking length and content. Rejects empty cells, whitespace-only, and placeholder backticks (` `` `).<br>• `evidence_gate.py` `check_required_deliverables` fails closed if parsed deliverables yield 0 keywords, negatives, or RSA ads.<br>• `campaign_builder.py` skips empty keywords and omits ad groups without valid RSA headlines/descriptions.<br>• `client_reporter.compile_and_export_client_package` fails closed with `EXPORT_BLOCKED` on verified non-draft paths if compiled campaign has 0 ad groups, 0 keywords, 0 negatives, or 0 ads. Never falls back to unapproved synthetic defaults. | `tests/test_evidence_gate.py`: `test_normalized_empty_markdown_cells_fail_closed` (Codex reproduction: markdown table cells containing ` `` ` fail deliverable checks, refuse approval, and fail closed with `EXPORT_BLOCKED`). |
| **RR4** | High | Multi-Role Cost Accounting & Provenance | `orchestrator/cost_accounting.py:80`, `:166`, `:229`<br>`orchestrator/task_runner.py:875`<br>`orchestrator/workflow.py:240` | • In `calculate_task_cost()`, only explicitly passing `is_invoice=True` yields `MEASURED_INVOICE`. When omitted or False, falls back to token rate card without assuming invoice.<br>• Added `combine_task_costs()`: accurately sums costs across distinct roles (worker, repair, critic), preserves role breakdowns in provenance, and marks overall cost `UNKNOWN` if any required component is unpriced.<br>• In `task_runner.py`, worker and critic are priced using their respective model rate cards and combined via `combine_task_costs()`; persists structured `task{tid}_a{attempt}_cost.json` and records `[COST_BASIS: {basis}]` in `critic_notes`.<br>• `audit_ledger_costs()` inspects `critic_notes` for `[cost_basis: measured_invoice]`, preserving invoice classification through the ledger round-trip. | `tests/test_cost_accounting.py`: `test_04_measured_invoice_priority` (asserts explicit `is_invoice=True` is required; omission falls back to rate card) and `test_14_combine_task_costs_and_ledger_invoice_roundtrip` (verifies multi-role sum, unknown propagation, and ledger invoice roundtrip). |
| **RR5** | High | Structured Review Authentication & Fitness Invariant | `orchestrator/operator_auth.py:120`<br>`orchestrator/cost_accounting.py:293`<br>`orchestrator/ledger.py:345` | • In `operator_auth.py`, added `create_operator_review()` generating cryptographically signed Ed25519 tokens (`[OPERATOR_REVIEW_TOKEN: <token>]`) bound to `task_id`, `artifact_sha256`, and timestamp.<br>• In `cost_accounting.py`, `is_genuine_operator_review()` verifies Ed25519 tokens against task and artifact SHA-256. Enforces strict fail-closed rejection of negative phrases (`": false"`, `"false"`, `"has not"`, `"not inspected"`, `"unreviewed"`).<br>• In `ledger.py`, `weekly_fitness` uses `independent_accuracy` for the fitness accuracy term (`acc`), and its exception handler fails closed (`spot_checked_independent = 0`, never falling back to permissive `not is_ai_performed`). | `tests/test_cost_accounting.py`: `test_11_negative_phrases_rejected_in_human_review_provenance` (asserts `OPERATOR-VERIFIED: false` and `"The operator personally has not inspected this report."` strictly return `False`) and `test_13_structured_operator_token_authentication` (verifies valid signed token passes and mismatched task/sha fails). |

---

## 2. Technical Implementation Details

### RR2: Shared Runtime Budget Controller
- **`orchestrator/budget_controller.py`:**
  - Manages per-task and shared pilot budgets using atomic JSON state files protected by file locks (`_budget_lock`).
  - `reserve(role, model_str, prompt_text)`: calculates maximum expected cost using `RATE_CARD_2026` (with safety margin for unbounded output) and reserves the amount from available budget. Raises `BudgetExhaustedError` if remaining budget is insufficient, or `UnboundedPricingError` if budget enforcement is `"hard_stop"` and model is unpriced.
  - `reconcile(reservation_id, actual_cost_usd, actual_tokens)`: replaces reserved cost with actual measured/estimated consumption and commits to shared ledger.
  - `release_reservation(reservation_id)`: safely refunds unconsumed reservation if execution encounters an exception.
- **`orchestrator/distribution.py`:**
  - Removed `max(0.01, ...)` cap inflation. `per_task_budget = round(float(max_cost) / len(held_out_manifest), 6)`. Sub-cent pilots (e.g. $0.005 across 4 tasks) allocate exactly $0.00125 per task.
  - Threads `shared_budget_id=pilot_id`, `shared_max_budget_usd=float(max_cost)`, and `shared_max_tokens=int(max_tokens)` to each admitted task.
- **`orchestrator/task_runner.py`:**
  - Worker execution: reserves before `execution.worker_with_failover`, reconciles on completion, releases in `finally` block if interrupted.
  - Repair loop: reserves before each repair iteration, reconciles on completion, breaks gracefully if budget exhausted.
  - Critic execution: reserves before `evaluation.run_critic`, reconciles on completion, releases in `finally` block if interrupted.

### RR3: Deliverables Sanitization & Campaign Export Gating
- **`orchestrator/client_reporter.py`:**
  - In `extract_keywords_from_deliverable()`, `extract_negatives_from_deliverable()`, and `extract_ad_copies_from_deliverable()`, all cell strings are sanitized via `re.sub(r"^[`'\"]+|[`'\"]+$", "", val).strip()` *before* evaluating truthiness or length.
  - Rejects empty strings, strings $< 2$ chars, and placeholders (`"n/a"`, `"none"`, `"``"`).
  - In `compile_and_export_client_package()`, validates the compiled campaign entities: if `len(campaign.ad_groups) == 0` or total keywords == 0 or negatives == 0 or ads == 0 on a verified non-draft path, halts export immediately with `EXPORT_BLOCKED` and zero-entity campaign error.
- **`orchestrator/evidence_gate.py`:**
  - In `check_required_deliverables()`, verifies that deliverables parse into substantive entities. If any required deliverable yields 0 parsed keywords, negatives, or RSA variants, fails closed (`can_approve == False`).
- **`orchestrator/campaign_builder.py`:**
  - In `build_campaign_from_deliverables()`, skips empty keywords and attaches RSA ads only if non-empty headlines and descriptions are present.

### RR4: Cost Provenance & Multi-Role Accounting
- **`orchestrator/cost_accounting.py`:**
  - In `calculate_task_cost()`, only explicit `is_invoice is True` produces `CostBasis.MEASURED_INVOICE`. Omitted or False defaults honestly to `CostBasis.ESTIMATED_TOKEN_RATE` (if in rate card) or `CostBasis.UNKNOWN`.
  - Added `combine_task_costs(costs: list[TaskCost | None]) -> TaskCost`: sums dollar costs across execution roles, preserves individual role breakdowns in `provenance["role_breakdowns"]`, and propagates `CostBasis.UNKNOWN` if any role is unpriced.
  - In `audit_ledger_costs()`, inspects `r["critic_notes"]` for `[COST_BASIS: measured_invoice]`, preserving explicit invoice evidence across ledger queries.
- **`orchestrator/task_runner.py`:**
  - Calculates worker cost using worker model, critic cost using critic model, and combines them via `combine_task_costs()`.
  - Persists structured `runs/task{tid}_a{attempt}_cost.json` containing complete role breakdowns.
  - Appends `[COST_BASIS: {task_cost.basis.value}]` to `critic_notes` for ledger persistence.

### RR5: Structured Operator Review Authentication & Fitness Invariant
- **`orchestrator/operator_auth.py`:**
  - Added `create_operator_review(task_id, artifact_sha256, verdict, notes) -> str`: produces cryptographically signed Ed25519 tokens bound to `task_id`, `artifact_sha256`, and timestamp.
- **`orchestrator/cost_accounting.py`:**
  - `is_genuine_operator_review()` extracts `[OPERATOR_REVIEW_TOKEN: <token>]` and verifies cryptographic Ed25519 signatures, ensuring token `task_id` and `artifact_sha256` match the audited entity.
  - For legacy text notes, enforces fail-closed rejection of negative polarity (`": false"`, `"false"`, `"not inspected"`, `"has not"`, `"did not"`, `"not reviewed"`, `"ai-performed"`).
- **`orchestrator/ledger.py`:**
  - In `weekly_fitness()`, accuracy term `acc` uses `independent_accuracy` (only genuine operator reviews contribute).
  - Exception handler fails closed: `spot_checked_independent = 0; independent_pass = 0`.

---

## 3. Empirical Verification Results

### A. Full Test Gate
Executed full model-free test gate:
```powershell
python tests/run_all.py
```
**Result:** **`106/106 suites green (tiers: unit, containment, integration)`**, exit 0, `FAIL_COUNT=0`.

### B. Targeted Regression Suites
Executed focused suites covering RR1–RR7:
```powershell
python -m unittest tests/test_distribution_cli.py tests/test_evidence_gate.py tests/test_cost_accounting.py tests/test_browser_real.py tests/test_sample_remediation.py
```
- `tests/test_distribution_cli.py`: **19/19 PASS** (including sub-cent budget allocation and shared runtime budget exhaustion)
- `tests/test_evidence_gate.py`: **16/16 PASS** (including normalized-empty markdown cells fail-closed)
- `tests/test_cost_accounting.py`: **14/14 PASS** (including strict invoice omission, negative phrase rejection, Ed25519 token verification, and multi-role cost composition)
- `tests/test_browser_real.py`: **16/16 PASS** (including CDP Fetch interception and iframe status pinning)
- `tests/test_sample_remediation.py`: **11/11 PASS**

**Total focused assertions:** **76/76 tests green, ZERO skips, ZERO failures.**

### C. Workspace Cleanliness & Integrity
Verified zero workspace corruption:
```powershell
git status -s workspace/
```
**Result:** Empty (0 modified files, 0 untracked files).

---

## 4. Instructions for Codex Independent Reverification

To independently confirm the repairs:

1. **Verify Shared Runtime Budget Enforcement (RR2):**
   ```powershell
   python -m unittest tests.test_distribution_cli.DistributionCLITests.test_pilot_subcent_budget_allocation_no_inflation tests.test_distribution_cli.DistributionCLITests.test_shared_runtime_budget_exhaustion
   ```
   Expect: PASS. Verifies that $0.005 budget does not inflate to $0.04 and shared budget exhaustion blocks subsequent task reservations.

2. **Verify Normalized-Empty Campaign Export Fail-Closed (RR3):**
   ```powershell
   python -m unittest tests.test_evidence_gate.TestEvidenceGate.test_normalized_empty_markdown_cells_fail_closed
   ```
   Expect: PASS. Verifies that markdown table cells containing ` `` ` fail deliverable checks, refuse approval, and fail closed with `EXPORT_BLOCKED`.

3. **Verify Cost Provenance & Invoice Omission (RR4):**
   ```powershell
   python -m unittest tests.test_cost_accounting.TestCostAccounting.test_04_measured_invoice_priority tests.test_cost_accounting.TestCostAccounting.test_14_combine_task_costs_and_ledger_invoice_roundtrip
   ```
   Expect: PASS. Verifies that omitting `is_invoice` defaults to token rate card, and multi-role costs sum accurately.

4. **Verify Structured Review Authentication (RR5):**
   ```powershell
   python -m unittest tests.test_cost_accounting.TestCostAccounting.test_11_negative_phrases_rejected_in_human_review_provenance tests.test_cost_accounting.TestCostAccounting.test_13_structured_operator_token_authentication
   ```
   Expect: PASS. Verifies that `OPERATOR-VERIFIED: false` and `"The operator personally has not inspected this report."` return `False`, and signed Ed25519 tokens authenticate genuine reviews.

5. **Run Full Test Gate:**
   ```powershell
   python tests/run_all.py
   ```
   Expect: 106/106 suites green.

6. **Verify Clean Workspace:**
   ```powershell
   git status -s workspace/
   ```
   Expect: empty.

Write ownership on `PRODUCT-REPAIR-RR2-RR5-2026-10-05` is hereby **RELEASED** for Codex's independent review.

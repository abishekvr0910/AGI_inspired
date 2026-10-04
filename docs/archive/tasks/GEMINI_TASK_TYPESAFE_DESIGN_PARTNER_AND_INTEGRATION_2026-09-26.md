# Gemini Directive: TypeSafe/Jev Design-Partner Integration and Partner-Ready Evidence

**From:** Codex, independent reviewer and execution planner  
**To:** Gemini CLI, forward implementer and final documentation owner  
**Date:** 2026-09-26  
**Task ID:** `TYPESAFE-DESIGN-PARTNER-INTEGRATION-2026-09-26`  
**Objective:** Finish every safe local backlog item, make the TypeSafe/Jev integration genuinely implementation-ready, and produce an honest partner-pitch package for TypeSafe first and Microsoft/AWS/Meta second. Execute all unblocked phases continuously and return one final evidence-backed report.

---

## 0. Operating rule: continue, but do not cross authorization boundaries

"Do not stop" means: do not pause after each phase, do not wait for praise or confirmation, and do not merely describe work that can safely be completed locally. Continue through every unblocked phase below, run the checks, repair failures, synchronize the canonical state, and report once at the end.

It does **not** authorize any of the following:

- disengaging ESTOP or opening a controlled live window;
- making live Jev, provider, or paid API calls;
- contacting Diogo Almeida, Erik Gafni, TypeSafe, Microsoft, AWS, Meta, investors, prospects, or any other external party;
- sending email, direct messages, forms, posts, or applications;
- adding credentials, widening egress, incurring spend, pushing, merging, or publishing;
- claiming a live Jev integration, benchmark, customer, partnership, endorsement, or independently achieved TypeSafe speed/cost result.

If an external credential, API allocation, approval, or human decision is required, finish every other safe local deliverable and write the exact request into `workspace/typesafe/OPERATOR_ACTION_REQUIRED.md`. Do not idle or fabricate a substitute.

---

## 1. Mandatory bootstrap and ownership

Before modifying anything:

1. Follow `AGENTS.md` in order.
2. Read `.harness/continuity/current.json`, `docs/ACTIVE_WORK.json`, `docs/CURRENT_STATE.md`, `docs/CANONICAL_ARCHITECTURE.md`, this directive, and `docs/CODEX_HANDOFF_2026-09-26_TYPESAFE_AI_AND_INVESTMENT.md` completely.
3. Run:

   ```powershell
   python orchestrator/continuity.py recover
   python orchestrator/continuity.py validate
   python tests/run_all.py
   python -B orchestrator/operator_cli.py status
   git status --short --branch
   git diff --check
   ```

4. Register a new active entry in `docs/ACTIVE_WORK.json` before implementation. Own only the paths required by this directive. If another active owner overlaps, do not edit the overlap; use an isolated worktree or wait for release as required by the registry.
5. Keep ESTOP engaged, zero live execution, zero spend, and `MAX_REPAIR_ATTEMPTS=2` throughout.

Live state wins over this document. Any baseline claim below must be re-measured.

### Baseline observed by Codex

- `python tests/run_all.py`: **98/98 suites green**, exit 0.
- Continuity revision 152: recovery discrepancies `[]`; validation passes.
- ESTOP engaged; batch lock free; no active task owner.
- Branch `product/v1-completion-2026-09-15`: 16 commits ahead of upstream; no push authorized.
- `python tests/test_typesafe_evaluator.py` in the Codex restricted filesystem sandbox still raises two `PermissionError` failures under `workspace/_test_tmp`, even though the canonical runner passes and Gemini separately reported `python -m unittest tests/test_typesafe_evaluator.py` green. Treat this as an unresolved portability discrepancy, not as a completed fix.

---

## 2. Phase A: close the audit backlog completely

### A1. Reproduce and fix both direct test entry points

The following must both pass from the repository root, in addition to the canonical gate:

```powershell
python tests/test_typesafe_evaluator.py
python -m unittest tests/test_typesafe_evaluator.py
```

Requirements:

- Six tests must run; zero skip, failure, or error.
- CSV input and `EvidenceGate` state must be isolated from repository production state.
- Temporary files must be writable and cleanly removable under normal Windows, restricted-token execution, and workspace-constrained agent environments.
- Do not solve this by weakening filesystem containment, disabling cleanup, swallowing `PermissionError`, or writing fixtures into production client/evidence paths.
- Prefer an explicitly injected temporary root supplied by the test runner. If a workspace fallback is necessary, create it with deterministic permissions, unique process/test ownership, and guaranteed cleanup. Prove cleanup with a test.
- `evaluate_prospects` must continue accepting an injected gate and CSV path; the production default remains unchanged.

### A2. Claims and terminology sweep

Search every TypeSafe-facing artifact, not only the tracked files:

```powershell
rg -n "97/97|82 unit|revision 151|3,962|4/4|437x|443\.75x|450x|48ms|48 ms|Null/Bool|we benchmarked Jev|integrated Jev|zero hallucinations|first end-to-end|impeccable" docs workspace scripts tests .harness
```

For each hit, either remove/correct it or document why it is historical and unambiguous. Current claims must use:

- official primitives: `Noul`, `Choice`, `Score`;
- TypeSafe vendor-published workflow figures, clearly attributed: 193.6x faster and 444.6x cheaper, with the displayed $0.000081 / 0.114s versus $0.013880 / 8.566s comparison;
- TypeSafe's published single-decision range of 70-500ms only when sourced as a vendor claim;
- wording such as "proposed integration", "reference architecture", or "integration-ready testbed" until a real Jev request/response is executed with authorization;
- "vendor-published" rather than "our benchmark" for TypeSafe figures.

Primary sources:

- `https://typesafe.ai/`
- `https://typesafe.ai/blog/introducing-system-one-models-and-jev`
- `https://evals.typesafe.ai/`
- `https://typesafe.ai/team`
- `https://www.dcvc.com/news-insights/typesafe-emerges-from-stealth-with-a-new-way-of-doing-ai/`

Do not rely on Wikipedia, scraped biographies, social posts, or secondary press when an official source exists. Do not claim a $200M valuation, a personal X handle, or other investor-sensitive fact without a direct primary source.

### A3. Canonical-document consistency

Synchronize at minimum:

- `docs/CODEX_HANDOFF_2026-09-26_TYPESAFE_AI_AND_INVESTMENT.md`
- `docs/reviews/GEMINI_REVIEW_TYPESAFE_AI_SYNERGY_AND_INVESTMENT_2026-09-26.md`
- `docs/CURRENT_STATE.md`
- `workspace/INVESTOR_AND_TYPESAFE_OFFERING_MEMORANDUM.md`
- `workspace/TYPESAFE_AI_PARTNERSHIP_DOSSIER.md`
- `workspace/TYPESAFE_LEAD_EVALUATION.md` and JSON output
- `.harness/continuity/current.json`

No document may say the repository is clean if it is dirty, call an emulator a Jev integration, or present vendor metrics as local empirical results. Historical gate counts may remain only when explicitly dated and scoped to their historical landing.

### Phase A done when

- both direct evaluator commands pass 6/6;
- the canonical gate is green;
- the claims sweep has no unexplained current false/stale hits;
- continuity recovery has no discrepancies and validation passes;
- the review dossier lists limitations as well as strengths.

---

## 3. Phase B: build an honest Jev integration seam

The goal is integration readiness without inventing TypeSafe's private API contract.

### B1. Contract discovery gate

Read the current official TypeSafe API/primitives documentation. Record the exact public request, response, authentication, error, rate-limit, and confidence semantics in `workspace/typesafe/JEV_INTEGRATION_SPEC.md` with source URLs and retrieval date.

If the public contract is incomplete or early-access-only:

- do not guess endpoints or payload fields;
- implement only a transport-agnostic local interface and fake transport tests;
- list the missing contract fields in `OPERATOR_ACTION_REQUIRED.md`.

### B2. Local typed decision interface

Create a small, isolated module only if it fits the verified architecture. Suggested shape:

- `NoulDecision`: probability/confidence plus Boolean outcome;
- `ChoiceDecision`: allowed choices, probability distribution, selected choice, confidence;
- `ScoreDecision`: bounded scale, score/distribution, confidence;
- a `DecisionBackend` protocol with dependency-injected transport;
- deterministic local rubric backend preserving current behavior;
- optional Jev backend disabled by default and impossible to invoke without explicit configuration and credentials;
- bounded timeouts, response/schema validation, redacted errors, and fail-closed behavior;
- no secrets in repository files, logs, exceptions, fixtures, or output.

Do not call the module "Jev" if it is only a generic contract. Do not add a live network test to the default tiers. Any future live test must be separately tiered and require explicit operator acknowledgement.

### B3. Integrate without replacing the safe default

- Allow the lead evaluator to accept an injected decision backend.
- Preserve the deterministic rubric as the default zero-spend path.
- Ensure `EvidenceGate` remains authoritative; model output can never authorize outbound export.
- Keep TypeSafe decisions advisory for scoring/routing until independently calibrated.
- Add hermetic tests for valid decisions, malformed distributions, out-of-range scores, unknown choices, timeouts, credential absence, and evidence-gate precedence.

### B4. Reproducible benchmark harness

Create `workspace/typesafe/BENCHMARK_PROTOCOL.md` and, where useful, a model-free benchmark runner that records:

- dataset version/hash;
- decision definitions and expected labels;
- backend and model identity;
- warmup policy and sample count;
- end-to-end latency distribution, not one cherry-picked number;
- input/output units and actual billed cost;
- accuracy/calibration/schema-error rate;
- failures, retries, timeouts, and confidence thresholds;
- separation of `vendor_published`, `locally_measured`, and `modeled` fields.

Until authorized Jev access exists, the harness may validate the deterministic/fake backends only. It must print `JEV_LIVE_MEASUREMENT_NOT_RUN` rather than substitute vendor figures into a local-results field.

### Phase B done when

- the public/private contract boundary is explicit;
- the local interface and all model-free tests pass;
- production defaults remain offline, deterministic, and evidence-gated;
- no document implies a live Jev integration;
- the benchmark protocol can be executed immediately after legitimate API access is supplied.

---

## 4. Phase C: create the design-partner and incubation package

Create or update these operator-review artifacts under `workspace/typesafe/`:

1. `DESIGN_PARTNER_ONE_PAGER.md`
2. `SECURITY_AND_ARCHITECTURE_BRIEF.md`
3. `DEMO_RUNBOOK.md`
4. `BENCHMARK_PROTOCOL.md`
5. `OUTREACH_PACKET.md`
6. `TARGET_AND_ASK_MATRIX.md`
7. `OPERATOR_ACTION_REQUIRED.md`

### C1. One-page value proposition

Use this honest core statement:

> AGI_like is a tested, fail-closed execution and evidence chassis for autonomous agents. It constrains identity, filesystem and network access, mechanically validates evidence, blocks unverified external action, and records an attested lifecycle. We propose Jev as the typed micro-decision layer and seek early access to build and publish a reproducible integration benchmark.

Distinguish:

- **implemented and tested locally**;
- **observed in historical controlled runs**;
- **vendor-published TypeSafe metrics**;
- **proposed/not yet executed**.

### C2. Demonstration runbook

Design a two-to-five-minute **offline** demonstration using existing fixtures:

1. ingest hostile/untrusted content;
2. show denied direct filesystem/network action;
3. allow policy-approved research through the broker/browser fixture;
4. fail an unsupported citation mechanically;
5. block an unverified lead export;
6. show the signed task lifecycle/evidence record;
7. show the injected decision-backend seam and explicitly state that Jev live execution awaits access.

Do not fabricate screenshots or output. Every displayed claim must have a reproducible command and artifact path.

### C3. TypeSafe outreach packet

Prepare, but do not send:

- a concise email to Diogo Almeida and Erik Gafni;
- a shorter LinkedIn/contact-form version;
- a technical follow-up for an engineer;
- a 30-minute meeting agenda;
- answers to likely objections: no live Jev test yet, Windows focus, open-source/licensing intent, security proof, benchmark neutrality, and what exactly TypeSafe receives.

Ask in this order:

1. early Jev API access and an engineering contact;
2. design-partner relationship;
3. joint reproducible benchmark and technical case study;
4. integration/incubation or a paid pilot;
5. only after technical fit: strategic investment, employment/acqui-hire, or deeper partnership discussion.

Never lead with "fund us" or "you are missing our technology." Lead with a concrete workload, testbed, and mutual deliverable.

### C4. Large-company variants

Prepare tailored, honest variants:

- **Microsoft first:** Windows Agentic / Windows 365 for Agents / Entra agent identity. Emphasize independent Windows-native containment evidence and compatibility research. Do not claim Microsoft lacks isolation.
- **AWS second:** Bedrock AgentCore Runtime, Browser, Evaluations, and Observability. Emphasize portable mechanical verification, evidence gating, and signed audit interoperability. Do not claim AWS lacks secure runtimes.
- **Meta third:** Llama Firewall, Prompt Guard, and the Agents Rule of Two. Emphasize enforceable separation of untrusted input, sensitive access, and state-changing action. Prefer an open security benchmark/research contribution.

For every target, specify the receiving team/profile, our evidence, the narrow ask, mutual benefit, and why the pitch is credible now. Do not invent employee names or contact details.

### Phase C done when

- all seven artifacts exist and agree with each other;
- the primary ask is design partnership/API access, not an unsupported investment pitch;
- TypeSafe, Microsoft, AWS, and Meta variants are materially different;
- no message has been sent;
- every demo claim is reproducible locally.

---

## 5. Phase D: package integrity, safety, and final handoff

### D1. Security and disclosure review

- Scan the proposed package for API keys, tokens, private paths, personal data, real prospect contact data, unverified waste estimates, and confidential ledger content.
- Use only sanitized sample data in externally shareable artifacts.
- Clearly label sample, vendor claim, local measurement, historical evidence, and proposal.
- Do not publish the repository or bundle without operator authorization.

### D2. Required verification

Run and capture:

```powershell
python tests/test_typesafe_evaluator.py
python -m unittest tests/test_typesafe_evaluator.py
python tests/run_all.py
python orchestrator/continuity.py recover
python orchestrator/continuity.py validate
python -B orchestrator/operator_cli.py status
git diff --check
git status --short --branch
```

Acceptance requires:

- both direct evaluator invocations green;
- full dynamic N/N gate green, exit 0, with zero `[FAIL]`, `FAILED`, or `ERROR` result lines;
- ESTOP engaged, no running task/zombie, no canary marker, batch lock free;
- continuity discrepancies `[]` and size at or below 4,096 bytes;
- no unapproved push, merge, egress widening, credential use, spend, or outreach;
- `MAX_REPAIR_ATTEMPTS=2` unchanged.

### D3. Canonical synchronization

- Update `docs/ACTIVE_WORK.json`, `docs/CURRENT_STATE.md`, and `.harness/continuity/current.json` to exact live truth.
- Record all changed and new paths; live `git status --porcelain` must match continuity exactly.
- Keep historical results historically scoped; do not rewrite prior evidence as if measured today.
- Write the final Gemini review/handoff under `docs/reviews/` with limitations and operator-required actions.

### D4. One final report only

At completion, report:

- exact files changed/created;
- direct-test and full-gate results;
- continuity validation and live safety state;
- what is implemented versus proposed;
- whether Jev was actually called (expected: **no**, absent explicit later authorization);
- remaining operator actions, especially API access and approval to send outreach;
- branch state and explicit confirmation of no push/outreach/spend.

Do not declare completion if any required check is red. Do not remain in a background-monitoring limbo: wait for gates to finish, inspect their exit/output, repair failures, and rerun. If the only remaining blocker is external authorization, mark the local package complete and the external action explicitly blocked in `OPERATOR_ACTION_REQUIRED.md`.

---

## 6. Absolute invariants

- ESTOP stays engaged.
- No live model/provider/Jev call.
- No outreach or public post.
- No push or merge.
- No egress allowlist change.
- No secret handling outside the existing secret bridge.
- No invented API contract, benchmark, partnership, customer, endorsement, or valuation.
- EvidenceGate remains authoritative for outbound eligibility.
- `MAX_REPAIR_ATTEMPTS` remains 2.
- Live state and parsed artifacts outrank summaries.

This task succeeds by leaving a truthful, reproducible, integration-ready package that an operator can confidently use to request TypeSafe early access and a design partnership. It does not succeed by producing louder claims.

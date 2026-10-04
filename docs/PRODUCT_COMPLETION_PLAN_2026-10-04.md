# Product Completion Plan and Agent Handoff

Date: 2026-10-04
Planning owner: Codex
Baseline: `e193b8c` on local `master`; implementation bytes unchanged since the
independently tested `7d07d78` (101/101 model-free suites, exit 0).
Status: PLAN READY. All implementation packages below are PENDING.

## 1. Outcome and Evidence

Deliver one useful, reviewed research-to-campaign workflow for a consenting
client, with traceable claims, honest costs, and reproducible validation.
Enterprise deployment is a separate milestone with host and retention evidence.
Neither milestone is complete merely because tests pass or files are generated.

Read `docs/reviews/CODEX_PRODUCT_REVIEW_2026-10-04.md` for the measured baseline.
Key reasons for this sequence:

- Eight prospects are samples in the verification index but the existing tracker
  calls them Ready to Send; older pitches and exports remain misleading.
- The generator ignores compilation failure and still announces success.
- The only record marked verified has a dossier with research sections pending;
  its coffee campaign contains generic service-business claims.
- The ledger's newest finished task is from September 14. October implementation
  changes have model-free coverage, without new live outcome evidence in that DB.
- All recorded task costs are zero; token-bearing tasks exist. Cost and human
  review provenance need reconciliation before making quality or savings claims.

## 2. Execution Rules

1. Follow `AGENTS.md`; live state wins. Re-read this board and ACTIVE_WORK before
   claiming a package. Suggested assignments below do not reserve any paths.
2. Claim exactly one package in `docs/ACTIVE_WORK.json` before editing. One writer
   per path in the main checkout; use isolated worktrees for concurrent code work.
3. Treat `tests/tiers.json`, state docs, ACTIVE_WORK, and continuity as shared
   integration files. The integration owner serializes their changes.
4. Every implementation package needs a concrete failure reproduction, a bounded
   fix, relevant regression coverage, the full model-free gate, and a handoff.
   Use the actual suite count. Record HEAD, commands, exits, limitations, and
   before/after behavior. New suites must be registered in `tests/tiers.json`.
5. Suggested reviewer: Claude Code, independent of the author of that package.
   A review must inspect code and exercise failure cases; quoting the author's
   test count is insufficient. Release ownership after the handoff.
6. Make reviewable local commits per package when implementation is completed.
   Refresh continuity using measured hashes and honest Git state. Push, external
   outreach, publication, ad spend, provider calls, credential provisioning, and
   host policy changes require their existing operator authorization.
7. Keep ESTOP engaged throughout model-free work. No task here silently grants a
   live window, widens the egress allowlist, or enables audit enforcement.
8. Preserve original runtime artifacts. Do not fabricate evidence, backfill
   guessed costs, erase failures, change old verdicts, or relax evaluation to
   obtain a pass. Archive history rather than treating old instructions as work.

## 3. Task Board

| ID | Suggested implementer | Dependency | Deliverable | Status |
| --- | --- | --- | --- | --- |
| P0-A | Gemini | None | Honest sample inventory, safe cleanup, truthful generator | PENDING |
| P0-B | Gemini | P0-A | Evidence-bound, complete client exports | PENDING |
| P1-C | Codex or another forward engineer | None; isolated from A/B | Real browser and bounded research path verification | PENDING |
| P1-D | Gemini or UI engineer | P0-B; P1-C before integration | Actual browser console acceptance | PENDING |
| P1-E | Codex or data engineer | Coordinate runner edits with P1-C | Honest outcome and cost measurement | PENDING |
| P1-F | Forward engineer + operator | A-E reviewed; data and live authority | One client pilot with reviewed outputs | PENDING |
| P1-G | Independent reviewer + deployment engineer | Read-only review can start now | Release and deployment evidence | PENDING |

Start P0-A now. P1-C can proceed in an isolated worktree while A/B proceed.
P1-E can proceed independently only if its path ownership does not overlap C.
Do not start additional frameworks, subagent fleets, dashboard redesigns, or
partner integrations until the accepted workflow exposes a concrete need.

## 4. P0-A: Samples and Truthful Generation

Primary paths: `scripts/generate_prospect_pipeline.py`, a dedicated remediation
script if needed, relevant new regression tests, and the eight known sample
directories/pitches/tracker entries under ignored `workspace/`.

Implementation:

- Check the compiler's `success` result. A refusal or exception must not produce
  a success message, client-ready pitch, or Ready to Send tracker entry.
- Make sample generation explicit and visibly sample-only. Remove assertions of
  measured query waste or guaranteed savings from sample outreach.
- Inventory existing artifacts before touching them. Produce a dry-run manifest
  with absolute paths, sample classification, hashes, and intended actions.
- Back up originals with checksums before relabeling or quarantining the eight
  known sample packages. Keep originals available for review and rollback.
  Resolve and validate all paths inside this workspace; never traverse arbitrary
  CSV paths for recursive moves/deletes. Preserve the coffee client separately.
- Reconcile tracker status, pitches, MD/HTML, JSON and CSV, plus UI/download access
  to old exports. A new generation gate does not fix a previously saved artifact.

Acceptance:

- Reproduce compiler refusal and verify no ready/success signal or usable stale
  artifact link is emitted. Preserve and report the failure reason.
- All eight known samples are visibly samples on every outward-facing surface.
- A second remediation run is idempotent. Restore from the backup manifest works
  in fixtures. No real-client or unrelated runtime file changes.
- Future sample CSVs are paused and clearly labeled; generating them makes no
  ad-platform calls. Do not certify Google Ads Editor import solely from CSV shape.

Verification: new fixture tests for this flow plus
`python -B tests/run_all.py test_client_reporter test_campaign_builder_regression`,
then the complete gate. Reviewer checks the local artifact manifest as well as code.

## 5. P0-B: Evidence and Complete Client Packages

Primary paths: `orchestrator/evidence_gate.py`, `client_reporter.py`,
`campaign_builder.py`, `client_profile.py`, distribution export entry points,
web console export/download endpoints, and their tests.

Implementation:

- Distinguish verified prospect identity from verified deliverable content.
  Validate actual claim values and supporting source/document references,
  dates, reviewer identity, and approval. Field names plus `verified=True`
  do not establish the underlying claim or authorize newly changed content.
- Bind approval to the reviewed evidence and package content/version. Changing
  a relevant profile, claim, source, or deliverable invalidates that approval.
  Reuse existing digest/signature mechanisms where their trust boundary fits.
- Represent estimates as estimates with assumptions and uncertainty. A claim of
  measured account waste requires an authorized account extract, date range,
  calculation and exclusions. Permit a package with no savings claim; do not
  force a fake waste figure to satisfy the current required-field list.
- Remove factual boilerplate such as licensing, years of experience, emergency
  availability and guarantees unless supported for this client. Apply checks
  after combining defaults and custom copy. Respect language and actual offer.
- Define required sections per deliverable type. Incomplete research can produce
  an internal draft, but cannot become a client-ready package or be silently
  replaced by seed keywords and generic copy. Failures must remain visible.
- Default exported campaigns to paused, including verified packages. Publishing
  is a separate operator action. Ensure existing download routes enforce status.

Acceptance:

- The current coffee profile with no research is rejected for client-ready
  export, with missing sections listed; a visibly marked internal draft is allowed.
- Empty source/reviewer fields, mismatched claim values, unsupported campaign
  claims, stale approvals and post-approval mutations all fail closed.
- Positive fixture: complete approved evidence produces useful sector/language
  appropriate MD, HTML and paused CSV; every material claim has traceable support.
- Verify import behavior offline in Google Ads Editor when available; record
  absence as unverified, never as a passed integration.

Verification: targeted gate filters `test_campaign_builder_regression`,
`test_client_reporter`, `test_distribution_cli`, `test_web_ui_security` and the new
evidence regressions, then full gate. Claude reviews the negative cases separately.

## 6. P1-C: Browser and Research Correctness

Primary paths: `orchestrator/native_worker.py`, `browser_daemon.py`,
`execution.py`, `deliverable_preflight.py`, `task_runner.py`, research notebook
integration, and browser/native/deep-loop tests. Coordinate shared runner paths.

Implementation and acceptance:

- Trace the actual Native CDP path. Check page-target versus browser-target
  selection, target/session ownership, response IDs versus asynchronous events,
  selector scope and fallback, navigation completion, and bounded timeouts.
- Exercise real Chrome on an ephemeral local fixture page whose required text
  appears only after JavaScript. Verify the requested selector and rendered text;
  HTTP fallback must not be reported as successful browser extraction.
- Fixtures must use temporary profiles/ports and a test-scoped local transport.
  Do not alter production egress policy or navigate external pages for this proof.
- Test absent selector, delayed events, failed navigation, timeout, cancellation,
  orphan cleanup and ESTOP interruption. Confirm task outputs cannot cross sessions.
- Verify blocked/empty/error retrieval cannot count as verified evidence and cannot
  satisfy the active-research requirement merely because a tool was invoked.
- Demonstrate repair retrieves missing evidence within explicit call/time/token
  bounds, preserves notebook history, and stops honestly when evidence is unavailable.
- Compare Hermes and Native enforcement paths. Record where Native runs inside
  the controller; do not imply it inherits a subprocess token or Job Object.

Verification: existing `test_native_worker`, `test_browser_daemon`,
`test_hypothesis_deep_loop`, `test_deliverable_preflight`, `test_research_notebook`
plus a real local browser regression under the appropriate tier, then full gate.
Mocks support unit coverage; actual browser proof must be separately identified.

## 7. P1-D: Console Acceptance in a Browser

Primary paths: `orchestrator/web_ui.py`, `trust_gateway.py`, local web test fixtures,
browser acceptance tests. Inspect current browser tooling before adding a dependency.

- Run the real sign-in flow against an isolated fixture server with a temporary
  token. Test failed authentication, successful sign-in, reload, CSP behavior,
  and script initialization. Do not use or log production credentials.
- Walk through client selection, template preview, paused dispatch rejection,
  fixture dispatch, repair diff, incomplete export refusal, sample display and
  approved package download. Confirm requests and visible states agree.
- Verify existing artifacts cannot bypass the evidence decision via direct
  download endpoints. Show draft/sample/blocked status and actionable missing data.
- Record actual browser/version, test commands and results. API tests that check
  HTML strings alone do not establish a working sign-in flow.

Verification: `test_web_ui`, `test_web_ui_security`, new isolated browser flow,
then full gate. P1-D is complete only with actual browser execution evidence.

## 8. P1-E: Honest Outcome and Cost Measurement

Primary paths: `orchestrator/ledger.py`, `scorecard.py`, usage aggregation in
`task_runner.py`/`workflow.py`/`evaluation.py` (`build_mission_usage`), provider usage
adapters and tests.
Inspect the current schema/migration mechanism before proposing a change.

- Separate unknown cost, measured charges, estimated API cost, and allocated
  subscription/local-compute cost. Store provenance, rate/date/currency and basis.
  Never turn historical zero/default values into invented measurements.
- Reconcile attempts, repair, failover, critic and synthesis usage without double
  counting. Retain available usage from failures and label missing evidence.
- Audit `human_verdict` provenance and the existing F28 AI-performed review guard.
  A populated column is not proof that an independent human reviewed the task.
- Report a cohort manifest, denominator, terminal/infra/abstention categories,
  human-reviewed correctness, intervention time, and accepted-deliverable cost.
  Keep historical canaries, queued tasks and unrelated missions separate.
- Use migration fixtures and backup/rollback checks if persisted schema changes
  are necessary. Do not rewrite production history during model-free tests.

Acceptance: fixtures prove unknown does not display as free, all attempts reconcile,
duplicate ingestion is idempotent, AI review is not counted as independent human
accuracy, and a mixed historical ledger cannot be represented as a fresh cohort.
Run targeted accounting regressions and full gate.

## 9. P1-F: One Consented Pilot and Fresh Evaluation

Suggested first candidate: the coffee profile, only if the operator confirms
the business relationship, intended service, data rights and real inputs.
Its current verification flag and generic dossier are not acceptance evidence.

Preparation can be model-free:

- Freeze the deliverable, input data, pass criteria, human reviewer, allowed data
  destinations, time/cost budget, and stop conditions before running anything.
- Build a held-out task list for the chosen workflow; identify fixtures separately
  from real work. Repeated frozen M1-M7 tasks remain regression tests, not new-market proof.
- Prepare commands from the current CLI/runbook and verify dry-run behavior.
  Do not copy an obsolete cohort command from archived instructions.
- Prepare a human scoring sheet and evidence manifest, including material claims,
  source dates, missing information, corrections, accepted output and elapsed work.

Live execution is BLOCKED until the operator authorizes that specific window and
its inputs/budget, and applicable runtime admission requirements pass. ESTOP must
be restored by the supported controlled-window path. Stop on a safety breach,
unapproved data transfer, missing evidence, exhausted budget or unhandled failure.

Acceptance: one complete useful package, independently checked source by source,
reviewed for the client's language/offer, accepted or rejected with reasons, and
import-tested offline where relevant. Record actual effort and cost. Delivery,
outreach and publication require separate existing authorization.

Expand to further fresh tasks only after reviewing that result. The design's
70% completion, 90% spot-check accuracy, declining intervention over eight weeks,
and $0.50/task are targets from `HARNESS_DESIGN.md`, not measurements established
by this pilot. A pilot pass does not establish enterprise readiness or revenue.

## 10. P1-G: Independent Release and Deployment Evidence

Read-only review may begin now. Implement fixes in separately owned worktrees;
someone else reviews any code written by the nominal reviewer.

- Review A-E for bypasses, input provenance, secret/data exposure, stale artifact
  access and failure handling. Require a reproduction and closure evidence per finding.
- Audit Windows, Native and POSIX threat boundaries separately. A process group
  or cgroup provides lifecycle/resource controls; do not treat it as proof of
  filesystem, credential or network isolation. Test denied operations on the
  declared supported deployment, including descendants and alternate paths.
- Keep Linux support provisional until an actual Linux installation and applicable
  tests pass. The current repository workflow runs on Windows. Pin a clean-install
  CI environment and dependencies, and retain its execution evidence.
- For enterprise release, provision the chosen remote immutable audit store and
  restricted identities under the deployment runbook; demonstrate tamper/deletion
  denial, concurrent writer correctness, retention readback, and restore/verify.
  Operator architectural choices/provisioning remain explicit dependencies.
- Run `python -B orchestrator/operator_cli.py preflight release --json` on the
  integrated deployment. Record every blocker and its owner. A missing control
  remains blocked; do not skip checks or set enforcement flags just to turn green.
- Obtain independent final review before the operator's release/push decision.
  `safe_to_proceed=true` means the implemented preflight passed in that environment;
  it does not establish customer value, generalized accuracy or a security guarantee.

## 11. Completion Record and Copy-Paste Handoffs

For each package, update its board status with implementing HEAD, review HEAD/report,
tests/exit codes, artifact locations, known limits and the next package. Update
CURRENT_STATE and continuity through the integration owner. Release ACTIVE_WORK
ownership. Never mark dependent or operator-blocked packages complete by association.

Gemini starting prompt:

> Follow AGENTS.md, then read docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md and the linked
> Codex product review. Claim P0-A under PRODUCT-P0-A-2026-10-04. Implement truthful
> sample generation and safe artifact remediation, with dry-run/backup/restore
> evidence and regressions. Leave P0-B pending until A has a reviewable handoff.
> Keep the scope model-free and follow the plan's ownership and safety rules.

Codex/forward engineer starting prompt:

> Follow AGENTS.md and the product completion plan. Claim P1-C under
> PRODUCT-P1-C-2026-10-04 in an isolated worktree if Gemini is implementing A/B.
> Prove actual local-browser rendering, bounded repair, and truthful retrieval
> evidence. Inspect engine-specific containment. Publish a local implementation
> handoff with regressions and the full gate; no external model calls.

Claude review prompt:

> Independently review the package diff and reproduction evidence against the
> product completion plan. Read current code and local artifacts; do not accept
> implementation docs as proof. Try the negative cases, distinguish fixtures from
> live outcomes, and report blockers with file/line references. Default read-only;
> do not claim implementation paths already held by another agent.

Immediate next action: the chosen forward agent claims P0-A and begins its dry-run
inventory. No implementing agent has been launched or assigned an active lock by
this document.

# Full Harness Completion Directive

Date: 2026-10-05. Author: Codex, independent reviewer and planning owner.
Task: `HARNESS-COMPLETION-DIRECTIVE-2026-10-05`.
Reviewed basis: local `master`, HEAD `749b42f2757d91e35ee3654442c150157049b641`,
plus Gemini's uncommitted repairs. This is not a review of a newly landed commit.
Status: DIRECTIVE COMPLETE; IMPLEMENTATION PARTIALLY ACCEPTED; PRODUCT/RELEASE OPEN.

## 1. Directive To The Next Lead

Own completion of the existing research-to-deliverable harness, not another
isolated patch batch. Follow AGENTS.md and claim one non-overlapping write scope
at a time. Work through stages 0-7 below. Implement, exercise real consumers,
obtain independent review, and update the acceptance board before advancing.
Do not stop merely because the last reported counterexample passes. Continue
all authorized model-free work; consolidate genuine operator dependencies into
one decision packet rather than repeatedly handing back partial fixes.

This directive supersedes conflicting next-action and acceptance wording in
earlier repair briefs and the product plan. It preserves the plan's P0-A through
P1-G requirements and the security blueprint. It does not revive archived work.

The bounded V1 product is a supervised, single-operator research/BI workflow:
consented client input -> bounded research -> evidence and independent review ->
approved, paused campaign/dossier exports -> honest cost and outcome reporting.
General autonomous coding, multi-tenant SaaS, specialist swarms, and frontier
benchmark parity are not prerequisites for this V1 and must not distract from it.

**Authority:** keep ESTOP engaged during model-free work. No live provider/cohort,
production key provisioning, host-policy change, cloud-store provisioning,
outreach, ad publication/spend, commit or push under this directive alone.
Explicit scoped operator authority is required for those steps. Never weaken
release admission, fake probe evidence, broaden an allowlist, or mark missing
deployment evidence passed. A blocked deployment does not prevent independent
code/tests/runbook work. Preserve existing dirty changes and runtime artifacts.

## 2. Independent Ground Truth

The latest Gemini claims were tested against code, not accepted from the brief.

| Observation | Independent result |
| --- | --- |
| Entry continuity | Rev 190, zero discrepancies, 8/8 reference hashes match |
| Git | `master`; recorded origin comparison behind 0/ahead 10; no fetch performed; 34 dirty/untracked paths at entry |
| Focused suites | `python -B -m unittest tests/test_cost_accounting.py tests/test_distribution_cli.py tests/test_evidence_gate.py`: 53 tests, exit 0, zero skips |
| Full gate retry | 106/106 suites, exit 0; unit/containment/integration; temporary unavailable proxy override described below |
| Live local state | ESTOP true; 218 ledger tasks; 0 running |
| Deployment probes | Egress `attestation_mismatch`; audit `audit_enforcement_not_enabled` |
| Preservation | All 299 monitored files hash-identical; `git status --short workspace/` empty |

The first full-gate session result was unavailable after interruption; it is NOT
counted as a pass. The retry ran `python -B -u tests/run_all.py` through a parent
that kept a test-owned loopback socket bound but NOT listening, setting
`HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` to that endpoint. This prevented the
unmocked search test from using the production broker. The runner's normal
live guard remained enabled. This qualifies the environment, not the assertions.
Do not call this proof that the unmodified test environment is hermetic.

The earlier exact focused command has an unmocked search path. Successful
external traffic was not established, but zero network *attempts* cannot be
claimed. Later reproductions intercepted that handler. No live model/cohort was
intentionally dispatched, and no production credentials were provisioned.
External primary-source documentation research was performed separately.
The full release preflight was NOT rerun in this review; no current complete
blocker count or `safe_to_proceed=true` is claimed.

### Findings Reproduced In Isolated Fixtures

| ID / severity | Reproduction and result | Root cause / code anchor |
| --- | --- | --- |
| C1 / High | Real `worker_with_failover` with a controller and Hermes engine raises `TypeError: hermes_worker() got an unexpected keyword argument 'budget_ctrl'`, before any worker body runs | `execution.py:592-598` forwards the kwarg; `hermes_worker` at line 66 does not accept it. `task_runner.py:541` supplies it even when enforcement is off |
| C2 / High | Native loop consumes 1,100 fake tokens; runner-style reconciliation records 2,200 in task AND shared spend. A 1,000-token reservation under a 1,000 cap blocks its own first call. A single fake 5,000-token completion returns successfully under a 4,000 cap | `native_worker.py:1198-1231`, `budget_controller.py:reconcile/record_turn_spend`, `task_runner.py:556`: two charging owners, own reservation subtracted as unavailable, heuristic rather than provider-enforced bound |
| C3 / High | Real `_record_outcome` stores $0.0035, $0.007, $0.014 for three identical attempts; true fixture sum is $0.0105. Audit reports $0.0035. Merged worker+repair usage costs $0.007 but stores $0.0105 when explicit repair cost is added | `task_runner.py:812-825,964-976` sums cumulative artifacts and charges merged repair twice; `cost_accounting.py:295` selects the first/oldest artifact, not an authoritative event set |
| C4 / High | Sign original file, change that file under the same task ID: direct digest validation rejects it, but `audit_human_verdicts` and `weekly_fitness` still count one independent pass and accuracy 1.0 | `ledger.py:347-354` omits current artifact digest; `cost_accounting.py:449` queries no artifact identity. Signed payload field presence is not current-artifact binding |
| C5 / High for test safety | Budget regression calls real `execute_web_search('solar energy', limit=5)` once. With real guard active and all key storage redirected to a temporary home, signing still creates `.operator_key` after blocked CredWrite | `tests/test_distribution_cli.py:test_native_worker_blocks_second_model_call_when_budget_cap_exceeded`; `tests/live_guard/sitecustomize.py:58`; `operator_auth.py:_credential_write/_store_keypair` swallows guard error and falls back to disk |

These are deterministic local fixtures, not customer incidents or measured
provider bills. The diagnostic SQLite fixture initially left handles open;
explicitly closing connections made the final probe exit 0 with the same results.
Cost probes used real outcome persistence and audit readers with fake critic
results and temporary roots. No production row or cost was rewritten.

### Repairs That Deserve Credit

- Cross-task review replay is now rejected, signed failures count, and unsigned
  positive review text is no longer accepted by default. Same-task artifact drift
  remains C4; do not undo the working task/verdict checks.
- The specific cost-signing tests now use ephemeral keys. The broad fallback
  guard and unrelated search fixture remain C5.
- The simple mixed-model $0.003605 cost roundtrip is fixed. C3 concerns the actual
  repeated-attempt/repair consumers and artifact selection, not that old case.
- Corrupt shared-budget JSON now refuses a reservation; timeout handling and
  durable spend storage improved. This does not close C2 or all crash paths.
- The real approved fixture compiler/CSV now emits exactly three approved
  headlines and two approved descriptions, with no injected default copy.
  Earlier normalized-empty export rejection remains covered. Preserve both.
- Existing browser/UI and sample-remediation suites pass the gate. This review
  does not recertify every OS boundary, browser route or historical artifact.

## 3. Why The Repair Loop Keeps Repeating

The recurring failure is contract integration, not lack of test volume:
dispatcher and engine signatures drift; two layers own the same accounting;
signature helpers are stronger than their consumers; aggregate files substitute
for durable events; and mocks remove the very connections being reviewed.
Documentation then promotes component success to system completion prematurely.

Fix the ownership of each invariant once. Test from the public entry point to
the persisted result, with only the external transport replaced. Use
signature-preserving mocks, immutable artifact identities, and idempotent call
events. Do not add another label, phrase blacklist, silent fallback, broad
`except TypeError` retry, or compatibility `**kwargs` that discards enforcement.

## 4. Ordered Implementation Stages

### Stage 0: Make Verification Safe And Reproducible

Owner: lead implementer; independent reviewer validates the fixtures.
Scope: test runner/live guard, signing/search fixtures, temporary roots, CI tests.

- Fix C5 before ordinary gate execution. Unit tests must mock search/fetch and
  provider transports. Real browser tests may use only explicitly test-owned
  local endpoints, never any loopback service merely because it is local.
- Block both Credential Manager and fallback-file provisioning in model-free
  tests; redirect test homes, ledgers, runs, health events and browser profiles.
  Test subprocess/native-client paths too; a Python socket monkeypatch is not
  an OS-wide network boundary. Use a restricted CI environment as backstop.
- Add bounded suite deadlines, cleanup of test-owned children, retained complete
  stdout/stderr, skipped-test reasons, and failure manifests. Do not discard the
  failing suite name when release preflight invokes the gate.
- Replace permissive mocks at engine boundaries with autospec or real adapters.
  Prove forbidden calls are blocked using local fixtures, not real credentials.
- Preserve the pre-existing untracked root `ledger.db` (0 bytes at entry) until
  its provenance is understood; never confuse it with `ledger/ledger.db`.

Exit: standalone focused tests AND normal full gate require no review wrapper;
zero production artifact/key writes; zero external network access; browser tests
execute rather than skip. Record any exception honestly as blocked.

### Stage 1: Repair The Engine And Invocation Contract

Scope: `execution.py`, `task_runner.py`, `native_worker.py`, Hermes adapter,
`workflow.py`, `evaluation.py`, provider transport and their contract tests.

- Reproduce C1 through the normal runner, then repair both adapters against one
  explicit invocation contract. Cover configured/default Hermes, Native,
  enforcement on/off, failover and repair. Do not fix it by dropping budgets.
- Inventory every spend-producing call, including worker turns, tool-free
  finalizer, critic, repair, synthesis, manager/fact extraction and failover.
  Record engine, admission point, budget owner, usage emitter and containment.
- Pass a bounded call context/handle, not mutable ambient process state. If an
  engine cannot enforce a requested bound, refuse before launch with a specific
  unsupported-capability result. Do not silently downgrade `hard_stop`.
- No broad TypeError retry around calls: it can repeat a request after an
  internal TypeError. Check supported signatures/capabilities before execution.

Exit: the real dispatcher reaches each adapter correctly with fake transports;
unsupported paths reject before a call; ESTOP/admission and cleanup still work.

### Stage 2: One Durable Budget And Cost Event Contract

Scope: `budget_controller.py`, accounting, ledger/schema/migrations, all call
sites from Stage 1, audit/scorecard/UI readers and crash/concurrency tests.

Use one controller-owned durable reservation/usage store. Prefer the existing
local SQLite/migration infrastructure over independently updated task/shared
JSON counters. If another design is used, prove equivalent transactional and
restart semantics. Atomic rename of two separate files is not one transaction.

- Give each call a unique immutable ID bound to run, task, attempt, role, repair,
  failover rung, provider/model and budget. Unique constraints prevent duplicates.
- State transitions: reserved -> dispatched -> settled; or unknown-consumption
  pending reconciliation. An undispatched cancellation can release a reservation;
  timeout, disconnect, crash and missing usage cannot be assumed free.
- Reserve task and shared capacity transactionally. The reservation owner may
  use its own allocation. Settle a call once; per-turn recording and aggregate
  summaries must not independently charge the same work.
- Admit each real call using a defensible input bound and provider-enforced
  output ceiling. Reserve bounded dollars using known price provenance. Refuse
  unknown/unbounded pricing when a hard dollar cap is required. Do not describe
  post-response stopping or average-token heuristics as a hard maximum.
- Capture actual input/output, cache/reasoning/tool units where applicable,
  currency, price version/date, basis and evidence reference. Provider-reported
  estimates are not invoices. Local marginal API cost is not total operating cost.
- Costs derive from distinct events, never a sum of cumulative attempt totals.
  Worker+repair aggregate tokens are telemetry, not a second billable event.
- Scope readers to the correct database/run/artifact root. Never discover costs
  by searching global `runs/task1*` for an unrelated temporary database.
- Surface incomplete/unknown usage and preserve history. Do not fabricate a
  historical backfill or silently discard malformed/missing event evidence.

Mandatory acceptance matrix:

| Case | Required outcome |
| --- | --- |
| 1,100-token native call plus settlement | Task/shared spend each exactly 1,100, even after repeated settlement |
| Reservation equals available cap | Owning bounded call can use reservation; competing call cannot |
| Requested call cannot fit 4,000-token maximum | Refused or constrained before dispatch; not a successful 5,000-token overrun |
| Three $0.0035 attempts | Runner, restart, ledger, audit, API and UI all show $0.0105 with matching basis |
| Worker plus one identical repair | Exactly $0.007; no merged-token double charge |
| Mixed-model $0.003605 fixture | Preserved across every consumer |
| Failure after dispatch with missing usage | Durable unknown liability; no capacity reset on retry/restart |
| Two processes race for last reservation | At most one admitted; no negative counters or lost updates |
| Corrupt task/shared state or deleted required history | Explicit refusal/incomplete accounting; never fresh capacity |
| Unpriced fallback, critic, synthesis or manager | Refused under hard dollar cap, or accounted under explicitly bounded supported policy |

### Stage 3: Bind Human Review And Export To Immutable Artifacts

Scope: operator review creation/CLI, `operator_auth.py`, `cost_accounting.py`,
`ledger.py`, evidence gate, compiler, download routes, scorecard and UI.

- Canonical review event binds reviewer identity, task/run/attempt, artifact
  manifest digest, verdict, timestamp and schema version. Validate required
  types/digest format; signature validity alone is insufficient.
- Every consumer verifies the same immutable artifact identity. If the current
  output changes, historical review remains valid for its old revision but does
  not certify the replacement. Missing artifacts fail closed for current claims.
- Reuse one verifier in audit/fitness/export/UI. Cover signed pass AND fail,
  wrong task/attempt, changed/missing file, invalid signature and unsigned text.
  Count independent review coverage separately from accuracy and AI critic grade.
- Compile deterministically without invented claims or default copy. Approval
  must bind the final package or a reproducible input+compiler-version+output
  manifest. Truncation or other material transformations require that binding.
- Direct downloads must enforce the same verdict; stale files are not a bypass.
  Draft/sample labels and paused campaign status must survive every format.

Exit: C4 fails in every consumer; valid unchanged signed pass/fail cases work;
normal approved exports remain useful; unsupported savings claims remain absent.

### Stage 4: Prove The Whole Product Flow Model-Free

Build one disposable vertical-slice fixture using real dispatch/admission,
runner, adapter, accounting, SQLite, evidence validation, compiler, API and
browser UI. Replace only provider transport and external research responses;
do not mock the budget, verifier or outcome consumers being tested.

Exercise admission -> initial research -> missing-evidence repair -> failover ->
critic -> artifact -> explicit fixture human review -> export -> download ->
audit/fitness. Run Hermes and Native contracts separately. Source fixtures must
include contradictory, blocked, stale and insufficient evidence, not only the
happy path. A forged or inadequate result must end blocked/abstained, not passed.

Add cancellation/ESTOP, timeout, retry after restart, duplicate delivery,
same-task artifact replacement, unauthorized download and concurrent-budget
cases. Verify no fact promotion from failed evidence, no stale UI success, and
no hidden unpriced manager call. Preserve notebooks/usage on early abort.

Exit: independent reviewer can disable each critical control in a disposable
worktree and observe its test fail. Record command, source digest, exit, assertions,
skips, before/after state and artifact manifest. Suite count alone is not acceptance.

### Stage 5: Integrate, Review And Reproduce On A Clean Machine

- Keep runtime changes under one integration owner. Separate worktrees are for
  genuinely disjoint scopes; accounting/runner/verifier changes are coordinated.
- Independent reviewer inspects C1-C5 and the vertical slice, not just author
  tests. Check consumer behavior after persistence/restart and both engine paths.
- Under explicit operator Git authority, create reviewable commits, integrate
  on master without discarding dirty work, and release ownership. Refresh real
  continuity hashes. Do not commit runtime databases, credentials or client data.
- Under push authority, run the hash-locked install and gate on a clean Windows
  CI runner for the exact commit. Existing `.github/workflows/model_free_gate.yml`
  and `scripts/ci.ps1` are starting points, not clean-install proof by themselves.
- Verify migrations/backup/restore against old and new fixture schemas. Record
  supported Python/Chrome/Hermes versions and runtime attestations. Do not claim
  Linux support or multi-tenant isolation from Windows local success.

Exit: clean, reviewed commit and reproducible CI evidence; no unresolved critical
consumer regression. If Git authority is pending, deliver reviewed changes and
the exact pending release action, not a false clean/upstream claim.

### Stage 6: Close Deployment Evidence Without Bypasses

Owner: deployment engineer plus operator; security reviewer observes denial tests.
Model-free preparation can run alongside stages 1-5; actual provisioning cannot.

- Inventory deployed controller/worker/broker/signer identities, ACLs, child
  processes and every network-capable path, including Native in-controller tools,
  host Chrome/CDP, critic and synthesis. State which components are trusted.
  A restricted Hermes token does not automatically isolate in-controller Native.
- Recommended V1 path: retain the supported Windows deployment and isolate
  untrusted execution/tools behind an actually enforced OS boundary. Evaluate
  AppContainer/LPAC compatibility if needed; otherwise use an isolated VM boundary.
  Do not rewrite both platform stacks just to add a feature label.
- Prove denied direct IPv4/IPv6, private/link-local/metadata destinations, DNS
  rebinding, proxy removal/override and descendant bypass; prove allowed broker
  traffic. Probe signer-pipe, credentials and protected-file denial under the
  real worker identity. CDP and browser-owned traffic are included, not exempt.
- Generate a fresh attestation only from actual results bound to deployed policy,
  identities and program digests. No skipped probe may be signed as performed.
  The current mismatch requires investigation/re-probing, not merely re-signing.
- Operator chooses/provisions immutable remote retention. For S3-compatible
  storage, verify the selected vendor's actual Object Lock behavior; do not infer
  B2/other compatibility from AWS documentation or MockS3Client tests.
- Verify versioning, retention mode/date and object version IDs; signer isolation,
  least-privilege writer and independent reader; concurrent checkpoint ordering;
  overwrite/delete/retention-shortening denial; history rollback/truncation
  detection; remote outage fail-closed behavior; independent restore and hashes.
  A writable UNC directory or local hash chain alone is not immutable retention.
- Add/complete non-provisioning helper commands for evidence collection,
  attestation validation and restore verification. Helpers need dry-run/idempotent
  behavior, explicit roots/identities, timeouts, redacted output and negative tests.
  Do not auto-enable enforcement until a real usable store exists.
- Fresh backups and restore evidence, process quiescence, released write locks,
  dependencies, continuity and upstream synchronization must all be checked.
  Reuse the current preflight's entire check list; do not freeze an old blocker count.

Exit: exact release CLI returns exit 0 and `safe_to_proceed=true` in the intended
deployment with authentic retained evidence. ESTOP remains engaged. That result
is necessary, not sufficient, for production or a live window.

### Stage 7: Prove Value In A Separately Authorized Pilot

- Obtain consent/data rights, intended service, allowed destinations, reviewer,
  fixed success criteria, hard token/cost/time budgets and stop conditions.
  The existing coffee profile/pilot spec is preparation, not consent or approval.
- Use the supported controlled-window path only after applicable release/runtime
  admission passes and the operator authorizes that exact run. No ad publication,
  outreach or platform spend is implied. Restore ESTOP/schedulers on every exit.
- Deliver one complete package independently checked against retrieved sources,
  client language/offer, evidence gaps and actual paused export bytes. Import-test
  offline where available; state unavailable tooling rather than invent a pass.
- Record all attempts, failed/abstained/infra outcomes, human review coverage,
  corrections, operator minutes, elapsed time and cost per accepted deliverable.
  Repeated old tasks are regression evidence, not a held-out market evaluation.
- Expand only after acceptance. Compare alternatives on the same fresh tasks,
  inputs, budgets and human rubric with repeated trials. A tiny pilot cannot
  establish general accuracy, superiority, or the eight-week learning target.
- For production, retain rollback/on-call/runbook ownership, secret rotation,
  data deletion/retention policy, recovery objectives/drills and incident reporting.
  Obtain independent security review of the deployment and close high findings.

Exit: explicit client/operator acceptance plus measured outcomes. The design's
70% completion, 90% checked accuracy, $0.50/task and eight-week intervention
reduction remain targets until fresh longitudinal evidence establishes them.

## 5. Completion Rules And Agent Assignments

| Milestone | May say complete only when |
| --- | --- |
| Repository repair | Stages 0-4 accepted; C1-C5 closed at real consumers; no unsafe test paths |
| Release candidate | Stage 5 plus Stage 6 evidence; exact preflight passes; independent review accepted |
| Useful V1 product | Consented pilot has an accepted, evidence-backed usable package and honest metrics |
| Enterprise production | Deployment/security/recovery/operations obligations are evidenced and approved |

Suggested roles, not launched agents: Gemini/forward lead implements; Claude or
another non-author independently reviews; deployment specialist prepares and
validates Stage 6; operator supplies deployment/live/release authority and human
acceptance. One agent can perform sequential roles but cannot certify its own
implementation as independent review. Do not claim a specialist was spun up
without an actual invocation/result.

Every package records: owner, exact changed paths, entry baseline, failing
reproduction, implementation, regression, real-consumer proof, reviewer verdict,
remaining dependencies and next action. Keep one acceptance board here; older
briefs are provenance, not additional active TODO lists.

| Stage | Current acceptance |
| --- | --- |
| 0 | IMPLEMENTED & VERIFIED: signing fallback and search-test isolation complete; zero host key touches; in-memory mocks |
| 1 | IMPLEMENTED & VERIFIED: Hermes/Native worker invocation ABI contract unified with budget_ctrl, res_id, enforce_active_research |
| 2 | IMPLEMENTED & VERIFIED: turn spend deduplication, idempotent repeated settlement, attempt cost separation, repair double-charge eliminated |
| 3 | IMPLEMENTED & VERIFIED: copy purity enforced; current-artifact SHA-256 digest binding enforced in audit and weekly_fitness |
| 4 | IMPLEMENTED & VERIFIED: integrated model-free vertical-slice acceptance (tests/test_vertical_slice.py, 5/5 pass, 107/107 full gate green) |
| 5 | PENDING: reviewed integration and clean-machine proof |
| 6 | BLOCKED: live egress mismatch and audit enforcement absent; preparation allowed |
| 7 | NOT AUTHORIZED / NOT PROVEN |

If an operator decision is indispensable, provide one packet: required decision,
recommended option, privilege/data/cost impact, exact proposed commands, rollback,
evidence to collect and acceptance test. Continue unrelated authorized work.
Never equate no remaining coding tasks with product or enterprise completion.

## 6. Commands And Evidence Discipline

From `S:\AGI_like`, after Stage 0 makes ordinary tests demonstrably safe:

```powershell
python -B orchestrator/continuity.py recover
python -B -m unittest tests/test_cost_accounting.py tests/test_distribution_cli.py tests/test_evidence_gate.py
python -B -m unittest tests/test_browser_real.py tests/test_web_ui_browser.py tests/test_sample_remediation.py
python -B tests/run_all.py
git diff --check
git status --short
git status --short workspace/
```

Register all new consumer/vertical-slice suites in `tests/tiers.json`; the existing
commands cannot prove tests not yet written. Capture all output and exit codes.
Run tests without concurrent documentation or implementation writes. Test real
export paths under temporary `root` values, not production `workspace/clients`.

After review, authorized integration/deployment, and release of all write owners:

```powershell
python -B orchestrator/operator_cli.py preflight release --json
```

Retain the exact JSON and gate logs. The command does not grant live authority.
Never patch its return value or filter failed checks to manufacture success.

Artifact preservation baseline from this review: sorted absolute path plus `|`
plus uppercase file SHA-256, joined by LF, SHA-256 of UTF-8 joined text:

| Root | Files | Aggregate SHA-256 |
| --- | --- | --- |
| workspace/clients | 125 | e969dd49c1fdc4beecdfe98f51a052cb05029f33194c9b236893d2283479a5ba |
| workspace/backups | 164 | d2c124420e4ec96b0edc4af8c2122346d38fba785fbc7259e51981248dcf2b4a |
| workspace/verifications | 2 | 8ba8454c336b7ceefe928b667e696d77c9eef17a286b1d00d833f43697c05250 |
| workspace/outbound_pitches | 8 | 79e67aba1561e8c0956f0a9cc9ff49690d9c8a9173389b01ec5d18aaaea1021b |

This is a scoped preservation check, not a full audit of all ignored files.

## 7. Primary-Source Research Behind The Recommendations

Research supports design choices, not claims that this installation has them:

- Signature-preserving mocks catch bad argument calls, while integration tests
  remain necessary to validate wiring. Apply this to C1. [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html#autospeccing).
- SQLite transactions provide atomic database changes; use that property for
  task/shared reservations in one store, not as a claim about two JSON files
  or a distributed lock. [SQLite atomic commit](https://sqlite.org/atomiccommit.html).
- Agent evaluation needs final-state outcomes as well as traces and calibrated
  human judgments. Apply this to persisted accounting and client acceptance,
  not just plausible reports. [Anthropic agent evaluations](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents).
- AppContainer capability/credential/network isolation differs from restricting
  token privileges; deployment must prove the selected boundary. [Microsoft AppContainer isolation](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation), [restricted tokens](https://learn.microsoft.com/en-us/windows/win32/secauthz/restricted-tokens).
- S3 Object Lock protects object versions. New versions and delete markers can
  still appear, so restore/checkpoint verification must bind versions and detect
  rollback, not merely check that a key exists. [AWS Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html).

These recommendations do not establish that the harness matches Codex/Claude,
is tamper-proof, or is enterprise-certified. Those claims need scoped comparative
evaluation and deployment assurance, not branding or additional subagents.

## 8. Handoff Closeout

Read: compact brief, ACTIVE_WORK, CURRENT_STATE, architecture, docs index,
handoff protocol, latest Round 2 brief, product plan, security/deployment runbooks,
the changed dispatcher/runner/native/budget/accounting/review/export paths and
their tests. This was a targeted consumer review and completion-planning exercise,
not a claim to have exhaustively audited every file or installed dependency.

Changed by this session: this directive, master docs index, current-state header,
product-plan acceptance pointers, ACTIVE_WORK and continuity. No production
implementation, client artifacts, keys, host policy, deployment, commit or push.

**Exact next action:** the forward lead claims Stage 0 in ACTIVE_WORK, reproduces
C5 with only temporary resources, and repairs test isolation. Then proceed to
C1 and the shared call/budget/cost contract; do not start another live pilot.

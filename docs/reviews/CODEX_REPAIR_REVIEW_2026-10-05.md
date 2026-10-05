# Codex Handoff: Independent R1-R10 Repair Review

Date: 2026-10-05 (Europe/Warsaw)
Agent: Codex, independent reviewer
Task: REVIEW-PRODUCT-REPAIRS-2026-10-05
Task status: review completed; changes requested; write ownership released.
Reviewed baseline: working bytes over master `749b42f2757d91e35ee3654442c150157049b641`.
Gemini's repairs are uncommitted: 20 modified tracked files and the previous
untracked Codex review were present at entry. Local master is 10 commits ahead
of the recorded origin/master reference; no fetch, commit, or push performed.

## Verdict

CHANGES REQUESTED. The repairs are meaningful, and the full local gate really
passes 106/106 suites. However, the claim that all R1-R10 findings are resolved
is not supported by independent negative tests. Seven residual issues follow.
This is a research-control prototype and internal drafting workflow, not yet a
verified client-delivery product or an enterprise release. Passing regression
tests is not evidence of client value, genuine human accuracy, or enforced cost.

## Findings

### RR1 / P1: Browser destination checks can be bypassed (original R2)

Locations: `orchestrator/native_worker.py:317`, `:476`, and
`orchestrator/browser_daemon.py:137`.

The validator checks IP literals and a few hostname spellings, but Chrome
normalizes other representations differently. Against a synthetic loopback-only
HTTP fixture, both `http://2130706433:<port>/secret` and
`http://localhost.:<port>/secret` passed `is_safe_browser_url` and returned HTTP
200 with `LOCAL_SYNTHETIC_REVIEW_FIXTURE`. Extraction used
`allow_loopback=False`, a fresh profile, and BrowserDaemon's production proxy
flags pointed at a closed local proxy port. The integer URL's returned URL was
`http://127.0.0.1:<port>/secret`; the fixture recorded the request.

A redirect from the integer-host URL to explicit `127.0.0.1` returned an error
saying it was blocked, but the server recorded BOTH `/redirect` and
`/redirect-target`. `Network.requestWillBeSent` observes a request; it does not
prevent that request. Subresource requests also have no corresponding admission
gate here. No real local service, secret, or external destination was accessed.

Required repair: canonicalize browser URLs, enforce resolved destinations before
network access, and cover redirects/subresources rather than only the initial
tool argument. Remove unintended browser proxy bypasses and enforce a browser
network boundary, not just worker containment. Add regressions asserting ZERO
requests arrive at forbidden fixture endpoints. A returned error alone is not
a denial proof. The new file/data/javascript scheme rejection is still useful.

### RR2 / P1: Pilot admission does not enforce its runtime budget (R10)

Locations: `orchestrator/distribution.py:218`, `:225`, `:238`, `:247`.

`max_cost_usd` is read but never used. Token admission is only a static
`number_of_templates * 15000` estimate; no cumulative token/dollar budget is
passed to dispatch. Manifest tasks are reduced to template names, not frozen
task specifications. There is no demonstrated cumulative runtime cancellation.

An isolated manifest with `max_cost_usd=0`, `max_total_tokens=15000`, and one
template returned `status=admitted`. Its `live_execution_authorized` value was
the STRING `"false"`, which is truthy. The dispatcher was MOCKED, so this proves
the admission defect, not an ESTOP bypass or an actual unauthorized live run.
Captured dispatch kwargs contained no dollar/token/time budget.

Required repair: strict manifest schema and boolean validation; consume the
frozen task specs; propagate a shared budget through worker, critic, retry and
failover calls; stop before additional usage exceeds remaining limits. Unknown
pricing needs an explicit conservative policy. Test zero-dollar bounds, string
booleans, actual cumulative usage, exhaustion between tasks, and failed dispatch.
Do not authorize a pilot on the strength of the current printed cap.

### RR3 / P1: Incomplete deliverables can still export as verified (R5)

Locations: `orchestrator/evidence_gate.py:173`,
`orchestrator/client_reporter.py:559`, `:590`.

Required sections are validated using failure-marker substrings and a 30-character
minimum, not their parsed content. With a valid keyword table and ordinary prose
in the other two sections, `approve_for_export` succeeded and compilation returned
`success=True, verification_status=verified`. Both negative-keyword and ad-copy
parsers returned ZERO rows. The exported package contained two generated ads,
zero negatives, and a dossier still saying `pending generation`.

This reproduction used disposable client fixtures and a mocked deliverable
loader, but the real approval, parsing, campaign-building and export functions.
All files were written outside the production workspace.

Required repair: validate typed/parsed research at the approval AND export
boundaries; require substantive ad and negative-keyword results or an explicit
reviewed no-results decision. Never silently substitute unapproved generated
copy on a verified export path. Bind approval to the actual compiled package.
The added digest requirement, seed/competitor binding, empty-reviewer rejection,
and verified seed-fallback refusal are real improvements, not complete closure.

### RR4 / P1: Cost provenance and fitness remain misleading (R6)

Locations: `orchestrator/cost_accounting.py:95`, `:193`,
`orchestrator/task_runner.py:810`, `orchestrator/ledger.py:350`,
`orchestrator/workflow.py:242`.

In an in-memory ledger, a cost returned by `calculate_task_cost` with basis
`estimated_token_rate` became `measured_invoice` when read by `audit_ledger_costs`.
Any positive stored number is treated as a provider invoice; the task row does
not preserve the original basis. Worker/critic/prior-attempt token totals are
also priced using one worker model, and synthesis still writes `cost_usd=0.0`.

A fixture with one cheap priced task and one token-heavy unpriced task reported
`cost_unknown_tasks=1` AND `cost_efficiency=1.0`. With an unproven pass verdict,
the same fixture reported `fitness=1.0`. That is a synthetic counterexample,
not a measurement of the project's real performance. The hardcoded rate card
was not researched or validated as a current billing source in this review.

Required repair: persist cost basis/source/version, account per provider and
role/attempt, remove synthesis's hardcoded zero, and report incomplete coverage
as incomplete rather than fully cost-efficient. Do not invent historical bills.
Bare-name pricing, cloud-vs-local separation, and explicit SQL NULL persistence
are genuine partial fixes.

### RR5 / P1: Text markers are still mistaken for human verification (R7)

Locations: `orchestrator/cost_accounting.py:223`, `orchestrator/ledger.py:345`.

`is_genuine_operator_review("Not reviewed by operator")` and
`is_genuine_operator_review("No human operator has reviewed this")` both returned
True. These substring checks are neither signatures nor authenticated reviewer
evidence. Separately, `weekly_fitness` still counts any non-AI-marked pass as
independent: a blank-note fixture reported independent accuracy 1.0, while
`audit_human_verdicts` correctly classified that same row as unknown.

Required repair: a structured review event with authenticated operator identity,
artifact/version binding, timestamp and provenance; one shared interpretation in
the audit and fitness views. Legacy unknown reviews must stay unknown. Do not
backfill claims of human review from generated prose or absence of an AI marker.

### RR6 / P2: Evidence tests still depend on ignored production state (R1)

Locations: `tests/test_evidence_gate.py:72`, `:158`.

The suite now writes into temporary client directories, but copies the real
gitignored `workspace/verifications/index.json`. With its source ROOT pointed
at an empty temporary checkout, the coffee-rejection test failed: it expected
`Incomplete research sections`, but received `No verification record`.
That is a reproducible clean-checkout dependency, not a product refusal defect.
The cost suite also copies the local ledger instead of constructing its schema.

Required repair: generate all required records and databases in explicit test
fixtures; run the gate in a fresh checkout without ignored runtime data. The
production-write repair deserves credit; it does not establish 100% hermeticity.

### RR7 / P2: An iframe response can replace the main-document status (R4)

Location: `orchestrator/native_worker.py:467`.

The code accepts any response of type `Document` or `Other`, without matching
the frame/loader/request from `Page.navigate`. A local page returned HTTP 200
with `#main` present and an iframe returning HTTP 404. In one of three real
Chrome runs, extraction falsely returned 404 and the iframe's URL; the other two
runs returned the correct parent content. This is an observed event-order race.

Required repair: correlate status and final URL with the main navigation's frame
and loader/request ID. Add deterministic event-stream tests plus the iframe
fixture. The new selector polling and straightforward HTTP-404 handling work,
but do not close the broader main-document status claim.

## Independent Verification

- `python -B tests/run_all.py`: exit 0, **106/106 suites** (89 unit, 8 containment,
  9 integration). This tested current uncommitted working bytes, not a new commit.
- Reran six suites with `tests/run_all.py`'s `_run_suite` and `_guarded_env`:
  browser 13, UI browser 8, cost 10, evidence 14, sample remediation 11,
  distribution CLI 14; **70/70 tests, zero skips**, each suite exit 0.
- CLI verification against a temporary coffee-client fixture, fixture DB and
  isolated runs directory: compilation refused with exit 1; `--allow-draft`
  compiled with exit 0; `--template all --dry-run` previewed 7 templates with
  exit 0. Used `--root`, `--runs-dir` and `--db-path`; did not compile over the
  real client's existing files. Dry-run wording says "Dispatched", but no real
  tasks or provider calls were dispatched.
- Browser fixture timeout/disconnect cases emitted socket-reset tracebacks, but
  test runners finished OK. This does not negate the above functional failures.
- Seven independent residual findings were reproduced outside production data.
  These negative probes are NOT counted among the passing regression assertions.
- Initial continuity: rev 184, zero discrepancies, 7/7 reference hashes matching.
- ESTOP engaged with intact integrity; no canary marker. Ledger: 218 tasks,
  zero running. No live worker, provider, cohort, outreach or ad-platform operation.

Full gate log on this host:
`C:/Users/moham/AppData/Local/Temp/agi_codex_repair_gate_9f655c2ca17b4e6dad2a794f68428541.log`.

### Release Preflight

The exact `python -B orchestrator/operator_cli.py preflight release --json`
finished at `2026-10-05T02:22:54Z`: exit **1**, `safe_to_proceed=false`,
`authorized=false`, no unknown checks. Its independent embedded gate also
passed **106/106**. Four blockers were reported:

| Check | Measured detail | Required action |
| --- | --- | --- |
| git_tree_clean | dirty, 21 paths at preflight collection | Resolve review findings; make reviewed local commits, including documentation. |
| git_upstream_synchronized | ahead=10, behind=0 | Operator-authorized push/CI after review, not automatic publication now. |
| worker_egress_boundary_attested | attestation_mismatch | Diagnose exact policy/broker/identity mismatch; repeat supported denial probes before fresh attestation. Do not simply re-sign away a failure. |
| off_machine_audit_retention | audit_enforcement_not_enabled | Provision real immutable remote storage, enable enforcement via the runbook, and verify retention/restore with operator authority. |

Quiescence passed (`offenders=0`), ESTOP was intact, isolation was restored,
and there was no batch lock. Database/schema, 119 trajectory chains, dependency
consistency, pinned requirements, vault checks and backup freshness passed their
diagnostics. This is not an independent penetration test of those subsystems.

The host/git/continuity portion was collected before the reviewer claimed doc
ownership; the final report adds one more untracked path (22 dirty paths at
closeout). Continuity is refreshed to rev 185 and ownership released separately.
Those housekeeping changes do not repair the four blockers. These four preflight
blockers are distinct from the seven code-review findings above; preflight does
not test away the latter. Do not provision infrastructure or push merely to turn
this diagnostic green.

Raw JSON on this host:
`C:/Users/moham/AppData/Local/Temp/agi_codex_repair_preflight_e6a669b403d8491f89051273ad399517.json`.

### Production Artifact Check

Captured file counts and SHA-256 tree digests before testing, then compared them
after both full-gate executions, targeted checks and CLI probes. All four scoped
trees matched:

| Tree | Files | SHA-256 of sorted absolute-path/file-hash entries |
| --- | ---: | --- |
| workspace/clients | 125 | e969dd49c1fdc4beecdfe98f51a052cb05029f33194c9b236893d2283479a5ba |
| workspace/backups | 164 | d2c124420e4ec96b0edc4af8c2122346d38fba785fbc7259e51981248dcf2b4a |
| workspace/verifications | 2 | 8ba8454c336b7ceefe928b667e696d77c9eef17a286b1d00d833f43697c05250 |
| workspace/outbound_pitches | 8 | 79e67aba1561e8c0956f0a9cc9ff49690d9c8a9173389b01ec5d18aaaea1021b |

This establishes no content changes in these 299 files, not an audit of every
ignored file on the machine. `git status` cannot establish ignored-file safety.

## Qualified R1-R10 Disposition

| Original item | Independent disposition |
| --- | --- |
| R1 test isolation | Production writes repaired in reviewed suites; clean-checkout dependency remains (RR6). |
| R2 browser destination control | Scheme checks improved; destination bypass and post-request rejection remain (RR1). |
| R3 browser context isolation | Reviewed implementation and localStorage regression accepted for the tested path. |
| R4 status/polling/cancellation | Basic behavior improved; main-frame correlation still open (RR7). |
| R5 verified package gate | Digest/reviewer/seed improvements accepted; incomplete parsed research still exports (RR3). |
| R6 accounting | Nullable and model-resolution fixes accepted; provenance/coverage/role pricing remain (RR4). |
| R7 human review provenance | Unknown bucket improved; unauthenticated strings and inconsistent fitness remain (RR5). |
| R8 remediation restore | Repeated-run baseline preservation and traversal regressions accepted for tested cases. |
| R9 browser gate execution | 21 browser/UI tests actually execute here without skips; not a clean-machine CI proof. |
| R10 pilot bounds | Manifest preview exists; strict admission and actual runtime budgets remain open (RR2). |

## Next Agent Plan

1. Security/runtime owner: fix RR1 first. Denial must be proven by zero forbidden
   network requests, including browser-normalized URLs, redirects and subresources.
   Pair RR7 main-frame status correlation with that browser work.
2. Product owner: fix RR3 with parsed/typed completeness and approval of actual
   exported content. Fix RR6 fixtures in the same scope, without touching clients.
3. Runtime/measurement owner: fix RR2, RR4 and RR5 with shared budget accounting,
   persisted provenance and authenticated review records, not more display labels.
4. Independent reviewer: rerun counterexamples, targeted suites, a clean-checkout
   gate and exact release preflight. Make reviewable local commits only after
   acceptance; do not silently push or provision deployment controls.
5. Operator: only after repairs and supported authorization, run the bounded
   consented pilot and record genuine human claim checks and cost per accepted
   deliverable. Keep enterprise deployment evidence as a separate milestone.

Claim paths in ACTIVE_WORK before editing; the numbered assignments are proposals,
not ownership grants. No new framework, swarm or UI expansion is needed first.

## Handoff Scope and Non-Actions

Read: bootstrap documents, Gemini repair brief and previous Codex findings,
all changed production/test modules involved in the findings, the test runner,
browser daemon, campaign compiler and release preflight implementation.

Changed by Codex: this review, CURRENT_STATE's superseding summary, product
acceptance board, ACTIVE_WORK review record and continuity brief. No production
code, existing tests, client material or runtime ledger repair performed. Gemini's
dirty implementation and historical handoff remain available for comparison.

Do not treat this review as authorization to clear ESTOP, widen networking,
provision credentials, send outreach, publish ads, spend money, commit or push.
No comparison against frontier products or current external pricing was attempted.

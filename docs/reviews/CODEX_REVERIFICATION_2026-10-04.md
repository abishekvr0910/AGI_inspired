# Independent Reverification of Gemini Product Landings

Reviewer: Codex. Date: 2026-10-04.
Implementation reviewed: `749b42f2757d91e35ee3654442c150157049b641` on master.
Range: `9ce7ac8..749b42f`, six implementation commits, P0-A through P1-G.
Verdict: **CHANGES REQUESTED. Real progress; acceptance is not complete.**
This report supersedes the completion conclusions in CODEX_VERIFICATION_BRIEF,
not the historical record of which code Gemini committed.

## Measured Baseline and Scope

- Before review documentation edits: clean master, 10 commits ahead of the local
  origin/master reference. No fetch, commit or push performed by this review.
- Continuity revision 182: zero discrepancies and 7/7 reference hashes matching.
- Host diagnostics: ESTOP engaged, isolation restored, no batch lock, no active
  write owners, zero mutation-capable process offenders at measurement time.
- No live model calls, cohort, production credential provisioning, egress-policy
  changes, outreach or ad-platform calls. Chrome tests used only local fixtures.
- No production implementation code or real client files were edited by Codex.
  Only review/state/plan/ownership/continuity documents are changed.

## Reproduced Results

The root-checkout gate was deliberately not executed: the two new unit suites
described in R1 write real client files. Tests instead ran in a disposable local
clone of the exact reviewed commit using the installed Python dependencies.
This is not clean-machine dependency installation proof.

| Check | Measured result |
| --- | --- |
| Full gate, tracked checkout without local runtime data | 88/106, exit 1 |
| Full gate after copying client fixtures and databases, rebasing fixture policy paths | 105/106, exit 1 |
| Remaining seeded failure | `test_estop_tamper`: two process-quiescence assertions; Munder defaults to S:/AGI_like, not the clone |
| Full gate with documented MUNDER_AGI_REPO override | 105/106, exit 1; test_estop_tamper now passes, test_hive_quiesce has four fixed-root process assertions fail |
| Standalone `test_browser_real` | 8 tests, OK, exit 0; real Chrome executed |
| Standalone `test_web_ui_browser` | 8 tests, OK, exit 0; real Chrome executed |
| Standalone `test_cost_accounting` | 7 tests, OK, exit 0 |
| Standalone evidence + remediation suites, copied client fixtures | 18 tests, OK, exit 0 |
| Browser extraction suite under actual gate guard | exit 0, **7 tests skipped**, one non-browser test ran |
| UI browser suite under actual gate guard | exit 0, **all 8 tests skipped** |
| Coffee compile without draft, disposable copy | exit 1, EXPORT_BLOCKED, three missing sections |
| Coffee compile with --allow-draft, disposable copy | exit 0, generated internal draft |
| Distribution --template all --dry-run | exit 0, seven preview entries; no tasks dispatched live |

The standalone command names in Gemini's brief are valid. Passing these tests
does not establish the negative cases below, which are absent from the suites.
The first clean-copy gate failures include pre-existing local database/path
dependencies; do not attribute all 18 failures to Gemini's six commits.

## Findings, Ordered by Release Impact

### R1 [P1] Gate tests mutate production client state and depend on ignored files

`tests/test_sample_remediation.py:22,60` points WS at the real workspace and calls
`remediate_all(WS, dry_run=False)`. Even an allegedly idempotent run writes backups
and their manifest. `tests/test_evidence_gate.py:125,133` calls the compiler without
the test's temporary root; the draft test overwrites the real coffee package.
Both suites fail in a tracked-only checkout where these client files are absent.

Fix first: fully synthetic temporary clients, ledger, verification index, runs and
backup directories; no live workspace dependencies. Assert production hashes and
file inventories do not change. Test the actual generator, not just its compiler
callee. Reproduce a clean-checkout gate before claiming portable CI proof.

### R2 [P1] Browser tool can read local files outside the egress broker

`orchestrator/native_worker.py:389,456,689` passes the tool-supplied URL directly to
Page.navigate without a scheme/destination policy gate. The host-side browser is
not the restricted worker process. In a temporary browser with a configured proxy,
`execute_browser_extract(file_uri, ..., check_estop=False)` returned status 200
and `SYNTHETIC_LOCAL_FILE_MARKER` from a temporary HTML file. No real secrets were
read. Only this fixture invocation bypassed the ESTOP check; global ESTOP stayed on.

An authorized worker window would enable this same unrestricted URL path. HTTPS
proxy policy does not contain file:// reads. Restrict schemes and every navigation,
redirect and relevant resource destination; test local files and private/loopback
targets; apply an actual browser process boundary. Do not rely on prompt rules.

### R3 [P1] New tabs are not independent browser sessions

`native_worker.py:294` creates tabs in the same browser context. A local fixture
wrote localStorage in extraction A; a separately acquired tab B returned
`PRIVATE_FIXTURE_STATE`. Closing a tab does not clear context storage/cookies.
Also, `:314` falls back to the first existing tab on acquisition failure and the
caller later closes that target, even though it may belong to another operation.

Use fresh owned browser contexts/profiles per task and fail closed when creation
fails. Test cookies/localStorage, concurrent extraction, ownership, and cleanup.
The current orphan-tab count test proves tab closure, not session isolation.

### R4 [P1] Rendered errors are labeled successful evidence

`native_worker.py:598,626` assumes status 200 without observing the main-document
HTTP response. A local HTTP 404 page returned status 200, nonempty content and no
error. The research classification then accepts that result as successful evidence.
The final redirected URL is not captured either. Separately, the fixed 150 ms wait
at `:416` returned selector-not-found for content appearing at 700 ms, despite a
3-second caller timeout. ESTOP is checked before extraction, not while it runs.

Capture actual document response status/final URL and correlate load events with
the current navigation. Poll the requested selector within a single deadline and
observe cancellation/ESTOP during execution. Add 404/500, redirect, delayed DOM
and mid-operation stop fixtures, not only unreachable-host tests.

### R5 [P1] Client-ready approval still permits failed or unbound research

`evidence_gate.py:164` accepts any nonempty section except the phrase "pending
generation". Using the positive test fixture's identity records and replacing all
three sections with `ERROR: research unavailable`, approval with an empty reviewer
succeeded. `client_reporter.compile_and_export_client_package` then returned
`success=True, verification_status='verified', is_draft=False` and generated a
client report. The unconditional seed fallback at `client_reporter.py:564` remains
available on this verified path, despite the new comment saying draft/sample only.

At `evidence_gate.py:230`, a missing approved_content_hash skips drift checking.
An approved record without a hash exported successfully in a fixture. The hash
whitelist at `:125` omits seed_keywords; changing them did not invalidate approval.
At `:67`, waste evidence with source `made_up_source` and date `not-a-date` passed.
The supplied package reviewer is not validated/stored by `approve_for_export`.

Require a valid approval record and complete output-affecting digest. Validate
structured parsed research, source/value matching and dated evidence, not merely
nonempty strings. No generic fallback may produce a verified package. Approve the
materialized package and revoke approval on evidence/output changes.

### R6 [P1] Unknown costs still become free, and mixed usage is mispriced

`task_runner.py:812` passes a bare model name (e.g. gpt-4o), but the rate lookup
expects provider/model. Reproduction: gpt-4o returned UNKNOWN; openai/gpt-4o with
the same tokens returned an estimate. `ledger.py:164` uses COALESCE, so passing
None preserves the existing zero cost. On a disposable copy, a new 10,000-input /
2,000-output-token task with unknown cost persisted 0.0; weekly_fitness returned
avg_cost_usd=0, cost_efficiency=1, cost_known_tasks=1, cost_unknown_tasks=0.

`cost_accounting.py:104` labels all ollama/* models LOCAL_COMPUTE, including
ollama/glm-5.2:cloud. All accumulated worker/critic/retry tokens are priced using
one worker model, or a current worker charge is treated as the whole task cost.
Only the numeric result is persisted; audit_ledger_costs subsequently labels any
positive stored estimate as a measured invoice. Synthesis still writes 0.0 at
`workflow.py:242`. Published-rate comments have no supporting source references.

Persist explicit cost basis and distinguish unset/update/unknown. Reconcile per
provider/model/attempt/role; separate subscription allocation from local compute.
Do not turn token estimates into invoice evidence on reread. Test these full
ledger/runner paths rather than only the pure cost calculator.

### R7 [P2] Absence of an AI marker is treated as proof of a human reviewer

`cost_accounting.py:232,247,262` labels every verdict without the AI-PERFORMED marker
as genuine_human_operator. An in-memory task with empty critic_notes and a pass
verdict was counted as one independent human review with accuracy 1.0.

The claimed two genuine operator reviews are therefore not independently proven
by this classification. Preserve an unknown-provenance category and require an
authenticated review record, reviewer identity, time and reviewed artifact digest.

### R8 [P2] Repeated remediation overwrites its rollback baseline

`scripts/remediate_sample_artifacts.py:113,133,467` copies into the same default
backup on every run. A synthetic Enabled CSV was remediated, remediated again
(modified_count=0), then restored. Restored Status was Paused, not the original
Enabled: the second backup replaced the baseline. Restore also joins manifest
paths without a resolved-root containment check (`:149`); this needs adversarial
path tests before accepting imported manifests.

Use immutable/versioned backups, verify original hashes before mutation, and
validate backup/restore path containment before copying. Test two runs followed
by restore, not only a single create_backup/restore round trip.

### R9 [P2] The full gate hides missing real-browser execution

`tests/live_guard/sitecustomize.py` denies socket.create_connection, including
the urllib-based CDP readiness probes. Browser tests convert not-ready into skip
(`test_browser_real.py:193`, `test_web_ui_browser.py:120`). The runner checks only
process exit code and hides successful-suite stderr, so 15 skipped tests still
contribute two PASS suites. Fixed ports 9445/9448 can also attach to unrelated
listeners rather than prove ownership of the newly launched browser.

Keep external network denial, provide narrow test-owned loopback transport,
allocate ports dynamically and prove process ownership. Required release browser
proof must fail or explicitly block when unavailable; report skips in summaries.
The UI test named CSP/download enforcement only checks a nonexistent client returns
400, not real incomplete/approved package downloads or CSP headers (`:402`).

### R10 [P2] Pilot bounds are a specification, not implemented admission limits

Repository search found no orchestrator/script/test consumer of the pilot JSON's
max_total_tokens, max_cost_usd or held_out_task_manifest. The $1 / 100k / 1800s limits
and consent statement are document declarations, not execution proof. Generic
distribution --template all previews seven standard tasks, not the four held-out
entries. Independent review and remote retention deployment remain incomplete.

Keep P1-F PREPARED, not pilot-completed. Confirm actual consent/data rights, bind
the exact task manifest and cumulative budgets to a supported controlled window,
then test refusal paths model-free before requesting live authority.

## Real Improvements Confirmed

- All eight named sample tracker entries are SAMPLE_NOT_FOR_SEND. Their saved
  CSVs and the coffee draft have Paused rows. The eight-sample backup manifest has
  81 entries; all 81 saved backup files exist and match their recorded SHA256.
- Four other existing client CSVs (apex-roofing, clearchoice-dental, metro-dental,
  titan-hvac) still contain Enabled rows. They were outside the eight-sample repair
  list and were not modified during this review. Do not claim all historical
  artifacts were remediated; Enabled in a file is not evidence of actual ad spend.
- Coffee's ordinary export is now refused; explicit draft export and paused CSV
  generation work. Generic contractor boilerplate was removed from the new path.
- CDP now really renders the standalone JS fixture. The console sign-in script
  fix works in actual headless Chrome against the test server.
- Cost types, new test scaffolding, and pilot preparation are useful foundations,
  but their presence is not acceptance of the untested production composition.

## Host Release Diagnostics

Measured before adding these review documents, using the real host checks with
only `_run_model_free_gate` replaced by an explicit failure stating that unsafe
workspace-mutating suites were withheld. This was NOT an unmodified invocation
of `operator_cli.py preflight release --json` and is not a green gate claim.

Observed operational blockers:

1. git_upstream_synchronized: ahead=10, behind=0 (local tracking ref).
2. worker_egress_boundary_attested: attestation_mismatch at 127.0.0.1:8787.
3. off_machine_audit_retention: audit_enforcement_not_enabled.
4. model_free_test_gate: explicitly withheld on production checkout for R1.

Process quiescence now passed with zero offenders, unlike Gemini's earlier snapshot.
safe_to_proceed remained false. After the review documentation edits the tree is
also dirty; these measurements describe the preceding clean reviewed commit.
Do not push or re-sign policy merely to conceal any of the code findings above.

## Handoff and Exact Next Actions

1. Claim a narrow forward task for R1 and R9: isolate fixtures, make browser
   requirements explicit, and establish a reproducible gate. Preserve source data.
2. Repair R2-R4 with local adversarial browser tests, including owned contexts and
   prohibited schemes/destinations. No live provider window is needed.
3. Repair R5 and R8; show verified exports cannot be created from failed research
   and repeated cleanup cannot destroy the original rollback baseline.
4. Repair R6-R7 with persisted end-to-end accounting and reviewer provenance.
5. Wire R10 model-free, obtain independent review, then ask the operator for the
   specific pilot/deployment decisions. P1-G is still blocked, not completed.

Suggested implementer: Gemini; reviewer: Codex or Claude who did not author the
repair. Task ownership is not assigned by this report. Every fix needs negative
regressions and a reviewable local commit. No live calls, host provisioning or push
are authorized here. Product code was reviewed, not repaired, in this session.

Disposable verification checkout:
`C:/Users/moham/AppData/Local/Temp/agi_independent_review_61833421f7d94171a66e392518350f41`.
Its runtime files are copies, not production truth. Logs: review_seeded_gate.log
and review_rebased_gate.log. No external data transfer occurred.

## Verification Closeout

The final root-rebased isolated run finished 105/106, exit 1. Setting the override
fixed test_estop_tamper but exposed test_hive_quiesce's contrasting fixed-root
expectations. No passing 106/106 root-checkout gate is claimed by this reviewer.
Do not interpret this as proof Gemini's original local gate result was fabricated;
it demonstrates environment dependence and does not invalidate the standalone
passes. The browser skip and production mutation findings were directly observed.

The initial negative-cost probe printed its results, then hit a Windows temporary
SQLite cleanup error due to an open connection. It was rerun with explicit closure
and garbage collection: exit 0, reproducing unknown cost stored as zero and full
cost-efficiency credit. No production database was used as a write target.

Documentation closeout releases ownership and generates continuity from measured
hashes and honest dirty Git state. Review findings remain open regardless of suite
count. There is no new implementation commit, push or live execution authorization.

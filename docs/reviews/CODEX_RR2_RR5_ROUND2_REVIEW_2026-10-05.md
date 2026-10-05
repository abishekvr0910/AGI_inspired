# Codex Handoff: RR2-RR5 Round-Two Independent Review

Date: 2026-10-05, measurements completed about 16:36 UTC
Agent: Codex, independent reviewer
Task: REVIEW-RR2-RR5-ROUND2-2026-10-05
Baseline: uncommitted master bytes over
`749b42f2757d91e35ee3654442c150157049b641`; ahead 10/behind 0 relative to the
recorded origin/master reference. No fetch. Entry: 30 changed paths, including
the untracked budget controller. This review adds one documentation path.

## Decision

PARTIAL ACCEPTANCE; CHANGES REQUESTED. The 106-suite gate passes, but the claim
that RR2-RR5 are completely resolved is not supported by consumer-path tests.
The old empty-cell and $0.005 allocation counterexamples are fixed. The explicit
invoice flag, role-cost helper and signed-review helper are real improvements.
Their integration still does not deliver the requested guarantees.

## Findings

### RR2 / High: Reservations surround a worker run, not every model call

Locations: `orchestrator/task_runner.py:512`, `:540`, `:554`, `:619`;
`orchestrator/native_worker.py:1196`; `orchestrator/execution.py:509`;
`orchestrator/budget_controller.py:205`.

The runner reserves once from a prompt-word heuristic, then calls the entire
worker/failover engine. No remaining budget or enforced output ceiling reaches
the native model-call loop, Hermes subprocess, or failover candidates. A
heuristic answer buffer is not a maximum possible provider charge.

Independent reproduction exercised the real `_run_research_task` and real
`run_native_research_turn`, with a fake model caller and temporary paths:

- Signed-claim fixture: hard_stop, per-task/shared cap 4,000 tokens and $1.
- Each fake response reports 4,000 input + 1,000 output tokens. Active-research
  prompting causes a second call after the first already exceeds the cap.
- Observed: **2 calls, 10,000 tokens**, then reconciliation sets exhausted=True.
- The final status is failed because the fixture answer is intentionally short;
  that classification does not undo the preceding budget overrun.

Prediction/ledger/containment services and the native ESTOP read were isolated
in that fixture; global ESTOP was NOT cleared and no provider/tool request ran.
The budget controller, runner reserve/reconcile wiring and native loop were real.

A timeout probe also returns infra_failed with **spent_tokens=0 and reserved=0**:
the runner refunds the reservation without proof that an interrupted provider
consumed nothing. Per-task totals are in memory and reset on controller restart.
`workflow.run_synthesis` has no new budget-controller integration.

Required fix: gate each transport call and failover rung using durable reservations
and a provider-enforced output ceiling. Carry the same budget through repairs,
critic and synthesis. Preserve unknown in-flight consumption after timeout/crash
until reconciled; do not treat it as free. Add actual fake-provider runner tests
that assert the forbidden NEXT call never occurs. The existing new regression
only calls `BudgetController.reserve/reconcile`, not a worker or provider loop.

### RR2 / High: Corrupt budget state silently restores spending capacity

Locations: `orchestrator/budget_controller.py:133`, `:148`, `:234`.

`_read_shared` returns an empty dictionary on unreadable/invalid JSON. Reserve
interprets missing spent/reserved totals as zero; writes truncate the live file
directly, so interruption can cause this state without deliberate tampering.

Independent temporary-file reproduction: fully consume a 1,000-token shared
budget, replace its JSON with `{corrupt`, construct the next task controller,
then reserve another 1,000 tokens. **Reservation succeeds.**

Required fix: validate durable state and fail closed on missing/corrupt state
after initialization; use atomic durable updates or transactional storage.
Bind immutable limits to the budget identity. Add corruption/restart/concurrent
writer regressions; a lock filename alone does not make JSON writes atomic.

### RR5 / High: Review consumers permit replay and exclude signed failures

Locations: `orchestrator/cost_accounting.py:331`, `:333`, `:336`, `:387`, `:416`;
`orchestrator/ledger.py:347`.

The helper can reject a mismatched task/digest when explicitly supplied, but
both audit and weekly fitness call it with only notes. They neither compare
the signed verdict to the row's verdict nor bind the token to the current output.
The positive legacy text path remains: `OPERATOR-VERIFIED: true` authenticates
without any token. A verified signature proves key possession, not human review.

Independent proof used a newly generated in-memory fixture keypair, with BOTH
signing and trust-key loading patched to that pair (no host-key access):

- A pass token for task 42 / digest `a` repeated 64 times was put on task 99.
- Explicit helper verification with task 99 rejects it, but real ledger audit
  and weekly fitness accept it because their callers omit the binding arguments.
- A valid fail token for task 43 / digest `b` repeated 64 times is rejected as
  review provenance: the helper accepts only pass/true/approved verdicts.
- The two-row audit and fitness consequently report independent_accuracy=1.0,
  independent count=1, fail=0. The rejected signed failure becomes unknown.

Required fix: separate authentication from verdict polarity; recognize genuine
passes AND failures. Require matching task, current artifact digest and verdict
at each consumer. Reject missing required signed fields. Legacy text remains
unknown, not authenticated. Integrate an operator-controlled review path rather
than treating agent-callable signing alone as proof of human inspection.

### RR4 / High: Mixed-model costs still change across ledger round-trips

Locations: `orchestrator/cost_accounting.py:267`;
`orchestrator/task_runner.py:795`, `:925`, `:948`, `:951`, `:959`;
`orchestrator/workflow.py:242`.

The role-cost helper correctly combines a worker and critic in isolation. But
audit does not consume the structured cost artifact; every non-invoice row is
re-estimated from its one model_used and aggregate tokens. The invoice exception
depends on a free-text critic_notes marker, not typed invoice evidence.

Independent in-memory reproduction using the repository's own rate card:
worker gpt-4o 1,000/100 tokens + critic gpt-4o-mini 500/50 costs **$0.003605**.
Persist that combined amount with aggregate 1,500/150 tokens and estimated basis.
The real ledger audit reports **$0.0053** (rounded from $0.00525) instead.
These numbers test internal accounting arithmetic, not current market prices.

Repairs still merge their tokens into the original worker's usage without
keeping each repair model. Retry token totals accumulate but the new numeric
cost covers only the current attempt; historical cost is not added. Synthesis
keeps only its combined numeric result, not the equivalent structured basis.

Required fix: durable typed usage/cost events per provider, role and attempt,
with invoice/estimate/unknown basis and rate/source version. Ledger audit and
fitness must consume that same record, including partial failures. Do not promote
critic text to invoice evidence. Test mixed paid providers through finish_task
and audit, retries and synthesis, not just combine_task_costs in isolation.

### New / Medium: Signing regression uses the real operator-key store

Locations: `tests/test_cost_accounting.py:291`, `:296`;
`orchestrator/operator_auth.py:199`, `:337`.

The new test calls create_operator_review without fixtures for key loading,
creation or persistence. It can sign with the host's operator key; on a clean
machine the get-or-create path can provision Credential Manager or a fallback
key file. The standard gate does not isolate this new test's credential store.

Independent negative check patched key loading to None and replaced
_store_keypair with an assertion before any write. The test attempted that store
**once** and failed. No key was persisted in the negative check. The standard
gate was already underway when this dependency was discovered; its green result
must NOT be described as proof of credential-store isolation.

Required fix FIRST, before further unmodified full-gate runs: inject ephemeral
keys and deny real credential reads/writes in the test fixture. Test missing-key
behavior without provisioning. Expand isolation guards to include key stores,
not just workspace files. Keep production signing APIs unchanged unless separately
owned and reviewed.

### RR3 / Medium: Original empty export fixed; final copy still not approved

Locations: `orchestrator/client_reporter.py:73`, `:637`;
`orchestrator/campaign_builder.py:250`, `:261`, `:276`.

Independent rerun of the exact supported-column backtick fixture now refuses
approval with zero parsed keywords/negatives/headlines/descriptions. The added
compiled entity check is a useful second boundary. Accept that narrow fix.

The earlier request also required approval of the actual compiled output.
Using the valid temporary evidence fixture, real approval and real compiler,
export still succeeds as verified after adding **12 headlines and 2 descriptions
absent from the approved research**. The loader alone was mocked. These include
"Schedule A Consultation" and catalog/selection copy generated by the builder.
They may be useful draft suggestions, but were not individually approved.

Required fix: compile first, review/hash the final campaign, then export exactly
those bytes; or forbid generated padding on verified paths. Defaults can remain
for visibly marked drafts. Do not imply that count>0 validates final claims.

## Measured Verification and Limits

- Initial continuity recovery: rev 188, 0 discrepancies, 8/8 references match.
- Exact full gate: `python -B tests/run_all.py`, **106/106 suites, exit 0**.
  No documentation edits overlapped it. Gate success does not cover the negative
  scenarios above and does not establish safe credential-store isolation.
- Five requested modules: **76 tests, zero skips, exit 0**, run through unittest
  with an ephemeral in-memory signing/trust-key override and host key writes
  forbidden. This is NOT a claim that the exact unwrapped focused command is
  hermetic. Browser fixture disconnect tracebacks were nonfatal.
- Live status: ESTOP engaged with intact integrity; no canary marker; 218 ledger
  rows, 0 running. No active write owners before this documentation claim.
- Fresh local deployment checks: egress `attestation_mismatch`; audit
  `audit_enforcement_not_enabled`. Full release preflight was NOT rerun this
  round; no safe_to_proceed or release-authorization claim is made.
- Browser tests use local loopback HTTP/CDP traffic. No external provider,
  cohort, outreach or ad-platform execution occurred.

All **299 monitored artifact files** matched both the entry snapshot and the
prior review after the gate, focused tests and probes. Git status alone cannot
establish integrity of ignored files. Same absolute-path + SHA256 aggregation
algorithm as the prior review:

| Tree | Files | SHA256 aggregate |
| --- | ---: | --- |
| workspace/clients | 125 | e969dd49c1fdc4beecdfe98f51a052cb05029f33194c9b236893d2283479a5ba |
| workspace/backups | 164 | d2c124420e4ec96b0edc4af8c2122346d38fba785fbc7259e51981248dcf2b4a |
| workspace/verifications | 2 | 8ba8454c336b7ceefe928b667e696d77c9eef17a286b1d00d833f43697c05250 |
| workspace/outbound_pitches | 8 | 79e67aba1561e8c0956f0a9cc9ff49690d9c8a9173389b01ec5d18aaaea1021b |

## Next Agent Sequence

1. Bootstrap and claim ownership. Isolate the signing regression before running
   more full gates. Preserve all existing dirty changes and production artifacts.
2. Implement durable per-call budgets at the actual execution/transport boundary,
   including failover, interruption and corrupt-state recovery. Register regressions
   proving the second fake call is not made once the first exhausts capacity.
3. Wire structured review verification into audit/fitness with mandatory current
   artifact/task/verdict binding; prove replay rejection and signed-failure counting.
4. Persist and consume per-role/per-attempt cost evidence end-to-end; verify mixed
   paid-model, unknown, retry and invoice round-trips without critic-note parsing.
5. Bind export approval to compiled output; test that unapproved padding cannot
   be exported as verified. Recheck the supported-column empty-cell counterexample.
6. Independent acceptance, then operator-approved integration and deployment
   evidence. Do not repair a readiness display by bypassing checks or rewriting
   historical evidence. A client pilot still needs explicit live authority.

Read: bootstrap/architecture, Gemini's latest verification brief, prior Codex RR
review, this review, and the production callers/tests named in each finding.
Codex changed only this report, CURRENT_STATE, the product acceptance board,
ACTIVE_WORK and continuity. No production code/test repairs, client edits,
host policy changes, intentional credential provisioning, commit or push.
Release documentation ownership at closeout and refresh continuity with real
reference hashes. Keep ESTOP engaged.

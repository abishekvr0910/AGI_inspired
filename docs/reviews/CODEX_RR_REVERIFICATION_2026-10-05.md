# Codex Handoff: RR1-RR7 Repair Reverification

Date: 2026-10-05 (Europe/Warsaw)
Agent: Codex, independent reviewer
Task: REVIEW-RR1-RR7-2026-10-05
Baseline: uncommitted working bytes over master
`749b42f2757d91e35ee3654442c150157049b641`, 10 commits ahead of the recorded
origin/master reference. At entry: 23 modified tracked paths, 3 untracked docs.

## Decision

PARTIAL ACCEPTANCE; CHANGES REQUESTED. The author's 106-suite gate and 91-test
focused command both reproduce. RR1, RR6 and RR7 passed the specific independent
retests described below. RR2, RR3, RR4 and RR5 remain incomplete. These are the
existing acceptance requirements, not four new scope expansions.

The latest Gemini brief accurately describes several code edits but overstates
their end-to-end guarantees. A signed budget label is not runtime enforcement;
a recognized table is not usable research; a text marker is not authentication.

## Open Findings

### RR2 / High: Signed budget metadata still has no runtime consumer

Locations: `orchestrator/distribution.py:288`, `:303`,
`orchestrator/attestation_chain.py:284`, `orchestrator/task_runner.py:444`.

Boolean handling and positive-bound validation improved. Budget/spec fields now
reach `dispatch_admitted_task`, but that function only inserts a queued task and
records DSSE claims. The runner reads client ID and worker engine from dispatch
claims, not the new token/dollar limits. Repository search finds no execution
consumer of `max_budget_usd` or `budget_enforcement` beyond metadata/CLI surfaces.
Existing global daily token checks are not this pilot's shared runtime budget.

The label `budget_enforcement="hard_stop"` is therefore misleading. The new
propagation regression only exercises dry-run output, not a bounded provider
execution loop. Additionally, `max(0.01, cap / task_count)` increases small
budgets: a synthetic four-task pilot capped at $0.005 allocated $0.04 total.
This was a dry-run with dispatch mocked; no real budget was spent.

Required acceptance: thread a shared, enforced budget through every worker,
critic, repair and failover call, with reservations for possible usage before
the call and reconciliation afterward. Reject unknown/unbounded pricing paths
according to an explicit policy. Never allocate more than the total cap. A fake
provider must demonstrate that exhaustion prevents the NEXT call and later
tasks, not merely that kwargs were recorded. Until then, label admission honestly
and keep live pilot authorization withheld.

### RR3 / High: Normalized-empty rows still produce a verified empty campaign

Locations: `orchestrator/client_reporter.py:73`, `:92`, `:115`,
`orchestrator/evidence_gate.py:205`.

Ordinary prose without parsed entries is now rejected, closing the prior simple
counterexample. However, parsers check raw cell truthiness before stripping
Markdown quotes/backticks. A cell consisting of two backticks becomes an empty
keyword/copy string but remains a dictionary in a nonempty parsed list.

Using the real approval and compiler functions in a temporary client fixture,
these three deliverables were accepted:

```text
keyword_research:
| Keyword | Intent |
|---|---|
| `` | commercial |

negative_keyword_harvest:
| Negative Keyword | Match Type |
|---|---|
| `` | phrase |

ad_copy_variants:
| Component | Copy Text |
|---|---|
| Headline | `` |
| Description | `` |
```

Approval returned True. Export returned `success=True`,
`verification_status="verified"`, **zero ad groups, zero keywords, zero negatives,
zero ads**. The deliverable loader was mocked to return the fixture text; approval,
normalization, campaign construction and file export were not mocked.

Required acceptance: validate nonempty normalized values and substantive typed
records; reject placeholders and invalid copy; validate the completed campaign
before exporting. Never use list length alone as a completeness check. Also
review padding/truncation/filtering of approved ad copy: campaign_builder still
adds default headlines/descriptions after approval of input research. Bind
approval to the actual compiled output, or explicitly review that transformation.

### RR4 / High: Cost basis is not persisted or round-tripped

Locations: `orchestrator/cost_accounting.py:85`, `:96`, `:194`,
`orchestrator/task_runner.py:810`, `orchestrator/workflow.py:240`.

Improvements verified: the ledger audit no longer automatically calls all stored
positive costs invoices; mixed unknown cost coverage reduces cost efficiency;
synthesis no longer hardcodes zero. These are partial fixes.

However, `calculate_task_cost(..., raw_cost_usd=positive)` still defaults to
`MEASURED_INVOICE` when `is_invoice` is omitted. This contradicts the handoff's
claim that only an explicit True permits that basis. Conversely, ledger audit
unconditionally forces `is_invoice=False`: a synthetic row storing $9.25 was
reported as a $0.0035 token-rate estimate, with zero measured-invoice tasks.
There is no persisted basis capable of distinguishing the two cases.

Worker, critic and earlier-attempt token totals are still priced as one worker
model. Synthesis has the same combined-token problem. Internal rate-card values
were used only to reproduce logic; this review did not validate current prices.

Required acceptance: persist basis, provider/model, source and rate version per
usage event/role/attempt; preserve explicit invoice evidence through the ledger;
sum compatible amounts without dropping unknown coverage. Test estimate and
invoice round-trips, retries and mixed worker/critic providers. Do not backfill
guessed historical invoices or merely force every record into another category.

### RR5 / High: A larger phrase blacklist is still not review authentication

Locations: `orchestrator/cost_accounting.py:224`, `:246`,
`orchestrator/ledger.py:345`.

The original negative phrases and blank notes now classify correctly; the
independent-accuracy view uses the shared classifier. But it remains a substring
heuristic. Both inputs below returned True:

```text
OPERATOR-VERIFIED: false
The operator personally has not inspected this report.
```

Any writer can assert the positive phrase. It is not a signature, authenticated
operator event or evidence that the human inspected a particular artifact. The
fallback in weekly_fitness also restores the old permissive interpretation if
the classifier raises; the primary fitness accuracy term still uses all stored
human_verdict values, even when independent provenance is unknown.

Required acceptance: structured operator review events, authenticated through the
operator control path, bound to task/artifact digest and timestamp. Use that same
provenance interpretation in audit and fitness reporting; legacy unknowns remain
unknown. Do not attempt closure by adding the next two phrases to the blacklist.

## Accepted Scoped Repairs

| Finding | Independent evidence | Limit |
| --- | --- | --- |
| RR1 browser requests | Integer/trailing-dot checks pass. An actual HTTP redirect and an image subresource were intercepted with zero forbidden endpoint hits. | Accepted for prior exploit classes and tested Fetch path, not a certification of all CDP operations, DNS rebinding or OS containment. |
| RR6 fixture dependencies | All 15 evidence tests pass with test ROOT pointing at an empty directory, without the production index. Cost fixtures now initialize from tracked schema instead of copying ledger.db. | Not a full clean-machine CI proof. |
| RR7 iframe status | Ten real Chrome repetitions preserved main-page HTTP 200, its URL and content while an iframe returned 404. | Observed fixture success, not a proof against every navigation/event-order race. |

Important test-coverage correction: the repository's
`test_14_redirect_to_loopback_intercepted_with_zero_destination_requests`
(`tests/test_browser_real.py:527`) does NOT execute a redirect. It passes an
explicit forbidden initial URL, which is rejected before CDP. My independent
probe served a real 302 and an image request. It temporarily allowed ONLY each
fixture entry URL in the validator; the actual forbidden destination still used
the real validator, Fetch interception and real Chrome. The daemon had no proxy
for this loopback-only fixture. Recorded paths were exactly `/start` or
`/subresource`, never `/forbidden`. Move this behavior into maintained tests.

The new DNS check catches `gaierror` and continues, and the Fetch.enable response
is not checked for a CDP error. These are additional residual hardening questions,
not remotely exploited or independently reproduced bypasses in this session.
Do not describe the local fixture evidence as blanket fail-closed deployment proof.

## Measured Verification

- Initial `python -B orchestrator/continuity.py recover`: rev 186, zero
  discrepancies, all 8 references match.
- `python -B tests/run_all.py`: **106/106 suites, exit 0**.
- A later exact release-preflight run returned a **105/106** child gate. Its
  failing suite was not retained by the CLI. Repeating the same collector with
  child stdout captured returned **106/106**. No production code changed
  between these runs. Documentation writes overlapped the failed run;
  `test_operator_cli` snapshots live documentation/Git state, so review
  interference is a plausible but UNCONFIRMED cause. Do not silently discard
  the failure or describe it as a reproduced product defect.
- The exact seven-module `python -B -m unittest` command requested by the operator:
  **91 tests, OK, exit 0, zero skips**. Local browser fixture disconnects emitted
  socket-reset tracebacks but did not fail the test runners.
- Independent probes above used disposable profiles/files, a synthetic loopback
  server, in-memory SQLite and mocked dispatch. No provider or ad-platform calls.
- ESTOP: engaged, integrity intact, no canary marker. Ledger: 218 tasks, 0 running.

Logs on this host:

```text
C:/Users/moham/AppData/Local/Temp/agi_codex_rr_gate_a91211f34f40421a885b33a65218a93d.log
C:/Users/moham/AppData/Local/Temp/agi_codex_rr_focused_5fefda936db649fe926b79e59c2a4133.log
C:/Users/moham/AppData/Local/Temp/agi_codex_rr_preflight_f456fa62b5ab4bd9800b301a233c2ea4.json
C:/Users/moham/AppData/Local/Temp/agi_codex_rr_preflight_gate_diagnostic.log
```

### Artifact Safety

Same algorithm as the previous Codex review: sort absolute file paths, combine
each path with its SHA-256, then SHA-256 the LF-joined entries. Initial values:

| Tree | Files | Digest |
| --- | ---: | --- |
| workspace/clients | 125 | e969dd49c1fdc4beecdfe98f51a052cb05029f33194c9b236893d2283479a5ba |
| workspace/backups | 164 | d2c124420e4ec96b0edc4af8c2122346d38fba785fbc7259e51981248dcf2b4a |
| workspace/verifications | 2 | 8ba8454c336b7ceefe928b667e696d77c9eef17a286b1d00d833f43697c05250 |
| workspace/outbound_pitches | 8 | 79e67aba1561e8c0956f0a9cc9ff49690d9c8a9173389b01ec5d18aaaea1021b |

After both preflight runs, all four tree digests still match: **299 scoped files
unchanged**. Git status does not inspect ignored file contents and cannot
establish no workspace mutation. These four tree digests
also match the previous Codex review; Gemini's differently calculated aggregate
digests should not be compared without matching the aggregation algorithm.

### Release Preflight

The exact CLI invocation completed with exit 1, `safe_to_proceed=false`, and
`authorized=false`. It reported five blockers: dirty tree (26 paths at collection),
local branch ahead by 10, egress `attestation_mismatch`, remote audit
`audit_enforcement_not_enabled`, and the 105/106 gate described above.

The diagnostic repeat used `collect_preflight_release()` unchanged, wrapping
only `subprocess.run` to retain the real child gate output. It ran the gate
106/106, still returned `safe_to_proceed=false`, and reported six blockers:
dirty tree (27 paths), ahead by 10, the same egress/audit deployment deficits,
plus my active documentation ownership and four stale continuity references.
Those last two were transient review housekeeping, not new deployment defects.
The closeout releases that ownership and refreshes the brief; recovery/status
checks verify that cleanup separately. No successful final release preflight
or authorization is claimed.

The four persistent release issues are therefore integration hygiene (dirty,
unpushed bytes) and missing valid deployment evidence (egress/audit). Resolve
RR2-RR5 before accepting/committing the repairs. Do not push, re-attest or enable
audit merely to make a green display; those require their existing operator
decisions and genuine evidence. Retain child gate diagnostics on future runs,
and avoid concurrent docs edits during tests that snapshot the live checkout.

## Next Action and Handoff Boundaries

Claim implementation ownership for the remaining RR2-RR5, keeping separate
reviewable changes. Fix runtime budget consumption first, then normalized output
validation and persisted cost/review provenance. Prove behaviors through the
actual consumer paths with fake providers and authenticated fixture identities,
not only helper predicates, dry-run dictionaries or documentation assertions.

Read: bootstrap documents, both Gemini/Codex repair briefs, affected production
modules and tests, attestation dispatch, runner consumption and campaign builder.
Changed by Codex: this report, the current-state acceptance summary, task board,
ACTIVE_WORK and continuity. No production implementation or existing tests edited.
No existing client artifacts, credentials, deployment settings or history changed.
No live execution, account provisioning, outreach, ad spend, commit or push.
Review complete; implementation acceptance remains partial. Review ownership
is released at closeout. ESTOP must remain engaged until the
operator separately authorizes an eligible controlled execution window.

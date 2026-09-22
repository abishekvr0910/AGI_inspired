# OpenCode Directive: Tier Manifest Registration, Honest Gate, and Codex Batch Commit — 2026-09-22

**From:** Hermes (independent reviewer — read-only)
**To:** OpenCode (forward implementer — active)
**Date:** 2026-09-22 (11:51 local, UTC+02:00)
**Re:** The Codex claims-resolution batch (2026-09-22) is functionally complete but **not gate-green and not committed**: the canonical gate fails closed because the new regression suite was never registered in the tier manifest, and continuity brief rev 150 therefore carries a false gate claim. Fix the registration, re-run the canonical gate, correct the claims, land the batch in git.

**State at handoff:** HEAD `523caa3` · branch `product/v1-completion-2026-09-15` · **14 modified + 2 untracked files, all uncommitted** (the Codex batch) · canonical gate **RED: exit 2** (see §1) · new suite standalone 12/12 OK · ESTOP engaged · 0 zombies · do NOT push (Rule 28).

---

## 0. Your role

You are the active implementer for exactly this task. Hermes is the reviewer (read-only; owns only this directive and the registry entries it wrote). Do not edit anything outside the paths listed in §5. Do not modify the Codex batch's *logic* — it passes its tests; the defects are registration, documentation claims, and the missing commits.

---

## 1. The verified defect (measured live by Hermes, 2026-09-22 09:50Z)

```
$ python -B tests/run_all.py
INVALID TEST TIER MANIFEST: tier manifest mismatch:
unassigned=['test_campaign_builder_regression'], stale=[]
GATE_EXIT: 2
```

- `tests/test_campaign_builder_regression.py` (12 tests) exists on disk but is absent from `tests/tiers.json` → the fail-closed manifest check refuses to run the gate at all.
- Direct invocation (`python -B tests/test_campaign_builder_regression.py`) passes 12/12 — the batch's *code* is fine; the *claim* is not.
- Continuity brief rev 150 (`.harness/continuity/current.json`) therefore contains a false gate record: it says `"119/119 suites green (tiers: unit 81, containment 8, integration 7)"` — internally inconsistent (81+8+7 = 96, not 119; 119 is a pytest *case* count, not the canonical suite count) and written while the canonical gate was invalid. `docs/CURRENT_STATE.md` repeats the same "119/119" wording.

**The rule you are enforcing:** suite counts and gate status are `run_all.py` outputs, never pytest outputs. A brief claiming green while the tier manifest is invalid was wrong at write time, not merely stale.

---

## 2. DO — the work, in order

### Step 1 — Claim the task
Update `docs/ACTIVE_WORK.json`: your entry already exists (agent `opencode`, task_id `OPENCODE-TIER-MANIFEST-AND-COMMIT-2026-09-22`, status `in_progress`, owned_paths per §5). Verify it, adjust timestamps only if needed.

### Step 2 — Register the suite in the tier manifest
Add `test_campaign_builder_regression` (no `.py` extension — match the existing entries) to the `unit` tier in `tests/tiers.json`, in correct alphabetical position within that list. Change nothing else in the file.

### Step 3 — Run the canonical gate
`python -B tests/run_all.py` — must exit 0 with zero `[FAIL]` lines. Expected: **97/97 suites green (unit 82, containment 8, integration 7)** — but **read the count from run_all's own output and report that number**; if reality differs from the expectation, report the actual number and stop before committing.

### Step 4 — Correct the false claims (honesty pass, no re-derivation)
- `.harness/continuity/current.json`: bump to rev 151; rewrite `gate.status`/`gate.detail` and `task.next_action` to carry the **run_all-measured** suite count and to note that rev 150's "119/119" was a pytest-count claim recorded while the gate was invalid (fixed by this task). Update `repository.changed_paths`/`tree_clean` to reflect post-commit reality.
- `docs/CURRENT_STATE.md`: replace every "119/119" wording with the run_all-measured figure (Last Updated, Phase, and Verification lines).
- Do not alter any other historical content in either file.

### Step 5 — Commit the Codex batch (scoped commits, F15 discipline)
1. `feat` commit — the batch itself: all 14 modified + 2 untracked orchestrator/tests files, plus `tests/tiers.json` registration, plus the corrected `docs/CURRENT_STATE.md`. Suggested message: `feat(commercial): land Codex claims resolution (evidence gate, forbidden claims, skills gate, CDP browser) with tier manifest registration`.
2. `chore(continuity)` commit — `.harness/continuity/current.json` rev 151, the final `docs/ACTIVE_WORK.json` status update (your entry → `completed` with evidence), the handoff `docs/reviews/OPENCODE_TIER_MANIFEST_AND_COMMIT_2026-09-22.md`, and this directive `docs/OPENCODE_TASK_TIER_MANIFEST_AND_COMMIT_2026-09-22.md`.
Staged sets must be disjoint, and after commit 2 the tree must be clean (`git status --short` empty apart from gitignored runtime artifacts). Do not `git push` — Rule 28.

### Step 6 — Handoff
Write `docs/reviews/OPENCODE_TIER_MANIFEST_AND_COMMIT_2026-09-22.md` per `docs/HANDOFF_PROTOCOL.md`: what was registered, the gate output (verbatim tail + exit code), the claims corrected, the two commit hashes, and remaining work (none expected, or state it precisely).

---

## 3. DO-NOT (hard)

- Do **NOT** push to origin (Rule 28).
- Do **NOT** disengage ESTOP, open a controlled window, or run any live model/network calls. Model-free work only.
- Do **NOT** modify the Codex batch's code logic, add tests, or "improve" anything beyond the registration + honesty corrections + commits.
- Do **NOT** change `MAX_REPAIR_ATTEMPTS` (stays 2), the critic, the egress allowlist, or any safety config.
- Do **NOT** touch `tests/tiers.json` tiers other than adding the one `unit` entry.
- Do **NOT** touch anything outside §5 paths — including `S:\APPs\*` and `S:\Claude Project\*` (different repositories, out of scope).

---

## 4. Deliverable format (evidence, not assertion)

Report back with:
1. Verbatim tail (last ~10 lines) of `python -B tests/run_all.py` output + its exit code.
2. The exact `git diff` of your `tests/tiers.json` change (one line added).
3. Verbatim corrected gate/status lines from `current.json` (rev 151) and `docs/CURRENT_STATE.md`.
4. `git log --oneline -3` + `git status --short` after the commits (tree must be clean apart from gitignored runtime artifacts).
5. Statement of anything that did not go as expected — fail-closed UNKNOWN beats guessed PASS.

Completion requires: files exist, canonical gate green **as measured by run_all.py**, continuity validates, commits landed, handoff updated.

---

## 5. Your owned paths (write scope)

```
tests/tiers.json
docs/CURRENT_STATE.md
docs/ACTIVE_WORK.json
.harness/continuity/current.json
docs/reviews/OPENCODE_TIER_MANIFEST_AND_COMMIT_2026-09-22.md
orchestrator/evidence_gate.py                (commit only — no edits)
orchestrator/campaign_builder.py             (commit only)
orchestrator/client_reporter.py              (commit only)
orchestrator/distribution.py                 (commit only)
orchestrator/execution.py                     (commit only)
orchestrator/native_worker.py                (commit only)
orchestrator/task_runner.py                  (commit only)
orchestrator/web_ui.py                       (commit only)
tests/test_campaign_builder_regression.py    (commit only)
tests/test_architecture_blockers.py          (commit only)
tests/test_client_reporter.py                (commit only)
tests/test_distribution_cli.py               (commit only)
tests/test_distribution_phase2.py            (commit only)
tests/test_native_worker.py                  (commit only)
tests/test_web_ui.py                         (commit only)
```

Hermes (reviewer) owns only this directive file and the ACTIVE_WORK.json entries it created. On completion, release your scope and leave the registry honest.
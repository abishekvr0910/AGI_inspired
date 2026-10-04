# AGENTS.md — Universal Agent Entry Point

This is the canonical entry point for all autonomous agents (Gemini, DeepSeek/Cade, Claude, Codex, Hermes) resuming work on the AGI_like harness.

---

## Universal Bootstrap Sequence

Before performing any action, reading deep history, or modifying files:

1. **Read Compact Brief:** Read [`.harness/continuity/current.json`](.harness/continuity/current.json).
2. **Check Active Work & Locks:** Read [`docs/ACTIVE_WORK.json`](docs/ACTIVE_WORK.json) to verify write ownership and avoid concurrent file conflicts.
3. **Read Current State:** Read [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).
4. **Read Architecture & Master Map:** Read [`docs/CANONICAL_ARCHITECTURE.md`](docs/CANONICAL_ARCHITECTURE.md) and [`docs/README.md`](docs/README.md). Note that prior agent shift handoffs and completed task directives are archived in `docs/archive/` and must NOT be treated as active work orders.
5. **Run Continuity Recovery:** Run `python orchestrator/continuity.py recover`.
6. **Verify Model-Free Test Gate:** Run `python tests/run_all.py` (all green, no FAIL).
7. **Verify Live State:** Live state wins over historical documentation (live always wins).
8. **Summarize Understanding:** Summarize your understanding of current state, task boundaries, and safety invariants before making edits.

---

## Canonical Document Index

* **Master Documentation Index:** [`docs/README.md`](docs/README.md)
* **Machine-Readable State:** [`.harness/continuity/current.json`](.harness/continuity/current.json)
* **Active Agent Registry:** [`docs/ACTIVE_WORK.json`](docs/ACTIVE_WORK.json)
* **Canonical Current State:** [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
* **Canonical Architecture:** [`docs/CANONICAL_ARCHITECTURE.md`](docs/CANONICAL_ARCHITECTURE.md)
* **Enterprise Readiness:** [`docs/SECURITY_BLUEPRINT_2026-09-04.md`](docs/SECURITY_BLUEPRINT_2026-09-04.md)
* **Handoff Protocol:** [`docs/HANDOFF_PROTOCOL.md`](docs/HANDOFF_PROTOCOL.md)
* **Chat / Human Continuity (Archived):** [`docs/archive/historical/CHAT_CONTINUITY_2026-08-30.md`](docs/archive/historical/CHAT_CONTINUITY_2026-08-30.md)
* **Chronological Incident & Fix Registries:** [`docs/INCIDENTS.md`](docs/INCIDENTS.md), [`docs/HARDENING.md`](docs/HARDENING.md)

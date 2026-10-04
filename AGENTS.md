# AGENTS.md — Universal Agent Entry Point

Entry point for autonomous agents (Gemini, Cade, Claude, Codex, Hermes) on AGI_like.

---

## Universal Bootstrap Sequence

Before performing any action, reading deep history, or modifying files:

1. **Read Compact Brief:** Read [`.harness/continuity/current.json`](.harness/continuity/current.json).
2. **Check Active Work & Locks:** Read [`docs/ACTIVE_WORK.json`](docs/ACTIVE_WORK.json) to verify write ownership.
3. **Read Current State:** Read [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md).
4. **Read Architecture & Master Map:** Read [`docs/CANONICAL_ARCHITECTURE.md`](docs/CANONICAL_ARCHITECTURE.md) and [`docs/README.md`](docs/README.md). Files in `docs/archive/` are historical, not active work.
5. **Run Continuity Recovery:** Run `python orchestrator/continuity.py recover`.
6. **Verify Model-Free Test Gate:** Run `python tests/run_all.py` (all green, no FAIL).
7. **Verify Live State:** Live state wins over historical documentation (live always wins).
8. **Summarize Understanding:** Summarize state and invariants before making edits.

---

## Canonical Document Index

* **Master Index:** [`docs/README.md`](docs/README.md)
* **Machine-Readable State:** [`.harness/continuity/current.json`](.harness/continuity/current.json)
* **Active Agent Registry:** [`docs/ACTIVE_WORK.json`](docs/ACTIVE_WORK.json)
* **Canonical Current State:** [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md)
* **Canonical Architecture:** [`docs/CANONICAL_ARCHITECTURE.md`](docs/CANONICAL_ARCHITECTURE.md)
* **Enterprise Readiness:** [`docs/SECURITY_BLUEPRINT_2026-09-04.md`](docs/SECURITY_BLUEPRINT_2026-09-04.md)
* **Handoff Protocol:** [`docs/HANDOFF_PROTOCOL.md`](docs/HANDOFF_PROTOCOL.md)
* **Incident & Fix Registries:** [`docs/INCIDENTS.md`](docs/INCIDENTS.md), [`docs/HARDENING.md`](docs/HARDENING.md)
* **Chat Continuity (Archived):** [`docs/archive/historical/CHAT_CONTINUITY_2026-08-30.md`](docs/archive/historical/CHAT_CONTINUITY_2026-08-30.md)

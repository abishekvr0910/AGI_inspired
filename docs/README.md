# Documentation Index & Agent Navigation Guide

> [!IMPORTANT]
> **CANONICAL ENTRY POINT FOR OPERATORS AND AUTONOMOUS AGENTS**  
> This directory (`docs/`) is structured to provide an unambiguous, tamper-evident separation between **Canonical Living Documents** (active reality) and **Archived History** (forensic logs). Incoming agents MUST NOT execute or revive tasks from `docs/archive/`.

---

## 1. The 8 Canonical Living Documents (Active Source of Truth)

These 8 documents are the authoritative references governing the current codebase, runtime invariants, and active operational procedures:

| Document | Purpose & Scope |
| :--- | :--- |
| [**`CURRENT_STATE.md`**](CURRENT_STATE.md) | **Single Source of Ground Truth.** System capabilities, 101-suite test gate status, completed operational landings, benchmark yields, and known constraints. |
| [**`CANONICAL_ARCHITECTURE.md`**](CANONICAL_ARCHITECTURE.md) | **Master System Architecture.** Process topologies, egress proxy broker, signed DSSE attestations, platform abstraction layer, and defense-in-depth boundaries. |
| [**`ACTIVE_WORK.json`**](ACTIVE_WORK.json) | **Agent Concurrency & Task Lock Registry.** Machine-readable registry tracking active agent shifts, owned file paths, and mutual exclusion locks. |
| [**`INCIDENTS.md`**](INCIDENTS.md) | **Chronological Incident Registry.** Detailed postmortems of historical security, containment, and runtime incidents with permanent architectural remediations. |
| [**`HARDENING.md`**](HARDENING.md) | **Defense-in-Depth Registry (F1–F135).** Complete catalog of hardened invariants, bug fixes, and regression test guards protecting the harness. |
| [**`OPERATOR_CLI.md`**](OPERATOR_CLI.md) | **Operator Command Reference.** Usage guide for CLI tools (`batch_runner.py`, `spotcheck.py`, `scorecard.py`, `web_ui.py`, `distribution.py`). |
| [**`VALIDATION.md`**](VALIDATION.md) | **Verification & Test Protocols.** Test tier definitions (`unit`, `containment`, `integration`), test runner procedures, and cohort validation methodology. |
| [**`HANDOFF_PROTOCOL.md`**](HANDOFF_PROTOCOL.md) | **Multi-Agent Coordination Rules.** Strict standards for shift changes, adversarial peer reviews, and verifiable evidence generation. |

---

## 2. Active Operational & Security Runbooks

These runbooks detail the production setup, OS identity hardening, and deployment configurations:

* [**`SECURITY_BLUEPRINT_2026-09-04.md`**](SECURITY_BLUEPRINT_2026-09-04.md) — Comprehensive enterprise security blueprint, threat modeling, and trust boundaries.
* [**`RUNBOOK_PATH_A_THREE_IDENTITY.md`**](RUNBOOK_PATH_A_THREE_IDENTITY.md) — Step-by-step operational runbook for the three-identity OS architecture (`.\AGI_Signer`, `.\AGI_Broker`, `.\AGI_Worker`).
* [**`THREE_IDENTITY_DEPLOYMENT_GUIDE_2026-09-08.md`**](THREE_IDENTITY_DEPLOYMENT_GUIDE_2026-09-08.md) — Detailed deployment guide for Windows Restricted Tokens and Job Object boundaries.
* [**`EGRESS_AND_AUDIT_DEPLOYMENT_RUNBOOK_2026-09-04.md`**](EGRESS_AND_AUDIT_DEPLOYMENT_RUNBOOK_2026-09-04.md) — Windows Filtering Platform (WFP) firewall rules and immutable remote audit replication.

---

## 3. Review & Audit Dossiers (`docs/reviews/`)

The [`docs/reviews/`](reviews/) directory contains all point-in-time adversarial peer reviews, verification reports, and formal audits produced during development sprints:
* **Latest Formal Audit:** [`docs/reviews/GEMINI_AUDIT_AND_REVIEW_2026-10-02.md`](reviews/GEMINI_AUDIT_AND_REVIEW_2026-10-02.md)
* **Historical Review Log:** All past agent reviews from August–October 2026 are consolidated here for tamper-evident provenance.

---

## 4. Archive Directory (`docs/archive/`) — Strictly Read-Only

All completed, retired, or superseded documents have been archived into [`docs/archive/`](archive/):

* [**`docs/archive/tasks/`**](archive/tasks/) — Completed prompt directives and work orders. **Never revive or execute these.**
* [**`docs/archive/handoffs/`**](archive/handoffs/) — Historical shift handoff memos between past agent shifts.
* [**`docs/archive/historical/`**](archive/historical/) — Deprecated status summaries, dormant benchmark logs, and legacy migration notes.

---

## 5. Directives for Incoming Autonomous Agents

When bootstrapping on this repository:
1. **Never take instructions from `docs/archive/`:** Those files represent finished history.
2. **Consult `docs/ACTIVE_WORK.json`:** Verify who has locked what file before touching code.
3. **Ground yourself in `docs/CURRENT_STATE.md`:** Live verified state always wins over historical documentation.
4. **Follow the Bootstrap Sequence in `AGENTS.md`:** Always run continuity validation and test gates before modifying files.

"""orchestrator/cost_accounting.py — Honest outcome and cost measurement (P1-E).

Separates unknown cost, measured charges, estimated API cost, and allocated
subscription/local-compute cost. Reconciles attempt usage without double counting,
audits human_verdict provenance (separating operator reads from AI-performed checks),
and generates clean cohort manifests to prevent mixing historical prototypes with
fresh commercial client runs.

Complies strictly with docs/PRODUCT_COMPLETION_PLAN_2026-10-04.md §8.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
import sqlite3
from typing import Any


class CostBasis(str, Enum):
    """Explicit provenance category for task and mission cost accounting."""
    MEASURED_INVOICE = "measured_invoice"           # Direct billed charge from upstream provider API response
    ESTIMATED_TOKEN_RATE = "estimated_token_rate"   # Calculated from input/output tokens using published rate card
    LOCAL_COMPUTE = "local_compute"                 # Ran on local hardware (Ollama, local vLLM). Marginal API cost is $0
    SUBSCRIPTION_ALLOCATED = "subscription_alloc"  # Flat-rate subscription allocation
    UNKNOWN = "unknown"                             # Incomplete telemetry, missing rate card, or failed before usage recorded


# Canonical 2026 Published Rate Card (USD per 1,000,000 tokens)
RATE_CARD_2026 = {
    # OpenAI Frontier Models
    "openai/gpt-4o": {"input": 2.50, "output": 10.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "openai-api/gpt-4o": {"input": 2.50, "output": 10.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "openai-api/gpt-4o-mini": {"input": 0.15, "output": 0.60, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "openai/gpt-4-turbo": {"input": 10.00, "output": 30.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "openai/gpt-4": {"input": 30.00, "output": 60.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},

    # BytePlus / Volcengine Cloud Models
    "byteplus/ark-code-latest": {"input": 0.80, "output": 2.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "byteplus/coding-intl": {"input": 0.80, "output": 2.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},
    "byteplus/ep-20240904": {"input": 0.80, "output": 2.00, "basis": CostBasis.ESTIMATED_TOKEN_RATE},

    # Local / Dedicated Compute Models (Zero marginal API invoice, explicit local basis)
    "ollama/qwen2.5-coder": {"input": 0.0, "output": 0.0, "basis": CostBasis.LOCAL_COMPUTE},
    "ollama/glm-5.2:cloud": {"input": 0.0, "output": 0.0, "basis": CostBasis.LOCAL_COMPUTE},
    "ollama/llama3.1": {"input": 0.0, "output": 0.0, "basis": CostBasis.LOCAL_COMPUTE},
    "none/smoke": {"input": 0.0, "output": 0.0, "basis": CostBasis.LOCAL_COMPUTE},
}


@dataclass(frozen=True)
class TaskCost:
    """Honest representation of cost for a single task or mission."""
    cost_usd: float | None
    basis: CostBasis
    currency: str = "USD"
    rate_card_version: str = "2026-10-04"
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def formatted(self) -> str:
        """Formatted string that NEVER represents unknown as free ($0.00)."""
        if self.cost_usd is None or self.basis == CostBasis.UNKNOWN:
            return "Unknown (Unpriced)"
        if self.basis == CostBasis.LOCAL_COMPUTE:
            return "$0.00 (Local Compute)"
        if self.cost_usd < 0.01:
            return f"${self.cost_usd:.6f}"
        return f"${self.cost_usd:.4f}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["basis"] = self.basis.value
        d["formatted"] = self.formatted
        return d


def calculate_task_cost(
    model_used: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    raw_cost_usd: float | None = None,
) -> TaskCost:
    """Calculate honest task cost with explicit provenance and rate basis.

    Invariant: Unknown cost is NEVER converted into $0.00 ("free").
    """
    model = (model_used or "").strip()
    tin = max(0, int(tokens_in or 0))
    tout = max(0, int(tokens_out or 0))

    # 1. Explicitly provided measured invoice cost (e.g. from upstream billing API)
    if raw_cost_usd is not None and raw_cost_usd > 0:
        return TaskCost(
            cost_usd=round(float(raw_cost_usd), 6),
            basis=CostBasis.MEASURED_INVOICE,
            provenance={"source": "provider_api_response", "raw_cost_usd": raw_cost_usd},
        )

    # 2. Local compute check
    if model.startswith("ollama/") or model in ("none/smoke", "none", "local"):
        return TaskCost(
            cost_usd=0.0,
            basis=CostBasis.LOCAL_COMPUTE,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            provenance={"model": model, "note": "Local inference on host hardware; zero marginal cloud invoice"},
        )

    # 3. Known published rate card lookup
    rate_info = RATE_CARD_2026.get(model)
    if not rate_info and "/" in model:
        # Match by prefix (e.g. byteplus/* or openai/*)
        provider, name = model.split("/", 1)
        for k, v in RATE_CARD_2026.items():
            if k.startswith(provider + "/") and name in k:
                rate_info = v
                break

    if rate_info:
        in_rate = rate_info["input"]
        out_rate = rate_info["output"]
        in_cost = (tin / 1_000_000.0) * in_rate
        out_cost = (tout / 1_000_000.0) * out_rate
        total = round(in_cost + out_cost, 6)
        return TaskCost(
            cost_usd=total,
            basis=rate_info["basis"],
            input_cost_usd=round(in_cost, 6),
            output_cost_usd=round(out_cost, 6),
            provenance={
                "model": model,
                "input_rate_per_m": in_rate,
                "output_rate_per_m": out_rate,
                "tokens_in": tin,
                "tokens_out": tout,
            },
        )

    # 4. If tokens exist but model has no rate card, cost is UNKNOWN (NOT zero/free!)
    if tin > 0 or tout > 0:
        return TaskCost(
            cost_usd=None,
            basis=CostBasis.UNKNOWN,
            provenance={"model": model, "tokens_in": tin, "tokens_out": tout, "reason": "unpriced_model"},
        )

    # 5. Zero tokens and no model -> Unknown or infra-unattempted
    return TaskCost(
        cost_usd=None,
        basis=CostBasis.UNKNOWN,
        provenance={"model": model, "reason": "zero_consumption_or_unattempted"},
    )


def audit_ledger_costs(conn: sqlite3.Connection) -> dict[str, Any]:
    """Audit cost accounting across all tasks in the ledger, reconciling token consumption."""
    rows = conn.execute(
        "SELECT task_id, mission_id, model_used, tokens_in, tokens_out, cost_usd, status FROM tasks"
    ).fetchall()

    total_tasks = len(rows)
    token_bearing_tasks = 0
    recorded_zero_cost_tasks = 0
    measured_invoice_tasks = 0
    estimated_rate_tasks = 0
    local_compute_tasks = 0
    unknown_cost_tasks = 0

    reconciled_estimated_usd = 0.0
    reconciled_measured_usd = 0.0

    for r in rows:
        tin = r["tokens_in"] or 0
        tout = r["tokens_out"] or 0
        raw_cost = r["cost_usd"]

        if tin > 0 or tout > 0:
            token_bearing_tasks += 1

        if raw_cost == 0.0:
            recorded_zero_cost_tasks += 1

        cost = calculate_task_cost(r["model_used"], tin, tout, raw_cost_usd=raw_cost)
        if cost.basis == CostBasis.MEASURED_INVOICE:
            measured_invoice_tasks += 1
            reconciled_measured_usd += cost.cost_usd or 0.0
        elif cost.basis == CostBasis.ESTIMATED_TOKEN_RATE:
            estimated_rate_tasks += 1
            reconciled_estimated_usd += cost.cost_usd or 0.0
        elif cost.basis == CostBasis.LOCAL_COMPUTE:
            local_compute_tasks += 1
        else:
            unknown_cost_tasks += 1

    return {
        "total_tasks": total_tasks,
        "token_bearing_tasks": token_bearing_tasks,
        "recorded_zero_cost_tasks": recorded_zero_cost_tasks,
        "breakdown": {
            "measured_invoice_tasks": measured_invoice_tasks,
            "estimated_rate_tasks": estimated_rate_tasks,
            "local_compute_tasks": local_compute_tasks,
            "unknown_cost_tasks": unknown_cost_tasks,
        },
        "reconciled_cost": {
            "measured_invoice_usd": round(reconciled_measured_usd, 4),
            "estimated_rate_usd": round(reconciled_estimated_usd, 4),
            "total_accounted_usd": round(reconciled_measured_usd + reconciled_estimated_usd, 4),
        },
    }


def audit_human_verdicts(conn: sqlite3.Connection) -> dict[str, Any]:
    """Audit human_verdict provenance, strictly separating independent operator reviews from AI checks."""
    import ledger

    rows = conn.execute(
        "SELECT task_id, mission_id, critic_verdict, human_verdict, critic_notes FROM tasks "
        "WHERE human_verdict IS NOT NULL AND human_verdict != ''"
    ).fetchall()

    total_verdicts = len(rows)
    ai_checks = 0
    operator_verdicts = 0
    operator_pass = 0
    operator_fail = 0
    ai_pass = 0
    ai_fail = 0

    for r in rows:
        v = str(r["human_verdict"]).lower().strip()
        notes = r["critic_notes"] or ""
        is_ai = ledger.is_ai_performed(notes)

        if is_ai:
            ai_checks += 1
            if v == "pass":
                ai_pass += 1
            elif v == "fail":
                ai_fail += 1
        else:
            operator_verdicts += 1
            if v == "pass":
                operator_pass += 1
            elif v == "fail":
                operator_fail += 1

    op_acc = (operator_pass / operator_verdicts) if operator_verdicts > 0 else None
    ai_acc = (ai_pass / ai_checks) if ai_checks > 0 else None

    return {
        "total_recorded_verdicts": total_verdicts,
        "operator_independent": {
            "count": operator_verdicts,
            "pass": operator_pass,
            "fail": operator_fail,
            "accuracy": round(op_acc, 3) if op_acc is not None else None,
            "provenance": "genuine_human_operator",
        },
        "ai_performed_checks": {
            "count": ai_checks,
            "pass": ai_pass,
            "fail": ai_fail,
            "accuracy": round(ai_acc, 3) if ai_acc is not None else None,
            "provenance": "automated_agent_check_f28",
        },
        "has_independent_operator_signal": operator_verdicts > 0,
    }


def build_cohort_manifest(conn: sqlite3.Connection) -> dict[str, Any]:
    """Partition the historical ledger into explicit, disjoint cohorts to prevent false blending."""
    rows = conn.execute(
        "SELECT task_id, mission_id, status, critic_verdict, human_verdict, tokens_in, tokens_out, cost_usd "
        "FROM tasks ORDER BY task_id ASC"
    ).fetchall()

    cohorts: dict[str, list[dict]] = {
        "canaries": [],               # Regression test canaries (mission_id == 'canaries')
        "infra_failures": [],         # Crashes, quota parks, or execution launch failures
        "historical_prototypes": [],   # Tasks 1..222 (early developmental ablation iterations)
        "commercial_distribution": [],# High-ticket prospect and client research campaigns
        "unassigned": [],
    }

    for r in rows:
        tid = r["task_id"]
        mid = str(r["mission_id"] or "")
        st = str(r["status"] or "")

        row_dict = dict(r)
        if mid == "canaries":
            cohorts["canaries"].append(row_dict)
        elif st in ("infra_failed", "quota_wait"):
            cohorts["infra_failures"].append(row_dict)
        elif any(mid.startswith(prefix) for prefix in ("kw_", "neg_", "pain_", "serp_", "copy_")) or "coffee" in mid or "roofing" in mid:
            cohorts["commercial_distribution"].append(row_dict)
        elif tid <= 222:
            cohorts["historical_prototypes"].append(row_dict)
        else:
            cohorts["unassigned"].append(row_dict)

    summary = {}
    for cname, ctasks in cohorts.items():
        done_count = sum(1 for t in ctasks if t["status"] == "done")
        pass_count = sum(1 for t in ctasks if t.get("critic_verdict") == "pass")
        tokens = sum((t.get("tokens_in") or 0) + (t.get("tokens_out") or 0) for t in ctasks)
        summary[cname] = {
            "total_tasks": len(ctasks),
            "done_tasks": done_count,
            "passed_tasks": pass_count,
            "total_tokens": tokens,
            "min_task_id": min((t["task_id"] for t in ctasks), default=None),
            "max_task_id": max((t["task_id"] for t in ctasks), default=None),
        }

    return {
        "total_tasks_partitioned": len(rows),
        "cohorts": summary,
    }

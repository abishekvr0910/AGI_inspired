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
import hashlib
import json
from pathlib import Path
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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TaskCost:
        basis_str = str(d.get("basis", "unknown")).lower()
        try:
            basis = CostBasis(basis_str)
        except Exception:
            basis = CostBasis.UNKNOWN
        return cls(
            cost_usd=d.get("cost_usd"),
            basis=basis,
            currency=d.get("currency", "USD"),
            rate_card_version=d.get("rate_card_version", "2026-10-04"),
            input_cost_usd=d.get("input_cost_usd"),
            output_cost_usd=d.get("output_cost_usd"),
            provenance=d.get("provenance", {}),
        )


def lookup_rate(model: str | None) -> dict[str, Any] | None:
    """Lookup rate card entry for a model string."""
    m = (model or "").strip()
    if not m:
        return None
    rate_info = RATE_CARD_2026.get(m)
    if rate_info:
        return rate_info
    if "/" in m:
        provider, name = m.split("/", 1)
        for k, v in RATE_CARD_2026.items():
            if k.startswith(provider + "/") and name in k:
                return v
    else:
        for k, v in RATE_CARD_2026.items():
            if k.endswith("/" + m) or k == m:
                return v
    return None


def calculate_task_cost(
    model_used: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    raw_cost_usd: float | None = None,
    is_invoice: bool | None = None,
) -> TaskCost:
    """Calculate honest task cost with explicit provenance and rate basis.

    Invariant: Unknown cost is NEVER converted into $0.00 ("free").
    """
    model = (model_used or "").strip()
    tin = max(0, int(tokens_in or 0))
    tout = max(0, int(tokens_out or 0))

    # 1. Explicitly provided measured invoice cost (e.g. from upstream billing API)
    if is_invoice is True and raw_cost_usd is not None and raw_cost_usd > 0:
        return TaskCost(
            cost_usd=round(float(raw_cost_usd), 6),
            basis=CostBasis.MEASURED_INVOICE,
            provenance={"source": "provider_api_response", "raw_cost_usd": raw_cost_usd, "is_invoice": True},
        )

    # 2. Local compute check (strictly local models; :cloud models are cloud-routed)
    if (model.startswith("ollama/") or model in ("none/smoke", "none", "local")) and ":cloud" not in model:
        return TaskCost(
            cost_usd=0.0,
            basis=CostBasis.LOCAL_COMPUTE,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            provenance={"model": model, "note": "Local inference on host hardware; zero marginal cloud invoice"},
        )

    # 3. Known published rate card lookup
    rate_info = lookup_rate(model)

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


def combine_task_costs(costs: list[TaskCost | None]) -> TaskCost:
    """Combine costs across multiple execution roles (worker, critic, repair) (RR4).

    Sums dollar costs where known, preserves role breakdowns in provenance,
    and accurately propagates unknown status if any required component is unpriced.
    """
    total_cost: float = 0.0
    total_in: float = 0.0
    total_out: float = 0.0
    has_unknown = False
    has_invoice = False
    has_rate = False
    has_local = False
    role_breakdowns: list[dict[str, Any]] = []

    for c in costs:
        if c is None:
            continue
        role_breakdowns.append({
            "basis": c.basis.value,
            "cost_usd": c.cost_usd,
            "input_cost_usd": c.input_cost_usd,
            "output_cost_usd": c.output_cost_usd,
            "provenance": c.provenance,
        })
        if c.basis == CostBasis.UNKNOWN or c.cost_usd is None:
            has_unknown = True
        elif c.basis == CostBasis.MEASURED_INVOICE:
            has_invoice = True
            total_cost += (c.cost_usd or 0.0)
        elif c.basis == CostBasis.ESTIMATED_TOKEN_RATE:
            has_rate = True
            total_cost += (c.cost_usd or 0.0)
            total_in += (c.input_cost_usd or 0.0)
            total_out += (c.output_cost_usd or 0.0)
        elif c.basis == CostBasis.LOCAL_COMPUTE:
            has_local = True

    if has_unknown:
        basis = CostBasis.UNKNOWN
        final_cost = None
    elif has_invoice and not has_rate:
        basis = CostBasis.MEASURED_INVOICE
        final_cost = round(total_cost, 6)
    elif has_rate or (has_invoice and has_rate):
        basis = CostBasis.ESTIMATED_TOKEN_RATE
        final_cost = round(total_cost, 6)
    elif has_local:
        basis = CostBasis.LOCAL_COMPUTE
        final_cost = 0.0
    else:
        basis = CostBasis.UNKNOWN
        final_cost = None

    return TaskCost(
        cost_usd=final_cost,
        basis=basis,
        input_cost_usd=round(total_in, 6) if total_in > 0 else (0.0 if basis == CostBasis.LOCAL_COMPUTE else None),
        output_cost_usd=round(total_out, 6) if total_out > 0 else (0.0 if basis == CostBasis.LOCAL_COMPUTE else None),
        provenance={"role_breakdowns": role_breakdowns, "has_unknown": has_unknown},
    )


def audit_ledger_costs(conn: sqlite3.Connection, runs_dir: Path | None = None) -> dict[str, Any]:
    """Audit cost accounting across all tasks in the ledger, reconciling token consumption."""
    cols = [row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    has_critic_notes = "critic_notes" in cols
    query = "SELECT task_id, mission_id, model_used, tokens_in, tokens_out, cost_usd, status"
    if has_critic_notes:
        query += ", critic_notes"
    query += " FROM tasks"
    rows = conn.execute(query).fetchall()

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

        tid = r["task_id"] if "task_id" in r.keys() else None
        notes = (r["critic_notes"] if has_critic_notes and "critic_notes" in r.keys() else "") or ""
        low_notes = notes.lower()

        # Check for structured cost artifact on disk (RR4 / C3)
        structured_cost: TaskCost | None = None
        if tid is not None:
            try:
                import runtime_context as rc
                r_dir = Path(runs_dir) if runs_dir is not None else rc.RUNS
                primary = r_dir / f"task{tid}_cost.json"
                if primary.is_file():
                    c_data = json.loads(primary.read_text(encoding="utf-8"))
                    structured_cost = TaskCost.from_dict(c_data)
                else:
                    cand_files = sorted(r_dir.glob(f"task{tid}_a*_cost.json"))
                    if cand_files:
                        att_costs = []
                        for cand in cand_files:
                            try:
                                c_data = json.loads(cand.read_text(encoding="utf-8"))
                                att_costs.append(TaskCost.from_dict(c_data))
                            except Exception:
                                pass
                        if att_costs:
                            structured_cost = combine_task_costs(att_costs)
            except Exception:
                structured_cost = None

        if structured_cost is not None:
            cost = structured_cost
        elif raw_cost is not None and float(raw_cost) > 0:
            # Respect recorded cost_usd without re-multiplying multi-role tokens by single model_used (RR4)
            if "[cost_basis: measured_invoice]" in low_notes:
                cost = TaskCost(
                    cost_usd=float(raw_cost),
                    basis=CostBasis.MEASURED_INVOICE,
                    provenance={"model": r["model_used"], "source": "persisted_invoice"},
                )
            elif "[cost_basis: estimated_token_rate]" in low_notes or lookup_rate(r["model_used"]) is not None:
                cost = TaskCost(
                    cost_usd=float(raw_cost),
                    basis=CostBasis.ESTIMATED_TOKEN_RATE,
                    provenance={"model": r["model_used"], "source": "persisted_estimated_rate"},
                )
            else:
                cost = calculate_task_cost(r["model_used"], tin, tout, raw_cost_usd=raw_cost, is_invoice=False)
        elif raw_cost is not None and float(raw_cost) == 0.0 and (tin == 0 and tout == 0):
            cost = calculate_task_cost(r["model_used"], tin, tout, raw_cost_usd=0.0)
        else:
            # Reconcile historical tasks where cost was uncalculated or masked as 0.0
            cost = calculate_task_cost(r["model_used"], tin, tout, raw_cost_usd=raw_cost, is_invoice=False)

        if cost.basis == CostBasis.MEASURED_INVOICE:
            measured_invoice_tasks += 1
            reconciled_measured_usd += (cost.cost_usd or 0.0)
        elif cost.basis == CostBasis.ESTIMATED_TOKEN_RATE:
            estimated_rate_tasks += 1
            reconciled_estimated_usd += (cost.cost_usd or 0.0)
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
            "measured_invoice_usd": round(reconciled_measured_usd, 6),
            "estimated_rate_usd": round(reconciled_estimated_usd, 6),
            "total_accounted_usd": round(reconciled_measured_usd + reconciled_estimated_usd, 6),
        },
    }


def get_operator_review_payload(notes: str | None) -> dict[str, Any] | None:
    """Extract and cryptographically verify operator review token from notes."""
    if not notes:
        return None
    token = None
    if "[OPERATOR_REVIEW_TOKEN:" in notes:
        try:
            part = notes.split("[OPERATOR_REVIEW_TOKEN:", 1)[1]
            token = part.split("]", 1)[0].strip()
        except Exception:
            token = None
    elif "." in notes and len(notes) > 50 and not notes.strip().startswith("{") and "\n" not in notes:
        token = notes.strip()

    if not token:
        return None

    try:
        from operator_auth import verify_marker
        payload = verify_marker(token)
        if payload and isinstance(payload, dict) and payload.get("event") == "operator_review":
            if "task_id" in payload and "artifact_sha256" in payload and "verdict" in payload:
                return payload
    except Exception:
        pass
    return None


def resolve_task_artifact_sha256(r: dict | sqlite3.Row, root: Path | None = None) -> str | None:
    """Resolve SHA-256 digest of the primary deliverable artifact on disk (C4)."""
    import hashlib
    raw_artifacts = r["artifacts"] if "artifacts" in r.keys() else None
    if not raw_artifacts:
        return None
    try:
        if isinstance(raw_artifacts, str):
            art_list = json.loads(raw_artifacts)
        elif isinstance(raw_artifacts, list):
            art_list = raw_artifacts
        else:
            return None
    except Exception:
        return None

    if not art_list:
        return None

    import runtime_context as rc
    base_root = Path(root) if root is not None else rc.ROOT
    art_path = Path(art_list[0])
    if not art_path.is_absolute():
        art_path = base_root / art_path

    if not art_path.is_file():
        return None

    try:
        return hashlib.sha256(art_path.read_bytes()).hexdigest()
    except Exception:
        return None


def is_genuine_operator_review(
    notes: str | None,
    task_id: int | None = None,
    artifact_sha256: str | None = None,
    expected_verdict: str | None = None,
    allow_legacy_text: bool = False,
    require_artifact_binding: bool = False,
) -> bool:
    """Verify that critic_notes contains affirmative proof of human operator verification (R7 / RR5 / C4).

    Cryptographic operator review tokens ([OPERATOR_REVIEW_TOKEN: <token>])
    are verified with Ed25519 signatures and bound to task_id, artifact_sha256,
    and verdict. Both pass and fail verdicts are recognized as authentic operator review events.
    Unsigned legacy text notes without a valid cryptographic token return False
    unless allow_legacy_text=True is explicitly passed.
    """
    payload = get_operator_review_payload(notes)
    if payload:
        if task_id is not None:
            try:
                if int(payload.get("task_id")) != int(task_id):
                    return False
            except (ValueError, TypeError):
                return False

        p_sha = str(payload.get("artifact_sha256", "")).strip()
        if artifact_sha256 is not None:
            if p_sha != str(artifact_sha256).strip():
                return False
        elif require_artifact_binding:
            # Missing or unverified artifact digest fails closed
            return False

        if expected_verdict is not None:
            p_v = str(payload.get("verdict", "")).strip().lower()
            if p_v != str(expected_verdict).strip().lower():
                return False

        return True

    if not allow_legacy_text:
        return False

    low = (notes or "").lower()
    negative_markers = (
        ": false", "false", "not reviewed", "no human", "not operator",
        "no operator", "without human", "ai-performed", "not performed",
        "not verified", "not inspected", "has not", "did not", "unreviewed",
        "unverified", "by claude", "automated", "never inspected", "neither",
    )
    if any(marker in low for marker in negative_markers):
        return False

    operator_markers = (
        "operator-verified: true", "operator-verified: pass",
        "operator-verified: checked", "operator-verified: verified",
        "operator-verified: inspected", "verification performed by the operator with their own eyes",
        "transcribed at the operator's explicit direction",
        "human operator verified and signed",
        "operator-verified verified",
        "operator-verified broken",
        "operator-verified",
    )
    return any(marker in low for marker in operator_markers)


def audit_human_verdicts(conn: sqlite3.Connection, allow_legacy_text: bool = False, root: Path | None = None) -> dict[str, Any]:
    """Audit human_verdict provenance, strictly separating independent operator reviews from AI checks (R7 / RR5 / C4)."""
    import ledger

    cols = [row[1] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()]
    select_cols = ["task_id", "mission_id", "critic_verdict", "human_verdict", "critic_notes"]
    if "artifacts" in cols:
        select_cols.append("artifacts")
    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM tasks "
        "WHERE human_verdict IS NOT NULL AND human_verdict != ''"
    ).fetchall()

    total_verdicts = len(rows)
    ai_checks = 0
    operator_verdicts = 0
    unknown_verdicts = 0
    operator_pass = 0
    operator_fail = 0
    ai_pass = 0
    ai_fail = 0
    unknown_pass = 0
    unknown_fail = 0

    for r in rows:
        tid = r["task_id"]
        v = str(r["human_verdict"]).lower().strip()
        notes = r["critic_notes"] or ""
        is_ai = ledger.is_ai_performed(notes)

        curr_sha = resolve_task_artifact_sha256(r, root=root)
        is_op = is_genuine_operator_review(
            notes,
            task_id=tid,
            artifact_sha256=curr_sha,
            expected_verdict=v,
            allow_legacy_text=allow_legacy_text,
            require_artifact_binding=True,
        )

        if is_ai:
            ai_checks += 1
            if v == "pass":
                ai_pass += 1
            elif v == "fail":
                ai_fail += 1
        elif is_op:
            operator_verdicts += 1
            if v == "pass":
                operator_pass += 1
            elif v == "fail":
                operator_fail += 1
        else:
            unknown_verdicts += 1
            if v == "pass":
                unknown_pass += 1
            elif v == "fail":
                unknown_fail += 1

    op_acc = (operator_pass / operator_verdicts) if operator_verdicts > 0 else None
    ai_acc = (ai_pass / ai_checks) if ai_checks > 0 else None
    unk_acc = (unknown_pass / unknown_verdicts) if unknown_verdicts > 0 else None

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
        "unknown_provenance": {
            "count": unknown_verdicts,
            "pass": unknown_pass,
            "fail": unknown_fail,
            "accuracy": round(unk_acc, 3) if unk_acc is not None else None,
            "provenance": "unknown_unauthenticated",
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

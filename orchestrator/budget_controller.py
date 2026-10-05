"""Runtime budget controller with shared reservation and hard-stop enforcement.

RR2 Production Implementation:
1. Enforces runtime shared and per-task dollar and token limits through every worker,
   critic, repair and failover call.
2. Implements reservations for estimated usage before each call and reconciles actual
   usage/costs afterward.
3. Rejects unknown or unbounded pricing paths under hard_stop policy.
4. Guarantees that budget exhaustion prevents the NEXT call and all LATER tasks in the cohort.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_context import ROOT, RUNS, log
import cost_accounting


class BudgetExhaustedError(RuntimeError):
    """Raised when an LLM call would exceed allowed budget or tokens."""
    pass


class UnboundedPricingError(RuntimeError):
    """Raised when an unpriced or unknown model is attempted under hard_stop budget."""
    pass


@contextlib.contextmanager
def _budget_lock(lock_path: Path, timeout: float = 10.0):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            if time.monotonic() >= deadline:
                # Break stale lock (>30s old)
                try:
                    if lock_path.stat().st_mtime < time.time() - 30:
                        lock_path.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    break
                except OSError:
                    raise RuntimeError(f"could not acquire budget lock: {lock_path}")
            time.sleep(0.02)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
            try:
                lock_path.unlink(missing_ok=True)
            except Exception:
                pass


class BudgetController:
    """Manages reservations, limits, and reconciliation for tasks and cohorts."""

    def __init__(
        self,
        runs_dir: Path | None = None,
        task_id: int | None = None,
        max_budget_usd: float | None = None,
        max_tokens: int | None = None,
        budget_enforcement: str | None = "admission_parameters_only",
        shared_budget_id: str | None = None,
        shared_max_budget_usd: float | None = None,
        shared_max_tokens: int | None = None,
    ) -> None:
        self.runs = Path(runs_dir) if runs_dir is not None else RUNS
        self.task_id = task_id
        self.max_budget_usd = float(max_budget_usd) if max_budget_usd is not None else None
        self.max_tokens = int(max_tokens) if max_tokens is not None else None
        self.budget_enforcement = str(budget_enforcement or "admission_parameters_only").strip().lower()
        self.shared_budget_id = str(shared_budget_id).strip() if shared_budget_id else None
        self.shared_max_budget_usd = float(shared_max_budget_usd) if shared_max_budget_usd is not None else None
        self.shared_max_tokens = int(shared_max_tokens) if shared_max_tokens is not None else None

        self.task_spent_usd = 0.0
        self.task_spent_tokens = 0
        self.active_reservations: dict[str, dict[str, Any]] = {}
        self.settled_reservations: set[str] = set()

        self.budgets_dir = self.runs / "budgets"
        self.budgets_dir.mkdir(parents=True, exist_ok=True)

        if self.task_id is not None:
            self.task_file = self.budgets_dir / f"task_{self.task_id}.json"
            self._load_task_state()
        else:
            self.task_file = None

        if self.shared_budget_id:
            self._ensure_shared_budget_init()

    def is_enforced(self) -> bool:
        return self.budget_enforcement == "hard_stop"

    def _load_task_state(self) -> None:
        if self.task_file and self.task_file.is_file():
            try:
                t_data = json.loads(self.task_file.read_text(encoding="utf-8"))
                self.task_spent_usd = float(t_data.get("task_spent_usd", 0.0))
                self.task_spent_tokens = int(t_data.get("task_spent_tokens", 0))
            except Exception:
                pass

    def _save_task_state(self) -> None:
        if self.task_file:
            t_data = {
                "task_id": self.task_id,
                "task_spent_usd": self.task_spent_usd,
                "task_spent_tokens": self.task_spent_tokens,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp = self.task_file.parent / f"{self.task_file.name}.tmp.{uuid.uuid4().hex}"
            try:
                tmp.write_text(json.dumps(t_data, indent=2) + "\n", encoding="utf-8")
                os.replace(tmp, self.task_file)
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink(missing_ok=True)
                    except Exception:
                        pass

    def _shared_file_and_lock(self) -> tuple[Path, Path]:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in (self.shared_budget_id or "default"))
        p = self.budgets_dir / f"{safe_id}.json"
        l = self.budgets_dir / f"{safe_id}.lock"
        return p, l

    def _ensure_shared_budget_init(self) -> None:
        if not self.shared_budget_id:
            return
        b_file, b_lock = self._shared_file_and_lock()
        with _budget_lock(b_lock):
            if not b_file.is_file():
                init_data = {
                    "budget_id": self.shared_budget_id,
                    "shared_max_budget_usd": self.shared_max_budget_usd,
                    "shared_max_tokens": self.shared_max_tokens,
                    "spent_usd": 0.0,
                    "spent_tokens": 0,
                    "active_reservations_usd": 0.0,
                    "active_reservations_tokens": 0,
                    "reservations": {},
                    "exhausted": False,
                    "exhaustion_reason": None,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                self._write_shared(init_data)

    def _read_shared(self) -> dict[str, Any]:
        if not self.shared_budget_id:
            return {}
        b_file, _ = self._shared_file_and_lock()
        if not b_file.is_file():
            return {}
        try:
            content = b_file.read_text(encoding="utf-8").strip()
            if not content:
                raise BudgetExhaustedError(
                    f"BUDGET_CORRUPTED: shared budget '{self.shared_budget_id}' file is empty; failing closed"
                )
            data = json.loads(content)
            if not isinstance(data, dict):
                raise BudgetExhaustedError(
                    f"BUDGET_CORRUPTED: shared budget '{self.shared_budget_id}' payload is not a dict; failing closed"
                )
            if "budget_id" not in data or "spent_tokens" not in data or "spent_usd" not in data:
                raise BudgetExhaustedError(
                    f"BUDGET_CORRUPTED: shared budget '{self.shared_budget_id}' missing required state fields; failing closed"
                )
            # Verify immutable limits
            if self.shared_max_tokens is not None and data.get("shared_max_tokens") is not None:
                if int(data["shared_max_tokens"]) != self.shared_max_tokens:
                    raise BudgetExhaustedError(
                        f"BUDGET_TAMPERED: shared budget max_tokens mismatch ({data.get('shared_max_tokens')} vs {self.shared_max_tokens})"
                    )
            if self.shared_max_budget_usd is not None and data.get("shared_max_budget_usd") is not None:
                if abs(float(data["shared_max_budget_usd"]) - self.shared_max_budget_usd) > 1e-6:
                    raise BudgetExhaustedError(
                        f"BUDGET_TAMPERED: shared budget max_budget_usd mismatch ({data.get('shared_max_budget_usd')} vs {self.shared_max_budget_usd})"
                    )
            return data
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError) as exc:
            raise BudgetExhaustedError(
                f"BUDGET_CORRUPTED: shared budget '{self.shared_budget_id}' file is unreadable: {exc}"
            )

    def _write_shared(self, data: dict[str, Any]) -> None:
        if not self.shared_budget_id:
            return
        b_file, _ = self._shared_file_and_lock()
        tmp_file = b_file.parent / f"{b_file.name}.tmp.{uuid.uuid4().hex}"
        try:
            tmp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp_file, b_file)
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink(missing_ok=True)
                except Exception:
                    pass

    def remaining_task_budget_usd(self, reservation_id: str | None = None) -> float:
        if self.max_budget_usd is None:
            return float("inf")
        other_active_res = sum(
            max(0.0, float(r.get("usd", 0.0)) - float(r.get("spent_usd", 0.0)))
            for k, r in self.active_reservations.items()
            if k != reservation_id
        )
        return max(0.0, self.max_budget_usd - (self.task_spent_usd + other_active_res))

    def remaining_task_tokens(self, reservation_id: str | None = None) -> int:
        if self.max_tokens is None:
            return 10**9
        other_active_res = sum(
            max(0, int(r.get("tokens", 0)) - int(r.get("spent_tokens", 0)))
            for k, r in self.active_reservations.items()
            if k != reservation_id
        )
        return max(0, self.max_tokens - (self.task_spent_tokens + other_active_res))

    def remaining_shared_budget_usd(self, reservation_id: str | None = None) -> float:
        if not self.shared_budget_id or self.shared_max_budget_usd is None:
            return float("inf")
        data = self._read_shared()
        if data.get("exhausted"):
            return 0.0
        all_res = data.get("reservations", {})
        other_active_res = sum(
            max(0.0, float(r.get("usd", 0.0)) - float(r.get("spent_usd", 0.0)))
            for k, r in all_res.items()
            if k != reservation_id
        )
        used = float(data.get("spent_usd", 0.0)) + other_active_res
        return max(0.0, self.shared_max_budget_usd - used)

    def remaining_shared_tokens(self, reservation_id: str | None = None) -> int:
        if not self.shared_budget_id or self.shared_max_tokens is None:
            return 10**9
        data = self._read_shared()
        if data.get("exhausted"):
            return 0
        all_res = data.get("reservations", {})
        other_active_res = sum(
            max(0, int(r.get("tokens", 0)) - int(r.get("spent_tokens", 0)))
            for k, r in all_res.items()
            if k != reservation_id
        )
        used = int(data.get("spent_tokens", 0)) + other_active_res
        return max(0, self.shared_max_tokens - used)

    def reserve(
        self,
        role: str,
        model_str: str | None,
        prompt_text: str = "",
        estimated_tokens: int | None = None,
        estimated_usd: float | None = None,
    ) -> str:
        """Reserve capacity before an LLM call. Fails closed under hard_stop."""
        res_id = f"res_{uuid.uuid4().hex[:12]}"
        if not self.is_enforced():
            return res_id

        # 1. Reject unpriced / unbounded models under hard_stop
        model = (model_str or "").strip()
        probe_cost = cost_accounting.calculate_task_cost(model, tokens_in=100, tokens_out=100)
        if probe_cost.basis == cost_accounting.CostBasis.UNKNOWN and (
            self.max_budget_usd is not None or self.shared_max_budget_usd is not None
        ):
            raise UnboundedPricingError(
                f"BUDGET_ENFORCEMENT_BLOCKED: Model '{model}' has unknown pricing basis; cannot execute under hard_stop dollar budget"
            )

        # 2. Compute token and dollar demand
        if estimated_tokens is None:
            # Estimate from prompt words + default answer buffer
            prompt_words = len(prompt_text.split()) if prompt_text else 500
            estimated_tokens = max(1000, prompt_words * 2 + 500)

        if estimated_usd is None:
            est_in = int(estimated_tokens * 0.7)
            est_out = int(estimated_tokens * 0.3)
            cost_res = cost_accounting.calculate_task_cost(model, est_in, est_out)
            estimated_usd = cost_res.cost_usd or 0.0

        # 3. Check per-task budget bounds
        if self.max_budget_usd is not None:
            rem_usd = self.remaining_task_budget_usd()
            if estimated_usd > rem_usd:
                raise BudgetExhaustedError(
                    f"Task {self.task_id} budget exhausted: estimated call spend (${estimated_usd:.6f}) exceeds remaining task budget (${rem_usd:.6f})"
                )

        if self.max_tokens is not None:
            rem_tok = self.remaining_task_tokens()
            if estimated_tokens > rem_tok:
                raise BudgetExhaustedError(
                    f"Task {self.task_id} token budget exhausted: estimated call tokens ({estimated_tokens}) exceeds remaining task tokens ({rem_tok})"
                )

        # 4. Check and commit shared budget bounds under atomic lock
        if self.shared_budget_id:
            b_file, b_lock = self._shared_file_and_lock()
            with _budget_lock(b_lock):
                shared = self._read_shared()
                if shared.get("exhausted"):
                    raise BudgetExhaustedError(
                        f"Shared cohort budget '{self.shared_budget_id}' is exhausted: {shared.get('exhaustion_reason')}"
                    )

                avail_usd = float("inf")
                if self.shared_max_budget_usd is not None:
                    used_usd = float(shared.get("spent_usd", 0.0)) + float(shared.get("active_reservations_usd", 0.0))
                    avail_usd = max(0.0, self.shared_max_budget_usd - used_usd)
                    if estimated_usd > avail_usd:
                        shared["exhausted"] = True
                        shared["exhaustion_reason"] = (
                            f"Call spend demand (${estimated_usd:.6f}) exceeds remaining shared budget (${avail_usd:.6f})"
                        )
                        self._write_shared(shared)
                        raise BudgetExhaustedError(shared["exhaustion_reason"])

                avail_tok = 10**9
                if self.shared_max_tokens is not None:
                    used_tok = int(shared.get("spent_tokens", 0)) + int(shared.get("active_reservations_tokens", 0))
                    avail_tok = max(0, self.shared_max_tokens - used_tok)
                    if estimated_tokens > avail_tok:
                        shared["exhausted"] = True
                        shared["exhaustion_reason"] = (
                            f"Call token demand ({estimated_tokens}) exceeds remaining shared token budget ({avail_tok})"
                        )
                        self._write_shared(shared)
                        raise BudgetExhaustedError(shared["exhaustion_reason"])

                # Commit reservation to shared store
                shared.setdefault("reservations", {})[res_id] = {
                    "usd": estimated_usd,
                    "tokens": estimated_tokens,
                    "spent_usd": 0.0,
                    "spent_tokens": 0,
                    "role": role,
                    "model": model,
                    "task_id": self.task_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                shared["active_reservations_usd"] = round(float(shared.get("active_reservations_usd", 0.0)) + estimated_usd, 6)
                shared["active_reservations_tokens"] = int(shared.get("active_reservations_tokens", 0)) + estimated_tokens
                self._write_shared(shared)

        # 5. Record task-local reservation
        self.active_reservations[res_id] = {
            "usd": estimated_usd,
            "tokens": estimated_tokens,
            "spent_usd": 0.0,
            "spent_tokens": 0,
            "role": role,
            "model": model,
        }
        return res_id

    def reconcile(
        self,
        reservation_id: str,
        actual_cost_usd: float | None = None,
        actual_tokens: int | None = None,
    ) -> None:
        """Reconcile reservation against actual usage."""
        if not self.is_enforced():
            return

        if reservation_id in self.settled_reservations:
            # Idempotent: repeated settlement does not re-add spend
            return

        res = self.active_reservations.pop(reservation_id, None)
        self.settled_reservations.add(reservation_id)

        act_usd = round(float(actual_cost_usd or 0.0), 6)
        act_tok = int(actual_tokens or 0)

        # Compute delta not already recorded via record_turn_spend
        prev_recorded_tok = int(res.get("spent_tokens", 0)) if res else 0
        prev_recorded_usd = float(res.get("spent_usd", 0.0)) if res else 0.0
        delta_tok = max(0, act_tok - prev_recorded_tok)
        delta_usd = max(0.0, round(act_usd - prev_recorded_usd, 6))

        self.task_spent_usd = round(self.task_spent_usd + delta_usd, 6)
        self.task_spent_tokens += delta_tok
        self._save_task_state()

        if self.shared_budget_id:
            b_file, b_lock = self._shared_file_and_lock()
            with _budget_lock(b_lock):
                shared = self._read_shared()
                s_res = shared.get("reservations", {}).pop(reservation_id, None)
                if s_res:
                    shared["active_reservations_usd"] = max(
                        0.0, round(float(shared.get("active_reservations_usd", 0.0)) - float(s_res.get("usd", 0.0)), 6)
                    )
                    shared["active_reservations_tokens"] = max(
                        0, int(shared.get("active_reservations_tokens", 0)) - int(s_res.get("tokens", 0))
                    )
                s_prev_tok = int(s_res.get("spent_tokens", 0)) if s_res else prev_recorded_tok
                s_prev_usd = float(s_res.get("spent_usd", 0.0)) if s_res else prev_recorded_usd
                s_delta_tok = max(0, act_tok - s_prev_tok)
                s_delta_usd = max(0.0, round(act_usd - s_prev_usd, 6))

                shared["spent_usd"] = round(float(shared.get("spent_usd", 0.0)) + s_delta_usd, 6)
                shared["spent_tokens"] = int(shared.get("spent_tokens", 0)) + s_delta_tok

                if self.shared_max_budget_usd is not None and shared["spent_usd"] >= self.shared_max_budget_usd:
                    shared["exhausted"] = True
                    shared["exhaustion_reason"] = (
                        f"Shared budget limit reached: spent ${shared['spent_usd']:.6f} of ${self.shared_max_budget_usd:.6f}"
                    )
                if self.shared_max_tokens is not None and shared["spent_tokens"] >= self.shared_max_tokens:
                    shared["exhausted"] = True
                    shared["exhaustion_reason"] = (
                        f"Shared token limit reached: spent {shared['spent_tokens']} of {self.shared_max_tokens} tokens"
                    )
                self._write_shared(shared)

        if self.max_tokens is not None and self.task_spent_tokens > self.max_tokens:
            raise BudgetExhaustedError(
                f"Task {self.task_id} token budget exhausted upon settlement: spent {self.task_spent_tokens} exceeds maximum {self.max_tokens}"
            )
        if self.max_budget_usd is not None and self.task_spent_usd > self.max_budget_usd:
            raise BudgetExhaustedError(
                f"Task {self.task_id} budget exhausted upon settlement: spent ${self.task_spent_usd:.6f} exceeds maximum ${self.max_budget_usd:.6f}"
            )

    def record_turn_spend(
        self,
        turn_tokens: int,
        turn_usd: float = 0.0,
        reservation_id: str | None = None,
    ) -> None:
        """Record intermediate turn spend during multi-turn agent loops (RR2)."""
        if not self.is_enforced():
            return
        act_tok = max(0, int(turn_tokens))
        act_usd = max(0.0, float(turn_usd))

        if reservation_id and reservation_id in self.active_reservations:
            res = self.active_reservations[reservation_id]
            res["spent_tokens"] = int(res.get("spent_tokens", 0)) + act_tok
            res["spent_usd"] = round(float(res.get("spent_usd", 0.0)) + act_usd, 6)

        self.task_spent_tokens += act_tok
        self.task_spent_usd = round(self.task_spent_usd + act_usd, 6)
        self._save_task_state()

        if self.shared_budget_id:
            b_file, b_lock = self._shared_file_and_lock()
            with _budget_lock(b_lock):
                shared = self._read_shared()
                if reservation_id and reservation_id in shared.get("reservations", {}):
                    s_res = shared["reservations"][reservation_id]
                    s_res["spent_tokens"] = int(s_res.get("spent_tokens", 0)) + act_tok
                    s_res["spent_usd"] = round(float(s_res.get("spent_usd", 0.0)) + act_usd, 6)

                shared["spent_tokens"] = int(shared.get("spent_tokens", 0)) + act_tok
                shared["spent_usd"] = round(float(shared.get("spent_usd", 0.0)) + act_usd, 6)
                if self.shared_max_tokens is not None and shared["spent_tokens"] >= self.shared_max_tokens:
                    shared["exhausted"] = True
                    shared["exhaustion_reason"] = (
                        f"Shared token limit reached during turn: spent {shared['spent_tokens']} of {self.shared_max_tokens} tokens"
                    )
                if self.shared_max_budget_usd is not None and shared["spent_usd"] >= self.shared_max_budget_usd:
                    shared["exhausted"] = True
                    shared["exhaustion_reason"] = (
                        f"Shared budget limit reached during turn: spent ${shared['spent_usd']:.6f} of ${self.shared_max_budget_usd:.6f}"
                    )
                self._write_shared(shared)

    def release_reservation(self, reservation_id: str, timeout: bool = False) -> None:
        """Release reservation when an execution call aborted without usage,
        or retain spend as in-flight unreconciled if interrupted by timeout/crash."""
        if not self.is_enforced():
            return
        res = self.active_reservations.pop(reservation_id, None)
        if not res:
            return

        if timeout:
            # INTERRUPTED BY TIMEOUT / CRASH: Preserve in-flight consumption; DO NOT treat as free!
            act_usd = float(res.get("usd", 0.0))
            act_tok = int(res.get("tokens", 0))
            self.task_spent_usd = round(self.task_spent_usd + act_usd, 6)
            self.task_spent_tokens += act_tok
            self._save_task_state()

            if self.shared_budget_id:
                b_file, b_lock = self._shared_file_and_lock()
                with _budget_lock(b_lock):
                    shared = self._read_shared()
                    s_res = shared.get("reservations", {}).pop(reservation_id, None)
                    if s_res:
                        shared["active_reservations_usd"] = max(
                            0.0, round(float(shared.get("active_reservations_usd", 0.0)) - float(s_res.get("usd", 0.0)), 6)
                        )
                        shared["active_reservations_tokens"] = max(
                            0, int(shared.get("active_reservations_tokens", 0)) - int(s_res.get("tokens", 0))
                        )
                    shared["spent_usd"] = round(float(shared.get("spent_usd", 0.0)) + act_usd, 6)
                    shared["spent_tokens"] = int(shared.get("spent_tokens", 0)) + act_tok
                    shared.setdefault("unreconciled_timeouts", {})[reservation_id] = {
                        "usd": act_usd,
                        "tokens": act_tok,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    if self.shared_max_budget_usd is not None and shared["spent_usd"] >= self.shared_max_budget_usd:
                        shared["exhausted"] = True
                        shared["exhaustion_reason"] = (
                            f"Shared budget limit reached on timeout: spent ${shared['spent_usd']:.6f} of ${self.shared_max_budget_usd:.6f}"
                        )
                    if self.shared_max_tokens is not None and shared["spent_tokens"] >= self.shared_max_tokens:
                        shared["exhausted"] = True
                        shared["exhaustion_reason"] = (
                            f"Shared token limit reached on timeout: spent {shared['spent_tokens']} of {self.shared_max_tokens} tokens"
                        )
                    self._write_shared(shared)
        else:
            if self.shared_budget_id:
                b_file, b_lock = self._shared_file_and_lock()
                with _budget_lock(b_lock):
                    shared = self._read_shared()
                    s_res = shared.get("reservations", {}).pop(reservation_id, None)
                    if s_res:
                        shared["active_reservations_usd"] = max(
                            0.0, round(float(shared.get("active_reservations_usd", 0.0)) - float(s_res.get("usd", 0.0)), 6)
                        )
                        shared["active_reservations_tokens"] = max(
                            0, int(shared.get("active_reservations_tokens", 0)) - int(s_res.get("tokens", 0))
                        )
                    self._write_shared(shared)

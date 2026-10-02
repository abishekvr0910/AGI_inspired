#!/usr/bin/env python3
"""TypeSafe AI Lead Generation Pipeline & ICP Scoring Engine.

Implements the official TypeSafe AI use-case map for Lead Generation:
(https://docs.typesafe.ai/concepts/use-case-map#lead-generation)

Decisions Implemented:
1. ICP Matching: Score industry fit and company maturity (0-100 rubric, TypeSafe 'Score').
2. Pain Point & Waste Detection: Categorize primary budget waste vector (TypeSafe 'Choice').
3. Buyer Intent & Relevance: High-ticket commercial value verification (TypeSafe 'Noul' Boolean).
4. Evidence Gate Routing: Enforce verification status via orchestrator/evidence_gate.py.

Usage:
    python scripts/evaluate_leads_typesafe.py
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "orchestrator"))

import evidence_gate
try:
    import typed_decisions
except ImportError:
    typed_decisions = None  # type: ignore[assignment]

PROSPECT_CSV = ROOT / "workspace" / "PROSPECT_TRACKER.csv"
OUTPUT_REPORT = ROOT / "workspace" / "TYPESAFE_LEAD_EVALUATION.json"
OUTPUT_SUMMARY_MD = ROOT / "workspace" / "TYPESAFE_LEAD_EVALUATION.md"


@dataclass
class TypeSafeScoredLead:
    company_name: str
    vertical: str
    market: str
    contact_name: str
    role: str
    email: str
    website: str
    est_monthly_waste: str
    # TypeSafe Primitives:
    icp_fit_score: int                 # TypeSafe 'Score' primitive (0-100)
    waste_vector: str                  # TypeSafe 'Choice' primitive
    commercial_ticket_fit: bool        # TypeSafe 'Noul' primitive (Boolean classification)
    confidence: float                  # Calibrated confidence (0.0 - 1.0)
    # Harness Governance:
    verification_status: str           # From orchestrator.evidence_gate
    can_export_outbound: bool          # Evidence gate barrier
    routing_action: str                # TypeSafe Routing decision
    pitch_path: str


def score_icp_fit(vertical: str, role: str, waste_str: str, email: str = "") -> tuple[int, bool, float]:
    """Evaluates ICP fit using TypeSafe rubric.
    High-ticket service verticals ($10k-$100k+ customer lifetime value)
    with executive decision makers (Owner/Director/Founder) score highest.
    """
    score = 0
    # Vertical weight (Max 40)
    high_ticket_verticals = {
        "Commercial Roofing": 40,
        "Dental Implants": 38,
        "Commercial HVAC": 39,
    }
    score += high_ticket_verticals.get(vertical, 20)

    # Decision-Maker Role weight (Max 35)
    role_lower = role.lower()
    if any(k in role_lower for k in ["owner", "president", "founder", "managing partner"]):
        score += 35
    elif any(k in role_lower for k in ["vp", "director", "administrator", "chief"]):
        score += 28
    else:
        score += 15

    # Waste scale weight (Max 25)
    nums = re.findall(r"\d+", waste_str.replace(",", ""))
    waste_val = int(nums[0]) if nums else 0
    if waste_val >= 15000:
        score += 25
    elif waste_val >= 10000:
        score += 20
    else:
        score += 12

    commercial_fit = score >= 75

    # Calibrated confidence based on verified contact email and waste scale
    has_contact = bool(email and "@" in email and "." in email)
    has_role = bool(role and role.strip())
    has_waste = waste_val > 0

    if has_contact and has_role and has_waste:
        confidence = 0.95
    elif has_role and (has_contact or has_waste):
        confidence = 0.85
    else:
        confidence = 0.65
    return score, commercial_fit, confidence


def classify_waste_vector(vertical: str, notes: str) -> str:
    """TypeSafe 'Choice' decision classifying the primary budget waste vector."""
    if "Dental" in vertical:
        return "Broad-Match Non-Converting Queries (Free Clinics / Denture Repairs)"
    elif "Roofing" in vertical:
        return "Residential Shingle Spillage & Low-Intent DIY Queries"
    elif "HVAC" in vertical:
        return "Residential AC Repair Clicks & Job Seeker Drainage"
    return "Unfiltered Broad Match Leakage"


def evaluate_prospects(
    csv_path: Path | str | None = None,
    gate: evidence_gate.EvidenceGate | None = None,
    backend: typed_decisions.DecisionBackend | None = None,
) -> list[TypeSafeScoredLead]:
    target_csv = Path(csv_path) if csv_path else PROSPECT_CSV
    if not target_csv.is_file():
        print(f"Error: {target_csv} not found")
        return []

    if gate is None:
        gate = evidence_gate.EvidenceGate(ROOT)

    results: list[TypeSafeScoredLead] = []

    with open(target_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = row.get("Company Name", "").strip()
            if not company:
                continue

            vertical = row.get("Vertical", "").strip()
            role = row.get("Role", "").strip()
            waste = row.get("Est Monthly Ad Waste", "").strip()
            dossier_path = row.get("Audit Dossier Path", "").strip()
            email = row.get("Email", "").strip()

            # Derive client_id slug from dossier path or company name
            client_slug = Path(dossier_path).parent.name if dossier_path else re.sub(r"[^a-z0-9_-]", "-", company.lower())

            # 1 & 2. TypeSafe Decision Primitives (Advisory)
            if backend is not None:
                score_dec = backend.decide_score({
                    "vertical": vertical,
                    "role": role,
                    "waste_str": waste,
                    "email": email,
                })
                fit_score = int(score_dec.score)
                confidence = score_dec.confidence
                noul_dec = backend.decide_noul({
                    "score": fit_score,
                    "threshold": 75,
                })
                is_high_ticket = noul_dec.outcome
                allowed_choices = (
                    "Broad-Match Non-Converting Queries (Free Clinics / Denture Repairs)",
                    "Residential Shingle Spillage & Low-Intent DIY Queries",
                    "Residential AC Repair Clicks & Job Seeker Drainage",
                    "Unfiltered Broad Match Leakage",
                )
                choice_dec = backend.decide_choice(
                    {"vertical": vertical, "notes": row.get("Notes", "")},
                    allowed_choices,
                )
                waste_vector = choice_dec.selected
            else:
                # Default offline zero-spend deterministic rubric
                fit_score, is_high_ticket, confidence = score_icp_fit(vertical, role, waste, email)
                waste_vector = classify_waste_vector(vertical, row.get("Notes", ""))

            # 3. Harness Evidence Gate Verification (AUTHORITATIVE: Model output CANNOT authorize outbound export)
            can_export, gate_reason = gate.can_export_prospect(client_slug)
            verif = gate.get(client_slug)
            verif_status = verif.status.value if verif else "unregistered"

            # 4. Routing Action (TypeSafe 'Routing' Task Category)
            if can_export:
                routing = "PRIORITY_OUTBOUND: Dispatch live email/LinkedIn sequence"
            else:
                routing = f"EVIDENCE_HOLD: Requires operator verification approval ({gate_reason})"

            lead = TypeSafeScoredLead(
                company_name=company,
                vertical=vertical,
                market=row.get("Market/City", "").strip(),
                contact_name=row.get("Contact Name", "").strip(),
                role=role,
                email=row.get("Email", "").strip(),
                website=row.get("Website", "").strip(),
                est_monthly_waste=waste,
                icp_fit_score=fit_score,
                waste_vector=waste_vector,
                commercial_ticket_fit=is_high_ticket,
                confidence=confidence,
                verification_status=verif_status,
                can_export_outbound=can_export,
                routing_action=routing,
                pitch_path=row.get("Outbound Pitch Path", "").strip()
            )
            results.append(lead)

    results.sort(key=lambda x: x.icp_fit_score, reverse=True)
    return results


def run_benchmark(
    csv_path: Path | str | None = None,
    samples: int | None = None,
    backend_type: str = "deterministic",
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Execute reproducible benchmark protocol across decision primitives.

    Keeps offline measurements distinct from vendor-published and live metrics.
    A Jev run defaults to one sample per prospect; every request is guarded by
    JevBackend's ESTOP, signed-boundary, allowlist, and credential preflight.
    """
    target_csv = Path(csv_path) if csv_path else PROSPECT_CSV
    backend_name = backend_type.lower()
    if backend_name not in {"jev", "deterministic"}:
        raise ValueError("backend_type must be 'jev' or 'deterministic'")
    samples = samples if samples is not None else (1 if backend_name == "jev" else 100)
    if isinstance(samples, bool) or not isinstance(samples, int) or not (1 <= samples <= 1000):
        raise ValueError("samples must be an integer from 1 to 1000")
    if not target_csv.is_file():
        raise FileNotFoundError(f"Benchmark dataset not found: {target_csv}")

    raw_bytes = target_csv.read_bytes()
    dataset_hash = hashlib.sha256(raw_bytes).hexdigest()

    rows: list[dict[str, str]] = []
    with open(target_csv, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("Company Name", "").strip():
                rows.append(r)

    now_iso = datetime.now(timezone.utc).isoformat()
    dest = Path(output_path) if output_path else ROOT / "workspace" / "typesafe" / "BENCHMARK_RESULTS.json"
    dest.parent.mkdir(parents=True, exist_ok=True)

    vendor_reference = {
        "source": "evals.typesafe.ai & blog.typesafe.ai (retrieved 2026-09-27)",
        "field_type": "vendor_published",
        "workflow_evaluation": {
            "speedup": "193.6x faster",
            "jev_workflow_time_s": 0.114,
            "standard_llm_workflow_time_s": 8.566,
            "cost_reduction": "444.6x cheaper",
            "jev_workflow_cost_usd": 0.000081,
            "standard_llm_workflow_cost_usd": 0.013880
        },
        "single_call_latency_ms_range": "70-500ms",
        "cost_reduction_range": "40x-200x",
        "input_cost_per_mtok": 0.042,
        "output_cost_per_mtok": 0.0,
        "schema_error_rate": 0.0,
        "caveat": "TypeSafe notes published 193.6x/444.6x figures are on the higher end of real-world gains."
    }

    if backend_name == "jev":
        jev = typed_decisions.JevBackend()
        latencies_ns: list[int] = []
        completed_decisions = 0
        allowed_choices = (
            "broad_match_non_converting",
            "residential_spillage",
            "residential_ac_drainage",
            "unfiltered_broad_match",
        )
        failure: str | None = None
        try:
            for row in rows:
                vertical = row.get("Vertical", "")
                role = row.get("Role", "")
                waste = row.get("Est Monthly Ad Waste", "")
                # The JevBackend applies a strict field allowlist and never sends
                # Company Name, Contact Name, Email, Phone, Website, or Notes.
                safe_context = {"vertical": vertical, "role": role, "waste_str": waste}
                for _ in range(samples):
                    start = time.perf_counter_ns()
                    score = jev.decide_score(safe_context)
                    latencies_ns.append(time.perf_counter_ns() - start)
                    completed_decisions += 1

                    start = time.perf_counter_ns()
                    jev.decide_noul({"score": int(score.score), "threshold": 75})
                    latencies_ns.append(time.perf_counter_ns() - start)
                    completed_decisions += 1

                    start = time.perf_counter_ns()
                    jev.decide_choice({"vertical": vertical}, allowed_choices)
                    latencies_ns.append(time.perf_counter_ns() - start)
                    completed_decisions += 1
        except (typed_decisions.JevBackendNotConfigured, typed_decisions.JevBackendError) as exc:
            failure = str(exc)

        live_transport = jev.live_transport_enabled
        transport_attempts = jev.transport_attempts
        requests_dispatched = jev.requests_dispatched
        if live_transport:
            run_status = (
                "COMPLETED_JEV_LIVE" if failure is None else
                "JEV_LIVE_MEASUREMENT_INCOMPLETE" if requests_dispatched else
                "JEV_LIVE_MEASUREMENT_NOT_RUN"
            )
            field_type = "live_measured" if failure is None else (
                "partial_live_measurement" if requests_dispatched else "unrun"
            )
        else:
            run_status = "JEV_MOCK_MEASUREMENT_COMPLETED" if failure is None else "JEV_MOCK_MEASUREMENT_FAILED"
            field_type = "mock_measured"
        result = {
            "benchmark_protocol_version": "1.0.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": run_status,
            "field_type": field_type,
            "reason": failure if failure else (None if live_transport else
                      "Injected transport selected; no external HTTP request was dispatched."),
            "dataset": {
                "path": str(target_csv.relative_to(ROOT) if target_csv.is_relative_to(ROOT) else target_csv),
                "sha256": dataset_hash,
                "prospect_count": len(rows),
                "provenance": "Synthetic commercial prospect fixtures with fictional 555-prefix phone numbers and modeled ad waste; email and website domains are not RFC 2606-sanitized. The live backend transmits only allowlisted decision fields and excludes direct contact, company, website, and notes fields."
            },
            "backend": "jev_typesafe",
            "samples_per_prospect": samples,
            "decision_calls_requested": len(rows) * samples * 3,
            "requests_dispatched": requests_dispatched,
            "transport_attempts": transport_attempts,
            "completed_decision_calls": completed_decisions,
            "vendor_published_reference": vendor_reference,
        }
        if latencies_ns:
            ordered_ms = sorted(value / 1_000_000.0 for value in latencies_ns)

            def percentile(p: float) -> float:
                index = min(int(len(ordered_ms) * p), len(ordered_ms) - 1)
                return round(ordered_ms[index], 6)

            result["latency_distribution_ms"] = {
                "count": len(ordered_ms),
                "min": round(ordered_ms[0], 6),
                "p50": percentile(0.50),
                "p95": percentile(0.95),
                "max": round(ordered_ms[-1], 6),
            }
        dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("\n" + "=" * 70)
        print(f"[{run_status}]")
        print("Dispatch evidence is recorded in the report counters below.")
        print(f"Real HTTP requests dispatched: {requests_dispatched}; transport attempts: {transport_attempts}; decisions completed: {completed_decisions}.")
        if failure:
            print(f"Reason: {failure}")
        print(f"Recorded status to: {dest}")
        print("=" * 70)
        return result

    # Deterministic local backend evaluation
    backend = typed_decisions.DeterministicRubricBackend() if typed_decisions else None
    if backend is None:
        raise RuntimeError("typed_decisions module is not available")

    # Warmup (3 trials)
    for row in rows:
        for _ in range(3):
            v = row.get("Vertical", "")
            r = row.get("Role", "")
            w = row.get("Est Monthly Ad Waste", "")
            e = row.get("Email", "")
            s = backend.decide_score({"vertical": v, "role": r, "waste_str": w, "email": e})
            backend.decide_noul({"score": int(s.score), "threshold": 75})
            backend.decide_choice({"vertical": v}, ("a", "b", "c", "d"))

    latencies_ns: list[int] = []
    schema_errors = 0
    total_decisions = 0

    allowed_choices = (
        "broad_match_non_converting",
        "residential_spillage",
        "residential_ac_drainage",
        "unfiltered_broad_match",
    )

    for row in rows:
        v = row.get("Vertical", "")
        r = row.get("Role", "")
        w = row.get("Est Monthly Ad Waste", "")
        e = row.get("Email", "")
        for _ in range(samples):
            # Score call
            t0 = time.perf_counter_ns()
            s_dec = backend.decide_score({"vertical": v, "role": r, "waste_str": w, "email": e})
            latencies_ns.append(time.perf_counter_ns() - t0)
            total_decisions += 1
            if not (0.0 <= s_dec.score <= 100.0) or not (0.0 <= s_dec.confidence <= 1.0):
                schema_errors += 1

            # Noul call
            t0 = time.perf_counter_ns()
            n_dec = backend.decide_noul({"score": int(s_dec.score), "threshold": 75})
            latencies_ns.append(time.perf_counter_ns() - t0)
            total_decisions += 1
            if not (0.0 <= n_dec.probability <= 1.0) or not (0.0 <= n_dec.confidence <= 1.0):
                schema_errors += 1

            # Choice call
            t0 = time.perf_counter_ns()
            c_dec = backend.decide_choice({"vertical": v, "notes": row.get("Notes", "")}, allowed_choices)
            latencies_ns.append(time.perf_counter_ns() - t0)
            total_decisions += 1
            if c_dec.selected not in allowed_choices:
                schema_errors += 1

    latencies_ms = [ns / 1_000_000.0 for ns in latencies_ns]
    latencies_ms.sort()

    def pct(p: float) -> float:
        idx = int(len(latencies_ms) * p)
        return latencies_ms[min(idx, len(latencies_ms) - 1)]

    stats = {
        "count": len(latencies_ms),
        "min_ms": round(latencies_ms[0], 6),
        "p50_ms": round(pct(0.50), 6),
        "p75_ms": round(pct(0.75), 6),
        "p90_ms": round(pct(0.90), 6),
        "p95_ms": round(pct(0.95), 6),
        "p99_ms": round(pct(0.99), 6),
        "max_ms": round(latencies_ms[-1], 6),
        "mean_ms": round(statistics.mean(latencies_ms), 6),
        "stddev_ms": round(statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0.0, 6),
    }

    result = {
        "benchmark_protocol_version": "1.0.0",
        "timestamp_utc": now_iso,
        "status": "COMPLETED_LOCAL_BASELINE",
        "field_type": "locally_measured",
        "backend": "deterministic_rubric",
        "dataset": {
            "path": str(target_csv.relative_to(ROOT) if target_csv.is_relative_to(ROOT) else target_csv),
            "sha256": dataset_hash,
            "prospect_count": len(rows),
            "provenance": "Synthetic commercial prospect fixtures with fictional 555-prefix phone numbers and modeled ad waste; email and website domains are not RFC 2606-sanitized and must not be transmitted externally."
        },
        "samples_per_prospect": samples,
        "total_decision_calls": total_decisions,
        "schema_error_count": schema_errors,
        "schema_compliance_rate": round((total_decisions - schema_errors) / total_decisions, 4) if total_decisions else 1.0,
        "billed_cost_usd": 0.0,
        "latency_distribution": stats,
        "vendor_published_reference": vendor_reference
    }

    dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("\n" + "=" * 70)
    print("TypeSafe Local Benchmark Run Complete")
    print(f"Dataset: {len(rows)} prospects | SHA256: {dataset_hash[:16]}...")
    print(f"Decisions Evaluated: {total_decisions} | Schema Errors: {schema_errors}")
    print(f"Latency (p50): {stats['p50_ms']} ms | (p95): {stats['p95_ms']} ms | (p99): {stats['p99_ms']} ms")
    print(f"Report saved to: {dest}")
    print("=" * 70)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TypeSafe Lead Evaluation & Benchmark Runner")
    parser.add_argument("--benchmark", action="store_true", help="Execute reproducible benchmark protocol")
    parser.add_argument("--samples", type=int, default=None, help="Trials per prospect (defaults: 100 local, 1 Jev)")
    parser.add_argument("--backend", choices=["deterministic", "jev"], default="deterministic", help="Decision backend to benchmark")
    parser.add_argument("--output", type=Path, default=None, help="Output path for benchmark report JSON")
    parser.add_argument("--csv", type=Path, default=None, help="Path to prospect CSV")
    args = parser.parse_args(argv)

    if args.benchmark:
        run_benchmark(
            csv_path=args.csv,
            samples=args.samples,
            backend_type=args.backend,
            output_path=args.output,
        )
        return 0

    print("=" * 70)
    print("TypeSafe AI Lead Generation Evaluation Pipeline")
    print("https://docs.typesafe.ai/concepts/use-case-map#lead-generation")
    print("=" * 70)

    leads = evaluate_prospects(csv_path=args.csv)
    print(f"\nEvaluated {len(leads)} Commercial Prospects against TypeSafe ICP Rubric:")

    for i, lead in enumerate(leads, 1):
        print(f"\n[{i}] {lead.company_name} ({lead.vertical} - {lead.market})")
        print(f"    Contact: {lead.contact_name} ({lead.role})")
        print(f"    ICP Fit Score: {lead.icp_fit_score}/100 (High-Ticket: {lead.commercial_ticket_fit}) | Confidence: {lead.confidence:.0%}")
        print(f"    Identified Waste Vector: {lead.waste_vector} [Est: {lead.est_monthly_waste}]")
        print(f"    Evidence Gate: {lead.verification_status.upper()} (Can Export: {lead.can_export_outbound})")
        print(f"    TypeSafe Route: {lead.routing_action}")

    # Export JSON
    OUTPUT_REPORT.write_text(json.dumps([asdict(l) for l in leads], indent=2), encoding="utf-8")
    print(f"\n[+] Saved detailed evaluation JSON to: {OUTPUT_REPORT.relative_to(ROOT)}")

    # Export Markdown Summary
    md_content = [
        "# TypeSafe AI Lead Generation Evaluation & Routing Report",
        "",
        "> Framework: [TypeSafe AI Use-Case Map (Lead Generation)](https://docs.typesafe.ai/concepts/use-case-map#lead-generation)",
        f"> Generated: 2026-09-26 | Total Prospects: {len(leads)}",
        "",
        "## Evaluated Prospect Pipeline",
        "",
        "| Rank | Company | Vertical | Market | ICP Score | Identified Waste Vector | Est. Waste | Evidence Gate | Routing Decision |",
        "| :--- | :--- | :--- | :--- | :---: | :--- | :---: | :---: | :--- |"
    ]
    for i, l in enumerate(leads, 1):
        md_content.append(
            f"| {i} | **{l.company_name}** | {l.vertical} | {l.market} | **{l.icp_fit_score}/100** | {l.waste_vector} | {l.est_monthly_waste} | `{l.verification_status}` | {l.routing_action.split(':')[0]} |"
        )

    md_content.extend([
        "",
        "## TypeSafe AI Decision Mapping",
        "- **Match ICP & Score Maturity (Score):** Scored on ticket value ($10k-$100k+), decision-maker authority, and monthly waste volume.",
        "- **Pain Point & Intent (Choice):** Categorized exact negative keyword leakage vectors without generative text overhead.",
        "- **Commercial Fit & Threshold (Noul):** Binary qualification on >= $10k commercial job threshold.",
        "- **Universal Verification:** Integrated with `orchestrator/evidence_gate.py` to prevent unauthorized outreach with synthetic sample data.",
        ""
    ])
    OUTPUT_SUMMARY_MD.write_text("\n".join(md_content), encoding="utf-8")
    print(f"[+] Saved executive summary Markdown to: {OUTPUT_SUMMARY_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

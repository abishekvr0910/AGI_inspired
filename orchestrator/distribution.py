"""Distribution Engine CLI Dispatcher (Phase 1).

Orchestrates grounded Ad & SEO research task generation and admission dispatch
under full Ed25519 DSSE attestation and per-client workspace confinement.
Zero-spend: Never executes write or mutate API calls to ad platforms.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import attestation_chain as chain
import client_profile
from research_templates import (
    generate_keyword_research_task,
    generate_competitive_serp_task,
    generate_ad_copy_variants_task,
    generate_seo_content_brief_task,
    generate_landing_page_recco_task,
    generate_negative_keyword_harvest_task,
    generate_audience_pain_point_research_task,
)

TEMPLATES = {
    "keyword_research": {
        "func": generate_keyword_research_task,
        "description": "Seed keyword expansion, intent classification, and funnel stage mapping.",
        "surface": "Ads + SEO",
    },
    "competitive_serp": {
        "func": generate_competitive_serp_task,
        "description": "SERP organic rankers, competitor ad angles, content gaps, and opportunities.",
        "surface": "Ads + SEO",
    },
    "ad_copy_variants": {
        "func": generate_ad_copy_variants_task,
        "description": "Multi-format ad copy (RSA, PMax) with strict character limits, CTAs, and superlative bans.",
        "surface": "Ads (Primary)",
    },
    "seo_content_brief": {
        "func": generate_seo_content_brief_task,
        "description": "H1/H2/H3 outline, semantic entity coverage list, and internal link suggestions.",
        "surface": "SEO (Primary)",
    },
    "landing_page_recco": {
        "func": generate_landing_page_recco_task,
        "description": "Structural conversion recommendations (Hero, Subhead, Proof, CTA) and rationale.",
        "surface": "Ads + SEO",
    },
    "negative_keyword_harvest": {
        "func": generate_negative_keyword_harvest_task,
        "description": "Exclusion harvesting (free/cheap/DIY/careers/out-of-scope) with match types and waste rationales.",
        "surface": "Ads (Primary)",
    },
    "audience_pain_point_research": {
        "func": generate_audience_pain_point_research_task,
        "description": "Customer complaint, objection, and anxiety mining with emotional triggers and ad hook angles.",
        "surface": "Ads + Copywriting",
    },
}


def dispatch_distribution_task(
    client_id: str,
    template_name: str,
    seed_input: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    worker_engine: str = "hermes",
    root: Path | str | None = None,
    runs_dir: Path | str | None = None,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Compile and admit a distribution research task.

    If dry_run is True, returns generated specification and pass criteria without
    inserting into ledger.db or appending attestation records.
    """
    if template_name not in TEMPLATES:
        raise ValueError(f"unknown distribution template {template_name!r}; valid choices: {list(TEMPLATES.keys())}")

    profile = client_profile.load_client_profile(client_id, root=root)
    template_info = TEMPLATES[template_name]
    spec, criteria = template_info["func"](profile, seed_input=seed_input)

    if dry_run:
        return {
            "client_id": client_id,
            "template": template_name,
            "surface": template_info["surface"],
            "worker_engine": worker_engine,
            "dry_run": True,
            "spec": spec,
            "pass_criteria": criteria,
        }

    if root is not None:
        root_path = Path(root)
        runs = Path(runs_dir) if runs_dir is not None else root_path / "runs"
        db = Path(db_path) if db_path is not None else root_path / "ledger" / "ledger.db"
    else:
        try:
            import runtime_context as rc
            runs = Path(runs_dir) if runs_dir is not None else rc.RUNS
        except Exception:
            runs = Path(runs_dir) if runs_dir is not None else ROOT / "runs"

        try:
            import ledger
            db = Path(db_path) if db_path is not None else ledger.LEDGER_DB
        except Exception:
            db = Path(db_path) if db_path is not None else ROOT / "ledger" / "ledger.db"

    task_id = chain.dispatch_admitted_task(
        db,
        runs,
        mission_id="distribution",
        spec=spec,
        pass_criteria=criteria,
        client_id=client_id,
        worker_engine=worker_engine,
    )

    return {
        "client_id": client_id,
        "template": template_name,
        "surface": template_info["surface"],
        "worker_engine": worker_engine,
        "dry_run": False,
        "task_id": task_id,
        "mission_id": "distribution",
        "status": "queued",
        "spec": spec,
        "pass_criteria": criteria,
    }


def dispatch_all_templates(
    client_id: str,
    seed_input: dict[str, Any] | None = None,
    *,
    dry_run: bool = False,
    worker_engine: str = "hermes",
    root: Path | str | None = None,
    runs_dir: Path | str | None = None,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Dispatch all 7 distribution templates for a client in sequence."""
    results = []
    for t_name in TEMPLATES:
        res = dispatch_distribution_task(
            client_id,
            t_name,
            seed_input=seed_input,
            dry_run=dry_run,
            worker_engine=worker_engine,
            root=root,
            runs_dir=runs_dir,
            db_path=db_path,
        )
        results.append(res)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m orchestrator.distribution",
        description="Distribution Engine: Grounded Ad & SEO Research Dispatcher (Phase 1, Zero-Spend)",
    )
    parser.add_argument("--client", "-c", help="Client ID slug (must exist in workspace/clients/<client_id>/profile.json)")
    parser.add_argument(
        "--template", "-t",
        choices=[*TEMPLATES.keys(), "all"],
        help="Research template to generate and dispatch ('all' dispatches all 5)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview generated spec and criteria without queueing to database")
    parser.add_argument("--list-clients", action="store_true", help="List all configured client profiles in workspace/clients/")
    parser.add_argument("--list-templates", action="store_true", help="List available distribution research templates")
    parser.add_argument("--target-keyword", help="Optional target keyword override")
    parser.add_argument("--seed-keyword", action="append", dest="seed_keywords", help="Optional seed keyword(s) to add")
    parser.add_argument(
        "--intent",
        choices=["commercial", "transactional", "informational", "navigational"],
        help="Optional search intent override",
    )
    parser.add_argument(
        "--worker-engine",
        choices=["hermes", "native"],
        default="hermes",
        help="Worker execution engine: 'hermes' (subprocess CLI) or 'native' (self-improving agent loop)",
    )
    parser.add_argument("--root", help=argparse.SUPPRESS)
    parser.add_argument("--runs-dir", help=argparse.SUPPRESS)
    parser.add_argument("--db-path", help=argparse.SUPPRESS)
    parser.add_argument("--json", action="store_true", help="Output response in machine-readable JSON format")

    args = parser.parse_args(argv)

    if args.list_templates:
        summary = {k: {"description": v["description"], "surface": v["surface"]} for k, v in TEMPLATES.items()}
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print("\nDistribution Research Templates (Phase 1):")
            print("=" * 60)
            for name, info in summary.items():
                print(f"  • {name:<22} [{info['surface']}]")
                print(f"    {info['description']}\n")
        return 0

    if args.list_clients:
        clients = client_profile.list_client_profiles(root=args.root)
        if args.json:
            print(json.dumps(clients, indent=2))
        else:
            print("\nConfigured Client Profiles:")
            print("=" * 40)
            if not clients:
                print("  No client profiles found in workspace/clients/.")
            for cid in clients:
                try:
                    p = client_profile.load_client_profile(cid, root=args.root)
                    print(f"  • {cid:<20} - {p.get('display_name')} ({p.get('domain')})")
                except Exception as exc:
                    print(f"  • {cid:<20} - [error: {exc}]")
            print()
        return 0

    if not args.client:
        parser.error("--client is required to dispatch or preview a task (or use --list-clients / --list-templates)")

    if not args.template:
        parser.error("--template is required (or use --template all)")

    seed_input: dict[str, Any] = {}
    if args.target_keyword:
        seed_input["target_keyword"] = args.target_keyword
        if not args.seed_keywords:
            seed_input["seed_keywords"] = [args.target_keyword]
    if args.seed_keywords:
        seed_input["seed_keywords"] = args.seed_keywords
    if args.intent:
        seed_input["intent"] = args.intent

    try:
        if args.template == "all":
            results = dispatch_all_templates(
                args.client,
                seed_input=seed_input or None,
                dry_run=args.dry_run,
                worker_engine=args.worker_engine,
                root=args.root,
                runs_dir=args.runs_dir,
                db_path=args.db_path,
            )
            if args.json:
                print(json.dumps(results, indent=2))
            else:
                mode_str = "[DRY-RUN PREVIEW]" if args.dry_run else "[ADMITTED & QUEUED]"
                print(f"\n{mode_str} Dispatched {len(results)} research tasks for client '{args.client}':")
                for r in results:
                    tid_info = f"task_id={r.get('task_id')}" if not args.dry_run else "dry-run"
                    print(f"  • {r['template']:<22} -> {tid_info}")
                print()
        else:
            res = dispatch_distribution_task(
                args.client,
                args.template,
                seed_input=seed_input or None,
                dry_run=args.dry_run,
                worker_engine=args.worker_engine,
                root=args.root,
                runs_dir=args.runs_dir,
                db_path=args.db_path,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                if args.dry_run:
                    print(f"\n[DRY-RUN PREVIEW] Client: {res['client_id']} | Template: {res['template']} [{res['surface']}]")
                    print("=" * 70)
                    print("--- SPECIFICATION ---")
                    print(res["spec"])
                    print("--- PASS CRITERIA ---")
                    print(res["pass_criteria"])
                    print("=" * 70 + "\n")
                else:
                    print(f"\n[SUCCESS] Admitted & Queued task {res['task_id']} for client '{res['client_id']}' [{res['template']}]")
                    print("Cryptographic Step.DISPATCH record appended to attestation chain.\n")
        return 0
    except Exception as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "client_id": args.client}, indent=2), file=sys.stderr)
        else:
            print(f"\n[ERROR] {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

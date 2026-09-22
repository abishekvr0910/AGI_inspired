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
    parser.add_argument(
        "--compile-campaign",
        action="store_true",
        help="Compile client deliverables into Google Ads Editor bulk CSV and Strategy Dossier",
    )
    parser.add_argument(
        "--auto-pipeline",
        action="store_true",
        help="Run full end-to-end client venture pipeline: dispatch all research templates, build STAG campaign, export Google Ads Editor CSV, and generate strategy dossier",
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

    seed_input: dict[str, Any] = {}
    if args.target_keyword:
        seed_input["target_keyword"] = args.target_keyword
        if not args.seed_keywords:
            seed_input["seed_keywords"] = [args.target_keyword]
    if args.seed_keywords:
        seed_input["seed_keywords"] = args.seed_keywords
    if args.intent:
        seed_input["intent"] = args.intent

    if args.auto_pipeline:
        import client_reporter
        try:
            dispatch_results = dispatch_all_templates(
                args.client,
                seed_input=seed_input or None,
                dry_run=args.dry_run,
                worker_engine=args.worker_engine,
                root=args.root,
                runs_dir=args.runs_dir,
                db_path=args.db_path,
            )
            package_res = client_reporter.compile_and_export_client_package(
                args.client,
                root=args.root,
                db_path=args.db_path,
                runs_dir=args.runs_dir,
                force_export=True,  # Auto-pipeline generates sample packages for review
            )
            combined = {
                "success": True,
                "client_id": args.client,
                "pipeline": "auto",
                "dispatch_results": dispatch_results,
                "campaign_package": package_res,
            }
            if args.json:
                print(json.dumps(combined, indent=2))
            else:
                mode_str = "[DRY-RUN]" if args.dry_run else "[ADMITTED & QUEUED]"
                print(f"\n{'=' * 65}")
                print(f"       END-TO-END VENTURE PIPELINE COMPLETE ({mode_str})")
                print(f"{'=' * 65}")
                print(f"Client: {package_res['display_name']} ({package_res['client_id']})")
                print(f"Engine: {args.worker_engine}")
                print(f"\n[1] Dispatched {len(dispatch_results)} Research Tasks:")
                for r in dispatch_results:
                    tid_info = f"task_id={r.get('task_id')}" if not args.dry_run else "dry-run"
                    print(f"  • {r['template']:<28} -> {tid_info}")
                print(f"\n[2] Client Campaign & Strategy Dossier:")
                print(f"  * Google Ads Editor CSV:   {package_res['csv_path']}")
                print(f"  * Campaign Structure JSON: {package_res['json_path']}")
                print(f"  * Strategy Dossier (MD):   {package_res['dossier_md_path']}")
                print(f"  * Strategy Dossier (HTML): {package_res['dossier_html_path']}")
                print(f"  * Ad Groups:              {package_res['campaign_summary']['ad_groups_count']}")
                print(f"  * Total Keywords:         {package_res['campaign_summary']['total_keywords']}")
                print(f"  * Total Negatives:        {package_res['campaign_summary']['total_negatives']}")
                print(f"{'=' * 65}\n")
            return 0
        except Exception as exc:
            if args.json:
                print(json.dumps({"error": str(exc), "client_id": args.client}, indent=2), file=sys.stderr)
            else:
                print(f"\n[ERROR] Auto-pipeline failed: {exc}\n", file=sys.stderr)
            return 1

    if args.compile_campaign:
        import client_reporter
        try:
            res = client_reporter.compile_and_export_client_package(
                args.client,
                root=args.root,
                db_path=args.db_path,
                runs_dir=args.runs_dir,
            )
            if args.json:
                print(json.dumps(res, indent=2))
            else:
                print(f"\n[CAMPAIGN COMPILED] Client: {res['display_name']} ({res['client_id']})")
                print("=" * 60)
                print(f"  * Google Ads Editor CSV: {res['csv_path']}")
                print(f"  * Campaign JSON:        {res['json_path']}")
                print(f"  * Strategy Dossier (MD): {res['dossier_md_path']}")
                print(f"  * Strategy Dossier(HTML):{res['dossier_html_path']}")
                print(f"  * Ad Groups:            {res['campaign_summary']['ad_groups_count']}")
                print(f"  * Total Keywords:       {res['campaign_summary']['total_keywords']}")
                print(f"  * Total Negatives:      {res['campaign_summary']['total_negatives']}")
                print("=" * 60 + "\n")
            return 0
        except Exception as exc:
            if args.json:
                print(json.dumps({"error": str(exc)}, indent=2))
            else:
                print(f"\n[ERROR] Campaign compilation failed: {exc}\n")
            return 1

    if not args.template:
        parser.error("--template is required (or use --template all / --auto-pipeline / --compile-campaign)")

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

"""Client Strategy Dossier & Campaign Exporter (Distribution Engine).

Compiles grounded research deliverables across all 7 templates for a client into:
1. Executive Marketing & Distribution Strategy Dossier (Markdown and styled HTML).
2. Offline Google Ads Editor bulk upload CSV via orchestrator.campaign_builder.
3. Campaign Structure JSON for multi-channel distribution.

Zero-spend: Pure deterministic offline synthesis and file export with zero ad-platform API calls.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from client_profile import client_dir, load_client_profile
import campaign_builder
from campaign_builder import Campaign, export_google_ads_editor_csv, export_campaign_json
from evidence_gate import verify_client_package_export, VerificationStatus


def parse_markdown_tables(text: str) -> list[list[dict[str, str]]]:
    """Extract all markdown tables from text as lists of row dictionaries."""
    tables: list[list[dict[str, str]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and line.endswith("|") and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Check for header separator line like |---|---|
            if next_line.startswith("|") and re.match(r"^\|(\s*:?-+:?\s*\|)+$", next_line):
                # Header row
                headers = [h.strip() for h in line.strip("|").split("|")]
                table_rows: list[dict[str, str]] = []
                j = i + 2
                while j < len(lines):
                    row_line = lines[j].strip()
                    if not (row_line.startswith("|") and row_line.endswith("|")):
                        break
                    cols = [c.strip() for c in row_line.strip("|").split("|")]
                    if len(cols) == len(headers):
                        table_rows.append(dict(zip(headers, cols)))
                    elif len(cols) > len(headers):
                        table_rows.append(dict(zip(headers, cols[:len(headers)])))
                    else:
                        padded = cols + [""] * (len(headers) - len(cols))
                        table_rows.append(dict(zip(headers, padded)))
                    j += 1
                if table_rows:
                    tables.append(table_rows)
                i = j
                continue
        i += 1
    return tables


def extract_keywords_from_deliverable(text: str) -> list[dict[str, Any]]:
    """Extract positive keyword entries from keyword_research deliverable."""
    results: list[dict[str, Any]] = []
    for table in parse_markdown_tables(text):
        for row in table:
            kw = row.get("Keyword") or row.get("keyword") or row.get("Search Query")
            if kw and not kw.startswith("-"):
                clean_kw = kw.strip("`\"'[]")
                results.append({
                    "keyword": clean_kw,
                    "intent": row.get("Intent") or row.get("intent") or "commercial",
                    "funnel_stage": row.get("Funnel Stage") or row.get("funnel_stage") or "consideration",
                    "rationale": row.get("Rationale") or row.get("rationale") or "",
                    "source_url": row.get("Source URL") or row.get("source_url") or "",
                    "theme": row.get("Theme") or row.get("Funnel Stage") or clean_kw,
                })
    return results


def extract_negatives_from_deliverable(text: str) -> list[dict[str, Any]]:
    """Extract negative keyword entries from negative_keyword_harvest deliverable."""
    results: list[dict[str, Any]] = []
    for table in parse_markdown_tables(text):
        for row in table:
            neg = row.get("Negative Keyword") or row.get("negative_keyword") or row.get("Keyword")
            if neg:
                clean_neg = neg.strip("`\"'[]")
                mt = row.get("Match Type") or row.get("match_type") or "Phrase"
                results.append({
                    "keyword": clean_neg,
                    "match_type": mt.strip().capitalize(),
                    "category": row.get("Category") or row.get("category") or "irrelevant_intent",
                    "rationale": row.get("Budget Waste Rationale") or row.get("rationale") or "",
                    "source_url": row.get("Source URL") or row.get("source_url") or "",
                })
    return results


def extract_ad_copies_from_deliverable(text: str) -> list[dict[str, Any]]:
    """Extract ad copy variants from ad_copy_variants deliverable."""
    results: list[dict[str, Any]] = []
    for table in parse_markdown_tables(text):
        for row in table:
            comp = row.get("Component") or row.get("component") or ""
            copy_text = row.get("Copy Text") or row.get("copy_text") or row.get("Headline / Description") or ""
            if comp and copy_text:
                results.append({
                    "format": row.get("Format") or row.get("format") or "RSA",
                    "component": comp.strip(),
                    "copy_text": copy_text.strip("`\"'"),
                    "characters": row.get("Characters") or row.get("characters") or str(len(copy_text)),
                    "cta": row.get("CTA") or row.get("cta") or "",
                    "rationale": row.get("Source / Rationale") or row.get("Rationale") or "",
                })
    return results


def extract_pain_points_from_deliverable(text: str) -> list[dict[str, Any]]:
    """Extract customer pain points and hooks from audience_pain_point_research deliverable."""
    results: list[dict[str, Any]] = []
    for table in parse_markdown_tables(text):
        for row in table:
            pain = row.get("Pain Point / Objection") or row.get("pain_point") or row.get("Objection")
            if pain:
                results.append({
                    "pain_point": pain.strip(),
                    "emotional_trigger": row.get("Emotional Trigger") or row.get("Underlying Anxiety") or row.get("emotional_trigger") or "",
                    "recommended_hook": row.get("Recommended Ad Hook") or row.get("Recommended Ad Hook / Angle") or row.get("recommended_hook") or "",
                    "proof_required": row.get("Proof Required") or row.get("Proof Requirement Needed") or row.get("proof_required") or "",
                    "source_url": row.get("Source URL") or row.get("source_url") or "",
                })
    return results


def extract_competitors_from_deliverable(text: str) -> list[dict[str, Any]]:
    """Extract competitor organic angles and opportunities from competitive_serp deliverable."""
    results: list[dict[str, Any]] = []
    for table in parse_markdown_tables(text):
        for row in table:
            comp = row.get("Competitor / Ranker") or row.get("Competitor") or row.get("competitor")
            if comp:
                results.append({
                    "competitor": comp.strip(),
                    "serp_angle": row.get("SERP Angle") or row.get("serp_angle") or "",
                    "content_gap": row.get("Content Gap") or row.get("content_gap") or "",
                    "opportunity": row.get("Opportunity for Us") or row.get("opportunity") or "",
                    "source_url": row.get("Source URL") or row.get("source_url") or "",
                })
    return results


def extract_landing_page_reccos(text: str) -> list[dict[str, Any]]:
    """Extract landing page section recommendations from landing_page_recco deliverable."""
    results: list[dict[str, Any]] = []
    for table in parse_markdown_tables(text):
        for row in table:
            sec = row.get("Section Name") or row.get("section_name") or row.get("Section")
            if sec:
                results.append({
                    "section": sec.strip(),
                    "purpose": row.get("Purpose") or row.get("purpose") or "",
                    "rationale": row.get("Why-It-Converts Rationale") or row.get("Rationale") or "",
                    "evidence": row.get("Evidence / Source") or row.get("Source") or "",
                })
    return results


def load_client_deliverables(
    client_id: str,
    root: Path | str | None = None,
    db_path: Path | str | None = None,
    runs_dir: Path | str | None = None,
) -> dict[str, str]:
    """Discover all completed deliverables for a client across workspace files and ledger."""
    cdir = client_dir(client_id, root)
    deliverables: dict[str, str] = {}

    # 1. Scan client's workspace directory
    for p in cdir.glob("*.md"):
        stem = p.stem.lower()
        if stem != "strategy_dossier":
            deliverables[stem] = p.read_text(encoding="utf-8", errors="replace")

    deliv_sub = cdir / "deliverables"
    if deliv_sub.is_dir():
        for p in deliv_sub.glob("*.md"):
            stem = p.stem.lower()
            if stem not in deliverables:
                deliverables[stem] = p.read_text(encoding="utf-8", errors="replace")

    # 2. Check ledger database and runs directory if supplied
    if db_path and Path(db_path).is_file() and runs_dir and Path(runs_dir).is_dir():
        import sqlite3
        runs_p = Path(runs_dir)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            cols = [c[1] for c in conn.execute("PRAGMA table_info(tasks)").fetchall()]
            tid_col = "task_id" if "task_id" in cols else "id" if "id" in cols else None
            mid_col = "mission_id" if "mission_id" in cols else None
            if tid_col:
                mid_sel = f", {mid_col}" if mid_col else ""
                rows = conn.execute(
                    f"SELECT {tid_col} as task_id{mid_sel}, status FROM tasks WHERE status = 'done' ORDER BY {tid_col} ASC"
                ).fetchall()
                for r in rows:
                    tid = r["task_id"]
                    mid = str(r[mid_col] or "") if mid_col else ""
                    # Check attestation claims for client_id
                    chain_file = runs_p / f"task{tid}.attestation.jsonl"
                    if chain_file.is_file():
                        try:
                            for line in chain_file.read_text(encoding="utf-8").splitlines():
                                rec = json.loads(line)
                                claims = rec.get("claims", {})
                                if claims.get("client_id") == client_id:
                                    # Found matching task
                                    tmpl_key = mid.replace("dist-", "").strip().lower()
                                    raw_file = runs_p / f"task{tid}_a1_worker_raw.txt"
                                    if not raw_file.is_file():
                                        raw_file = runs_p / f"task{tid}_worker_raw.txt"
                                    if raw_file.is_file() and tmpl_key not in deliverables:
                                        deliverables[tmpl_key] = raw_file.read_text(encoding="utf-8", errors="replace")
                                    break
                        except Exception:
                            pass
        finally:
            conn.close()

    return deliverables


def generate_executive_dossier(
    client_profile: dict[str, Any],
    deliverables: dict[str, str],
) -> str:
    """Generate a comprehensive Executive Marketing & Distribution Dossier."""
    display_name = client_profile.get("display_name", client_profile.get("client_id"))
    domain = client_profile.get("domain", "Commercial")
    offer = client_profile.get("offer", "Core Offer")
    audience = client_profile.get("audience", "Target Audience")
    brand_voice = client_profile.get("brand_voice", "Professional")
    landing_url = client_profile.get("landing_url", "https://example.com")
    geos = ", ".join(client_profile.get("geo", ["Global"]))
    forbidden = ", ".join(f"'{c}'" for c in client_profile.get("forbidden_claims", [])) or "None specified"
    
    # Check for sample/verification status
    is_sample = (
        client_profile.get("_force_export", False) or
        client_profile.get("_verification_status") == "sample"
    )
    sample_banner = ""
    if is_sample:
        sample_banner = "\n> **⚠ SAMPLE MATERIAL — NOT VERIFIED FOR CLIENT USE**\n> This package was generated from synthetic/demonstration data. All contacts, waste estimates, and claims are UNVERIFIED.\n"

    lines: list[str] = [
        f"# Executive Strategy & Distribution Audit: {display_name}",
        "",
        "> **Confidential Client Report** | Compiled Deterministically via AGI_like Distribution Engine",
        f"> **Primary Domain:** {domain} | **Market/Geo:** {geos} | **Target URL:** [{landing_url}]({landing_url})",
        sample_banner,
        "---",
        "",
        "## 1. Executive Summary & Brand Positioning",
        "",
        f"- **Core Value Proposition:** {offer}",
        f"- **Primary Target Audience:** {audience}",
        f"- **Brand Voice & Tone Guidelines:** {brand_voice}",
        f"- **Compliance & Policy Guardrails (Forbidden Claims):** {forbidden}",
        "",
    ]

    # 2. Audience Pain Points
    pain_text = deliverables.get("audience_pain_point_research", "")
    pains = extract_pain_points_from_deliverable(pain_text)
    lines.append("## 2. Customer Psychology: Pain Points, Anxiety Drivers & Proven Hooks")
    lines.append("")
    if pains:
        lines.append("| Objection / Pain Point | Emotional Trigger | Recommended Ad Hook | Required Proof Point |")
        lines.append("|---|---|---|---|")
        for p in pains:
            lines.append(f"| {p['pain_point']} | {p['emotional_trigger']} | **{p['recommended_hook']}** | {p['proof_required']} |")
    else:
        lines.append("*Audience pain point research pending generation.*")
    lines.append("")

    # 3. High-Intent Keyword Matrix
    kw_text = deliverables.get("keyword_research", "")
    keywords = extract_keywords_from_deliverable(kw_text)
    lines.append("## 3. High-Intent Keyword Matrix & Funnel Architecture")
    lines.append("")
    if keywords:
        lines.append("| Search Query | Intent | Funnel Stage | Strategic Rationale |")
        lines.append("|---|---|---|---|")
        for k in keywords:
            lines.append(f"| `{k['keyword']}` | {k['intent']} | {k['funnel_stage']} | {k['rationale']} |")
    else:
        lines.append("*Keyword research pending generation.*")
    lines.append("")

    # 4. Negative Keyword Shield
    neg_text = deliverables.get("negative_keyword_harvest", "")
    negatives = extract_negatives_from_deliverable(neg_text)
    lines.append("## 4. Negative Keyword Shield (Budget-Waste Prevention)")
    lines.append("")
    if negatives:
        lines.append("| Exclusion Keyword | Match Type | Category | Budget Waste Rationale |")
        lines.append("|---|---|---|---|")
        for n in negatives:
            lines.append(f"| `{n['keyword']}` | {n['match_type']} | `{n['category']}` | {n['rationale']} |")
    else:
        lines.append("*Negative keyword harvesting pending generation.*")
    lines.append("")

    # 5. Ad Copy Variants
    copy_text = deliverables.get("ad_copy_variants", "")
    ad_copies = extract_ad_copies_from_deliverable(copy_text)
    lines.append("## 5. Responsive Search Ad (RSA) Creative Suite")
    lines.append("")
    if ad_copies:
        lines.append("| Component | Copy Text | Chars | Call To Action | Strategic Angle |")
        lines.append("|---|---|---|---|---|")
        for a in ad_copies:
            lines.append(f"| {a['component']} | **{a['copy_text']}** | `{a['characters']}` | {a['cta']} | {a['rationale']} |")
    else:
        lines.append("*Ad copy variants pending generation.*")
    lines.append("")

    # 6. Competitive SERP
    serp_text = deliverables.get("competitive_serp", "")
    comps = extract_competitors_from_deliverable(serp_text)
    lines.append("## 6. Competitive SERP Landscape & Exploitable Gaps")
    lines.append("")
    if comps:
        lines.append("| Competitor / Ranker | SERP Angle | Identified Gap | Exploitable Opportunity |")
        lines.append("|---|---|---|---|")
        for c in comps:
            lines.append(f"| {c['competitor']} | {c['serp_angle']} | {c['content_gap']} | **{c['opportunity']}** |")
    else:
        lines.append("*Competitive SERP research pending generation.*")
    lines.append("")

    # 7. Landing Page Architecture
    lp_text = deliverables.get("landing_page_recco", "")
    lp_reccos = extract_landing_page_reccos(lp_text)
    lines.append("## 7. High-Converting Landing Page Architecture")
    lines.append("")
    if lp_reccos:
        lines.append("| Page Section | Core Purpose | Conversion Rationale | Reference Evidence |")
        lines.append("|---|---|---|---|")
        for l in lp_reccos:
            lines.append(f"| **{l['section']}** | {l['purpose']} | {l['rationale']} | {l['evidence']} |")
    else:
        lines.append("*Landing page architecture recommendations pending generation.*")
    lines.append("")

    # 8. Implementation Guidance
    lines.extend([
        "## 8. Google Ads Editor Bulk Deployment Instructions",
        "",
        "1. Open **Google Ads Editor** on your desktop.",
        "2. Navigate to **Account** $\\to$ **Import** $\\to$ **From file...**",
        f"3. Select `workspace/clients/{client_profile.get('client_id')}/google_ads_editor_import.csv`.",
        "4. Review the Single-Theme Ad Groups (STAGs), Exact/Phrase keywords, and Negative lists in the preview grid.",
        "5. Click **Process** and then **Post** to publish campaigns live with 100% human verification.",
        "",
        "---",
        f"*Report generated by AGI_like Autonomous Harness | Client ID: `{client_profile.get('client_id')}`*",
    ])

    return "\n".join(lines) + "\n"


def generate_dossier_html(client_profile: dict[str, Any], dossier_markdown: str) -> str:
    """Wrap executive dossier markdown in responsive, client-ready dark-mode HTML."""
    display_name = html.escape(client_profile.get("display_name", "Client"))
    domain = html.escape(client_profile.get("domain", "Commercial"))
    
    # Check for sample status
    is_sample = (
        client_profile.get("_force_export", False) or
        client_profile.get("_verification_status") == "sample"
    )
    sample_banner_html = ""
    if is_sample:
        sample_banner_html = """
    <div class="no-print mb-6 p-4 rounded-xl border-2 border-amber-600 bg-amber-900/30 text-amber-200">
      <div class="flex items-center gap-3">
        <svg class="w-6 h-6 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
        </svg>
        <div>
          <p class="font-bold text-base">SAMPLE MATERIAL — NOT VERIFIED FOR CLIENT USE</p>
          <p class="text-sm">This package was generated from synthetic/demonstration data. All contacts, waste estimates, and claims are UNVERIFIED.</p>
        </div>
      </div>
    </div>"""

    # Convert simple markdown headers, tables, bold, and code to clean HTML
    content_html = []
    in_table = False
    table_headers: list[str] = []

    for line in dossier_markdown.splitlines():
        line_str = line.strip()
        if not line_str:
            if in_table:
                content_html.append("</tbody></table></div>")
                in_table = False
            continue

        if line_str.startswith("# "):
            if in_table:
                content_html.append("</tbody></table></div>")
                in_table = False
            content_html.append(f"<h1 class='text-3xl font-extrabold text-white tracking-tight mt-6 mb-2 border-b border-slate-800 pb-3'>{html.escape(line_str[2:])}</h1>")
        elif line_str.startswith("## "):
            if in_table:
                content_html.append("</tbody></table></div>")
                in_table = False
            content_html.append(f"<h2 class='text-xl font-bold text-cyan-400 tracking-wide mt-8 mb-3 flex items-center gap-2'><span class='w-2 h-2 rounded-full bg-cyan-400'></span>{html.escape(line_str[3:])}</h2>")
        elif line_str.startswith("> "):
            content_html.append(f"<blockquote class='p-3 my-2 border-l-4 border-cyan-500 bg-slate-900/60 rounded-r text-xs text-slate-300 font-mono'>{html.escape(line_str[2:])}</blockquote>")
        elif line_str.startswith("|") and line_str.endswith("|"):
            cells = [c.strip() for c in line_str.strip("|").split("|")]
            if re.match(r"^(\s*:?-+:?\s*\|)+$", line_str.strip("|") + "|"):
                # Header separator line
                continue
            if not in_table:
                in_table = True
                table_headers = cells
                th_html = "".join(f"<th class='py-2.5 px-3 bg-slate-950 font-mono text-[11px] text-slate-400 uppercase tracking-wider text-left border-b border-slate-800'>{html.escape(c)}</th>" for c in cells)
                content_html.append(f"<div class='overflow-x-auto my-3 rounded-xl border border-slate-800 bg-slate-900/40'><table class='w-full text-left border-collapse'><thead><tr>{th_html}</tr></thead><tbody class='divide-y divide-slate-800/60 text-xs font-mono text-slate-300'>")
            else:
                td_html = "".join(f"<td class='py-2 px-3'>{html.escape(c)}</td>" for c in cells)
                content_html.append(f"<tr class='hover:bg-slate-800/40 transition'>{td_html}</tr>")
        elif line_str.startswith("- "):
            if in_table:
                content_html.append("</tbody></table></div>")
                in_table = False
            content_html.append(f"<li class='text-xs text-slate-300 my-1 ml-4 list-disc'>{html.escape(line_str[2:])}</li>")
        else:
            if in_table:
                content_html.append("</tbody></table></div>")
                in_table = False
            content_html.append(f"<p class='text-xs text-slate-400 leading-relaxed my-2'>{html.escape(line_str)}</p>")

    if in_table:
        content_html.append("</tbody></table></div>")

    body_content = "\n".join(content_html)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{display_name} - Executive Distribution Strategy Dossier</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @media print {{
      body {{ background: #ffffff !important; color: #000000 !important; }}
      .no-print {{ display: none !important; }}
    }}
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased selection:bg-cyan-500 selection:text-black">
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 to-emerald-500 flex items-center justify-center text-black font-extrabold text-sm">AGI</div>
        <div>
          <h1 class="text-sm font-bold text-white tracking-wide">{display_name} — Distribution Dossier</h1>
          <p class="text-[11px] text-slate-400 font-mono">Vertical: {domain} | Zero-Spend Deterministic Compiler</p>
        </div>
      </div>
      <div class="flex items-center gap-2 no-print">
        <button onclick="window.print()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-mono text-slate-200 border border-slate-700 transition">Print / PDF</button>
      </div>
    </div>
  </header>

  <main class="max-w-5xl mx-auto px-6 py-8">
    {sample_banner_html}
    {body_content}
  </main>

  <footer class="border-t border-slate-800 mt-12 py-6 text-center text-xs text-slate-500 font-mono">
    Generated deterministically by AGI_like Distribution Engine • Zero-Spend Audit Invariant Enforced
  </footer>
</body>
</html>
"""


def compile_and_export_client_package(
    client_id: str,
    root: Path | str | None = None,
    db_path: Path | str | None = None,
    runs_dir: Path | str | None = None,
    force_export: bool = False,
) -> dict[str, Any]:
    """Compile all deliverables for a client into strategy dossier and Google Ads Editor CSV.
    
    Evidence Gate: Blocks client-ready export unless prospect is VERIFIED with operator approval.
    Use force_export=True only for sample/internal generation (adds SAMPLE watermark).
    """
    # Evidence gate check
    if not force_export:
        can_export, reason = verify_client_package_export(client_id, root=root)
        if not can_export:
            return {
                "success": False,
                "client_id": client_id,
                "error": "EXPORT_BLOCKED",
                "message": f"Evidence gate blocked export: {reason}. Use force_export=True for sample generation only.",
                "verification_status": "blocked",
            }
    
    prof = load_client_profile(client_id, root=root)
    cdir = client_dir(client_id, root=root)
    deliverables = load_client_deliverables(client_id, root=root, db_path=db_path, runs_dir=runs_dir)
    
    # Add verification status to profile for watermarking
    from evidence_gate import EvidenceGate, VerificationStatus
    gate = EvidenceGate(root)
    verification = gate.get(client_id)
    prof["_verification_status"] = verification.status.value if verification else "unknown"
    prof["_force_export"] = force_export

    # 1. Parse structured findings
    kw_entries = extract_keywords_from_deliverable(deliverables.get("keyword_research", ""))
    neg_entries = extract_negatives_from_deliverable(deliverables.get("negative_keyword_harvest", ""))
    ad_entries = extract_ad_copies_from_deliverable(deliverables.get("ad_copy_variants", ""))

    # If deliverables are empty or in progress, fallback to profile defaults so compiler always works
    if not kw_entries and prof.get("seed_keywords"):
        kw_entries = [{"keyword": kw, "theme": kw, "intent": "commercial"} for kw in prof["seed_keywords"]]

    # 2. Build Campaign structure via campaign_builder
    # Organize ad copy entries into standard dictionary
    ad_copy_dicts: list[dict[str, Any]] = []
    if ad_entries:
        headlines = [a["copy_text"] for a in ad_entries if "headline" in a.get("component", "").lower()]
        descriptions = [a["copy_text"] for a in ad_entries if "description" in a.get("component", "").lower()]
        if headlines or descriptions:
            ad_copy_dicts.append({
                "headlines": headlines,
                "descriptions": descriptions,
                "final_url": prof.get("landing_url", "https://example.com"),
            })

    campaign = campaign_builder.build_campaign_from_research(
        client_profile=prof,
        keywords=kw_entries,
        ad_copies=ad_copy_dicts if ad_copy_dicts else None,
        negatives=neg_entries if neg_entries else None,
        verified_for_export=not force_export,  # Only verified for export if not forced sample
    )

    # 3. Export Google Ads Editor bulk CSV
    csv_path = cdir / "google_ads_editor_import.csv"
    export_google_ads_editor_csv(campaign, csv_path)

    # 4. Export Campaign structure JSON
    json_path = cdir / "campaign_structure.json"
    export_campaign_json(campaign, json_path)

    # 5. Generate and write Executive Dossier (Markdown + HTML)
    dossier_md = generate_executive_dossier(prof, deliverables)
    md_path = cdir / "strategy_dossier.md"
    md_path.write_text(dossier_md, encoding="utf-8")

    dossier_html = generate_dossier_html(prof, dossier_md)
    html_path = cdir / "strategy_dossier.html"
    html_path.write_text(dossier_html, encoding="utf-8")

    return {
        "success": True,
        "client_id": client_id,
        "display_name": prof.get("display_name", client_id),
        "deliverables_found": list(deliverables.keys()),
        "csv_path": str(csv_path),
        "json_path": str(json_path),
        "dossier_md_path": str(md_path),
        "dossier_html_path": str(html_path),
        "campaign_summary": {
            "campaign_name": campaign.name,
            "ad_groups_count": len(campaign.ad_groups),
            "total_keywords": campaign.total_keywords(),
            "total_negatives": campaign.total_negatives(),
            "total_ads": campaign.total_ads(),
        },
    }

"""Audience pain point & objection mining template function for distribution engine (Phase 2).

Pure function mapping (client_profile, seed_input) -> (spec, pass_criteria).
Outputs grounded audience pain-point research specifications arming preflight criteria.
"""
from __future__ import annotations

from typing import Any


def generate_audience_pain_point_research_task(
    client_profile: dict[str, Any],
    seed_input: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Generate (spec, pass_criteria) for an audience pain point research task.

    Arms deliverable_preflight checks:
    - Minimum 2 distinct independent sources cited.
    - Mandatory bounded-failure section ('### Sources Attempted').
    - Disallows speculative placeholders (mandates 'not publicly disclosed').
    - Disallows unsubstantiated claims and superlatives ('best', '#1', 'guaranteed').
    - Excludes client's declared forbidden claims.
    """
    client_id = client_profile.get("client_id", "unknown-client")
    display_name = client_profile.get("display_name", client_id)
    domain = client_profile.get("domain", "")
    offer = client_profile.get("offer", "")
    audience = client_profile.get("audience", "")
    brand_voice = client_profile.get("brand_voice", "Professional and trustworthy")
    competitors = client_profile.get("competitors", [])
    forbidden_claims = client_profile.get("forbidden_claims", [])

    seeds = list(client_profile.get("seed_keywords", []))
    target_kw = ""
    if seed_input:
        target_kw = seed_input.get("target_keyword", "")
        if "seed_keywords" in seed_input:
            for s in seed_input["seed_keywords"]:
                if s not in seeds:
                    seeds.append(s)

    spec = (
        f"Mission: Grounded audience pain point, objection, and anxiety research for client '{display_name}' (client_id: '{client_id}').\n"
        f"Domain/Vertical: {domain}\n"
        f"Core Offer: {offer}\n"
        f"Target Audience: {audience}\n"
        f"Brand Voice Guidelines: {brand_voice}\n"
        f"Core Focus Query: {target_kw or (seeds[0] if seeds else 'Market discovery')}\n"
        f"Known Competitors for Review Mining: {', '.join(competitors) if competitors else 'None specified'}\n"
        "\n"
        "Requirements:\n"
        "1. Research actual customer reviews, complaints, buyer anxieties, and hesitation points in this vertical from grounded web sources.\n"
        "2. Identify at least 3 distinct, high-impact Pain Points or Objections buyers experience when purchasing this service.\n"
        "3. For each pain point, identify the underlying Emotional Trigger (e.g. fear of property damage, dread of hidden fees, frustration with delays).\n"
        "4. Formulate a Recommended Ad Hook or Headline Angle directly addressing and diffusing that specific pain point.\n"
        "5. Specify the Proof Required (e.g. warranty length, transparent upfront pricing, license/bonding, response SLA) needed to validate the hook.\n"
        "6. Ground each observation in a verifiable customer review, case study, or vertical forum link.\n"
    )

    forbidden_clause = ""
    if forbidden_claims:
        claims_str = ", ".join(f"'{c}'" for c in forbidden_claims)
        forbidden_clause = f"\nDeliverable must not contain any forbidden claim: {claims_str}."

    pass_criteria = (
        "Deliverable must provide a markdown table with columns:\n"
        "| Pain Point / Objection | Emotional Trigger | Recommended Ad Hook | Proof Required | Source URL |\n"
        "\n"
        "At least 2 distinct independent sources cited.\n"
        "Deliverable must include a bounded-failure section titled '### Sources Attempted' naming every source attempted with status (rating-obtained/blocked/unavailable).\n"
        "For unavailable data points, explicitly enter 'not publicly disclosed' rather than speculative placeholders or empty cells.\n"
        "No unsubstantiated superlative claims ('best', '#1', 'world-class', 'guaranteed cheapest')."
        f"{forbidden_clause}"
    )

    return spec, pass_criteria

"""Negative keyword harvest template function for distribution engine (Phase 2).

Pure function mapping (client_profile, seed_input) -> (spec, pass_criteria).
Outputs grounded negative keyword research specifications arming preflight criteria.
"""
from __future__ import annotations

from typing import Any

VALID_MATCH_TYPES = ("exact", "phrase", "broad")
VALID_CATEGORIES = (
    "irrelevant_intent",
    "career_or_education",
    "out_of_scope_service",
    "competitor_brand",
)


def generate_negative_keyword_harvest_task(
    client_profile: dict[str, Any],
    seed_input: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Generate (spec, pass_criteria) for a negative keyword harvest task.

    Arms deliverable_preflight checks:
    - Minimum 2 distinct independent sources cited.
    - Mandatory bounded-failure section ('### Sources Attempted').
    - Disallows speculative placeholders (mandates 'not publicly disclosed').
    - Strict classification into valid match types (exact, phrase, broad) and categories.
    - Excludes client's declared forbidden claims.
    """
    client_id = client_profile.get("client_id", "unknown-client")
    display_name = client_profile.get("display_name", client_id)
    domain = client_profile.get("domain", "")
    offer = client_profile.get("offer", "")
    audience = client_profile.get("audience", "")
    competitors = client_profile.get("competitors", [])
    forbidden_claims = client_profile.get("forbidden_claims", [])

    seeds = list(client_profile.get("seed_keywords", []))
    target_kw = ""
    excluded_services = []
    if seed_input:
        target_kw = seed_input.get("target_keyword", "")
        excluded_services = seed_input.get("excluded_services", [])
        if "seed_keywords" in seed_input:
            for s in seed_input["seed_keywords"]:
                if s not in seeds:
                    seeds.append(s)

    spec = (
        f"Mission: Negative keyword harvest and budget-waste prevention research for client '{display_name}' (client_id: '{client_id}').\n"
        f"Domain/Vertical: {domain}\n"
        f"Core Offer: {offer}\n"
        f"Target Audience: {audience}\n"
        f"Primary Service Focus: {target_kw or (seeds[0] if seeds else 'Core service offering')}\n"
        f"Explicitly Excluded Services/Sub-verticals: {', '.join(excluded_services) if excluded_services else 'General low-intent/free/DIY/career exclusions'}\n"
        f"Known Competitors: {', '.join(competitors) if competitors else 'None specified'}\n"
        "\n"
        "Requirements:\n"
        "1. Research actual search queries and search patterns that trigger ads in this vertical with zero or negative commercial conversion intent.\n"
        "2. Identify at least 5 distinct negative keywords across the following categories:\n"
        "   - irrelevant_intent: search terms like free, cheap, wholesale, torrent, pdf, diy, etc.\n"
        "   - career_or_education: search terms like jobs, hiring, salary, training, school, course, certificate.\n"
        "   - out_of_scope_service: services or product tiers client does not offer (e.g. residential vs commercial, parts-only, rental vs installation).\n"
        "   - competitor_brand: competitor brand terms to exclude if client does not run conquesting campaigns.\n"
        "3. Assign each negative keyword a strict Match Type: exact, phrase, or broad.\n"
        "4. Provide a concrete Budget Waste Rationale explaining why unblocked clicks on this term waste ad spend.\n"
        "5. Cite verifiable sources (SERP observations, forum discussions, or vertical market documentation) for query patterns.\n"
    )

    forbidden_clause = ""
    if forbidden_claims:
        claims_str = ", ".join(f"'{c}'" for c in forbidden_claims)
        forbidden_clause = f"\nDeliverable must not contain any forbidden claim: {claims_str}."

    pass_criteria = (
        "Deliverable must provide a markdown table with columns:\n"
        "| Negative Keyword | Match Type | Category | Budget Waste Rationale | Source URL |\n"
        "\n"
        "Match type must be one of: exact, phrase, broad.\n"
        "Category must be one of: irrelevant_intent, career_or_education, out_of_scope_service, competitor_brand.\n"
        "At least 2 distinct independent sources cited.\n"
        "Deliverable must include a bounded-failure section titled '### Sources Attempted' naming every source attempted with status (rating-obtained/blocked/unavailable).\n"
        "For unavailable data points, explicitly enter 'not publicly disclosed' rather than speculative placeholders or empty cells."
        f"{forbidden_clause}"
    )

    return spec, pass_criteria

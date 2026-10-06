"""Campaign Structure Builder & Offline Compiler for Google Ads (Phase 2).

Compiles client profiles, keyword research, ad copy variants, and negative keywords
into structured Single-Theme Ad Groups (STAGs) and exportable Google Ads Editor bulk CSVs.

Zero-spend: Pure deterministic offline compilation with zero ad-platform API mutations.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io
import json
from pathlib import Path
import re
from typing import Any


MAX_HEADLINE_LENGTH = 30
MAX_DESCRIPTION_LENGTH = 90
MAX_RSA_HEADLINES = 15
MAX_RSA_DESCRIPTIONS = 4

# Claims that are commonly forbidden and should never appear in generated ads
DEFAULT_FORBIDDEN_CLAIMS = [
    "certified",
    "insured",
    "guaranteed",
    "satisfaction guaranteed",
    "100% guaranteed",
    "money back guarantee",
    "risk free",
    "free guarantee",
    "cheapest",
    "lowest price",
    "#1",
    "best",
    "number one",
]


@dataclass(frozen=True)
class KeywordTarget:
    text: str
    match_type: str = "Exact"  # "Exact", "Phrase"

    def formatted_text(self) -> str:
        clean = self.text.strip().strip("[]\"")
        if self.match_type.lower() == "exact":
            return f"[{clean}]"
        elif self.match_type.lower() == "phrase":
            return f'"{clean}"'
        return clean


@dataclass(frozen=True)
class NegativeKeyword:
    text: str
    match_type: str = "Phrase"  # "Exact", "Phrase", "Broad"
    level: str = "Campaign"     # "Campaign", "AdGroup"

    def formatted_text(self) -> str:
        clean = self.text.strip().strip("[]\"")
        if self.match_type.lower() == "exact":
            return f"[{clean}]"
        elif self.match_type.lower() == "phrase":
            return f'"{clean}"'
        return clean


@dataclass
class RSAAd:
    headlines: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    final_url: str = ""

    def validate(self) -> list[str]:
        errors = []
        for i, h in enumerate(self.headlines):
            if len(h) > MAX_HEADLINE_LENGTH:
                errors.append(f"Headline {i+1} exceeds {MAX_HEADLINE_LENGTH} chars: '{h}' ({len(h)})")
        for i, d in enumerate(self.descriptions):
            if len(d) > MAX_DESCRIPTION_LENGTH:
                errors.append(f"Description {i+1} exceeds {MAX_DESCRIPTION_LENGTH} chars: '{d}' ({len(d)})")
        if not self.final_url.startswith("http"):
            errors.append(f"Invalid final URL: '{self.final_url}'")
        return errors


@dataclass
class AdGroup:
    name: str
    keywords: list[KeywordTarget] = field(default_factory=list)
    ads: list[RSAAd] = field(default_factory=list)
    negatives: list[NegativeKeyword] = field(default_factory=list)


@dataclass
class Campaign:
    name: str
    client_id: str
    daily_budget: float = 50.0
    ad_groups: list[AdGroup] = field(default_factory=list)
    campaign_negatives: list[NegativeKeyword] = field(default_factory=list)

    def total_keywords(self) -> int:
        return sum(len(ag.keywords) for ag in self.ad_groups)

    def total_ads(self) -> int:
        return sum(len(ag.ads) for ag in self.ad_groups)

    def total_negatives(self) -> int:
        return len(self.campaign_negatives) + sum(len(ag.negatives) for ag in self.ad_groups)


def sanitize_theme_name(text: str) -> str:
    """Convert keyword or intent into clean title-cased ad group name."""
    clean = re.sub(r"[^\w\s-]", "", text).strip()
    words = clean.split()
    return " ".join(w.capitalize() for w in words[:4]) or "General"


def deduplicate_preserve_order(items: list[str]) -> list[str]:
    """Deduplicate strings preserving case and original order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = item.strip()
        norm = clean.lower()
        if norm and norm not in seen:
            seen.add(norm)
            result.append(clean)
    return result


def truncate_to_word_boundary(text: str, max_length: int, ensure_punctuation: bool = False) -> str:
    """Truncate text to max_length without slicing words in half.
    
    If ensure_punctuation is True (for descriptions), ensures the text terminates
    with appropriate sentence punctuation ('.', '!', or '?').
    """
    clean = str(text or "").strip()
    if not clean:
        return ""
    if len(clean) <= max_length:
        if ensure_punctuation and not clean.endswith((".", "!", "?")):
            if len(clean) + 1 <= max_length:
                return clean + "."
        return clean

    # Sliced candidate
    sliced = clean[:max_length].rstrip()

    # Check if the split happened on whitespace or punctuation boundary
    if len(clean) > max_length and clean[max_length] in (" ", "\t", "\n", ".", ",", ";", ":", "!", "?"):
        result = sliced.rstrip(" ,;:-")
    elif " " in sliced:
        truncated = sliced.rsplit(" ", 1)[0].rstrip(" ,;:-")
        # Remove trailing dangling short prepositions / conjunctions (PL & EN)
        dangling = (
            "i", "a", "o", "u", "w", "z", "ze", "do", "na", "po", "od", "za",
            "and", "or", "the", "in", "on", "at", "to", "for", "of", "with", "by",
        )
        words = truncated.split()
        if len(words) > 1 and words[-1].lower() in dangling:
            truncated = truncated.rsplit(" ", 1)[0].rstrip(" ,;:-")
        result = truncated if truncated else sliced
    else:
        result = sliced

    if ensure_punctuation and result:
        result = result.rstrip(" ,;:-")
        if not result.endswith((".", "!", "?")):
            if len(result) + 1 <= max_length:
                result = result + "."
            elif " " in result:
                result = result.rsplit(" ", 1)[0].rstrip(" ,;:-") + "."

    return result


def _contains_forbidden_claim(text: str, forbidden_claims: list[str]) -> bool:
    """Check if text contains any forbidden claim (case-insensitive)."""
    text_lower = text.lower()
    for claim in forbidden_claims:
        if claim.lower() in text_lower:
            return True
    return False


def filter_forbidden_claims(
    headlines: list[str],
    descriptions: list[str],
    forbidden_claims: list[str],
) -> tuple[list[str], list[str]]:
    """Filter out headlines and descriptions containing forbidden claims."""
    all_forbidden = DEFAULT_FORBIDDEN_CLAIMS + [c.lower() for c in forbidden_claims]
    clean_headlines = [h for h in headlines if not _contains_forbidden_claim(h, all_forbidden)]
    clean_descriptions = [d for d in descriptions if not _contains_forbidden_claim(d, all_forbidden)]
    return clean_headlines, clean_descriptions


def build_campaign_from_research(
    client_profile: dict[str, Any],
    keywords: list[dict[str, Any]],
    ad_copies: list[dict[str, Any]] | None = None,
    negatives: list[dict[str, Any]] | None = None,
    *,
    campaign_name: str | None = None,
    daily_budget: float = 50.0,
    verified_for_export: bool = False,
) -> Campaign:
    """Compile research findings into a structured Google Ads Campaign.
    
    Args:
        verified_for_export: If True, campaign is for verified client export.
                           If False, forbidden claims are still filtered but
                           campaign is marked as sample-only.
    """
    client_id = client_profile.get("client_id", "unknown-client")
    display_name = client_profile.get("display_name", client_id)
    landing_url = client_profile.get("landing_url", "https://example.com")
    name = campaign_name or f"{display_name} - Search - {client_profile.get('domain', 'Core')}"
    
    # Get forbidden claims from client profile + defaults
    forbidden_claims = client_profile.get("forbidden_claims", [])

    campaign = Campaign(name=name, client_id=client_id, daily_budget=daily_budget)
    campaign.verified_for_export = verified_for_export  # type: ignore[attr-defined]

    # 1. Compile Campaign-level Negatives
    if negatives:
        for neg in negatives:
            kw = str(neg.get("keyword") or neg.get("negative_keyword") or "").strip()
            if not kw:
                continue
            mt = str(neg.get("match_type") or "Phrase").capitalize()
            if mt not in ("Exact", "Phrase", "Broad"):
                mt = "Phrase"
            campaign.campaign_negatives.append(NegativeKeyword(text=kw, match_type=mt, level="Campaign"))

    # 2. Group Positive Keywords into Single-Theme Ad Groups (STAGs)
    theme_groups: dict[str, list[dict[str, Any]]] = {}
    for item in keywords:
        kw = str(item.get("keyword") or "").strip()
        if not kw:
            continue
        theme = str(item.get("theme") or item.get("intent") or sanitize_theme_name(kw))
        theme_groups.setdefault(theme, []).append(item)

    # 3. Compile Ad Copies for reuse across Ad Groups (targeting Excellent Ad Strength: 15 headlines, 4 descriptions)
    # Neutral, profile-grounded defaults derived directly from client profile without fabricating factual claims
    lang = (client_profile.get("language") or ["en"])[0].lower() if client_profile.get("language") else "en"

    if lang == "pl":
        h13 = (
            f"{display_name} Online"
            if len(f"{display_name} Online") <= MAX_HEADLINE_LENGTH
            else "Sprawdz Oferte Online"
        )
        default_headlines = [
            truncate_to_word_boundary(f"{display_name}", MAX_HEADLINE_LENGTH),
            "Oficjalna Strona",
            "Poznaj Nasza Oferte",
            "Skontaktuj Sie Z Nami",
            "Sprawdz Nasz Katalog",
            "Wysoka Jakosc Produktow",
            "Oferta Online",
            "Dowiedz Sie Wiecej",
            "Szeroki Wybor",
            "Zamow Online",
            "Oryginalne Produkty",
            "Sprawdz Szczegoly",
            truncate_to_word_boundary(h13, MAX_HEADLINE_LENGTH),
            "Kontakt I Informacje",
            "Zobacz Nowosci",
        ]
        default_descriptions = [
            truncate_to_word_boundary(
                f"Poznaj oferte {display_name}. Sprawdz szczegoly na naszej oficjalnej stronie.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
            truncate_to_word_boundary(
                f"Skontaktuj sie z {display_name}. Zapewniamy bogaty wybor i fachowe doradztwo.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
            truncate_to_word_boundary(
                "Szukasz sprawdzonych rozwiazan? Dowiedz sie wiecej o ofercie dopasowanej do potrzeb.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
            truncate_to_word_boundary(
                f"Odwiedz strone {display_name} i sprawdz nasz aktualny katalog produktow.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
        ]
    else:
        h14 = (
            f"{display_name} Online"
            if len(f"{display_name} Online") <= MAX_HEADLINE_LENGTH
            else "Shop Online Today"
        )
        default_headlines = [
            truncate_to_word_boundary(f"{display_name}", MAX_HEADLINE_LENGTH),
            "Official Website",
            "Explore Our Offerings",
            "Learn More Today",
            "Contact Our Team",
            "View Products & Services",
            "Dedicated Customer Care",
            "Discover Options Online",
            "Quality & Commitment",
            "Inquire Online",
            "Connect With Us",
            "Schedule A Consultation",
            "Browse Our Selection",
            truncate_to_word_boundary(h14, MAX_HEADLINE_LENGTH),
            "Find What You Need",
        ]
        default_descriptions = [
            truncate_to_word_boundary(
                f"Discover {display_name}. Explore our full selection on our official website.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
            truncate_to_word_boundary(
                f"Welcome to {display_name}. Connect with our team and browse our offerings today.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
            truncate_to_word_boundary(
                f"Tailored solutions from {display_name}. Learn more and request a consultation.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
            truncate_to_word_boundary(
                f"Visit {display_name} online to explore our catalog, services, and special offers.",
                MAX_DESCRIPTION_LENGTH,
                ensure_punctuation=True,
            ),
        ]

    # Filter forbidden claims from defaults BEFORE use
    default_headlines, default_descriptions = filter_forbidden_claims(
        default_headlines, default_descriptions, forbidden_claims
    )
    default_headlines = deduplicate_preserve_order(default_headlines)
    default_descriptions = deduplicate_preserve_order(default_descriptions)

    custom_rsa = RSAAd(headlines=list(default_headlines), descriptions=list(default_descriptions), final_url=landing_url)
    if ad_copies:
        if verified_for_export:
            custom_rsa.headlines = []
            custom_rsa.descriptions = []
        for copy_entry in ad_copies:
            h_list = copy_entry.get("headlines") or []
            d_list = copy_entry.get("descriptions") or []
            if h_list:
                cleaned_h = [
                    truncate_to_word_boundary(str(h), MAX_HEADLINE_LENGTH)
                    for h in h_list
                    if str(h).strip() and len(str(h).strip()) >= 3
                ]
                cleaned_h = [h for h in cleaned_h if h.lower() not in ("n/a", "none", "null", "-", "--", "``")]
                # Filter custom headlines for forbidden claims
                cleaned_h, _ = filter_forbidden_claims(cleaned_h, [], forbidden_claims)
                cleaned_h = deduplicate_preserve_order(cleaned_h)
                if cleaned_h:
                    if not verified_for_export:
                        # Supplement with defaults to ensure 15 headlines for Excellent Ad Strength in draft mode only
                        for dh in default_headlines:
                            if len(cleaned_h) >= MAX_RSA_HEADLINES:
                                break
                            if dh.lower() not in {ch.lower() for ch in cleaned_h}:
                                cleaned_h.append(dh)
                    custom_rsa.headlines = cleaned_h
                elif verified_for_export:
                    custom_rsa.headlines = []
            if d_list:
                cleaned_d = [
                    truncate_to_word_boundary(str(d), MAX_DESCRIPTION_LENGTH, ensure_punctuation=True)
                    for d in d_list
                    if str(d).strip() and len(str(d).strip()) >= 5
                ]
                cleaned_d = [d for d in cleaned_d if d.lower() not in ("n/a", "none", "null", "-", "--", "``")]
                # Filter custom descriptions for forbidden claims
                _, cleaned_d = filter_forbidden_claims([], cleaned_d, forbidden_claims)
                cleaned_d = deduplicate_preserve_order(cleaned_d)
                if cleaned_d:
                    if not verified_for_export:
                        for dd in default_descriptions:
                            if len(cleaned_d) >= MAX_RSA_DESCRIPTIONS:
                                break
                            if dd.lower() not in {cd.lower() for cd in cleaned_d}:
                                cleaned_d.append(dd)
                    custom_rsa.descriptions = cleaned_d
                elif verified_for_export:
                    custom_rsa.descriptions = []
            url = copy_entry.get("landing_url") or copy_entry.get("final_url")
            if url and str(url).startswith("http"):
                custom_rsa.final_url = str(url)

    # 4. Populate Ad Groups with both Exact and Phrase matches
    for theme, kw_items in theme_groups.items():
        ag_name = sanitize_theme_name(theme)
        ag = AdGroup(name=ag_name)

        for item in kw_items:
            kw_text = str(item.get("keyword") or "").strip()
            if not kw_text or len(kw_text) < 2 or kw_text.lower() in ("n/a", "none", "null", "-", "--", "``"):
                continue
            # Add Exact Match
            ag.keywords.append(KeywordTarget(text=kw_text, match_type="Exact"))
            # Add Phrase Match
            ag.keywords.append(KeywordTarget(text=kw_text, match_type="Phrase"))

        if not ag.keywords:
            continue

        # Attach RSA ad copy only if valid non-empty headlines and descriptions exist
        if custom_rsa.headlines and custom_rsa.descriptions:
            ag.ads.append(custom_rsa)
        campaign.ad_groups.append(ag)

    return campaign


def campaign_to_dict(campaign: Campaign) -> dict[str, Any]:
    """Serialize Campaign dataclass to dictionary."""
    return {
        "campaign_name": campaign.name,
        "client_id": campaign.client_id,
        "daily_budget": campaign.daily_budget,
        "campaign_negatives": [
            {"text": n.text, "match_type": n.match_type, "formatted": n.formatted_text()}
            for n in campaign.campaign_negatives
        ],
        "ad_groups": [
            {
                "name": ag.name,
                "keywords": [
                    {"text": k.text, "match_type": k.match_type, "formatted": k.formatted_text()}
                    for k in ag.keywords
                ],
                "ads": [
                    {
                        "headlines": ad.headlines,
                        "descriptions": ad.descriptions,
                        "final_url": ad.final_url,
                    }
                    for ad in ag.ads
                ],
                "negatives": [
                    {"text": n.text, "match_type": n.match_type, "formatted": n.formatted_text()}
                    for n in ag.negatives
                ],
            }
            for ag in campaign.ad_groups
        ],
        "stats": {
            "total_ad_groups": len(campaign.ad_groups),
            "total_keywords": campaign.total_keywords(),
            "total_ads": campaign.total_ads(),
            "total_negatives": campaign.total_negatives(),
        },
    }


def export_campaign_json(campaign: Campaign, target_path: Path | str) -> Path:
    """Export campaign structure as formatted JSON."""
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = campaign_to_dict(campaign)
    p.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return p


def export_google_ads_editor_csv(campaign: Campaign, target_path: Path | str) -> Path:
    """Export campaign structure in Google Ads Editor bulk CSV format.
    
    If campaign is not verified_for_export, adds SAMPLE_ prefix to campaign name
    and includes a comment row warning about sample status.
    """
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Check if campaign is verified for client export
    is_verified = getattr(campaign, "verified_for_export", False)
    campaign_name = campaign.name
    if not is_verified:
        if not campaign_name.startswith("SAMPLE_") and not campaign_name.startswith("[SAMPLE]") and not campaign_name.startswith("[DRAFT]"):
            campaign_name = f"SAMPLE_{campaign_name}"

    headers = [
        "Campaign",
        "Ad Group",
        "Keyword",
        "Criterion Type",
        "Headline 1",
        "Headline 2",
        "Headline 3",
        "Headline 4",
        "Headline 5",
        "Headline 6",
        "Headline 7",
        "Headline 8",
        "Headline 9",
        "Headline 10",
        "Headline 11",
        "Headline 12",
        "Headline 13",
        "Headline 14",
        "Headline 15",
        "Description 1",
        "Description 2",
        "Description 3",
        "Description 4",
        "Final URL",
        "Status",
    ]

    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Row 1: Authoritative column headers
        writer.writerow(headers)

        # Row 2 (if not verified): Sample disclaimer formatted with exact same column count (25 columns)
        if not is_verified:
            writer.writerow([
                "# SAMPLE CAMPAIGN - NOT VERIFIED FOR CLIENT USE",
            ] + [""] * (len(headers) - 1))

        # 1. Campaign-level negative keywords (always default to Paused)
        for neg in campaign.campaign_negatives:
            writer.writerow([
                campaign_name,
                "",  # Campaign negative has empty Ad Group
                neg.text,
                f"Negative {neg.match_type}",
            ] + [""] * 19 + ["", "Paused"])

        # 2. Ad Groups, Keywords, and RSA Ads (always default to Paused)
        for ag in campaign.ad_groups:
            # Positive keywords
            for kw in ag.keywords:
                writer.writerow([
                    campaign_name,
                    ag.name,
                    kw.text,
                    kw.match_type,
                ] + [""] * 19 + ["", "Paused"])

            # Ad Group level negatives
            for neg in ag.negatives:
                writer.writerow([
                    campaign_name,
                    ag.name,
                    neg.text,
                    f"Negative {neg.match_type}",
                ] + [""] * 19 + ["", "Paused"])

            # RSA Ads
            for ad in ag.ads:
                hl = [(ad.headlines[i] if i < len(ad.headlines) else "") for i in range(15)]
                dl = [(ad.descriptions[i] if i < len(ad.descriptions) else "") for i in range(4)]
                writer.writerow([
                    campaign_name,
                    ag.name,
                    "",  # Ad row has empty keyword
                    "",
                ] + hl + dl + [ad.final_url, "Paused"])

    return p

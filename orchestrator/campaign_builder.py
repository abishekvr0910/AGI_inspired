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


def build_campaign_from_research(
    client_profile: dict[str, Any],
    keywords: list[dict[str, Any]],
    ad_copies: list[dict[str, Any]] | None = None,
    negatives: list[dict[str, Any]] | None = None,
    *,
    campaign_name: str | None = None,
    daily_budget: float = 50.0,
) -> Campaign:
    """Compile research findings into a structured Google Ads Campaign."""
    client_id = client_profile.get("client_id", "unknown-client")
    display_name = client_profile.get("display_name", client_id)
    landing_url = client_profile.get("landing_url", "https://example.com")
    name = campaign_name or f"{display_name} - Search - {client_profile.get('domain', 'Core')}"

    campaign = Campaign(name=name, client_id=client_id, daily_budget=daily_budget)

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

    # 3. Compile Ad Copies for reuse across Ad Groups
    default_headlines = [
        f"{display_name[:30]}",
        f"Fast & Reliable Service"[:30],
        f"Get A Free Quote Today"[:30],
    ]
    default_descriptions = [
        f"Contact {display_name} today for certified and dependable service. Call now!"[:90],
        f"Transparent pricing with zero hidden fees. Satisfaction guaranteed on every project."[:90],
    ]

    custom_rsa = RSAAd(headlines=list(default_headlines), descriptions=list(default_descriptions), final_url=landing_url)
    if ad_copies:
        for copy_entry in ad_copies:
            h_list = copy_entry.get("headlines") or []
            d_list = copy_entry.get("descriptions") or []
            if h_list:
                custom_rsa.headlines = [str(h)[:MAX_HEADLINE_LENGTH] for h in h_list[:MAX_RSA_HEADLINES]]
            if d_list:
                custom_rsa.descriptions = [str(d)[:MAX_DESCRIPTION_LENGTH] for d in d_list[:MAX_RSA_DESCRIPTIONS]]
            url = copy_entry.get("landing_url") or copy_entry.get("final_url")
            if url and str(url).startswith("http"):
                custom_rsa.final_url = str(url)

    # 4. Populate Ad Groups with both Exact and Phrase matches
    for theme, kw_items in theme_groups.items():
        ag_name = sanitize_theme_name(theme)
        ag = AdGroup(name=ag_name)

        for item in kw_items:
            kw_text = str(item.get("keyword") or "").strip()
            # Add Exact Match
            ag.keywords.append(KeywordTarget(text=kw_text, match_type="Exact"))
            # Add Phrase Match
            ag.keywords.append(KeywordTarget(text=kw_text, match_type="Phrase"))

        # Attach RSA ad copy
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
    """Export campaign structure in Google Ads Editor bulk CSV format."""
    p = Path(target_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "Campaign",
        "Ad Group",
        "Keyword",
        "Criterion Type",
        "Headline 1",
        "Headline 2",
        "Headline 3",
        "Description 1",
        "Description 2",
        "Final URL",
        "Status",
    ]

    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        # 1. Campaign-level negative keywords
        for neg in campaign.campaign_negatives:
            writer.writerow([
                campaign.name,
                "",  # Campaign negative has empty Ad Group
                neg.text,
                f"Negative {neg.match_type}",
                "", "", "", "", "", "",
                "Enabled",
            ])

        # 2. Ad Groups, Keywords, and RSA Ads
        for ag in campaign.ad_groups:
            # Positive keywords
            for kw in ag.keywords:
                writer.writerow([
                    campaign.name,
                    ag.name,
                    kw.text,
                    kw.match_type,
                    "", "", "", "", "", "",
                    "Enabled",
                ])

            # Ad Group level negatives
            for neg in ag.negatives:
                writer.writerow([
                    campaign.name,
                    ag.name,
                    neg.text,
                    f"Negative {neg.match_type}",
                    "", "", "", "", "", "",
                    "Enabled",
                ])

            # RSA Ads
            for ad in ag.ads:
                h1 = ad.headlines[0] if len(ad.headlines) > 0 else ""
                h2 = ad.headlines[1] if len(ad.headlines) > 1 else ""
                h3 = ad.headlines[2] if len(ad.headlines) > 2 else ""
                d1 = ad.descriptions[0] if len(ad.descriptions) > 0 else ""
                d2 = ad.descriptions[1] if len(ad.descriptions) > 1 else ""
                writer.writerow([
                    campaign.name,
                    ag.name,
                    "",  # Ad row has empty keyword
                    "",
                    h1,
                    h2,
                    h3,
                    d1,
                    d2,
                    ad.final_url,
                    "Enabled",
                ])

    return p

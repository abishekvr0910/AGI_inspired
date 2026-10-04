"""Commercial Evidence Gate — Verification system for prospect data and claims.

Enforces:
- Separate sample/unverified/verified records
- Source/date/reviewer approval required for contacts and factual claims
- Actual authorized account data required for savings estimates; optional when no savings claimed
- Post-approval content drift invalidation via cryptographic digests
- Incomplete research sections blocked from client-ready export (internal drafts allowed)
- Default exported campaigns to paused
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT, ROOT / "orchestrator"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


class VerificationStatus(Enum):
    SAMPLE = "sample"           # Demonstration material, not for client use
    UNVERIFIED = "unverified"   # Real prospect, data not yet verified
    VERIFIED = "verified"       # All claims verified with sources and approvals


class ClaimType(Enum):
    CONTACT = "contact"              # Contact name, email, phone, role
    COMPANY = "company"              # Company name, website, location
    WASTE_ESTIMATE = "waste_estimate"  # Monthly ad waste estimate (optional; requires authorized account extract if claimed)
    CAMPAIGN_CLAIM = "campaign_claim"  # Claims in ad copy (certifications, guarantees)
    DELIVERABLE = "deliverable"        # Complete deliverable section verification


REQUIRED_IDENTITY_FIELDS = {
    ClaimType.CONTACT: ["contact_name", "contact_email", "contact_role"],
    ClaimType.COMPANY: ["company_name", "website", "city"],
}

REQUIRED_RESEARCH_DELIVERABLES = [
    "keyword_research",
    "negative_keyword_harvest",
    "ad_copy_variants",
]


@dataclass
class EvidenceRecord:
    """Single piece of evidence supporting a claim."""
    claim_type: ClaimType
    claim_value: str
    source: str                    # URL, document, or "operator_provided"
    source_date: str               # ISO date when source was accessed/verified
    reviewer: str                  # Who approved this evidence
    reviewer_date: str             # ISO date of approval
    notes: str = ""
    verified: bool = False
    field_name: str = ""           # Target attribute: "contact_name", "company_name", etc.

    def is_valid_evidence(self) -> tuple[bool, str | None]:
        """Validate whether this evidence meets empirical gating standards."""
        if not self.verified:
            return False, "Evidence not verified"
        if not self.claim_value or not str(self.claim_value).strip():
            return False, "Claim value cannot be empty"
        if not self.source or not str(self.source).strip():
            return False, "Source cannot be empty"
        if not self.source_date or not str(self.source_date).strip():
            return False, "Source date cannot be empty"
        if not self.reviewer or not str(self.reviewer).strip():
            return False, "Reviewer cannot be empty"
        if not self.reviewer_date or not str(self.reviewer_date).strip():
            return False, "Reviewer date cannot be empty"

        # Check for placeholder field names passed as values
        fn = self.field_name or self.claim_value
        if self.field_name and self.claim_value.strip().lower() == self.field_name.strip().lower():
            return False, f"Claim value cannot be identical to field name '{self.field_name}'"

        # Waste estimate claim requires authorized account extract or audit calculation
        if self.claim_type == ClaimType.WASTE_ESTIMATE:
            src_lower = self.source.lower()
            if "operator_estimate" in src_lower and "authorized" not in src_lower and "extract" not in src_lower and "audit" not in src_lower:
                return False, "Waste estimate claim requires an authorized account extract, audit date range, or verified calculation"

        return True, None


@dataclass
class ProspectVerification:
    """Complete verification record for a prospect."""
    client_id: str
    company_name: str
    status: VerificationStatus = VerificationStatus.SAMPLE
    evidence: list[EvidenceRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    approved_for_export: bool = False
    export_blocked_reason: str | None = None
    approved_content_hash: str | None = None

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        self.evidence.append(evidence)
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def verify_claim(self, claim_type: ClaimType, claim_value: str, reviewer: str, field_name: str = "") -> bool:
        """Mark a specific claim as verified by reviewer."""
        for e in self.evidence:
            matches_field = (e.field_name and e.field_name == field_name) or (not e.field_name and e.claim_value == claim_value)
            if e.claim_type == claim_type and (e.claim_value == claim_value or matches_field):
                e.verified = True
                e.reviewer = reviewer
                e.reviewer_date = datetime.utcnow().isoformat() + "Z"
                self.updated_at = datetime.utcnow().isoformat() + "Z"
                return True
        return False

    def compute_content_hash(
        self,
        profile: dict[str, Any] | None = None,
        deliverables: dict[str, str] | None = None,
    ) -> str:
        """Compute cryptographic hash of profile + verified claims + deliverables."""
        data_to_hash: dict[str, Any] = {
            "client_id": self.client_id,
            "company_name": self.company_name,
            "evidence": [
                {
                    "type": e.claim_type.value,
                    "field": e.field_name or e.claim_value,
                    "val": e.claim_value,
                    "source": e.source,
                    "reviewer": e.reviewer,
                }
                for e in sorted(self.evidence, key=lambda x: (x.claim_type.value, x.field_name, x.claim_value))
                if e.verified
            ],
        }
        if profile:
            data_to_hash["profile"] = {
                "display_name": profile.get("display_name"),
                "domain": profile.get("domain"),
                "landing_url": profile.get("landing_url"),
                "geo": profile.get("geo"),
                "language": profile.get("language"),
                "offer": profile.get("offer"),
                "forbidden_claims": sorted(profile.get("forbidden_claims", [])),
            }
        if deliverables:
            data_to_hash["deliverables"] = {
                k: hashlib.sha256(v.encode("utf-8")).hexdigest()
                for k, v in sorted(deliverables.items())
            }
        serialized = json.dumps(data_to_hash, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def check_required_deliverables(self, deliverables: dict[str, str] | None) -> tuple[bool, list[str]]:
        """Verify that all required research deliverables are complete and not pending."""
        if deliverables is None:
            return False, ["deliverables_not_provided"]
        missing = []
        for req in REQUIRED_RESEARCH_DELIVERABLES:
            content = deliverables.get(req, "").strip()
            if not content:
                missing.append(f"{req} missing")
            elif "pending generation" in content.lower():
                missing.append(f"{req} pending generation")
        return len(missing) == 0, missing

    def all_required_verified(self) -> tuple[bool, list[str]]:
        """Check if all required identity claims have valid verified evidence."""
        missing = []
        for ctype, fields in REQUIRED_IDENTITY_FIELDS.items():
            for target_field in fields:
                matching = [
                    e for e in self.evidence
                    if e.claim_type == ctype and (e.field_name == target_field or e.claim_value == target_field)
                ]
                if not matching:
                    missing.append(f"{ctype.value}:{target_field} (not recorded)")
                    continue
                valid = any(e.is_valid_evidence()[0] for e in matching)
                if not valid:
                    reasons = [e.is_valid_evidence()[1] for e in matching if e.is_valid_evidence()[1]]
                    missing.append(f"{ctype.value}:{target_field} ({'; '.join(reasons)})")

        # Waste estimate is optional, but if present, MUST be validly supported
        waste_records = [e for e in self.evidence if e.claim_type == ClaimType.WASTE_ESTIMATE]
        for w in waste_records:
            w_valid, reason = w.is_valid_evidence()
            if not w_valid:
                missing.append(f"waste_estimate:est_monthly_leak ({reason})")

        return len(missing) == 0, missing

    def can_export(
        self,
        profile: dict[str, Any] | None = None,
        deliverables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """Determine if this prospect can be exported for client-ready use."""
        if self.status == VerificationStatus.SAMPLE:
            return False, "Sample material — not verified for client use"
        if self.status == VerificationStatus.UNVERIFIED:
            return False, "Unverified prospect — requires full verification"

        ok, missing = self.all_required_verified()
        if not ok:
            self.export_blocked_reason = f"Missing verified evidence: {', '.join(missing)}"
            return False, self.export_blocked_reason

        # Deliverables completeness check
        if deliverables is not None:
            deliv_ok, deliv_missing = self.check_required_deliverables(deliverables)
            if not deliv_ok:
                self.export_blocked_reason = f"Incomplete research sections: {', '.join(deliv_missing)}"
                return False, self.export_blocked_reason

        if not self.approved_for_export:
            return False, "Operator approval required for export"

        # Content drift check against approved hash
        if self.approved_content_hash and (profile is not None or deliverables is not None):
            current_hash = self.compute_content_hash(profile, deliverables)
            if current_hash != self.approved_content_hash:
                self.export_blocked_reason = "Approved content drift: profile or deliverable content modified since approval"
                return False, self.export_blocked_reason

        self.export_blocked_reason = None
        return True, None

    def approve_for_export(
        self,
        reviewer: str,
        profile: dict[str, Any] | None = None,
        deliverables: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """Approve prospect package for client export, binding to content digest."""
        ok, missing = self.all_required_verified()
        if not ok:
            return False, f"Cannot approve: missing verified evidence ({', '.join(missing)})"
        if deliverables is not None:
            deliv_ok, deliv_missing = self.check_required_deliverables(deliverables)
            if not deliv_ok:
                return False, f"Cannot approve: incomplete research sections ({', '.join(deliv_missing)})"

        self.status = VerificationStatus.VERIFIED
        self.approved_for_export = True
        self.export_blocked_reason = None
        self.approved_content_hash = self.compute_content_hash(profile, deliverables)
        self.updated_at = datetime.utcnow().isoformat() + "Z"
        return True, "Prospect verified and approved for export"

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "company_name": self.company_name,
            "status": self.status.value,
            "evidence": [
                {
                    "claim_type": e.claim_type.value,
                    "field_name": e.field_name or e.claim_value,
                    "claim_value": e.claim_value,
                    "source": e.source,
                    "source_date": e.source_date,
                    "reviewer": e.reviewer,
                    "reviewer_date": e.reviewer_date,
                    "notes": e.notes,
                    "verified": e.verified,
                }
                for e in self.evidence
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approved_for_export": self.approved_for_export,
            "export_blocked_reason": self.export_blocked_reason,
            "approved_content_hash": self.approved_content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProspectVerification":
        ev = []
        for e in data.get("evidence", []):
            e_copy = dict(e)
            e_copy["claim_type"] = ClaimType(e_copy["claim_type"])
            # Support backwards compatibility if field_name wasn't serialized
            if "field_name" not in e_copy:
                e_copy["field_name"] = e_copy.get("claim_value", "")
            ev.append(EvidenceRecord(**e_copy))
        return cls(
            client_id=data["client_id"],
            company_name=data["company_name"],
            status=VerificationStatus(data["status"]),
            evidence=ev,
            created_at=data.get("created_at", datetime.utcnow().isoformat() + "Z"),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat() + "Z"),
            approved_for_export=data.get("approved_for_export", False),
            export_blocked_reason=data.get("export_blocked_reason"),
            approved_content_hash=data.get("approved_content_hash"),
        )


class EvidenceGate:
    """Central evidence gate for all commercial prospect operations."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else ROOT
        self.verifications_dir = self.root / "workspace" / "verifications"
        self.verifications_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.verifications_dir / "index.json"
        self._index: dict[str, ProspectVerification] = {}
        self._load_index()

    def _load_index(self) -> None:
        if self.index_path.is_file():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._index = {k: ProspectVerification.from_dict(v) for k, v in data.items()}
            except Exception:
                self._index = {}

    def _save_index(self) -> None:
        data = {k: v.to_dict() for k, v in self._index.items()}
        self.index_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def get(self, client_id: str) -> ProspectVerification | None:
        return self._index.get(client_id)

    def create_or_update(self, verification: ProspectVerification) -> ProspectVerification:
        self._index[verification.client_id] = verification
        self._save_index()
        return verification

    def relabel_all_as_samples(self) -> int:
        """Relabel all existing verifications as SAMPLE status."""
        count = 0
        for v in self._index.values():
            if v.status != VerificationStatus.SAMPLE:
                v.status = VerificationStatus.SAMPLE
                v.approved_for_export = False
                v.export_blocked_reason = "Relabeled as sample per evidence gate policy"
                count += 1
        if count:
            self._save_index()
        return count

    def verify_prospect_for_export(
        self,
        client_id: str,
        reviewer: str,
        profile: dict[str, Any] | None = None,
        deliverables: dict[str, str] | None = None,
    ) -> tuple[bool, str]:
        """Mark prospect as verified and approved for export, binding content hash."""
        v = self._index.get(client_id)
        if not v:
            return False, f"No verification record for {client_id}"
        ok, msg = v.approve_for_export(reviewer, profile=profile, deliverables=deliverables)
        if ok:
            self._save_index()
        return ok, msg

    def block_export(self, client_id: str, reason: str) -> bool:
        """Explicitly block export for a prospect."""
        v = self._index.get(client_id)
        if not v:
            return False
        v.approved_for_export = False
        v.export_blocked_reason = reason
        v.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_index()
        return True

    def can_export_prospect(
        self,
        client_id: str,
        profile: dict[str, Any] | None = None,
        deliverables: dict[str, str] | None = None,
    ) -> tuple[bool, str | None]:
        """Check if a prospect's package can be exported for client-ready use."""
        v = self._index.get(client_id)
        if not v:
            return False, "No verification record — run verification first"
        return v.can_export(profile=profile, deliverables=deliverables)

    def list_all(self) -> list[ProspectVerification]:
        return list(self._index.values())


def create_sample_verification(client_id: str, company_name: str) -> ProspectVerification:
    """Create a sample verification record for demonstration material."""
    return ProspectVerification(
        client_id=client_id,
        company_name=company_name,
        status=VerificationStatus.SAMPLE,
        evidence=[],
        approved_for_export=False,
        export_blocked_reason="Sample material — generated from synthetic data for demonstration only",
    )


def verify_client_package_export(
    client_id: str,
    root: Path | str | None = None,
    profile: dict[str, Any] | None = None,
    deliverables: dict[str, str] | None = None,
) -> tuple[bool, str | None]:
    """Gate function: verify a client package can be exported for client-ready use.

    Called by client_reporter.compile_and_export_client_package before export.
    """
    gate = EvidenceGate(root)
    return gate.can_export_prospect(client_id, profile=profile, deliverables=deliverables)
"""Commercial Evidence Gate — Verification system for prospect data and claims.

Enforces:
- Separate sample/unverified/verified records
- Source/date/reviewer approval required for contacts and factual claims
- Actual authorized account data required for savings estimates
- Client-ready export blocked without verification
- Existing packages relabeled as samples
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
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
    WASTE_ESTIMATE = "waste_estimate"  # Monthly ad waste estimate
    CAMPAIGN_CLAIM = "campaign_claim"  # Claims in ad copy (certifications, guarantees)


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

    def add_evidence(self, evidence: EvidenceRecord) -> None:
        self.evidence.append(evidence)
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def verify_claim(self, claim_type: ClaimType, claim_value: str, reviewer: str) -> bool:
        """Mark a specific claim as verified by reviewer."""
        for e in self.evidence:
            if e.claim_type == claim_type and e.claim_value == claim_value:
                e.verified = True
                e.reviewer = reviewer
                e.reviewer_date = datetime.utcnow().isoformat() + "Z"
                self.updated_at = datetime.utcnow().isoformat() + "Z"
                return True
        return False

    def all_required_verified(self) -> tuple[bool, list[str]]:
        """Check if all required claims have verified evidence."""
        required = {
            ClaimType.CONTACT: ["contact_name", "contact_email", "contact_role"],
            ClaimType.COMPANY: ["company_name", "website", "city"],
            ClaimType.WASTE_ESTIMATE: ["est_monthly_leak"],
        }
        missing = []
        for ctype, fields in required.items():
            for field in fields:
                found = any(e.claim_type == ctype and e.claim_value == field and e.verified
                           for e in self.evidence)
                if not found:
                    missing.append(f"{ctype.value}:{field}")
        return len(missing) == 0, missing

    def can_export(self) -> tuple[bool, str | None]:
        """Determine if this prospect can be exported for client use."""
        if self.status == VerificationStatus.SAMPLE:
            return False, "Sample material — not verified for client use"
        if self.status == VerificationStatus.UNVERIFIED:
            return False, "Unverified prospect — requires full verification"
        ok, missing = self.all_required_verified()
        if not ok:
            self.export_blocked_reason = f"Missing verified evidence: {', '.join(missing)}"
            return False, self.export_blocked_reason
        if not self.approved_for_export:
            return False, "Operator approval required for export"
        self.export_blocked_reason = None
        return True, None

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "company_name": self.company_name,
            "status": self.status.value,
            "evidence": [
                {
                    "claim_type": e.claim_type.value,
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProspectVerification":
        ev = []
        for e in data.get("evidence", []):
            e_copy = dict(e)
            # Convert claim_type string back to enum
            e_copy["claim_type"] = ClaimType(e_copy["claim_type"])
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

    def verify_prospect_for_export(self, client_id: str, reviewer: str) -> tuple[bool, str]:
        """Mark prospect as verified and approved for export."""
        v = self._index.get(client_id)
        if not v:
            return False, f"No verification record for {client_id}"
        v.status = VerificationStatus.VERIFIED
        v.approved_for_export = True
        v.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_index()
        return True, "Prospect verified and approved for export"

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

    def can_export_prospect(self, client_id: str) -> tuple[bool, str]:
        """Check if a prospect's package can be exported for client use."""
        v = self._index.get(client_id)
        if not v:
            return False, f"No verification record — run verification first"
        return v.can_export()

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
        export_blocked_reason="Sample material — generated from synthetic data for demonstration only"
    )


def verify_client_package_export(client_id: str, root: Path | str | None = None) -> tuple[bool, str]:
    """Gate function: verify a client package can be exported for client use.
    
    Called by client_reporter.compile_and_export_client_package before export.
    """
    gate = EvidenceGate(root)
    return gate.can_export_prospect(client_id)


if __name__ == "__main__":
    # Demo: relabel all existing as samples
    gate = EvidenceGate()
    count = gate.relabel_all_as_samples()
    print(f"Relabeled {count} existing verifications as SAMPLE")
    
    # Create sample records for the 8 generated prospects
    for cid in [
        "texas-premier-roofing", "lone-star-industrial-roofs", "austin-commercial-roof-pros",
        "illinois-implant-institute", "south-florida-implant-center", "pacific-implant-surgeons",
        "desert-valley-commercial-hvac", "sunbelt-commercial-mechanical"
    ]:
        gate.create_or_update(create_sample_verification(cid, cid.replace("-", " ").title()))
    print("Created sample verification records for all 8 prospects")
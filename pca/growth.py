from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class GrowthStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    REQUIRES_REVIEW = "requires_review"


class GrowthKind(str, Enum):
    MEMORY = "memory"
    COMMITMENT = "commitment"
    SKILL = "skill"
    PREFERENCE = "preference"
    POLICY = "policy"
    IDENTITY = "identity"


class IdentityImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IDENTITY_DEFINING = "identity_defining"


@dataclass(frozen=True)
class GrowthRecord:
    growth_id: str
    identity_id: str
    kind: GrowthKind
    status: GrowthStatus
    identity_impact: IdentityImpact
    summary_sha256: str
    summary_length: int
    evidence_refs: list[str] = field(default_factory=list)
    source_event_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    reason: str = ""
    supersedes_growth_id: str | None = None

    @classmethod
    def propose(
        cls,
        identity_id: str,
        kind: str | GrowthKind,
        summary: str,
        identity_impact: str | IdentityImpact = IdentityImpact.LOW,
        evidence_refs: list[str] | None = None,
        source_event_ids: list[str] | None = None,
        reason: str = "",
    ) -> "GrowthRecord":
        impact = _parse_impact(identity_impact)
        status = (
            GrowthStatus.REQUIRES_REVIEW
            if impact in {IdentityImpact.HIGH, IdentityImpact.IDENTITY_DEFINING}
            else GrowthStatus.PROPOSED
        )
        return cls(
            growth_id=f"growth_{uuid.uuid4()}",
            identity_id=identity_id,
            kind=_parse_kind(kind),
            status=status,
            identity_impact=impact,
            summary_sha256=_text_hash(summary),
            summary_length=len(summary),
            evidence_refs=evidence_refs or [],
            source_event_ids=source_event_ids or [],
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthRecord":
        return cls(
            growth_id=str(data["growth_id"]),
            identity_id=str(data["identity_id"]),
            kind=_parse_kind(data["kind"]),
            status=GrowthStatus(str(data["status"])),
            identity_impact=_parse_impact(data["identity_impact"]),
            summary_sha256=str(data["summary_sha256"]),
            summary_length=int(data["summary_length"]),
            evidence_refs=[str(item) for item in data.get("evidence_refs", [])],
            source_event_ids=[str(item) for item in data.get("source_event_ids", [])],
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
            reason=str(data.get("reason", "")),
            supersedes_growth_id=data.get("supersedes_growth_id"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "growth_id": self.growth_id,
            "identity_id": self.identity_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "identity_impact": self.identity_impact.value,
            "summary_sha256": self.summary_sha256,
            "summary_length": self.summary_length,
            "evidence_refs": self.evidence_refs,
            "source_event_ids": self.source_event_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
            "supersedes_growth_id": self.supersedes_growth_id,
        }

    def with_status(
        self,
        status: GrowthStatus,
        reason: str = "",
        supersedes_growth_id: str | None = None,
    ) -> "GrowthRecord":
        return GrowthRecord(
            growth_id=self.growth_id,
            identity_id=self.identity_id,
            kind=self.kind,
            status=status,
            identity_impact=self.identity_impact,
            summary_sha256=self.summary_sha256,
            summary_length=self.summary_length,
            evidence_refs=self.evidence_refs,
            source_event_ids=self.source_event_ids,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            reason=reason or self.reason,
            supersedes_growth_id=supersedes_growth_id or self.supersedes_growth_id,
        )


def propose_growth(
    ledger: ContinuityLedger,
    identity_id: str,
    kind: str | GrowthKind,
    summary: str,
    identity_impact: str | IdentityImpact = IdentityImpact.LOW,
    evidence_refs: list[str] | None = None,
    source_event_ids: list[str] | None = None,
    reason: str = "",
) -> GrowthRecord:
    record = GrowthRecord.propose(
        identity_id=identity_id,
        kind=kind,
        summary=summary,
        identity_impact=identity_impact,
        evidence_refs=evidence_refs,
        source_event_ids=source_event_ids,
        reason=reason,
    )
    ledger.append("lucien.growth_proposed", identity_id, record.to_dict())
    return record


def accept_growth(
    ledger: ContinuityLedger,
    identity_id: str,
    growth_id: str,
    reason: str = "",
) -> GrowthRecord:
    record = _require_growth_record(ledger.events(), growth_id)
    accepted = record.with_status(GrowthStatus.ACCEPTED, reason=reason)
    ledger.append("lucien.growth_updated", identity_id, accepted.to_dict())
    return accepted


def reject_growth(
    ledger: ContinuityLedger,
    identity_id: str,
    growth_id: str,
    reason: str = "",
) -> GrowthRecord:
    record = _require_growth_record(ledger.events(), growth_id)
    rejected = record.with_status(GrowthStatus.REJECTED, reason=reason)
    ledger.append("lucien.growth_updated", identity_id, rejected.to_dict())
    return rejected


def growth_records_from_events(events: list[ContinuityEvent]) -> list[GrowthRecord]:
    records: dict[str, GrowthRecord] = {}
    for event in events:
        if event.event_type in {"lucien.growth_proposed", "lucien.growth_updated"}:
            record = GrowthRecord.from_dict(event.payload)
            records[record.growth_id] = record
    return list(records.values())


def active_growth_records(events: list[ContinuityEvent]) -> list[GrowthRecord]:
    return [
        record
        for record in growth_records_from_events(events)
        if record.status in {GrowthStatus.PROPOSED, GrowthStatus.REQUIRES_REVIEW}
    ]


def _require_growth_record(
    events: list[ContinuityEvent],
    growth_id: str,
) -> GrowthRecord:
    for record in growth_records_from_events(events):
        if record.growth_id == growth_id:
            return record
    raise ValueError(f"Growth record not found: {growth_id}")


def _parse_kind(value: str | GrowthKind) -> GrowthKind:
    if isinstance(value, GrowthKind):
        return value
    return GrowthKind(str(value))


def _parse_impact(value: str | IdentityImpact) -> IdentityImpact:
    if isinstance(value, IdentityImpact):
        return value
    return IdentityImpact(str(value))

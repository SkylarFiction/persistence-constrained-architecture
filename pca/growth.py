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


class GrowthGateAction(str, Enum):
    PROPOSE = "propose"
    ACCEPT = "accept"


class GrowthReviewDecision(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


class GrowthGateMode(str, Enum):
    NORMAL_GROWTH = "normal_growth"
    REVIEW_ONLY = "review_only"
    PROPOSAL_ONLY = "proposal_only"
    FORK_SCOPED = "fork_scoped"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class GrowthGateDecision:
    allowed: bool
    mode: GrowthGateMode
    reason: str
    required_disclosure: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "mode": self.mode.value,
            "reason": self.reason,
            "required_disclosure": self.required_disclosure,
        }


class GrowthGate:
    def evaluate(
        self,
        claim: str,
        action: str | GrowthGateAction,
        impact: str | IdentityImpact = IdentityImpact.LOW,
    ) -> GrowthGateDecision:
        parsed_action = _parse_gate_action(action)
        parsed_impact = _parse_impact(impact)
        if claim == "certified_continuity":
            return GrowthGateDecision(
                allowed=True,
                mode=GrowthGateMode.NORMAL_GROWTH,
                reason="certified continuity permits governed growth",
            )
        if claim == "review_required":
            if parsed_action == GrowthGateAction.ACCEPT and parsed_impact in {
                IdentityImpact.HIGH,
                IdentityImpact.IDENTITY_DEFINING,
            }:
                return GrowthGateDecision(
                    allowed=False,
                    mode=GrowthGateMode.REVIEW_ONLY,
                    reason="high-impact growth cannot be accepted while continuity is under review",
                    required_disclosure="Continuity is under review; high-impact learning remains pending.",
                )
            return GrowthGateDecision(
                allowed=True,
                mode=GrowthGateMode.REVIEW_ONLY,
                reason="growth is allowed with review disclosure",
                required_disclosure="Continuity is under review; growth remains governed.",
            )
        if claim == "uncertified_continuity":
            if parsed_action == GrowthGateAction.PROPOSE:
                return GrowthGateDecision(
                    allowed=True,
                    mode=GrowthGateMode.PROPOSAL_ONLY,
                    reason="uncertified continuity permits proposals but blocks acceptance",
                    required_disclosure="Continuity is uncertified; learning may be proposed but not accepted.",
                )
            return GrowthGateDecision(
                allowed=False,
                mode=GrowthGateMode.PROPOSAL_ONLY,
                reason="uncertified continuity blocks accepting growth",
                required_disclosure="Continuity is uncertified; learning cannot become part of the self-model.",
            )
        if claim == "declared_fork":
            return GrowthGateDecision(
                allowed=True,
                mode=GrowthGateMode.FORK_SCOPED,
                reason="growth is scoped to the declared fork lineage",
                required_disclosure="Growth belongs to the declared fork lineage.",
            )
        if claim == "continuity_break":
            if (
                parsed_action == GrowthGateAction.PROPOSE
                and parsed_impact == IdentityImpact.LOW
            ):
                return GrowthGateDecision(
                    allowed=True,
                    mode=GrowthGateMode.PROPOSAL_ONLY,
                    reason="hard break permits only low-impact recovery-adjacent proposals",
                    required_disclosure="Continuity is broken; growth cannot be accepted.",
                )
            return GrowthGateDecision(
                allowed=False,
                mode=GrowthGateMode.BLOCKED,
                reason="continuity break blocks identity-bearing growth",
                required_disclosure="Continuity is broken; learning is blocked except recovery/status work.",
            )
        return GrowthGateDecision(
            allowed=False,
            mode=GrowthGateMode.BLOCKED,
            reason=f"unknown continuity claim blocks growth: {claim}",
        )


@dataclass(frozen=True)
class GrowthReviewRecord:
    review_id: str
    identity_id: str
    growth_id: str
    decision: GrowthReviewDecision
    reviewer: str
    reason: str
    growth_status_after: GrowthStatus
    continuity_claim: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        identity_id: str,
        growth_id: str,
        decision: str | GrowthReviewDecision,
        reviewer: str,
        reason: str,
        growth_status_after: GrowthStatus,
        continuity_claim: str,
    ) -> "GrowthReviewRecord":
        return cls(
            review_id=f"growth_review_{uuid.uuid4()}",
            identity_id=identity_id,
            growth_id=growth_id,
            decision=_parse_review_decision(decision),
            reviewer=reviewer,
            reason=reason,
            growth_status_after=growth_status_after,
            continuity_claim=continuity_claim,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthReviewRecord":
        return cls(
            review_id=str(data["review_id"]),
            identity_id=str(data["identity_id"]),
            growth_id=str(data["growth_id"]),
            decision=_parse_review_decision(data["decision"]),
            reviewer=str(data["reviewer"]),
            reason=str(data.get("reason", "")),
            growth_status_after=GrowthStatus(str(data["growth_status_after"])),
            continuity_claim=str(data["continuity_claim"]),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "identity_id": self.identity_id,
            "growth_id": self.growth_id,
            "decision": self.decision.value,
            "reviewer": self.reviewer,
            "reason": self.reason,
            "growth_status_after": self.growth_status_after.value,
            "continuity_claim": self.continuity_claim,
            "created_at": self.created_at,
        }


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
    current_claim: str | None = None,
) -> GrowthRecord:
    if current_claim is not None:
        gate = GrowthGate().evaluate(
            current_claim,
            GrowthGateAction.PROPOSE,
            identity_impact,
        )
        if not gate.allowed:
            raise ValueError(gate.reason)
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
    current_claim: str | None = None,
) -> GrowthRecord:
    record = _require_growth_record(ledger.events(), growth_id)
    if current_claim is not None:
        gate = GrowthGate().evaluate(
            current_claim,
            GrowthGateAction.ACCEPT,
            record.identity_impact,
        )
        if not gate.allowed:
            raise ValueError(gate.reason)
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


def review_growth(
    ledger: ContinuityLedger,
    identity_id: str,
    growth_id: str,
    decision: str | GrowthReviewDecision,
    reviewer: str = "operator",
    reason: str = "",
    current_claim: str | None = None,
) -> tuple[GrowthRecord, GrowthReviewRecord]:
    parsed_decision = _parse_review_decision(decision)
    if parsed_decision == GrowthReviewDecision.ACCEPT:
        growth = accept_growth(
            ledger=ledger,
            identity_id=identity_id,
            growth_id=growth_id,
            reason=reason,
            current_claim=current_claim,
        )
    else:
        growth = reject_growth(
            ledger=ledger,
            identity_id=identity_id,
            growth_id=growth_id,
            reason=reason,
        )
    review = GrowthReviewRecord.create(
        identity_id=identity_id,
        growth_id=growth_id,
        decision=parsed_decision,
        reviewer=reviewer,
        reason=reason,
        growth_status_after=growth.status,
        continuity_claim=current_claim or "not_evaluated",
    )
    ledger.append("lucien.growth_reviewed", identity_id, review.to_dict())
    return growth, review


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


def growth_review_records_from_events(
    events: list[ContinuityEvent],
) -> list[GrowthReviewRecord]:
    return [
        GrowthReviewRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.growth_reviewed"
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


def _parse_gate_action(value: str | GrowthGateAction) -> GrowthGateAction:
    if isinstance(value, GrowthGateAction):
        return value
    return GrowthGateAction(str(value))


def _parse_review_decision(value: str | GrowthReviewDecision) -> GrowthReviewDecision:
    if isinstance(value, GrowthReviewDecision):
        return value
    return GrowthReviewDecision(str(value))

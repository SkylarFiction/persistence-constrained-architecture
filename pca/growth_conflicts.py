from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


class GrowthConflictDecision(str, Enum):
    ACCEPT_NEW = "accept_new"
    KEEP_EXISTING = "keep_existing"
    FORK = "fork"


@dataclass(frozen=True)
class GrowthConflictRecord:
    conflict_id: str
    identity_id: str
    proposed_growth_id: str
    conflicting_growth_ids: list[str]
    conflict_type: str
    severity: str
    reason: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        identity_id: str,
        proposed_growth_id: str,
        conflicting_growth_ids: list[str],
        conflict_type: str,
        severity: str,
        reason: str,
    ) -> "GrowthConflictRecord":
        return cls(
            conflict_id=f"growth_conflict_{uuid.uuid4()}",
            identity_id=identity_id,
            proposed_growth_id=proposed_growth_id,
            conflicting_growth_ids=conflicting_growth_ids,
            conflict_type=conflict_type,
            severity=severity,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthConflictRecord":
        return cls(
            conflict_id=str(data["conflict_id"]),
            identity_id=str(data["identity_id"]),
            proposed_growth_id=str(data["proposed_growth_id"]),
            conflicting_growth_ids=[
                str(item) for item in data.get("conflicting_growth_ids", [])
            ],
            conflict_type=str(data["conflict_type"]),
            severity=str(data["severity"]),
            reason=str(data.get("reason", "")),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "identity_id": self.identity_id,
            "proposed_growth_id": self.proposed_growth_id,
            "conflicting_growth_ids": self.conflicting_growth_ids,
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class GrowthConflictResolutionRecord:
    resolution_id: str
    identity_id: str
    conflict_id: str
    decision: GrowthConflictDecision
    resolved_by: str
    reason: str
    effect: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        identity_id: str,
        conflict_id: str,
        decision: str | GrowthConflictDecision,
        resolved_by: str,
        reason: str,
    ) -> "GrowthConflictResolutionRecord":
        parsed_decision = _parse_decision(decision)
        return cls(
            resolution_id=f"growth_conflict_resolution_{uuid.uuid4()}",
            identity_id=identity_id,
            conflict_id=conflict_id,
            decision=parsed_decision,
            resolved_by=resolved_by,
            reason=reason,
            effect=_resolution_effect(parsed_decision),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GrowthConflictResolutionRecord":
        return cls(
            resolution_id=str(data["resolution_id"]),
            identity_id=str(data["identity_id"]),
            conflict_id=str(data["conflict_id"]),
            decision=_parse_decision(data["decision"]),
            resolved_by=str(data["resolved_by"]),
            reason=str(data.get("reason", "")),
            effect=str(data.get("effect", "")),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_id": self.resolution_id,
            "identity_id": self.identity_id,
            "conflict_id": self.conflict_id,
            "decision": self.decision.value,
            "resolved_by": self.resolved_by,
            "reason": self.reason,
            "effect": self.effect,
            "created_at": self.created_at,
        }


def record_growth_conflict(
    ledger: ContinuityLedger,
    identity_id: str,
    proposed_growth_id: str,
    conflicting_growth_ids: list[str],
    conflict_type: str,
    severity: str,
    reason: str,
) -> GrowthConflictRecord:
    record = GrowthConflictRecord.create(
        identity_id=identity_id,
        proposed_growth_id=proposed_growth_id,
        conflicting_growth_ids=conflicting_growth_ids,
        conflict_type=conflict_type,
        severity=severity,
        reason=reason,
    )
    ledger.append("lucien.growth_conflict_detected", identity_id, record.to_dict())
    return record


def resolve_growth_conflict(
    ledger: ContinuityLedger,
    identity_id: str,
    conflict_id: str,
    decision: str | GrowthConflictDecision,
    resolved_by: str = "steward",
    reason: str = "",
) -> GrowthConflictResolutionRecord:
    if find_growth_conflict(ledger.events(), conflict_id) is None:
        raise ValueError(f"Growth conflict not found: {conflict_id}")
    if find_growth_conflict_resolution(ledger.events(), conflict_id) is not None:
        raise ValueError(f"Growth conflict already resolved: {conflict_id}")
    record = GrowthConflictResolutionRecord.create(
        identity_id=identity_id,
        conflict_id=conflict_id,
        decision=decision,
        resolved_by=resolved_by,
        reason=reason,
    )
    ledger.append("lucien.growth_conflict_resolved", identity_id, record.to_dict())
    return record


def growth_conflict_records_from_events(
    events: list[ContinuityEvent],
) -> list[GrowthConflictRecord]:
    return [
        GrowthConflictRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.growth_conflict_detected"
    ]


def growth_conflict_resolution_records_from_events(
    events: list[ContinuityEvent],
) -> list[GrowthConflictResolutionRecord]:
    return [
        GrowthConflictResolutionRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.growth_conflict_resolved"
    ]


def find_growth_conflict(
    events: list[ContinuityEvent],
    conflict_id: str,
) -> GrowthConflictRecord | None:
    for record in growth_conflict_records_from_events(events):
        if record.conflict_id == conflict_id:
            return record
    return None


def find_growth_conflict_resolution(
    events: list[ContinuityEvent],
    conflict_id: str,
) -> GrowthConflictResolutionRecord | None:
    for record in growth_conflict_resolution_records_from_events(events):
        if record.conflict_id == conflict_id:
            return record
    return None


def _parse_decision(
    value: str | GrowthConflictDecision,
) -> GrowthConflictDecision:
    if isinstance(value, GrowthConflictDecision):
        return value
    return GrowthConflictDecision(str(value))


def _resolution_effect(decision: GrowthConflictDecision) -> str:
    values = {
        GrowthConflictDecision.ACCEPT_NEW: "permits steward-reviewed acceptance of the proposed growth",
        GrowthConflictDecision.KEEP_EXISTING: "keeps existing accepted growth and blocks the conflicting proposal",
        GrowthConflictDecision.FORK: "requires fork-scoped treatment before conflicting growth can proceed",
    }
    return values[decision]

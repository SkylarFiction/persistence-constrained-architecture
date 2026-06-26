from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


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


def growth_conflict_records_from_events(
    events: list[ContinuityEvent],
) -> list[GrowthConflictRecord]:
    return [
        GrowthConflictRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.growth_conflict_detected"
    ]

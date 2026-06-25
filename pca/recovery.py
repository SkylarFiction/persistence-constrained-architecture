from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent


class RecoveryStatus(str, Enum):
    OPENED = "recovery_opened"
    PLAN_REQUIRED = "recovery_plan_required"
    UNDERWAY = "recovery_underway"
    AUDIT_REQUIRED = "recovery_audit_required"
    REJECTED = "recovery_rejected"
    CERTIFIED = "recovery_certified"


@dataclass(frozen=True)
class RecoveryRecord:
    recovery_id: str
    identity_id: str
    status: RecoveryStatus
    opened_by: str
    reason: str
    source_claim_id: str | None
    required_followups: list[str]
    created_at: str
    completed_at: str | None = None
    evidence: dict[str, str] = field(default_factory=dict)

    @classmethod
    def open(
        cls,
        identity_id: str,
        opened_by: str,
        reason: str,
        source_claim_id: str | None,
        required_followups: list[str] | None = None,
    ) -> "RecoveryRecord":
        return cls(
            recovery_id=f"recovery_{uuid.uuid4()}",
            identity_id=identity_id,
            status=RecoveryStatus.AUDIT_REQUIRED,
            opened_by=opened_by,
            reason=reason,
            source_claim_id=source_claim_id,
            required_followups=required_followups or ["recovery_audit"],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecoveryRecord":
        return cls(
            recovery_id=str(data["recovery_id"]),
            identity_id=str(data["identity_id"]),
            status=RecoveryStatus(str(data["status"])),
            opened_by=str(data["opened_by"]),
            reason=str(data.get("reason", "")),
            source_claim_id=data.get("source_claim_id"),
            required_followups=[
                str(item) for item in data.get("required_followups", [])
            ],
            created_at=str(data["created_at"]),
            completed_at=data.get("completed_at"),
            evidence={
                str(key): str(value)
                for key, value in data.get("evidence", {}).items()
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "identity_id": self.identity_id,
            "status": self.status.value,
            "opened_by": self.opened_by,
            "reason": self.reason,
            "source_claim_id": self.source_claim_id,
            "required_followups": self.required_followups,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "evidence": self.evidence,
        }

    def with_status(
        self,
        status: RecoveryStatus,
        evidence: dict[str, str] | None = None,
    ) -> "RecoveryRecord":
        completed_at = self.completed_at
        if status in {RecoveryStatus.REJECTED, RecoveryStatus.CERTIFIED}:
            completed_at = datetime.now(timezone.utc).isoformat()
        return RecoveryRecord(
            recovery_id=self.recovery_id,
            identity_id=self.identity_id,
            status=status,
            opened_by=self.opened_by,
            reason=self.reason,
            source_claim_id=self.source_claim_id,
            required_followups=self.required_followups,
            created_at=self.created_at,
            completed_at=completed_at,
            evidence=evidence or self.evidence,
        )


def recovery_records_from_events(
    events: list[ContinuityEvent],
) -> list[RecoveryRecord]:
    records: dict[str, RecoveryRecord] = {}
    for event in events:
        if event.event_type in {"recovery_opened", "recovery_updated"}:
            record = RecoveryRecord.from_dict(event.payload)
            records[record.recovery_id] = record
    return list(records.values())


def current_recovery_record(
    events: list[ContinuityEvent],
) -> RecoveryRecord | None:
    records = recovery_records_from_events(events)
    if not records:
        return None
    return records[-1]


def find_recovery(
    events: list[ContinuityEvent],
    recovery_id: str,
) -> RecoveryRecord | None:
    for record in recovery_records_from_events(events):
        if record.recovery_id == recovery_id:
            return record
    return None


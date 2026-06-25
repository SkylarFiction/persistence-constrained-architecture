from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent


class FollowUpStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    FAILED = "failed"
    WAIVED = "waived"


@dataclass(frozen=True)
class FollowUpRecord:
    followup_id: str
    identity_id: str
    source_event_id: str
    followup_type: str
    status: FollowUpStatus
    created_at: str
    due_at: str | None = None
    completed_at: str | None = None
    required_evidence: list[str] = field(default_factory=list)
    provided_evidence: dict[str, str] = field(default_factory=dict)
    failure_effect: str = "keep_uncertified_continuity"
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        source_event_id: str,
        followup_type: str,
        required_evidence: list[str] | None = None,
        failure_effect: str | None = None,
        reason: str = "",
        due_at: str | None = None,
    ) -> "FollowUpRecord":
        return cls(
            followup_id=str(uuid.uuid4()),
            identity_id=identity_id,
            source_event_id=source_event_id,
            followup_type=followup_type,
            status=FollowUpStatus.OPEN,
            created_at=datetime.now(timezone.utc).isoformat(),
            due_at=due_at,
            required_evidence=required_evidence or [],
            failure_effect=failure_effect or default_failure_effect(followup_type),
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FollowUpRecord":
        return cls(
            followup_id=str(data["followup_id"]),
            identity_id=str(data["identity_id"]),
            source_event_id=str(data["source_event_id"]),
            followup_type=str(data["followup_type"]),
            status=FollowUpStatus(str(data.get("status", FollowUpStatus.OPEN.value))),
            created_at=str(data["created_at"]),
            due_at=data.get("due_at"),
            completed_at=data.get("completed_at"),
            required_evidence=[str(item) for item in data.get("required_evidence", [])],
            provided_evidence={
                str(key): str(value)
                for key, value in data.get("provided_evidence", {}).items()
            },
            failure_effect=str(
                data.get("failure_effect", default_failure_effect(data["followup_type"]))
            ),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "followup_id": self.followup_id,
            "identity_id": self.identity_id,
            "source_event_id": self.source_event_id,
            "followup_type": self.followup_type,
            "status": self.status.value,
            "created_at": self.created_at,
            "due_at": self.due_at,
            "completed_at": self.completed_at,
            "required_evidence": self.required_evidence,
            "provided_evidence": self.provided_evidence,
            "failure_effect": self.failure_effect,
            "reason": self.reason,
        }

    def with_status(
        self,
        status: FollowUpStatus,
        provided_evidence: dict[str, str] | None = None,
        reason: str | None = None,
    ) -> "FollowUpRecord":
        completed_at = self.completed_at
        if status in {FollowUpStatus.COMPLETED, FollowUpStatus.FAILED}:
            completed_at = datetime.now(timezone.utc).isoformat()
        return FollowUpRecord(
            followup_id=self.followup_id,
            identity_id=self.identity_id,
            source_event_id=self.source_event_id,
            followup_type=self.followup_type,
            status=status,
            created_at=self.created_at,
            due_at=self.due_at,
            completed_at=completed_at,
            required_evidence=self.required_evidence,
            provided_evidence=provided_evidence or self.provided_evidence,
            failure_effect=self.failure_effect,
            reason=reason if reason is not None else self.reason,
        )


def default_failure_effect(followup_type: str) -> str:
    effects = {
        "post_migration_identity_audit": "keep_uncertified_continuity",
        "post_transform_identity_audit": "keep_uncertified_continuity",
        "lineage_freeze": "freeze_lineage",
        "recovery_authority_review": "require_recovery_authority_review",
        "future_transform_hold": "block_future_transforms",
    }
    return effects.get(followup_type, "keep_uncertified_continuity")


def required_evidence_for(followup_type: str) -> list[str]:
    evidence = {
        "post_migration_identity_audit": ["audit_report"],
        "post_transform_identity_audit": ["audit_report"],
        "memory_compaction_audit": ["audit_report"],
        "lineage_freeze": ["lineage_freeze"],
        "recovery_authority_review": ["review_record"],
        "recovery_audit": ["recovery_audit_report"],
        "future_transform_hold": ["hold_record"],
    }
    return evidence.get(followup_type, [])


def followups_from_events(events: list[ContinuityEvent]) -> list[FollowUpRecord]:
    records: dict[str, FollowUpRecord] = {}
    for event in events:
        if event.event_type == "followup_created":
            record = FollowUpRecord.from_dict(event.payload)
            records[record.followup_id] = _mark_overdue_if_needed(record)
        elif event.event_type == "followup_updated":
            record = FollowUpRecord.from_dict(event.payload)
            records[record.followup_id] = _mark_overdue_if_needed(record)
    return list(records.values())


def active_followups(events: list[ContinuityEvent]) -> list[FollowUpRecord]:
    return [
        record
        for record in followups_from_events(events)
        if record.status
        in {FollowUpStatus.OPEN, FollowUpStatus.OVERDUE, FollowUpStatus.FAILED}
    ]


def find_followup(
    events: list[ContinuityEvent],
    followup_id: str,
) -> FollowUpRecord | None:
    for record in followups_from_events(events):
        if record.followup_id == followup_id:
            return record
    return None


def continuity_claim_from_followups(
    events: list[ContinuityEvent],
    default_claim: str,
) -> tuple[str, list[FollowUpRecord]]:
    blocking = active_followups(events)
    if any(record.status == FollowUpStatus.FAILED for record in blocking):
        return "continuity_break", blocking
    if any(record.status == FollowUpStatus.OVERDUE for record in blocking):
        return "uncertified_continuity", blocking
    if blocking:
        return "uncertified_continuity", blocking
    return default_claim, []


def _mark_overdue_if_needed(record: FollowUpRecord) -> FollowUpRecord:
    if record.status != FollowUpStatus.OPEN or not record.due_at:
        return record
    due_at = datetime.fromisoformat(record.due_at)
    if due_at < datetime.now(timezone.utc):
        return record.with_status(FollowUpStatus.OVERDUE)
    return record

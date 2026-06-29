from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger
from .missions import add_mission_item, require_mission


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MissionStepRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MissionStepApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MissionStepExecutionStatus(str, Enum):
    PROPOSED = "proposed"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class MissionStepRecord:
    step_id: str
    mission_id: str
    identity_id: str
    description_sha256: str
    description_length: int
    risk_level: MissionStepRisk
    required_tool: str
    approval_status: MissionStepApprovalStatus
    execution_status: MissionStepExecutionStatus
    expected_outcome_sha256: str | None = None
    expected_outcome_length: int = 0
    actual_outcome_sha256: str | None = None
    actual_outcome_length: int = 0
    failure_note_sha256: str | None = None
    failure_note_length: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    reason: str = ""

    @classmethod
    def propose(
        cls,
        mission_id: str,
        identity_id: str,
        description: str,
        risk_level: str | MissionStepRisk,
        required_tool: str,
        expected_outcome: str = "",
        reason: str = "",
    ) -> "MissionStepRecord":
        risk = _parse_risk(risk_level)
        approval = (
            MissionStepApprovalStatus.NOT_REQUIRED
            if risk == MissionStepRisk.LOW
            else MissionStepApprovalStatus.PENDING
        )
        execution = (
            MissionStepExecutionStatus.READY
            if risk == MissionStepRisk.LOW
            else MissionStepExecutionStatus.PROPOSED
        )
        return cls(
            step_id=f"mission_step_{uuid.uuid4()}",
            mission_id=mission_id,
            identity_id=identity_id,
            description_sha256=_text_hash(description),
            description_length=len(description),
            risk_level=risk,
            required_tool=required_tool,
            approval_status=approval,
            execution_status=execution,
            expected_outcome_sha256=_text_hash(expected_outcome) if expected_outcome else None,
            expected_outcome_length=len(expected_outcome),
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionStepRecord":
        return cls(
            step_id=str(data["step_id"]),
            mission_id=str(data["mission_id"]),
            identity_id=str(data["identity_id"]),
            description_sha256=str(data["description_sha256"]),
            description_length=int(data["description_length"]),
            risk_level=_parse_risk(data["risk_level"]),
            required_tool=str(data.get("required_tool", "")),
            approval_status=_parse_approval(data["approval_status"]),
            execution_status=_parse_execution(data["execution_status"]),
            expected_outcome_sha256=data.get("expected_outcome_sha256"),
            expected_outcome_length=int(data.get("expected_outcome_length", 0)),
            actual_outcome_sha256=data.get("actual_outcome_sha256"),
            actual_outcome_length=int(data.get("actual_outcome_length", 0)),
            failure_note_sha256=data.get("failure_note_sha256"),
            failure_note_length=int(data.get("failure_note_length", 0)),
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "mission_id": self.mission_id,
            "identity_id": self.identity_id,
            "description_sha256": self.description_sha256,
            "description_length": self.description_length,
            "risk_level": self.risk_level.value,
            "required_tool": self.required_tool,
            "approval_status": self.approval_status.value,
            "execution_status": self.execution_status.value,
            "expected_outcome_sha256": self.expected_outcome_sha256,
            "expected_outcome_length": self.expected_outcome_length,
            "actual_outcome_sha256": self.actual_outcome_sha256,
            "actual_outcome_length": self.actual_outcome_length,
            "failure_note_sha256": self.failure_note_sha256,
            "failure_note_length": self.failure_note_length,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }

    def with_status(
        self,
        approval_status: str | MissionStepApprovalStatus | None = None,
        execution_status: str | MissionStepExecutionStatus | None = None,
        reason: str = "",
        actual_outcome: str = "",
        failure_note: str = "",
    ) -> "MissionStepRecord":
        return MissionStepRecord(
            step_id=self.step_id,
            mission_id=self.mission_id,
            identity_id=self.identity_id,
            description_sha256=self.description_sha256,
            description_length=self.description_length,
            risk_level=self.risk_level,
            required_tool=self.required_tool,
            approval_status=(
                _parse_approval(approval_status)
                if approval_status is not None
                else self.approval_status
            ),
            execution_status=(
                _parse_execution(execution_status)
                if execution_status is not None
                else self.execution_status
            ),
            expected_outcome_sha256=self.expected_outcome_sha256,
            expected_outcome_length=self.expected_outcome_length,
            actual_outcome_sha256=(
                _text_hash(actual_outcome)
                if actual_outcome
                else self.actual_outcome_sha256
            ),
            actual_outcome_length=(
                len(actual_outcome) if actual_outcome else self.actual_outcome_length
            ),
            failure_note_sha256=(
                _text_hash(failure_note) if failure_note else self.failure_note_sha256
            ),
            failure_note_length=(
                len(failure_note) if failure_note else self.failure_note_length
            ),
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            reason=reason or self.reason,
        )


def propose_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    description: str,
    risk_level: str | MissionStepRisk,
    required_tool: str,
    expected_outcome: str = "",
    reason: str = "",
) -> MissionStepRecord:
    require_mission(ledger.events(), mission_id)
    record = MissionStepRecord.propose(
        mission_id=mission_id,
        identity_id=identity_id,
        description=description,
        risk_level=risk_level,
        required_tool=required_tool,
        expected_outcome=expected_outcome,
        reason=reason,
    )
    ledger.append("mission.step_proposed", identity_id, record.to_dict())
    return record


def approve_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    reason: str = "",
) -> MissionStepRecord:
    step = require_mission_step(ledger.events(), step_id)
    if step.execution_status not in {
        MissionStepExecutionStatus.PROPOSED,
        MissionStepExecutionStatus.READY,
        MissionStepExecutionStatus.BLOCKED,
    }:
        raise ValueError(f"Step cannot be approved from {step.execution_status.value}.")
    updated = step.with_status(
        approval_status=MissionStepApprovalStatus.APPROVED,
        execution_status=MissionStepExecutionStatus.READY,
        reason=reason,
    )
    ledger.append("mission.step_approved", identity_id, updated.to_dict())
    return updated


def start_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    reason: str = "",
) -> MissionStepRecord:
    step = require_mission_step(ledger.events(), step_id)
    if step.risk_level in {MissionStepRisk.MEDIUM, MissionStepRisk.HIGH} and (
        step.approval_status != MissionStepApprovalStatus.APPROVED
    ):
        raise ValueError("Medium and high risk mission steps require approval before start.")
    if step.execution_status not in {
        MissionStepExecutionStatus.PROPOSED,
        MissionStepExecutionStatus.READY,
    }:
        raise ValueError(f"Step cannot start from {step.execution_status.value}.")
    updated = step.with_status(
        execution_status=MissionStepExecutionStatus.RUNNING,
        reason=reason,
    )
    ledger.append("mission.step_started", identity_id, updated.to_dict())
    return updated


def complete_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    actual_outcome: str,
    reason: str = "",
) -> MissionStepRecord:
    step = require_mission_step(ledger.events(), step_id)
    if step.execution_status != MissionStepExecutionStatus.RUNNING:
        raise ValueError(f"Step cannot complete from {step.execution_status.value}.")
    updated = step.with_status(
        execution_status=MissionStepExecutionStatus.COMPLETED,
        actual_outcome=actual_outcome,
        reason=reason,
    )
    event = ledger.append("mission.step_completed", identity_id, updated.to_dict())
    add_mission_item(
        ledger,
        identity_id,
        updated.mission_id,
        "outcome",
        actual_outcome,
        status="completed",
        confidence="medium",
        evidence_refs=[event.event_hash],
        reason=f"completed mission step {updated.step_id}",
    )
    return updated


def fail_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    failure_note: str,
    reason: str = "",
) -> MissionStepRecord:
    step = require_mission_step(ledger.events(), step_id)
    if step.execution_status not in {
        MissionStepExecutionStatus.RUNNING,
        MissionStepExecutionStatus.READY,
        MissionStepExecutionStatus.PROPOSED,
    }:
        raise ValueError(f"Step cannot fail from {step.execution_status.value}.")
    updated = step.with_status(
        execution_status=MissionStepExecutionStatus.FAILED,
        failure_note=failure_note,
        reason=reason,
    )
    event = ledger.append("mission.step_failed", identity_id, updated.to_dict())
    add_mission_item(
        ledger,
        identity_id,
        updated.mission_id,
        "outcome",
        failure_note,
        status="failed",
        confidence="medium",
        evidence_refs=[event.event_hash],
        reason=f"failed mission step {updated.step_id}",
    )
    return updated


def block_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    reason: str,
) -> MissionStepRecord:
    step = require_mission_step(ledger.events(), step_id)
    updated = step.with_status(
        execution_status=MissionStepExecutionStatus.BLOCKED,
        failure_note=reason,
        reason=reason,
    )
    event = ledger.append("mission.step_blocked", identity_id, updated.to_dict())
    add_mission_item(
        ledger,
        identity_id,
        updated.mission_id,
        "outcome",
        reason,
        status="blocked",
        confidence="medium",
        evidence_refs=[event.event_hash],
        reason=f"blocked mission step {updated.step_id}",
    )
    return updated


def mission_step_records_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[MissionStepRecord]:
    records: dict[str, MissionStepRecord] = {}
    for event in events:
        if event.event_type in {
            "mission.step_proposed",
            "mission.step_approved",
            "mission.step_started",
            "mission.step_completed",
            "mission.step_failed",
            "mission.step_blocked",
        }:
            record = MissionStepRecord.from_dict(event.payload)
            records[record.step_id] = record
    result = list(records.values())
    if mission_id is None:
        return result
    return [record for record in result if record.mission_id == mission_id]


def require_mission_step(
    events: list[ContinuityEvent],
    step_id: str,
) -> MissionStepRecord:
    for record in mission_step_records_from_events(events):
        if record.step_id == step_id:
            return record
    raise ValueError(f"Mission step not found: {step_id}")


def _parse_risk(value: str | MissionStepRisk) -> MissionStepRisk:
    if isinstance(value, MissionStepRisk):
        return value
    return MissionStepRisk(str(value))


def _parse_approval(
    value: str | MissionStepApprovalStatus,
) -> MissionStepApprovalStatus:
    if isinstance(value, MissionStepApprovalStatus):
        return value
    return MissionStepApprovalStatus(str(value))


def _parse_execution(
    value: str | MissionStepExecutionStatus,
) -> MissionStepExecutionStatus:
    if isinstance(value, MissionStepExecutionStatus):
        return value
    return MissionStepExecutionStatus(str(value))

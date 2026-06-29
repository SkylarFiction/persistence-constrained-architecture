from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger
from .mission_steps import (
    MissionStepExecutionStatus,
    MissionStepRecord,
    mission_step_records_from_events,
    require_mission_step,
)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SkillCandidateStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SkillCandidateRecord:
    skill_id: str
    identity_id: str
    name: str
    source_step_ids: list[str]
    required_tool: str
    risk_level: str
    procedure_sha256: str
    procedure_length: int
    status: SkillCandidateStatus
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        name: str,
        source_step_ids: list[str],
        required_tool: str,
        risk_level: str,
        procedure: str,
        reason: str = "",
    ) -> "SkillCandidateRecord":
        return cls(
            skill_id=f"skill_{uuid.uuid4()}",
            identity_id=identity_id,
            name=name,
            source_step_ids=source_step_ids,
            required_tool=required_tool,
            risk_level=risk_level,
            procedure_sha256=_text_hash(procedure),
            procedure_length=len(procedure),
            status=SkillCandidateStatus.PROPOSED,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SkillCandidateRecord":
        return cls(
            skill_id=str(data["skill_id"]),
            identity_id=str(data["identity_id"]),
            name=str(data["name"]),
            source_step_ids=[str(item) for item in data.get("source_step_ids", [])],
            required_tool=str(data.get("required_tool", "")),
            risk_level=str(data.get("risk_level", "")),
            procedure_sha256=str(data["procedure_sha256"]),
            procedure_length=int(data["procedure_length"]),
            status=SkillCandidateStatus(str(data["status"])),
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "identity_id": self.identity_id,
            "name": self.name,
            "source_step_ids": self.source_step_ids,
            "required_tool": self.required_tool,
            "risk_level": self.risk_level,
            "procedure_sha256": self.procedure_sha256,
            "procedure_length": self.procedure_length,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }

    def with_status(
        self,
        status: str | SkillCandidateStatus,
        reason: str = "",
    ) -> "SkillCandidateRecord":
        status_value = status.value if isinstance(status, SkillCandidateStatus) else str(status)
        return SkillCandidateRecord(
            skill_id=self.skill_id,
            identity_id=self.identity_id,
            name=self.name,
            source_step_ids=self.source_step_ids,
            required_tool=self.required_tool,
            risk_level=self.risk_level,
            procedure_sha256=self.procedure_sha256,
            procedure_length=self.procedure_length,
            status=SkillCandidateStatus(status_value),
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            reason=reason or self.reason,
        )


def propose_skill_candidate(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    name: str,
    procedure: str,
    reason: str = "",
) -> SkillCandidateRecord:
    step = require_mission_step(ledger.events(), step_id)
    if step.execution_status != MissionStepExecutionStatus.COMPLETED:
        raise ValueError("Only completed mission steps can seed skill candidates.")
    record = SkillCandidateRecord.create(
        identity_id=identity_id,
        name=name,
        source_step_ids=[step.step_id],
        required_tool=step.required_tool,
        risk_level=step.risk_level.value,
        procedure=procedure,
        reason=reason or f"skill candidate from completed step {step.step_id}",
    )
    ledger.append("skill.candidate_proposed", identity_id, record.to_dict())
    return record


def auto_propose_skill_candidates(
    ledger: ContinuityLedger,
    identity_id: str,
    minimum_repetitions: int = 2,
) -> list[SkillCandidateRecord]:
    existing_source_steps = {
        step_id
        for candidate in skill_candidates_from_events(ledger.events())
        for step_id in candidate.source_step_ids
    }
    completed = [
        step
        for step in mission_step_records_from_events(ledger.events())
        if step.execution_status == MissionStepExecutionStatus.COMPLETED
        and step.step_id not in existing_source_steps
    ]
    grouped: dict[tuple[str, str], list[MissionStepRecord]] = {}
    for step in completed:
        grouped.setdefault((step.required_tool, step.risk_level.value), []).append(step)
    records = []
    for (required_tool, risk_level), steps in grouped.items():
        if len(steps) < minimum_repetitions:
            continue
        name = f"Reusable {required_tool} procedure"
        procedure = (
            f"Derived from {len(steps)} completed mission step(s) using "
            f"{required_tool} at {risk_level} risk. Requires steward review before reuse."
        )
        record = SkillCandidateRecord.create(
            identity_id=identity_id,
            name=name,
            source_step_ids=[step.step_id for step in steps],
            required_tool=required_tool,
            risk_level=risk_level,
            procedure=procedure,
            reason="auto-proposed from repeated completed mission steps",
        )
        ledger.append("skill.candidate_proposed", identity_id, record.to_dict())
        records.append(record)
    return records


def review_skill_candidate(
    ledger: ContinuityLedger,
    identity_id: str,
    skill_id: str,
    decision: str,
    reason: str = "",
) -> SkillCandidateRecord:
    if decision not in {"accept", "reject"}:
        raise ValueError("decision must be accept or reject")
    candidate = require_skill_candidate(ledger.events(), skill_id)
    if candidate.status != SkillCandidateStatus.PROPOSED:
        raise ValueError(f"Skill candidate is already {candidate.status.value}.")
    updated = candidate.with_status(
        SkillCandidateStatus.ACCEPTED if decision == "accept" else SkillCandidateStatus.REJECTED,
        reason=reason,
    )
    ledger.append("skill.candidate_reviewed", identity_id, updated.to_dict())
    return updated


def skill_candidates_from_events(
    events: list[ContinuityEvent],
) -> list[SkillCandidateRecord]:
    records: dict[str, SkillCandidateRecord] = {}
    for event in events:
        if event.event_type in {"skill.candidate_proposed", "skill.candidate_reviewed"}:
            record = SkillCandidateRecord.from_dict(event.payload)
            records[record.skill_id] = record
    return list(records.values())


def accepted_skills_from_events(
    events: list[ContinuityEvent],
) -> list[SkillCandidateRecord]:
    return [
        record
        for record in skill_candidates_from_events(events)
        if record.status == SkillCandidateStatus.ACCEPTED
    ]


def skill_suggestions_for_mission(
    events: list[ContinuityEvent],
    mission_id: str,
) -> list[dict[str, Any]]:
    steps = mission_step_records_from_events(events, mission_id)
    accepted = accepted_skills_from_events(events)
    suggestions = []
    for skill in accepted:
        matching_steps = [
            step.step_id
            for step in steps
            if step.required_tool == skill.required_tool
            and step.risk_level.value == skill.risk_level
            and step.execution_status.value in {"proposed", "ready"}
        ]
        if matching_steps:
            suggestions.append(
                {
                    "skill": skill.to_dict(),
                    "mission_id": mission_id,
                    "matching_step_ids": matching_steps,
                    "reason": "accepted skill matches mission step tool and risk",
                }
            )
    return suggestions


def require_skill_candidate(
    events: list[ContinuityEvent],
    skill_id: str,
) -> SkillCandidateRecord:
    for record in skill_candidates_from_events(events):
        if record.skill_id == skill_id:
            return record
    raise ValueError(f"Skill candidate not found: {skill_id}")

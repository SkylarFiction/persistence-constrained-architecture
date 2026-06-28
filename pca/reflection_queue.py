from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger
from .reflections import ReflectionRecord


class ReflectionTaskKind(str, Enum):
    REVIEW_GROWTH = "review_growth"
    RESOLVE_CONFLICT = "resolve_conflict"
    AUDIT_MEMORY = "audit_memory"
    REVIEW_MISSION = "review_mission"
    OPEN_RECOVERY = "open_recovery"


class ReflectionTaskStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass(frozen=True)
class ReflectionTaskRecord:
    task_id: str
    identity_id: str
    kind: ReflectionTaskKind
    severity: str
    status: ReflectionTaskStatus
    source_reflection_id: str
    reason: str
    recommended_action: str
    blocking_effect: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolved_at: str | None = None
    resolution_reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        kind: str | ReflectionTaskKind,
        severity: str,
        source_reflection_id: str,
        reason: str,
        recommended_action: str,
    ) -> "ReflectionTaskRecord":
        parsed_kind = _parse_kind(kind)
        return cls(
            task_id=f"rq_{uuid.uuid4()}",
            identity_id=identity_id,
            kind=parsed_kind,
            severity=severity,
            status=ReflectionTaskStatus.OPEN,
            source_reflection_id=source_reflection_id,
            reason=reason,
            recommended_action=recommended_action,
            blocking_effect=_blocking_effect(parsed_kind),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReflectionTaskRecord":
        return cls(
            task_id=str(data["task_id"]),
            identity_id=str(data["identity_id"]),
            kind=_parse_kind(data["kind"]),
            severity=str(data["severity"]),
            status=_parse_status(data["status"]),
            source_reflection_id=str(data["source_reflection_id"]),
            reason=str(data.get("reason", "")),
            recommended_action=str(data.get("recommended_action", "")),
            blocking_effect=str(data.get("blocking_effect", "")),
            created_at=str(data["created_at"]),
            resolved_at=data.get("resolved_at"),
            resolution_reason=str(data.get("resolution_reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "identity_id": self.identity_id,
            "kind": self.kind.value,
            "severity": self.severity,
            "status": self.status.value,
            "source_reflection_id": self.source_reflection_id,
            "reason": self.reason,
            "recommended_action": self.recommended_action,
            "blocking_effect": self.blocking_effect,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "resolution_reason": self.resolution_reason,
        }

    def with_status(
        self,
        status: str | ReflectionTaskStatus,
        reason: str = "",
    ) -> "ReflectionTaskRecord":
        parsed_status = _parse_status(status)
        return ReflectionTaskRecord(
            task_id=self.task_id,
            identity_id=self.identity_id,
            kind=self.kind,
            severity=self.severity,
            status=parsed_status,
            source_reflection_id=self.source_reflection_id,
            reason=self.reason,
            recommended_action=self.recommended_action,
            blocking_effect=self.blocking_effect,
            created_at=self.created_at,
            resolved_at=datetime.now(timezone.utc).isoformat(),
            resolution_reason=reason,
        )


def open_tasks_from_reflection(
    ledger: ContinuityLedger,
    reflection: ReflectionRecord,
    skip_existing: bool = True,
) -> list[ReflectionTaskRecord]:
    existing_open = [
        task
        for task in reflection_task_records_from_events(ledger.events())
        if task.status == ReflectionTaskStatus.OPEN
    ]
    opened: list[ReflectionTaskRecord] = []
    for item in _task_specs(reflection):
        task = ReflectionTaskRecord.create(
            identity_id=reflection.identity_id,
            kind=item["kind"],
            severity=item["severity"],
            source_reflection_id=reflection.reflection_id,
            reason=item["reason"],
            recommended_action=item["recommended_action"],
        )
        if skip_existing and _has_matching_open_task(task, existing_open + opened):
            continue
        ledger.append("reflection.task_opened", reflection.identity_id, task.to_dict())
        opened.append(task)
    return opened


def update_reflection_task(
    ledger: ContinuityLedger,
    identity_id: str,
    task_id: str,
    status: str | ReflectionTaskStatus,
    reason: str = "",
) -> ReflectionTaskRecord:
    task = find_reflection_task(ledger.events(), task_id)
    if task is None:
        raise ValueError(f"Reflection task not found: {task_id}")
    if task.status != ReflectionTaskStatus.OPEN:
        raise ValueError(f"Reflection task is already {task.status.value}: {task_id}")
    updated = task.with_status(status, reason=reason)
    event_type = (
        "reflection.task_resolved"
        if updated.status == ReflectionTaskStatus.RESOLVED
        else "reflection.task_dismissed"
    )
    ledger.append(event_type, identity_id, updated.to_dict())
    return updated


def find_reflection_task(
    events: list[ContinuityEvent],
    task_id: str,
) -> ReflectionTaskRecord | None:
    for task in reflection_task_records_from_events(events):
        if task.task_id == task_id:
            return task
    return None


def reflection_task_records_from_events(
    events: list[ContinuityEvent],
) -> list[ReflectionTaskRecord]:
    records: dict[str, ReflectionTaskRecord] = {}
    for event in events:
        if event.event_type in {
            "reflection.task_opened",
            "reflection.task_resolved",
            "reflection.task_dismissed",
        }:
            record = ReflectionTaskRecord.from_dict(event.payload)
            records[record.task_id] = record
    return list(records.values())


def active_reflection_tasks(events: list[ContinuityEvent]) -> list[ReflectionTaskRecord]:
    return [
        task
        for task in reflection_task_records_from_events(events)
        if task.status == ReflectionTaskStatus.OPEN
    ]


def resolve_matching_reflection_tasks(
    ledger: ContinuityLedger,
    identity_id: str,
    kind: str | ReflectionTaskKind,
    reason_contains: str,
    resolution_reason: str,
) -> list[ReflectionTaskRecord]:
    parsed_kind = _parse_kind(kind)
    resolved = []
    for task in active_reflection_tasks(ledger.events()):
        if task.kind != parsed_kind:
            continue
        if reason_contains and reason_contains not in task.reason:
            continue
        resolved.append(
            update_reflection_task(
                ledger,
                identity_id,
                task.task_id,
                ReflectionTaskStatus.RESOLVED,
                reason=resolution_reason,
            )
        )
    return resolved


def _task_specs(reflection: ReflectionRecord) -> list[dict[str, str]]:
    specs: list[dict[str, str]] = []
    observation_text = " ".join(reflection.observations)
    action_text = " ".join(reflection.recommended_actions)
    if "growth record" in observation_text or "review pending growth" in action_text:
        specs.append(
            {
                "kind": ReflectionTaskKind.REVIEW_GROWTH.value,
                "severity": "medium",
                "reason": _matching_observation(
                    reflection,
                    "growth record",
                    "growth record requires review",
                ),
                "recommended_action": "Review pending growth records.",
            }
        )
    if "growth conflict" in observation_text or "resolve growth conflicts" in action_text:
        specs.append(
            {
                "kind": ReflectionTaskKind.RESOLVE_CONFLICT.value,
                "severity": "high",
                "reason": _matching_observation(
                    reflection,
                    "growth conflict",
                    "growth conflict requires steward attention",
                ),
                "recommended_action": "Resolve conflict before accepting related growth.",
            }
        )
    if "memory card" in observation_text or "low-confidence memory" in action_text:
        specs.append(
            {
                "kind": ReflectionTaskKind.AUDIT_MEMORY.value,
                "severity": "medium",
                "reason": _matching_observation(
                    reflection,
                    "memory card",
                    "memory confidence requires audit",
                ),
                "recommended_action": "Audit contradicted or low-confidence memory cards.",
            }
        )
    if "mission" in observation_text or "mission" in action_text:
        specs.append(
            {
                "kind": ReflectionTaskKind.REVIEW_MISSION.value,
                "severity": "medium",
                "reason": _matching_observation(
                    reflection,
                    "mission",
                    "mission pressure requires steward review",
                ),
                "recommended_action": "Review mission risk, evidence, outcome, or lesson before proceeding.",
            }
        )
    if reflection.continuity_claim == "continuity_break":
        specs.append(
            {
                "kind": ReflectionTaskKind.OPEN_RECOVERY.value,
                "severity": "critical",
                "reason": "continuity break requires staged recovery",
                "recommended_action": "Open a governed recovery path.",
            }
        )
    return specs


def _matching_observation(
    reflection: ReflectionRecord,
    needle: str,
    fallback: str,
) -> str:
    for observation in reflection.observations:
        if needle in observation:
            return observation
    return fallback


def _has_matching_open_task(
    task: ReflectionTaskRecord,
    open_tasks: list[ReflectionTaskRecord],
) -> bool:
    return any(
        other.kind == task.kind
        and other.reason == task.reason
        and other.recommended_action == task.recommended_action
        for other in open_tasks
    )


def _blocking_effect(kind: ReflectionTaskKind) -> str:
    values = {
        ReflectionTaskKind.REVIEW_GROWTH: "blocks identity/self-model acceptance for pending growth",
        ReflectionTaskKind.RESOLVE_CONFLICT: "blocks related growth acceptance",
        ReflectionTaskKind.AUDIT_MEMORY: "does not block output but lowers confidence until reviewed",
        ReflectionTaskKind.REVIEW_MISSION: "does not block output but requires steward review before mission work proceeds",
        ReflectionTaskKind.OPEN_RECOVERY: "blocks normal continuity claims when tied to hard breach",
    }
    return values[kind]


def _parse_kind(value: str | ReflectionTaskKind) -> ReflectionTaskKind:
    if isinstance(value, ReflectionTaskKind):
        return value
    return ReflectionTaskKind(str(value))


def _parse_status(value: str | ReflectionTaskStatus) -> ReflectionTaskStatus:
    if isinstance(value, ReflectionTaskStatus):
        return value
    return ReflectionTaskStatus(str(value))

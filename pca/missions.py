from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid

from .growth import GrowthRecord, propose_growth
from .ledger import ContinuityEvent, ContinuityLedger
from .reflection_queue import ReflectionTaskRecord, open_tasks_from_reflection
from .reflections import ReflectionRecord


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MissionStatus(str, Enum):
    OPEN = "open"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class MissionItemKind(str, Enum):
    HYPOTHESIS = "hypothesis"
    EVIDENCE = "evidence"
    INTERVENTION = "intervention"
    PLAN_STEP = "plan_step"
    RISK = "risk"
    OUTCOME = "outcome"
    LESSON = "lesson"


@dataclass(frozen=True)
class MissionRecord:
    mission_id: str
    identity_id: str
    title: str
    problem_sha256: str
    problem_length: int
    status: MissionStatus
    values: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        title: str,
        problem_statement: str,
        values: list[str] | None = None,
        reason: str = "",
    ) -> "MissionRecord":
        return cls(
            mission_id=f"mission_{uuid.uuid4()}",
            identity_id=identity_id,
            title=title,
            problem_sha256=_text_hash(problem_statement),
            problem_length=len(problem_statement),
            status=MissionStatus.OPEN,
            values=values or [],
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionRecord":
        return cls(
            mission_id=str(data["mission_id"]),
            identity_id=str(data["identity_id"]),
            title=str(data["title"]),
            problem_sha256=str(data["problem_sha256"]),
            problem_length=int(data["problem_length"]),
            status=MissionStatus(str(data["status"])),
            values=[str(item) for item in data.get("values", [])],
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "identity_id": self.identity_id,
            "title": self.title,
            "problem_sha256": self.problem_sha256,
            "problem_length": self.problem_length,
            "status": self.status.value,
            "values": self.values,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }

    def with_status(self, status: str | MissionStatus, reason: str = "") -> "MissionRecord":
        return MissionRecord(
            mission_id=self.mission_id,
            identity_id=self.identity_id,
            title=self.title,
            problem_sha256=self.problem_sha256,
            problem_length=self.problem_length,
            status=MissionStatus(str(status)),
            values=self.values,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            reason=reason or self.reason,
        )


@dataclass(frozen=True)
class MissionItemRecord:
    item_id: str
    mission_id: str
    identity_id: str
    kind: MissionItemKind
    summary_sha256: str
    summary_length: int
    status: str
    confidence: str = "unknown"
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        mission_id: str,
        identity_id: str,
        kind: str | MissionItemKind,
        summary: str,
        status: str = "proposed",
        confidence: str = "unknown",
        evidence_refs: list[str] | None = None,
        reason: str = "",
    ) -> "MissionItemRecord":
        parsed_kind = _parse_item_kind(kind)
        return cls(
            item_id=f"mission_item_{uuid.uuid4()}",
            mission_id=mission_id,
            identity_id=identity_id,
            kind=parsed_kind,
            summary_sha256=_text_hash(summary),
            summary_length=len(summary),
            status=status,
            confidence=confidence,
            evidence_refs=evidence_refs or [],
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionItemRecord":
        return cls(
            item_id=str(data["item_id"]),
            mission_id=str(data["mission_id"]),
            identity_id=str(data["identity_id"]),
            kind=_parse_item_kind(data["kind"]),
            summary_sha256=str(data["summary_sha256"]),
            summary_length=int(data["summary_length"]),
            status=str(data.get("status", "proposed")),
            confidence=str(data.get("confidence", "unknown")),
            evidence_refs=[str(item) for item in data.get("evidence_refs", [])],
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "mission_id": self.mission_id,
            "identity_id": self.identity_id,
            "kind": self.kind.value,
            "summary_sha256": self.summary_sha256,
            "summary_length": self.summary_length,
            "status": self.status,
            "confidence": self.confidence,
            "evidence_refs": self.evidence_refs,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class MissionBrief:
    mission: MissionRecord
    items: list[MissionItemRecord]

    def to_dict(self) -> dict[str, Any]:
        by_kind: dict[str, list[dict[str, Any]]] = {
            kind.value: [] for kind in MissionItemKind
        }
        for item in self.items:
            by_kind[item.kind.value].append(item.to_dict())
        return {
            "mission": self.mission.to_dict(),
            "items": [item.to_dict() for item in self.items],
            "by_kind": by_kind,
            "counts": {kind: len(records) for kind, records in by_kind.items()},
        }


@dataclass(frozen=True)
class MissionPressureResult:
    reflection: ReflectionRecord | None = None
    opened_tasks: list[ReflectionTaskRecord] = field(default_factory=list)
    growth: GrowthRecord | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "reflection": self.reflection.to_dict() if self.reflection else None,
            "opened_tasks": [task.to_dict() for task in self.opened_tasks],
            "growth": self.growth.to_dict() if self.growth else None,
        }


def open_mission(
    ledger: ContinuityLedger,
    identity_id: str,
    title: str,
    problem_statement: str,
    values: list[str] | None = None,
    reason: str = "",
) -> MissionRecord:
    record = MissionRecord.create(
        identity_id=identity_id,
        title=title,
        problem_statement=problem_statement,
        values=values,
        reason=reason,
    )
    ledger.append("mission.opened", identity_id, record.to_dict())
    return record


def update_mission_status(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    status: str | MissionStatus,
    reason: str = "",
) -> MissionRecord:
    mission = require_mission(ledger.events(), mission_id)
    updated = mission.with_status(status, reason=reason)
    ledger.append("mission.status_updated", identity_id, updated.to_dict())
    return updated


def add_mission_item(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    kind: str | MissionItemKind,
    summary: str,
    status: str = "proposed",
    confidence: str = "unknown",
    evidence_refs: list[str] | None = None,
    reason: str = "",
    bridge_reflection: bool = True,
) -> MissionItemRecord:
    require_mission(ledger.events(), mission_id)
    record = MissionItemRecord.create(
        mission_id=mission_id,
        identity_id=identity_id,
        kind=kind,
        summary=summary,
        status=status,
        confidence=confidence,
        evidence_refs=evidence_refs,
        reason=reason,
    )
    event = ledger.append("mission.item_added", identity_id, record.to_dict())
    if bridge_reflection:
        route_mission_pressure(
            ledger,
            identity_id,
            record,
            source_event_id=event.event_hash,
            raw_summary=summary,
        )
    return record


def route_mission_pressure(
    ledger: ContinuityLedger,
    identity_id: str,
    item: MissionItemRecord,
    source_event_id: str,
    raw_summary: str = "",
) -> MissionPressureResult:
    observations, actions, severity, focus = _mission_pressure(item)
    reflection = None
    opened_tasks: list[ReflectionTaskRecord] = []
    growth = None

    if observations:
        reflection = ReflectionRecord.create(
            identity_id=identity_id,
            continuity_claim="mission_scoped_review",
            focus=focus,
            severity=severity,
            observations=observations,
            recommended_actions=actions,
            source_event_ids=[source_event_id],
        )
        ledger.append("lucien.reflection_recorded", identity_id, reflection.to_dict())
        opened_tasks = open_tasks_from_reflection(ledger, reflection)

    if item.kind == MissionItemKind.LESSON:
        growth = propose_growth(
            ledger=ledger,
            identity_id=identity_id,
            kind="memory",
            summary=raw_summary,
            identity_impact="low",
            evidence_refs=[item.item_id, *item.evidence_refs],
            source_event_ids=[source_event_id],
            reason=f"mission lesson from {item.mission_id}",
        )

    return MissionPressureResult(
        reflection=reflection,
        opened_tasks=opened_tasks,
        growth=growth,
    )


def mission_records_from_events(events: list[ContinuityEvent]) -> list[MissionRecord]:
    records: dict[str, MissionRecord] = {}
    for event in events:
        if event.event_type in {"mission.opened", "mission.status_updated"}:
            record = MissionRecord.from_dict(event.payload)
            records[record.mission_id] = record
    return list(records.values())


def mission_items_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[MissionItemRecord]:
    records = [
        MissionItemRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "mission.item_added"
    ]
    if mission_id is None:
        return records
    return [record for record in records if record.mission_id == mission_id]


def mission_briefs_from_events(events: list[ContinuityEvent]) -> list[MissionBrief]:
    return [
        MissionBrief(
            mission=mission,
            items=mission_items_from_events(events, mission.mission_id),
        )
        for mission in mission_records_from_events(events)
    ]


def require_mission(events: list[ContinuityEvent], mission_id: str) -> MissionRecord:
    for mission in mission_records_from_events(events):
        if mission.mission_id == mission_id:
            return mission
    raise ValueError(f"Mission not found: {mission_id}")


def _parse_item_kind(value: str | MissionItemKind) -> MissionItemKind:
    if isinstance(value, MissionItemKind):
        return value
    return MissionItemKind(str(value))


def _mission_pressure(
    item: MissionItemRecord,
) -> tuple[list[str], list[str], str, str]:
    if item.kind == MissionItemKind.RISK:
        return (
            [f"mission risk requires steward review: {item.mission_id}"],
            ["review mission risk before approving related interventions"],
            "review_required",
            "mission_risk_review",
        )
    if item.kind == MissionItemKind.EVIDENCE and (
        item.status in {"requested", "unresolved", "missing"}
        or item.confidence in {"unknown", "low", "uncertain"}
    ):
        return (
            [f"mission evidence remains unresolved: {item.mission_id}"],
            ["verify mission evidence before strengthening conclusions"],
            "watch",
            "mission_evidence_review",
        )
    if item.kind == MissionItemKind.OUTCOME and (
        item.status in {"failed", "negative", "blocked"}
        or "fail" in item.reason.lower()
    ):
        return (
            [f"mission outcome signals failed intervention: {item.mission_id}"],
            ["review failed mission outcome before continuing intervention"],
            "review_required",
            "mission_outcome_review",
        )
    return ([], [], "stable", "mission_review")

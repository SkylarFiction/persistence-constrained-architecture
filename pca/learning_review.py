from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .chat_sessions import chat_turns_from_events
from .growth import propose_growth
from .ledger import ContinuityEvent, ContinuityLedger
from .mission_steps import (
    MissionStepExecutionStatus,
    mission_step_records_from_events,
    require_mission_step,
)
from .missions import (
    MissionItemKind,
    add_mission_item,
    mission_briefs_from_events,
    require_mission,
)
from .reflections import ReflectionRecord
from .reflection_queue import open_tasks_from_reflection
from .skill_memory import propose_skill_candidate


@dataclass(frozen=True)
class LearningReviewRecord:
    review_id: str
    identity_id: str
    scope: str
    target_id: str
    status: str
    observations: list[str]
    recommended_actions: list[str]
    candidate_counts: dict[str, int]
    source_event_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        scope: str,
        target_id: str,
        status: str,
        observations: list[str],
        recommended_actions: list[str],
        candidate_counts: dict[str, int] | None = None,
        source_event_ids: list[str] | None = None,
        reason: str = "",
        review_id: str | None = None,
    ) -> "LearningReviewRecord":
        return cls(
            review_id=review_id or f"learning_review_{uuid.uuid4()}",
            identity_id=identity_id,
            scope=scope,
            target_id=target_id,
            status=status,
            observations=observations,
            recommended_actions=recommended_actions,
            candidate_counts=candidate_counts or _empty_counts(),
            source_event_ids=source_event_ids or [],
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearningReviewRecord":
        return cls(
            review_id=str(data["review_id"]),
            identity_id=str(data["identity_id"]),
            scope=str(data["scope"]),
            target_id=str(data["target_id"]),
            status=str(data["status"]),
            observations=[str(item) for item in data.get("observations", [])],
            recommended_actions=[str(item) for item in data.get("recommended_actions", [])],
            candidate_counts={str(key): int(value) for key, value in data.get("candidate_counts", {}).items()},
            source_event_ids=[str(item) for item in data.get("source_event_ids", [])],
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "identity_id": self.identity_id,
            "scope": self.scope,
            "target_id": self.target_id,
            "status": self.status,
            "observations": self.observations,
            "recommended_actions": self.recommended_actions,
            "candidate_counts": self.candidate_counts,
            "source_event_ids": self.source_event_ids,
            "created_at": self.created_at,
            "reason": self.reason,
        }


def learning_review_records_from_events(
    events: list[ContinuityEvent],
) -> list[LearningReviewRecord]:
    records: dict[str, LearningReviewRecord] = {}
    for event in events:
        if event.event_type in {"learning_review.started", "learning_review.completed"}:
            record = LearningReviewRecord.from_dict(event.payload)
            records[record.review_id] = record
    return list(records.values())


def run_learning_review(
    ledger: ContinuityLedger,
    identity_id: str,
    scope: str,
    target_id: str,
    apply: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    events = ledger.events()
    plan = _review_plan(events, identity_id, scope, target_id)
    started = LearningReviewRecord.create(
        identity_id=identity_id,
        scope=scope,
        target_id=target_id,
        status="started",
        observations=plan["observations"],
        recommended_actions=plan["recommended_actions"],
        source_event_ids=plan["source_event_ids"],
        reason=reason,
    )
    start_event = ledger.append("learning_review.started", identity_id, started.to_dict())
    created = _apply_learning_plan(
        ledger,
        identity_id,
        plan,
        apply=apply,
        review_id=started.review_id,
    )
    completed = LearningReviewRecord.create(
        identity_id=identity_id,
        scope=scope,
        target_id=target_id,
        status="completed",
        observations=plan["observations"],
        recommended_actions=plan["recommended_actions"],
        candidate_counts=_candidate_counts(created),
        source_event_ids=[start_event.event_hash, *plan["source_event_ids"]],
        reason=reason,
        review_id=started.review_id,
    )
    ledger.append("learning_review.completed", identity_id, completed.to_dict())
    return {
        "started": started.to_dict(),
        "completed": completed.to_dict(),
        "applied": apply,
        "candidates": created,
    }


def run_latest_session_learning_review(
    ledger: ContinuityLedger,
    identity_id: str,
    apply: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    sessions = [
        event.payload
        for event in ledger.events()
        if event.event_type in {"lucien.chat_session_started", "lucien.chat_session_closed"}
    ]
    if not sessions:
        raise ValueError("No chat sessions found.")
    session_id = str(sessions[-1]["session_id"])
    return run_learning_review(
        ledger,
        identity_id,
        "session",
        session_id,
        apply=apply,
        reason=reason,
    )


def _review_plan(
    events: list[ContinuityEvent],
    identity_id: str,
    scope: str,
    target_id: str,
) -> dict[str, Any]:
    if scope == "step":
        return _step_plan(events, identity_id, target_id)
    if scope == "mission":
        return _mission_plan(events, identity_id, target_id)
    if scope == "session":
        return _session_plan(events, identity_id, target_id)
    raise ValueError("learning review scope must be session, mission, or step")


def _step_plan(events: list[ContinuityEvent], identity_id: str, step_id: str) -> dict[str, Any]:
    step = require_mission_step(events, step_id)
    source_ids = _event_hashes_for_payload_id(events, "step_id", step_id)
    observations = [f"reviewed mission step {step_id} with status {step.execution_status.value}"]
    actions: list[str] = []
    planned: list[dict[str, Any]] = []
    if step.execution_status == MissionStepExecutionStatus.COMPLETED:
        actions.append("propose skill candidate from completed step")
        planned.append({"type": "skill_candidate", "step_id": step.step_id})
    elif step.execution_status in {MissionStepExecutionStatus.FAILED, MissionStepExecutionStatus.BLOCKED}:
        actions.append("open mission review pressure for failed or blocked step")
        planned.append({"type": "reflection_task", "mission_id": step.mission_id, "step_id": step.step_id})
        planned.append({"type": "mission_lesson", "mission_id": step.mission_id, "step_id": step.step_id})
    else:
        actions.append("wait for step completion, failure, or blockage before durable learning")
    return _plan("step", step_id, observations, actions, planned, source_ids)


def _mission_plan(events: list[ContinuityEvent], identity_id: str, mission_id: str) -> dict[str, Any]:
    require_mission(events, mission_id)
    brief = _require_brief(events, mission_id)
    steps = mission_step_records_from_events(events, mission_id)
    completed = [step for step in steps if step.execution_status == MissionStepExecutionStatus.COMPLETED]
    failed = [
        step
        for step in steps
        if step.execution_status in {MissionStepExecutionStatus.FAILED, MissionStepExecutionStatus.BLOCKED}
    ]
    observations = [
        f"reviewed mission {mission_id}",
        f"completed_steps={len(completed)} failed_or_blocked_steps={len(failed)}",
    ]
    actions: list[str] = []
    planned: list[dict[str, Any]] = []
    if completed:
        actions.append("propose skill candidates from completed mission steps")
        for step in completed:
            planned.append({"type": "skill_candidate", "step_id": step.step_id})
    if failed:
        actions.append("route failed or blocked mission work into review pressure")
        for step in failed:
            planned.append({"type": "reflection_task", "mission_id": mission_id, "step_id": step.step_id})
    if not brief.to_dict()["counts"].get(MissionItemKind.EVIDENCE.value, 0):
        actions.append("request evidence before strengthening mission claims")
        planned.append({"type": "evidence_needed", "mission_id": mission_id})
    if completed or failed:
        actions.append("record mission lesson candidate")
        planned.append({"type": "mission_lesson", "mission_id": mission_id, "step_id": steps[-1].step_id if steps else ""})
    if not planned:
        actions.append("continue mission until outcomes or evidence create learning pressure")
    return _plan(
        "mission",
        mission_id,
        observations,
        actions,
        planned,
        _event_hashes_for_payload_id(events, "mission_id", mission_id),
    )


def _session_plan(events: list[ContinuityEvent], identity_id: str, session_id: str) -> dict[str, Any]:
    turns = [turn for turn in chat_turns_from_events(events) if turn.session_id == session_id]
    observations = [f"reviewed session {session_id}", f"turn_count={len(turns)}"]
    actions = ["propose low-impact memory candidate summarizing that session learning needs review"]
    planned = [{"type": "memory_candidate", "session_id": session_id}]
    if not turns:
        actions.append("no chat turns found; keep learning candidate low confidence")
    return _plan(
        "session",
        session_id,
        observations,
        actions,
        planned,
        _event_hashes_for_payload_id(events, "session_id", session_id),
    )


def _apply_learning_plan(
    ledger: ContinuityLedger,
    identity_id: str,
    plan: dict[str, Any],
    apply: bool,
    review_id: str,
) -> dict[str, list[dict[str, Any]]]:
    created: dict[str, list[dict[str, Any]]] = {
        "memory_candidates": [],
        "skill_candidates": [],
        "mission_lessons": [],
        "evidence_needed": [],
        "reflection_tasks": [],
    }
    if not apply:
        return created
    for item in plan["planned_candidates"]:
        kind = item["type"]
        if kind == "memory_candidate":
            growth = propose_growth(
                ledger,
                identity_id,
                kind="memory",
                summary=f"Session {item['session_id']} produced learning that requires steward review.",
                identity_impact="low",
                evidence_refs=[review_id],
                reason="learning review memory candidate",
            )
            created["memory_candidates"].append(growth.to_dict())
        elif kind == "skill_candidate":
            try:
                candidate = propose_skill_candidate(
                    ledger,
                    identity_id,
                    item["step_id"],
                    name="Reviewed mission step procedure",
                    procedure=f"Learning review {review_id} identified completed step {item['step_id']} as a possible reusable procedure.",
                    reason="learning review skill candidate",
                )
            except ValueError:
                continue
            created["skill_candidates"].append(candidate.to_dict())
        elif kind == "mission_lesson":
            lesson = add_mission_item(
                ledger,
                identity_id,
                item["mission_id"],
                "lesson",
                f"Learning review {review_id} found mission work that should be reviewed before becoming durable memory.",
                status="proposed",
                confidence="low",
                evidence_refs=[review_id, item.get("step_id", "")],
                reason="learning review mission lesson",
            )
            created["mission_lessons"].append(lesson.to_dict())
        elif kind == "evidence_needed":
            evidence = add_mission_item(
                ledger,
                identity_id,
                item["mission_id"],
                "evidence",
                f"Learning review {review_id} found that mission claims need supporting evidence.",
                status="requested",
                confidence="unknown",
                evidence_refs=[review_id],
                reason="learning review evidence needed",
            )
            created["evidence_needed"].append(evidence.to_dict())
        elif kind == "reflection_task":
            reflection = ReflectionRecord.create(
                identity_id=identity_id,
                continuity_claim="learning_review",
                focus="mission_outcome_review",
                severity="review_required",
                observations=[f"learning review found failed or blocked step {item['step_id']}"],
                recommended_actions=["review failed or blocked mission work before reusing the pattern"],
                source_event_ids=[review_id, item["step_id"]],
            )
            ledger.append("lucien.reflection_recorded", identity_id, reflection.to_dict())
            tasks = open_tasks_from_reflection(ledger, reflection)
            created["reflection_tasks"].extend(task.to_dict() for task in tasks)
    return created


def _plan(
    scope: str,
    target_id: str,
    observations: list[str],
    actions: list[str],
    planned: list[dict[str, Any]],
    source_ids: list[str],
) -> dict[str, Any]:
    return {
        "scope": scope,
        "target_id": target_id,
        "observations": observations,
        "recommended_actions": _dedupe(actions),
        "planned_candidates": planned,
        "source_event_ids": _dedupe(source_ids),
    }


def _candidate_counts(created: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    counts = _empty_counts()
    for key, records in created.items():
        counts[key] = len(records)
    return counts


def _empty_counts() -> dict[str, int]:
    return {
        "memory_candidates": 0,
        "skill_candidates": 0,
        "mission_lessons": 0,
        "evidence_needed": 0,
        "reflection_tasks": 0,
    }


def _require_brief(events: list[ContinuityEvent], mission_id: str):
    for brief in mission_briefs_from_events(events):
        if brief.mission.mission_id == mission_id:
            return brief
    raise ValueError(f"Mission not found: {mission_id}")


def _event_hashes_for_payload_id(
    events: list[ContinuityEvent],
    field_name: str,
    field_value: str,
) -> list[str]:
    return [
        event.event_hash
        for event in events
        if str(event.payload.get(field_name, "")) == field_value
    ]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

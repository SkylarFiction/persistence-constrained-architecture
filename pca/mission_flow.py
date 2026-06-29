from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .ledger import ContinuityEvent, ContinuityLedger
from .missions import (
    MissionBrief,
    MissionItemKind,
    MissionStatus,
    mission_briefs_from_events,
    require_mission,
)
from .mission_steps import (
    MissionStepApprovalStatus,
    MissionStepExecutionStatus,
    MissionStepRisk,
    mission_step_records_from_events,
)
from .reflection_queue import active_reflection_tasks


class MissionPhase(str, Enum):
    INTAKE = "intake"
    HYPOTHESIS_BUILDING = "hypothesis_building"
    EVIDENCE_REVIEW = "evidence_review"
    PLANNING = "planning"
    INTERVENTION_READY = "intervention_ready"
    OUTCOME_REVIEW = "outcome_review"
    LESSON_REVIEW = "lesson_review"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class MissionFlowState:
    mission_id: str
    phase: MissionPhase
    blockers: list[str] = field(default_factory=list)
    next_action: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    step_counts: dict[str, int] = field(default_factory=dict)
    open_task_ids: list[str] = field(default_factory=list)
    ready_to_advance: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "phase": self.phase.value,
            "blockers": self.blockers,
            "next_action": self.next_action,
            "counts": self.counts,
            "step_counts": self.step_counts,
            "open_task_ids": self.open_task_ids,
            "ready_to_advance": self.ready_to_advance,
        }


def mission_flow_from_events(
    events: list[ContinuityEvent],
    mission_id: str,
) -> MissionFlowState:
    mission = require_mission(events, mission_id)
    brief = _require_brief(events, mission_id)
    counts = brief.to_dict()["counts"]
    open_mission_tasks = _open_mission_tasks(events, mission_id)
    steps = mission_step_records_from_events(events, mission_id)
    step_counts = _step_counts(steps)
    blockers = [
        f"open steward task {task.task_id}: {task.reason}"
        for task in open_mission_tasks
    ]
    approval_blockers = [
        f"step {step.step_id} requires approval before start"
        for step in steps
        if step.risk_level in {MissionStepRisk.MEDIUM, MissionStepRisk.HIGH}
        and step.approval_status != MissionStepApprovalStatus.APPROVED
        and step.execution_status
        in {
            MissionStepExecutionStatus.PROPOSED,
            MissionStepExecutionStatus.READY,
        }
    ]
    blockers.extend(approval_blockers)
    unresolved_evidence = [
        item
        for item in brief.items
        if item.kind == MissionItemKind.EVIDENCE
        and (
            item.status in {"requested", "unresolved", "missing"}
            or item.confidence in {"unknown", "low", "uncertain"}
        )
    ]
    failed_outcomes = [
        item
        for item in brief.items
        if item.kind == MissionItemKind.OUTCOME
        and (
            item.status in {"failed", "negative", "blocked"}
            or "fail" in item.reason.lower()
        )
    ]

    if mission.status == MissionStatus.COMPLETED:
        return _state(
            mission_id,
            MissionPhase.COMPLETED,
            counts,
            step_counts,
            [],
            [],
            "Archive or review lessons for future governed growth.",
        )
    if mission.status in {MissionStatus.PAUSED, MissionStatus.ARCHIVED}:
        return _state(
            mission_id,
            MissionPhase.BLOCKED,
            counts,
            step_counts,
            [f"mission status is {mission.status.value}"],
            [],
            "Reopen the mission before continuing.",
        )
    if blockers:
        return _state(
            mission_id,
            MissionPhase.BLOCKED,
            counts,
            step_counts,
            blockers,
            [task.task_id for task in open_mission_tasks],
            "Resolve mission review tasks before advancing.",
        )
    if step_counts["failed"] or step_counts["blocked"]:
        return _state(
            mission_id,
            MissionPhase.OUTCOME_REVIEW,
            counts,
            step_counts,
            [],
            [],
            "Review failed or blocked mission steps and add lessons.",
            ready=True,
        )
    if step_counts["running"]:
        return _state(
            mission_id,
            MissionPhase.INTERVENTION_READY,
            counts,
            step_counts,
            [],
            [],
            "Complete, fail, or block the running mission step.",
        )
    if step_counts["completed"]:
        return _state(
            mission_id,
            MissionPhase.OUTCOME_REVIEW,
            counts,
            step_counts,
            [],
            [],
            "Review completed step outcomes and extract lessons.",
            ready=True,
        )
    if step_counts["ready"]:
        return _state(
            mission_id,
            MissionPhase.INTERVENTION_READY,
            counts,
            step_counts,
            [],
            [],
            "Start an approved or low-risk mission step.",
            ready=True,
        )
    if step_counts["proposed"]:
        return _state(
            mission_id,
            MissionPhase.PLANNING,
            counts,
            step_counts,
            [],
            [],
            "Approve or refine proposed mission steps.",
        )
    if failed_outcomes:
        return _state(
            mission_id,
            MissionPhase.OUTCOME_REVIEW,
            counts,
            step_counts,
            [],
            [],
            "Review failed outcome and add a lesson or revised plan.",
            ready=True,
        )
    if counts.get(MissionItemKind.LESSON.value, 0):
        return _state(
            mission_id,
            MissionPhase.LESSON_REVIEW,
            counts,
            step_counts,
            [],
            [],
            "Review lesson growth candidates before completing the mission.",
            ready=True,
        )
    if counts.get(MissionItemKind.OUTCOME.value, 0):
        return _state(
            mission_id,
            MissionPhase.OUTCOME_REVIEW,
            counts,
            step_counts,
            [],
            [],
            "Extract lessons from the recorded outcome.",
            ready=True,
        )
    if counts.get(MissionItemKind.INTERVENTION.value, 0):
        return _state(
            mission_id,
            MissionPhase.INTERVENTION_READY,
            counts,
            step_counts,
            [],
            [],
            "Run or record the intervention outcome.",
            ready=True,
        )
    if counts.get(MissionItemKind.PLAN_STEP.value, 0) and counts.get(
        MissionItemKind.RISK.value,
        0,
    ):
        return _state(
            mission_id,
            MissionPhase.INTERVENTION_READY,
            counts,
            step_counts,
            [],
            [],
            "Select or record the intervention once steward risk review is clear.",
            ready=True,
        )
    if counts.get(MissionItemKind.PLAN_STEP.value, 0):
        return _state(
            mission_id,
            MissionPhase.PLANNING,
            counts,
            step_counts,
            [],
            [],
            "Add risk review before marking an intervention ready.",
        )
    if unresolved_evidence:
        return _state(
            mission_id,
            MissionPhase.EVIDENCE_REVIEW,
            counts,
            step_counts,
            ["mission evidence is unresolved or low confidence"],
            [],
            "Resolve evidence before planning intervention.",
        )
    if counts.get(MissionItemKind.EVIDENCE.value, 0) and counts.get(
        MissionItemKind.HYPOTHESIS.value,
        0,
    ):
        return _state(
            mission_id,
            MissionPhase.PLANNING,
            counts,
            step_counts,
            [],
            [],
            "Draft plan steps and risk review.",
            ready=True,
        )
    if counts.get(MissionItemKind.HYPOTHESIS.value, 0):
        return _state(
            mission_id,
            MissionPhase.EVIDENCE_REVIEW,
            counts,
            step_counts,
            [],
            [],
            "Add evidence for or against the hypothesis.",
        )
    return _state(
        mission_id,
        MissionPhase.INTAKE,
        counts,
        step_counts,
        [],
        [],
        "Add a first hypothesis that can be tested.",
    )


def mission_flows_from_events(events: list[ContinuityEvent]) -> list[MissionFlowState]:
    return [
        mission_flow_from_events(events, brief.mission.mission_id)
        for brief in mission_briefs_from_events(events)
    ]


def mission_flow(
    ledger: ContinuityLedger,
    mission_id: str,
) -> MissionFlowState:
    return mission_flow_from_events(ledger.events(), mission_id)


def _require_brief(events: list[ContinuityEvent], mission_id: str) -> MissionBrief:
    for brief in mission_briefs_from_events(events):
        if brief.mission.mission_id == mission_id:
            return brief
    raise ValueError(f"Mission not found: {mission_id}")


def _open_mission_tasks(events: list[ContinuityEvent], mission_id: str):
    return [
        task
        for task in active_reflection_tasks(events)
        if task.kind.value == "review_mission" and mission_id in task.reason
    ]


def _state(
    mission_id: str,
    phase: MissionPhase,
    counts: dict[str, int],
    step_counts: dict[str, int],
    blockers: list[str],
    task_ids: list[str],
    next_action: str,
    ready: bool = False,
) -> MissionFlowState:
    return MissionFlowState(
        mission_id=mission_id,
        phase=phase,
        blockers=blockers,
        next_action=next_action,
        counts=counts,
        step_counts=step_counts,
        open_task_ids=task_ids,
        ready_to_advance=ready and not blockers,
    )


def _step_counts(steps) -> dict[str, int]:
    counts = {
        "total": len(steps),
        "proposed": 0,
        "ready": 0,
        "running": 0,
        "completed": 0,
        "failed": 0,
        "blocked": 0,
        "approval_pending": 0,
        "approved": 0,
    }
    for step in steps:
        counts[step.execution_status.value] += 1
        if step.approval_status == MissionStepApprovalStatus.PENDING:
            counts["approval_pending"] += 1
        if step.approval_status == MissionStepApprovalStatus.APPROVED:
            counts["approved"] += 1
    return counts

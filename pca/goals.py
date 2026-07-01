from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .mission_flow import mission_flows_from_events
from .mission_steps import (
    MissionStepApprovalStatus,
    MissionStepExecutionStatus,
    mission_step_records_from_events,
)
from .missions import MissionStatus, mission_briefs_from_events
from .report import build_trace_report
from .skill_memory import accepted_skills_from_events
from .state import derive_current_claim
from .steward_inbox import steward_inbox


class GoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class GoalHistoryEntry:
    action: str
    reason: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(cls, action: str, reason: str = "") -> "GoalHistoryEntry":
        return cls(action=action, reason=reason)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalHistoryEntry":
        return cls(
            action=str(data["action"]),
            reason=str(data.get("reason", "")),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class GoalRecord:
    goal_id: str
    identity_id: str
    title: str
    purpose: str
    success_criteria: str
    priority: str
    status: GoalStatus
    linked_mission_ids: list[str] = field(default_factory=list)
    linked_evidence_ids: list[str] = field(default_factory=list)
    linked_skill_ids: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_recommended_action: str = ""
    review_state: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    history: list[GoalHistoryEntry] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        identity_id: str,
        title: str,
        purpose: str,
        success_criteria: str,
        priority: str = "medium",
        next_recommended_action: str = "",
        review_state: str = "pending",
        reason: str = "",
    ) -> "GoalRecord":
        return cls(
            goal_id=f"goal_{uuid.uuid4()}",
            identity_id=identity_id,
            title=title,
            purpose=purpose,
            success_criteria=success_criteria,
            priority=priority,
            status=GoalStatus.ACTIVE,
            next_recommended_action=next_recommended_action
            or "Open or link a mission that advances this goal.",
            review_state=review_state,
            history=[GoalHistoryEntry.create("created", reason)],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GoalRecord":
        return cls(
            goal_id=str(data["goal_id"]),
            identity_id=str(data["identity_id"]),
            title=str(data["title"]),
            purpose=str(data.get("purpose", "")),
            success_criteria=str(data.get("success_criteria", "")),
            priority=str(data.get("priority", "medium")),
            status=GoalStatus(str(data.get("status", GoalStatus.ACTIVE.value))),
            linked_mission_ids=[str(item) for item in data.get("linked_mission_ids", [])],
            linked_evidence_ids=[str(item) for item in data.get("linked_evidence_ids", [])],
            linked_skill_ids=[str(item) for item in data.get("linked_skill_ids", [])],
            blockers=[str(item) for item in data.get("blockers", [])],
            next_recommended_action=str(data.get("next_recommended_action", "")),
            review_state=str(data.get("review_state", "pending")),
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
            history=[
                GoalHistoryEntry.from_dict(item)
                for item in data.get("history", [])
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "identity_id": self.identity_id,
            "title": self.title,
            "purpose": self.purpose,
            "success_criteria": self.success_criteria,
            "priority": self.priority,
            "status": self.status.value,
            "linked_mission_ids": self.linked_mission_ids,
            "linked_evidence_ids": self.linked_evidence_ids,
            "linked_skill_ids": self.linked_skill_ids,
            "blockers": self.blockers,
            "next_recommended_action": self.next_recommended_action,
            "review_state": self.review_state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": [entry.to_dict() for entry in self.history],
        }

    def with_update(
        self,
        *,
        status: str | GoalStatus | None = None,
        linked_mission_ids: list[str] | None = None,
        linked_evidence_ids: list[str] | None = None,
        linked_skill_ids: list[str] | None = None,
        blockers: list[str] | None = None,
        next_recommended_action: str | None = None,
        review_state: str | None = None,
        action: str,
        reason: str = "",
    ) -> "GoalRecord":
        return GoalRecord(
            goal_id=self.goal_id,
            identity_id=self.identity_id,
            title=self.title,
            purpose=self.purpose,
            success_criteria=self.success_criteria,
            priority=self.priority,
            status=GoalStatus(str(status)) if status is not None else self.status,
            linked_mission_ids=linked_mission_ids
            if linked_mission_ids is not None
            else self.linked_mission_ids,
            linked_evidence_ids=linked_evidence_ids
            if linked_evidence_ids is not None
            else self.linked_evidence_ids,
            linked_skill_ids=linked_skill_ids
            if linked_skill_ids is not None
            else self.linked_skill_ids,
            blockers=blockers if blockers is not None else self.blockers,
            next_recommended_action=(
                next_recommended_action
                if next_recommended_action is not None
                else self.next_recommended_action
            ),
            review_state=review_state if review_state is not None else self.review_state,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            history=self.history + [GoalHistoryEntry.create(action, reason)],
        )


def create_goal_record(
    ledger: ContinuityLedger,
    identity_id: str,
    title: str,
    purpose: str,
    success_criteria: str,
    priority: str = "medium",
    next_recommended_action: str = "",
    review_state: str = "pending",
    reason: str = "",
) -> GoalRecord:
    record = GoalRecord.create(
        identity_id=identity_id,
        title=title,
        purpose=purpose,
        success_criteria=success_criteria,
        priority=priority,
        next_recommended_action=next_recommended_action,
        review_state=review_state,
        reason=reason,
    )
    ledger.append("goal.created", identity_id, record.to_dict())
    return record


def update_goal_status(
    ledger: ContinuityLedger,
    identity_id: str,
    goal_id: str,
    status: str | GoalStatus,
    reason: str = "",
) -> GoalRecord:
    goal = require_goal(ledger.events(), goal_id)
    updated = goal.with_update(
        status=status,
        action=f"status_{str(status)}",
        reason=reason,
    )
    ledger.append("goal.status_updated", identity_id, updated.to_dict())
    return updated


def link_goal_mission(
    ledger: ContinuityLedger,
    identity_id: str,
    goal_id: str,
    mission_id: str,
    reason: str = "",
) -> GoalRecord:
    goal = require_goal(ledger.events(), goal_id)
    linked = _append_unique(goal.linked_mission_ids, mission_id)
    updated = goal.with_update(
        linked_mission_ids=linked,
        next_recommended_action="Continue the linked mission or review its blockers.",
        action="linked_mission",
        reason=reason,
    )
    ledger.append("goal.mission_linked", identity_id, updated.to_dict())
    return updated


def add_goal_blocker(
    ledger: ContinuityLedger,
    identity_id: str,
    goal_id: str,
    blocker: str,
    reason: str = "",
) -> GoalRecord:
    goal = require_goal(ledger.events(), goal_id)
    updated = goal.with_update(
        blockers=_append_unique(goal.blockers, blocker),
        next_recommended_action="Resolve or route the active goal blocker.",
        review_state="review_required",
        action="blocker_added",
        reason=reason or blocker,
    )
    ledger.append("goal.blocker_added", identity_id, updated.to_dict())
    return updated


def goal_records_from_events(events: list[ContinuityEvent]) -> list[GoalRecord]:
    records: dict[str, GoalRecord] = {}
    for event in events:
        if event.event_type in {
            "goal.created",
            "goal.status_updated",
            "goal.mission_linked",
            "goal.blocker_added",
        }:
            record = GoalRecord.from_dict(event.payload)
            records[record.goal_id] = record
    return list(records.values())


def active_goal_records(events: list[ContinuityEvent]) -> list[GoalRecord]:
    return [
        goal
        for goal in goal_records_from_events(events)
        if goal.status == GoalStatus.ACTIVE
    ]


def require_goal(events: list[ContinuityEvent], goal_id: str) -> GoalRecord:
    for goal in goal_records_from_events(events):
        if goal.goal_id == goal_id:
            return goal
    raise ValueError(f"Goal not found: {goal_id}")


def daily_plan(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    events = ledger.events()
    goals = active_goal_records(events)
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    focus_goal = sorted(
        goals,
        key=lambda goal: (priority_order.get(goal.priority, 2), goal.created_at),
    )[0] if goals else None
    missions = mission_briefs_from_events(events)
    active_missions = [
        brief for brief in missions if brief.mission.status == MissionStatus.OPEN
    ]
    flows = {flow.mission_id: flow for flow in mission_flows_from_events(events)}
    inbox_items = steward_inbox(ledger)
    high_inbox = [
        item for item in inbox_items if item.severity in {"high", "critical"}
    ]
    steps = mission_step_records_from_events(events)
    blocked_steps = [
        step
        for step in steps
        if step.execution_status == MissionStepExecutionStatus.BLOCKED
    ]
    pending_approvals = [
        step for step in steps if step.approval_status == MissionStepApprovalStatus.PENDING
    ]
    ready_steps = [
        step for step in steps if step.execution_status == MissionStepExecutionStatus.READY
    ]
    claim, _, _ = derive_current_claim(ledger, manifest)
    report = build_trace_report(ledger, manifest)
    evidence_needed = _evidence_needed_count(events)
    accepted_skills = accepted_skills_from_events(events)
    blockers = _plan_blockers(
        focus_goal=focus_goal,
        high_inbox_count=len(high_inbox),
        blocked_step_count=len(blocked_steps),
        pending_approval_count=len(pending_approvals),
        evidence_needed=evidence_needed,
        continuity_state=claim,
        stale_reasons=[str(item) for item in report.summary.get("reasons", [])],
    )
    best_next_action = _best_next_action(
        focus_goal=focus_goal,
        active_mission_count=len(active_missions),
        high_inbox_count=len(high_inbox),
        blocked_step_count=len(blocked_steps),
        pending_approval_count=len(pending_approvals),
        ready_step_count=len(ready_steps),
        evidence_needed=evidence_needed,
        continuity_state=claim,
    )
    steward_review_needed = [
        item.to_dict() for item in inbox_items[:5]
    ]
    if focus_goal and focus_goal.blockers:
        steward_review_needed.append(
            {
                "source_type": "goal_blocker",
                "severity": "medium",
                "title": focus_goal.title,
                "reason": focus_goal.blockers[0],
            }
        )
    what_not_to_do = _what_not_to_do(claim)
    current_focus = (
        f"Goal: {focus_goal.title}"
        if focus_goal
        else (
            f"Mission: {active_missions[-1].mission.title}"
            if active_missions
            else "No active goal or mission selected."
        )
    )
    linked_missions = []
    if focus_goal:
        linked_missions = [
            {
                "mission_id": brief.mission.mission_id,
                "title": brief.mission.title,
                "status": brief.mission.status.value,
                "phase": flows.get(brief.mission.mission_id).phase.value
                if flows.get(brief.mission.mission_id)
                else "unknown",
            }
            for brief in active_missions
            if brief.mission.mission_id in focus_goal.linked_mission_ids
        ]
    return {
        "current_focus": current_focus,
        "best_next_safe_action": best_next_action,
        "blockers": blockers,
        "steward_review_needed": steward_review_needed,
        "what_not_to_do_yet": what_not_to_do,
        "continuity_state": claim,
        "active_goal_count": len(goals),
        "active_mission_count": len(active_missions),
        "blocked_step_count": len(blocked_steps),
        "pending_tool_approvals": len(pending_approvals),
        "ready_step_count": len(ready_steps),
        "evidence_needed_count": evidence_needed,
        "accepted_skill_count": len(accepted_skills),
        "focus_goal": focus_goal.to_dict() if focus_goal else None,
        "linked_missions": linked_missions,
    }


def render_daily_plan_text(plan: dict[str, Any]) -> str:
    lines = [
        "Daily Plan",
        f"Current focus: {plan['current_focus']}",
        f"Best next safe action: {plan['best_next_safe_action']}",
        f"Continuity: {plan['continuity_state']}",
        "",
        "Blockers:",
    ]
    lines.extend(f"- {item}" for item in plan["blockers"] or ["none"])
    lines.extend(["", "Steward review needed:"])
    review = plan["steward_review_needed"]
    if review:
        lines.extend(
            f"- {item.get('severity', 'unknown')} / {item.get('source_type', 'review')} / {item.get('reason', '')}"
            for item in review
        )
    else:
        lines.append("- none")
    lines.extend(["", "What not to do yet:"])
    lines.extend(f"- {item}" for item in plan["what_not_to_do_yet"])
    return "\n".join(lines)


def _append_unique(items: list[str], value: str) -> list[str]:
    if value in items:
        return items
    return items + [value]


def _evidence_needed_count(events: list[ContinuityEvent]) -> int:
    return sum(
        1
        for event in events
        if event.event_type in {
            "lucien.memory_evidence_requested",
            "evidence.requested",
        }
    )


def _plan_blockers(
    *,
    focus_goal: GoalRecord | None,
    high_inbox_count: int,
    blocked_step_count: int,
    pending_approval_count: int,
    evidence_needed: int,
    continuity_state: str,
    stale_reasons: list[str],
) -> list[str]:
    blockers: list[str] = []
    if focus_goal:
        blockers.extend(focus_goal.blockers)
    if continuity_state != "certified_continuity":
        blockers.append(f"continuity is {continuity_state}")
        blockers.extend(stale_reasons[:2])
    if high_inbox_count:
        blockers.append(f"{high_inbox_count} high-priority steward item(s)")
    if blocked_step_count:
        blockers.append(f"{blocked_step_count} blocked mission step(s)")
    if pending_approval_count:
        blockers.append(f"{pending_approval_count} step(s) need approval")
    if evidence_needed:
        blockers.append(f"{evidence_needed} evidence request(s) are open")
    return blockers


def _best_next_action(
    *,
    focus_goal: GoalRecord | None,
    active_mission_count: int,
    high_inbox_count: int,
    blocked_step_count: int,
    pending_approval_count: int,
    ready_step_count: int,
    evidence_needed: int,
    continuity_state: str,
) -> str:
    if continuity_state != "certified_continuity":
        return "Review continuity blockers before high-impact work."
    if high_inbox_count:
        return "Review high-priority steward inbox items."
    if focus_goal and focus_goal.blockers:
        return "Resolve the active goal blocker."
    if blocked_step_count:
        return "Review blocked mission steps."
    if pending_approval_count:
        return "Approve or reject pending mission steps."
    if ready_step_count:
        return "Start or dry-run the next ready mission step."
    if evidence_needed:
        return "Add or review evidence for open evidence requests."
    if focus_goal and not focus_goal.linked_mission_ids:
        return "Propose a mission that advances the active goal."
    if active_mission_count:
        return "Ask Lucien to suggest the next safe mission step."
    if focus_goal:
        return focus_goal.next_recommended_action
    return "Create a goal or open a mission before using Lucien for work."


def _what_not_to_do(continuity_state: str) -> list[str]:
    items = [
        "Do not auto-execute tools from the daily plan.",
        "Do not accept memories, skills, evidence, or goals without steward review.",
    ]
    if continuity_state != "certified_continuity":
        items.append("Do not perform high-impact identity or tool actions until continuity review is resolved.")
    return items

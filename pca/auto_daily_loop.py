from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .autonomy_queue import (
    AutonomyQueueItem,
    autonomy_queue_items_from_events,
    propose_autonomy_action,
)
from .coherence_seed import (
    COHERENCE_PHYSICS_SEED_SPECS,
    seed_coherence_physics_goals,
)
from .daily_command_center import daily_command_center
from .goals import active_goal_records, daily_plan
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .missions import MissionStatus, mission_briefs_from_events


@dataclass(frozen=True)
class AutoDailyResearchLoopRecord:
    loop_id: str
    identity_id: str
    loop_date: str
    status: str
    focus_goal_id: str | None = None
    focus_goal_title: str | None = None
    mission_id: str | None = None
    mission_title: str | None = None
    proposed_item_ids: list[str] = field(default_factory=list)
    briefing: str = ""
    recommended_first_action: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        loop_date: str,
        status: str,
        focus_goal_id: str | None = None,
        focus_goal_title: str | None = None,
        mission_id: str | None = None,
        mission_title: str | None = None,
        proposed_item_ids: list[str] | None = None,
        briefing: str = "",
        recommended_first_action: str = "",
        reason: str = "",
    ) -> "AutoDailyResearchLoopRecord":
        return cls(
            loop_id=f"daily_loop_{uuid.uuid4()}",
            identity_id=identity_id,
            loop_date=loop_date,
            status=status,
            focus_goal_id=focus_goal_id,
            focus_goal_title=focus_goal_title,
            mission_id=mission_id,
            mission_title=mission_title,
            proposed_item_ids=proposed_item_ids or [],
            briefing=briefing,
            recommended_first_action=recommended_first_action,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutoDailyResearchLoopRecord":
        return cls(
            loop_id=str(data["loop_id"]),
            identity_id=str(data["identity_id"]),
            loop_date=str(data["loop_date"]),
            status=str(data.get("status", "prepared")),
            focus_goal_id=data.get("focus_goal_id"),
            focus_goal_title=data.get("focus_goal_title"),
            mission_id=data.get("mission_id"),
            mission_title=data.get("mission_title"),
            proposed_item_ids=[str(item) for item in data.get("proposed_item_ids", [])],
            briefing=str(data.get("briefing", "")),
            recommended_first_action=str(data.get("recommended_first_action", "")),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "identity_id": self.identity_id,
            "loop_date": self.loop_date,
            "status": self.status,
            "focus_goal_id": self.focus_goal_id,
            "focus_goal_title": self.focus_goal_title,
            "mission_id": self.mission_id,
            "mission_title": self.mission_title,
            "proposed_item_ids": self.proposed_item_ids,
            "briefing": self.briefing,
            "recommended_first_action": self.recommended_first_action,
            "created_at": self.created_at,
            "reason": self.reason,
        }


def run_auto_daily_research_loop(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    loop_date: str | None = None,
    seed_coherence: bool = True,
    force: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    loop_date = loop_date or datetime.now(timezone.utc).date().isoformat()
    previous = latest_auto_daily_research_loop(ledger.events(), loop_date)
    if previous and not force:
        return {
            "record": previous.to_dict(),
            "proposed_items": [],
            "seeded": False,
            "already_prepared": True,
        }

    seeded = False
    if seed_coherence and not _has_coherence_goal(ledger):
        seed_coherence_physics_goals(ledger, manifest)
        seeded = True

    daily = daily_command_center(ledger, manifest)
    plan = daily_plan(ledger, manifest)
    focus_goal = plan.get("focus_goal") or _first_active_goal(ledger)
    focus_mission = _focus_mission(ledger, focus_goal, daily)
    proposed = _propose_daily_actions(
        ledger=ledger,
        manifest=manifest,
        loop_date=loop_date,
        focus_goal=focus_goal,
        focus_mission=focus_mission,
        daily=daily,
        project_root=Path(project_root),
    )
    record = AutoDailyResearchLoopRecord.create(
        identity_id=manifest.system_id,
        loop_date=loop_date,
        status="prepared",
        focus_goal_id=focus_goal.get("goal_id") if focus_goal else None,
        focus_goal_title=focus_goal.get("title") if focus_goal else None,
        mission_id=focus_mission.get("mission_id") if focus_mission else None,
        mission_title=focus_mission.get("title") if focus_mission else None,
        proposed_item_ids=[item.item_id for item in proposed],
        briefing=str(daily.get("briefing", "")),
        recommended_first_action=str(daily.get("recommended_first_action", "")),
        reason=reason or "auto daily research loop prepared launch agenda",
    )
    ledger.append("daily_research.loop_ran", manifest.system_id, record.to_dict())
    return {
        "record": record.to_dict(),
        "proposed_items": [item.to_dict() for item in proposed],
        "seeded": seeded,
        "already_prepared": False,
    }


def auto_daily_research_loop_records_from_events(
    events: list[ContinuityEvent],
) -> list[AutoDailyResearchLoopRecord]:
    return [
        AutoDailyResearchLoopRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "daily_research.loop_ran"
    ]


def latest_auto_daily_research_loop(
    events: list[ContinuityEvent],
    loop_date: str | None = None,
) -> AutoDailyResearchLoopRecord | None:
    records = auto_daily_research_loop_records_from_events(events)
    if loop_date:
        records = [record for record in records if record.loop_date == loop_date]
    if not records:
        return None
    return sorted(records, key=lambda record: (record.created_at, record.loop_id))[-1]


def render_auto_daily_research_loop_text(result: dict[str, Any]) -> str:
    record = result["record"]
    lines = [
        "Auto Daily Research Loop",
        f"status: {'already prepared' if result.get('already_prepared') else record['status']}",
        f"date: {record['loop_date']}",
        f"focus goal: {record.get('focus_goal_title') or 'none'}",
        f"mission: {record.get('mission_title') or 'none'}",
        f"seeded coherence goals: {bool(result.get('seeded'))}",
        f"proposed actions: {len(result.get('proposed_items') or [])}",
        f"next: {record.get('recommended_first_action') or 'none'}",
    ]
    for item in result.get("proposed_items") or []:
        lines.append(f"- {item['action_type']} / {item['risk']} / {item['reason']}")
    return "\n".join(lines)


def _propose_daily_actions(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    loop_date: str,
    focus_goal: dict[str, Any] | None,
    focus_mission: dict[str, Any] | None,
    daily: dict[str, Any],
    project_root: Path,
) -> list[AutonomyQueueItem]:
    specs: list[tuple[str, str, dict[str, Any]]] = [
        (
            "daily_plan",
            "Prepare today's governed research plan.",
            {"loop_date": loop_date},
        ),
        (
            "project_brief",
            "Summarize current project state before research work.",
            {"loop_date": loop_date, "project_root": str(project_root)},
        ),
    ]
    if int(daily.get("open_steward_inbox_count", 0) or 0) > 0:
        specs.append(
            (
                "review_inbox",
                "Review open steward pressure before deep research.",
                {"loop_date": loop_date},
            )
        )
    if focus_goal:
        specs.append(
            (
                "next_build",
                "Recommend the next governed build or research move.",
                {"loop_date": loop_date, "goal_id": focus_goal.get("goal_id")},
            )
        )
    if focus_mission:
        specs.append(
            (
                "propose_step",
                "Ask Lucien to propose the next safe mission step for the focus mission.",
                {"loop_date": loop_date, "mission_id": focus_mission.get("mission_id")},
            )
        )

    proposed: list[AutonomyQueueItem] = []
    for action_type, reason, payload in specs:
        if _has_daily_action(ledger, loop_date, action_type, payload):
            continue
        proposed.append(
            propose_autonomy_action(
                ledger,
                manifest.system_id,
                action_type,
                reason=reason,
                payload=payload,
                proposed_by="auto_daily_research_loop",
            )
        )
    return proposed


def _has_daily_action(
    ledger: ContinuityLedger,
    loop_date: str,
    action_type: str,
    payload: dict[str, Any],
) -> bool:
    for item in autonomy_queue_items_from_events(ledger.events()):
        item_payload = item.payload or {}
        if item.action_type.value != action_type:
            continue
        if item_payload.get("loop_date") != loop_date:
            continue
        if payload.get("mission_id") and item_payload.get("mission_id") != payload.get("mission_id"):
            continue
        if payload.get("goal_id") and item_payload.get("goal_id") != payload.get("goal_id"):
            continue
        return True
    return False


def _has_coherence_goal(ledger: ContinuityLedger) -> bool:
    titles = {goal.title for goal in active_goal_records(ledger.events())}
    return any(spec.title in titles for spec in COHERENCE_PHYSICS_SEED_SPECS)


def _first_active_goal(ledger: ContinuityLedger) -> dict[str, Any] | None:
    goals = active_goal_records(ledger.events())
    if not goals:
        return None
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    goal = sorted(goals, key=lambda item: (priority.get(item.priority, 4), item.created_at))[0]
    return goal.to_dict()


def _focus_mission(
    ledger: ContinuityLedger,
    focus_goal: dict[str, Any] | None,
    daily: dict[str, Any],
) -> dict[str, Any] | None:
    briefs = mission_briefs_from_events(ledger.events())
    if focus_goal:
        linked_ids = set(focus_goal.get("linked_mission_ids") or [])
        for brief in briefs:
            if brief.mission.mission_id in linked_ids:
                return _mission_summary(brief)
    active = daily.get("current_active_mission")
    if active:
        return active
    for brief in briefs:
        if brief.mission.status == MissionStatus.OPEN:
            return _mission_summary(brief)
    return None


def _mission_summary(brief) -> dict[str, Any]:
    return {
        "mission_id": brief.mission.mission_id,
        "title": brief.mission.title,
        "status": brief.mission.status.value,
        "item_count": len(brief.items),
    }

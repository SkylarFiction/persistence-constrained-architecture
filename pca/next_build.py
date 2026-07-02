from __future__ import annotations

from typing import Any

from .checkpoint_story import checkpoint_story
from .commit_readiness import commit_readiness
from .goals import active_goal_records, daily_plan
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_flow import mission_flows_from_events
from .missions import MissionStatus, mission_briefs_from_events
from .steward_inbox import steward_inbox


def next_governed_build(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    events = ledger.events()
    readiness = commit_readiness()
    story = checkpoint_story()
    plan = daily_plan(ledger, manifest)
    inbox_items = steward_inbox(ledger)
    high_items = [item for item in inbox_items if item.severity in {"high", "critical"}]
    active_goals = active_goal_records(events)
    mission_briefs = [
        brief
        for brief in mission_briefs_from_events(events)
        if brief.mission.status == MissionStatus.OPEN
    ]
    flows = {flow.mission_id: flow for flow in mission_flows_from_events(events)}
    blocked_missions = [
        brief
        for brief in mission_briefs
        if flows.get(brief.mission.mission_id)
        and (
            flows[brief.mission.mission_id].blockers
            or flows[brief.mission.mission_id].phase.value == "blocked"
        )
    ]
    if readiness.get("state") in {"needs_review", "blocked"}:
        proposal = _finish_current_checkpoint(readiness, story)
    elif high_items:
        proposal = _clear_steward_pressure(high_items)
    elif blocked_missions:
        proposal = _unblock_mission(blocked_missions[0])
    elif mission_briefs:
        proposal = _advance_active_mission(mission_briefs[0], plan)
    elif active_goals:
        proposal = _open_goal_mission(active_goals[0])
    else:
        proposal = _create_foundation_mission()
    proposal["context"] = {
        "readiness_state": readiness.get("state"),
        "checkpoint_title": story.get("title"),
        "open_steward_items": len(inbox_items),
        "high_priority_steward_items": len(high_items),
        "active_goal_count": len(active_goals),
        "active_mission_count": len(mission_briefs),
        "blocked_mission_count": len(blocked_missions),
    }
    proposal["does_not_execute"] = True
    return proposal


def render_next_governed_build_text(proposal: dict[str, Any]) -> str:
    lines = [
        "Next Governed Build",
        proposal.get("title", "No build proposal available."),
        "",
        f"Reason: {proposal.get('reason', 'none')}",
        f"Expected impact: {proposal.get('expected_impact', 'none')}",
        f"Risk: {proposal.get('risk', 'unknown')}",
        f"Suggested first step: {proposal.get('suggested_first_step', 'none')}",
    ]
    for title, key in [
        ("Checks", "checks"),
        ("Likely files/modules", "likely_touches"),
        ("Do not do yet", "do_not_do_yet"),
    ]:
        values = proposal.get(key) or []
        if values:
            lines.extend(["", f"{title}:"])
            lines.extend(f"- {item}" for item in values)
    context = proposal.get("context") or {}
    if context:
        lines.extend(
            [
                "",
                "Context:",
                f"- Readiness: {context.get('readiness_state', 'unknown')}",
                f"- Steward inbox: {context.get('open_steward_items', 0)} open / {context.get('high_priority_steward_items', 0)} high",
                f"- Goals: {context.get('active_goal_count', 0)} active",
                f"- Missions: {context.get('active_mission_count', 0)} active / {context.get('blocked_mission_count', 0)} blocked",
            ]
        )
    return "\n".join(lines)


def _finish_current_checkpoint(
    readiness: dict[str, Any],
    story: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": "Finish the current checkpoint safely",
        "reason": "Local build state is not ready for a new feature yet.",
        "expected_impact": "Keeps Lucien's repo history clean and prevents generated or unreviewed files from slipping into a checkpoint.",
        "risk": "low",
        "suggested_first_step": (readiness.get("required_actions") or ["Review commit readiness."])[0],
        "checks": readiness.get("recommended_checks") or ["python3 scripts/check_all.py"],
        "likely_touches": ["current changed files only"],
        "do_not_do_yet": [
            "Do not start another large feature until readiness is clear.",
            "Do not push until the checkpoint story says it is safe.",
        ],
        "source": story.get("title", ""),
    }


def _clear_steward_pressure(high_items: list[Any]) -> dict[str, Any]:
    item = high_items[0]
    return {
        "title": "Clear high-priority steward pressure",
        "reason": f"{len(high_items)} high-priority steward item(s) are open.",
        "expected_impact": "Restores cleaner continuity conditions before adding more autonomy.",
        "risk": "low",
        "suggested_first_step": f"Review `{item.inbox_id}` from the Steward Inbox.",
        "checks": ["python3 pca_cli.py steward-inbox --high"],
        "likely_touches": ["ledger review records"],
        "do_not_do_yet": ["Do not auto-accept memory, skills, evidence, or growth."],
    }


def _unblock_mission(brief: Any) -> dict[str, Any]:
    return {
        "title": f"Unblock mission: {brief.mission.title}",
        "reason": "A mission is blocked, so adding new work would increase unresolved pressure.",
        "expected_impact": "Moves existing governed work back into a recoverable phase.",
        "risk": "low-medium",
        "suggested_first_step": "Inspect mission blockers and create one bounded resolution step.",
        "checks": ["python3 pca_cli.py daily", "python3 pca_cli.py steward-inbox"],
        "likely_touches": ["pca/missions.py", "pca/mission_flow.py", "pca/live_chat.py"],
        "do_not_do_yet": ["Do not execute tools for blocked mission steps without approval."],
    }


def _advance_active_mission(brief: Any, plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": f"Advance mission: {brief.mission.title}",
        "reason": "An active mission exists and can be advanced with a governed next step.",
        "expected_impact": "Turns Lucien's mission state into visible progress without bypassing approval gates.",
        "risk": "low-medium",
        "suggested_first_step": plan.get("best_next_safe_action")
        or "Propose one low-risk mission step.",
        "checks": ["python3 pca_cli.py daily-plan", "python3 scripts/check_all.py"],
        "likely_touches": ["pca/mission_steps.py", "pca/live_chat.py", "tests/test_continuity.py"],
        "do_not_do_yet": ["Do not run medium/high-risk mission steps automatically."],
    }


def _open_goal_mission(goal: Any) -> dict[str, Any]:
    return {
        "title": f"Open a mission for goal: {goal.title}",
        "reason": "A goal exists without enough active mission pressure.",
        "expected_impact": "Converts a durable direction into governed work.",
        "risk": "low",
        "suggested_first_step": goal.next_recommended_action
        or "Open a mission linked to this goal.",
        "checks": ["python3 pca_cli.py daily", "python3 pca_cli.py workbench-status"],
        "likely_touches": ["ledger mission records", "live workbench state"],
        "do_not_do_yet": ["Do not treat a goal as completed until mission evidence exists."],
    }


def _create_foundation_mission() -> dict[str, Any]:
    return {
        "title": "Create the next Lucien foundation mission",
        "reason": "No active mission or goal is currently steering the build.",
        "expected_impact": "Gives Lucien a governed direction before new features are added.",
        "risk": "low",
        "suggested_first_step": "Open a mission named `Improve Lucien daily usefulness`.",
        "checks": ["python3 pca_cli.py daily", "python3 pca_cli.py project-brief"],
        "likely_touches": ["mission ledger records"],
        "do_not_do_yet": ["Do not add autonomous execution until a mission and approval path exist."],
    }

from __future__ import annotations

from typing import Any

from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_flow import mission_flows_from_events
from .missions import MissionStatus, mission_briefs_from_events
from .model_adapter import model_environment_diagnostic
from .output_gate import OutputGate
from .report import build_trace_report
from .state import derive_current_claim
from .steward_inbox import steward_inbox


def workbench_status(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    events = ledger.events()
    claim, _, _ = derive_current_claim(ledger, manifest)
    gate = OutputGate().evaluate(claim)
    report = build_trace_report(ledger, manifest)
    model_adapter = model_environment_diagnostic()
    model_usage = _model_usage_summary(events)
    inbox_items = steward_inbox(ledger)
    high_priority = [
        item for item in inbox_items if item.severity in {"high", "critical"}
    ]
    mission_briefs = mission_briefs_from_events(events)
    active_briefs = [
        brief
        for brief in mission_briefs
        if brief.mission.status == MissionStatus.OPEN
    ]
    flows = {flow.mission_id: flow for flow in mission_flows_from_events(events)}
    active_brief = active_briefs[-1] if active_briefs else None
    active_flow = (
        flows.get(active_brief.mission.mission_id)
        if active_brief is not None
        else None
    )
    blocked_count = sum(
        1
        for flow in flows.values()
        if flow.phase.value == "blocked" or flow.blockers
    )
    active_mission = (
        {
            "mission_id": active_brief.mission.mission_id,
            "title": active_brief.mission.title,
            "status": active_brief.mission.status.value,
            "phase": active_flow.phase.value if active_flow else "unknown",
            "ready_to_advance": bool(active_flow.ready_to_advance) if active_flow else False,
            "blockers": active_flow.blockers if active_flow else [],
            "blocker_count": len(active_flow.blockers) if active_flow else 0,
            "next_action": active_flow.next_action if active_flow else "",
            "open_task_ids": active_flow.open_task_ids if active_flow else [],
            "item_counts": active_brief.to_dict()["counts"],
        }
        if active_brief is not None
        else None
    )
    return {
        "continuity_state": claim,
        "output_gate_mode": gate.mode.value,
        "model_mode": model_adapter.get("default_model_mode", "serious_only"),
        "latest_provider": model_usage["latest_provider"],
        "estimated_session_cost_usd": model_usage["estimated_session_cost_usd"],
        "active_mission_count": len(active_briefs),
        "blocked_mission_count": blocked_count,
        "open_steward_inbox_count": len(inbox_items),
        "high_priority_inbox_count": len(high_priority),
        "active_mission": active_mission,
        "recommended_next_action": _recommended_next_action(
            active_mission,
            len(inbox_items),
            len(high_priority),
            blocked_count,
        ),
        "summary": {
            "event_count": report.summary.get("event_count", 0),
            "current_recovery_status": report.summary.get("current_recovery_status"),
            "identity_state": report.summary.get("identity_state"),
        },
    }


def _recommended_next_action(
    active_mission: dict[str, Any] | None,
    inbox_count: int,
    high_priority_count: int,
    blocked_mission_count: int,
) -> str:
    if active_mission is None:
        return "Open a mission before using Lucien for work."
    if high_priority_count:
        return "Review high-priority Steward Inbox items before advancing work."
    if blocked_mission_count or active_mission.get("blocker_count", 0):
        return "Clear mission blockers or related Steward Inbox items."
    next_action = str(active_mission.get("next_action", "")).strip()
    if next_action:
        return next_action
    if inbox_count:
        return "Review open Steward Inbox items."
    return "Continue the active mission."


def _model_usage_summary(events) -> dict[str, Any]:
    model_events = [
        event
        for event in events
        if event.event_type == "chat.model_response_generated"
    ]
    openai_events = [
        event
        for event in model_events
        if event.payload.get("provider") == "openai"
    ]
    session_cost = sum(
        float(event.payload.get("estimated_cost_usd") or 0.0)
        for event in openai_events
    )
    latest = model_events[-1].payload if model_events else {}
    return {
        "estimated_session_cost_usd": round(session_cost, 6),
        "latest_provider": latest.get("provider", "none"),
    }

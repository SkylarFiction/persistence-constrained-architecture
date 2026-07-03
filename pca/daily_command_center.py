from __future__ import annotations

from typing import Any

from .ledger import ContinuityLedger
from .learning_review import learning_review_records_from_events
from .manifest import IdentityManifest
from .goals import active_goal_records, daily_plan
from .mission_flow import mission_flows_from_events
from .mission_steps import (
    MissionStepApprovalStatus,
    MissionStepExecutionStatus,
    mission_step_records_from_events,
)
from .missions import MissionStatus, mission_briefs_from_events
from .model_adapter import model_environment_diagnostic
from .output_gate import OutputGate
from .report import build_trace_report
from .skill_memory import skill_suggestions_for_mission
from .state import derive_current_claim
from .steward_inbox import steward_inbox
from .workbench import workbench_status


def daily_command_center(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    events = ledger.events()
    report = build_trace_report(ledger, manifest)
    workbench = workbench_status(ledger, manifest)
    plan = daily_plan(ledger, manifest)
    claim, _, _ = derive_current_claim(ledger, manifest)
    gate = OutputGate().evaluate(claim)
    model_adapter = model_environment_diagnostic()
    inbox_items = steward_inbox(ledger)
    high_priority_items = [
        item for item in inbox_items if item.severity in {"high", "critical"}
    ]
    mission_briefs = mission_briefs_from_events(events)
    active_briefs = [
        brief
        for brief in mission_briefs
        if brief.mission.status == MissionStatus.OPEN
    ]
    flows = {flow.mission_id: flow for flow in mission_flows_from_events(events)}
    active_mission = workbench.get("active_mission")
    steps = mission_step_records_from_events(events)
    ready_steps = [
        step for step in steps if step.execution_status == MissionStepExecutionStatus.READY
    ]
    pending_tool_approvals = [
        step
        for step in steps
        if step.approval_status == MissionStepApprovalStatus.PENDING
    ]
    evidence_needed_count = _evidence_needed_count(events)
    skill_suggestions = (
        skill_suggestions_for_mission(events, active_mission["mission_id"])
        if active_mission
        else []
    )
    active_goals = active_goal_records(events)
    focus_goal = plan.get("focus_goal")
    blocked_mission_count = sum(
        1
        for flow in flows.values()
        if flow.phase.value == "blocked" or flow.blockers
    )
    conflicts_count = int(report.summary.get("unresolved_growth_conflict_count", 0) or 0)
    recovery_state = report.summary.get("current_recovery_status")
    briefing = _briefing(
        continuity_state=claim,
        active_mission=active_mission,
        open_inbox_count=len(inbox_items),
        high_priority_count=len(high_priority_items),
        blocked_mission_count=blocked_mission_count,
        ready_step_count=len(ready_steps),
        evidence_needed_count=evidence_needed_count,
        local_available=bool(model_adapter.get("local_model_configured")),
        latest_provider=str(workbench.get("latest_provider", "none")),
    )
    recommended_first_action = _recommended_first_action(
        active_mission=active_mission,
        high_priority_count=len(high_priority_items),
        blocked_mission_count=blocked_mission_count,
        ready_step_count=len(ready_steps),
        evidence_needed_count=evidence_needed_count,
        workbench_next_action=str(workbench.get("recommended_next_action", "")),
    )
    guided_actions = _guided_actions(
        active_mission=active_mission,
        recommended_first_action=recommended_first_action,
        high_priority_count=len(high_priority_items),
        blocked_mission_count=blocked_mission_count,
        open_inbox_count=len(inbox_items),
        evidence_needed_count=evidence_needed_count,
        local_available=bool(model_adapter.get("local_model_configured")),
        local_model=str(model_adapter.get("local_model") or "local model"),
    )
    default_work_mode = _default_work_mode(active_mission)
    guided_action = guided_actions.get(default_work_mode) or guided_actions["research"]
    return {
        "briefing": briefing,
        "recommended_first_action": recommended_first_action,
        "plain_status": _plain_status(
            active_mission=active_mission,
            high_priority_count=len(high_priority_items),
            blocked_mission_count=blocked_mission_count,
            evidence_needed_count=evidence_needed_count,
        ),
        "default_work_mode": default_work_mode,
        "guided_action": guided_action,
        "guided_actions": guided_actions,
        "continuity_state": claim,
        "output_gate_mode": gate.mode.value,
        "model_mode": workbench.get("model_mode", "auto"),
        "latest_provider": workbench.get("latest_provider", "none"),
        "estimated_session_cost_usd": workbench.get("estimated_session_cost_usd", 0.0),
        "active_mission_count": len(active_briefs),
        "active_goal_count": len(active_goals),
        "focus_goal": focus_goal,
        "current_active_mission": active_mission,
        "mission_phase": active_mission.get("phase") if active_mission else "none",
        "next_safe_action": workbench.get("recommended_next_action"),
        "blocked_mission_count": blocked_mission_count,
        "ready_mission_steps": len(ready_steps),
        "ready_step_ids": [step.step_id for step in ready_steps[:5]],
        "pending_tool_approvals": len(pending_tool_approvals),
        "pending_tool_approval_ids": [step.step_id for step in pending_tool_approvals[:5]],
        "open_steward_inbox_count": len(inbox_items),
        "high_priority_steward_count": len(high_priority_items),
        "evidence_needed_count": evidence_needed_count,
        "skill_suggestions_available": len(skill_suggestions),
        "recovery_state": recovery_state,
        "conflicts_count": conflicts_count,
        "daily_plan": plan,
        "cost_brain_mode": {
            "local_model_available": bool(model_adapter.get("local_model_configured")),
            "local_model": model_adapter.get("local_model"),
            "openai_key_present": bool(model_adapter.get("openai_key_present")),
            "openai_spend_gated": True,
            "routine_recommendation": (
                "Use Local Model for routine work."
                if model_adapter.get("local_model_configured")
                else "Use Brain Router; Echo fallback remains available."
            ),
        },
        "review_needed": {
            "title": "Review Needed",
            "open_count": len(inbox_items),
            "high_priority_count": len(high_priority_items),
            "blocks_today": bool(high_priority_items or blocked_mission_count),
            "summary": _review_needed_summary(
                len(inbox_items),
                len(high_priority_items),
                blocked_mission_count,
            ),
        },
        "cards": {
            "work_today": _work_today_card(active_mission, len(active_briefs)),
            "goals": {
                "title": "Goals",
                "value": (
                    f"{len(active_goals)} active"
                    + (f" / focus {focus_goal['title']}" if focus_goal else "")
                ),
            },
            "blockers": _blockers_card(
                blocked_mission_count,
                len(high_priority_items),
                evidence_needed_count,
                conflicts_count,
            ),
            "safe_next_action": {
                "title": "Safe Next Action",
                "value": recommended_first_action,
            },
            "needs_steward_review": {
                "title": "Needs Steward Review",
                "value": (
                    f"{len(inbox_items)} open / {len(high_priority_items)} high priority"
                ),
            },
            "cost_brain_mode": {
                "title": "Cost / Brain Mode",
                "value": (
                    f"{workbench.get('model_mode', 'auto')} / latest "
                    f"{workbench.get('latest_provider', 'none')} / "
                    f"${float(workbench.get('estimated_session_cost_usd') or 0.0):.6f}"
                ),
            },
        },
    }


def render_daily_command_center_text(daily: dict[str, Any]) -> str:
    lines = [
        "Daily Command Center",
        daily["briefing"],
        "",
        f"Recommended first action: {daily['recommended_first_action']}",
        f"Continuity / gate: {daily['continuity_state']} / {daily['output_gate_mode']}",
        f"Model mode: {daily['model_mode']} / latest provider: {daily['latest_provider']}",
        f"Session cost estimate: ${float(daily['estimated_session_cost_usd'] or 0.0):.6f}",
        f"Active missions: {daily['active_mission_count']}",
        f"Active goals: {daily.get('active_goal_count', 0)}",
        f"Blocked missions: {daily['blocked_mission_count']}",
        f"Ready steps: {daily['ready_mission_steps']}",
        f"Pending tool approvals: {daily['pending_tool_approvals']}",
        f"Steward inbox: {daily['open_steward_inbox_count']} open / {daily['high_priority_steward_count']} high",
        f"Evidence needed: {daily['evidence_needed_count']}",
        f"Skill suggestions: {daily['skill_suggestions_available']}",
        f"Recovery: {daily['recovery_state'] or 'none'}",
        f"Conflicts: {daily['conflicts_count']}",
    ]
    goal = daily.get("focus_goal")
    if goal:
        lines.extend(
            [
                "",
                f"Focus goal: {goal['title']}",
                f"Goal next action: {goal.get('next_recommended_action') or 'none'}",
            ]
        )
    mission = daily.get("current_active_mission")
    if mission:
        lines.extend(
            [
                "",
                f"Current mission: {mission['title']}",
                f"Phase: {mission['phase']}",
                f"Mission next action: {mission.get('next_action') or 'none'}",
            ]
        )
    return "\n".join(lines)


def _briefing(
    continuity_state: str,
    active_mission: dict[str, Any] | None,
    open_inbox_count: int,
    high_priority_count: int,
    blocked_mission_count: int,
    ready_step_count: int,
    evidence_needed_count: int,
    local_available: bool,
    latest_provider: str,
) -> str:
    if active_mission is None:
        mission_line = "No active mission is selected."
    else:
        mission_line = (
            f"Active mission: {active_mission['title']} "
            f"({active_mission.get('phase', 'unknown')})."
        )
    review_line = (
        f"{open_inbox_count} steward item(s) are open"
        + (f", including {high_priority_count} high priority" if high_priority_count else "")
        + "."
    )
    blocker_line = (
        f"{blocked_mission_count} mission(s) are blocked. "
        if blocked_mission_count
        else ""
    )
    step_line = (
        f"{ready_step_count} ready step(s) can move after review. "
        if ready_step_count
        else ""
    )
    evidence_line = (
        f"{evidence_needed_count} evidence gap(s) need attention. "
        if evidence_needed_count
        else ""
    )
    brain_line = (
        "Local model mode is available; OpenAI remains spend-gated."
        if local_available
        else "Local model is not configured; Echo fallback and gated OpenAI remain available."
    )
    return (
        f"{mission_line} Continuity is {continuity_state}. {review_line} "
        f"{blocker_line}{step_line}{evidence_line}"
        f"Latest provider: {latest_provider}. {brain_line}"
    )


def _recommended_first_action(
    active_mission: dict[str, Any] | None,
    high_priority_count: int,
    blocked_mission_count: int,
    ready_step_count: int,
    evidence_needed_count: int,
    workbench_next_action: str,
) -> str:
    if active_mission is None:
        return "Open or resume a mission before using Lucien for work."
    if high_priority_count:
        return "Review high-priority Steward Inbox items first."
    if blocked_mission_count:
        return "Resolve mission blockers before proposing new work."
    if evidence_needed_count:
        return "Review evidence gaps before treating mission claims as grounded."
    if ready_step_count:
        return "Review ready mission steps and run approved low-risk actions."
    return workbench_next_action or "Continue the active mission."


def _default_work_mode(active_mission: dict[str, Any] | None) -> str:
    if not active_mission:
        return "research"
    title = str(active_mission.get("title") or "").lower()
    if any(token in title for token in ["write", "narrative", "paper", "readme", "public"]):
        return "write"
    if any(token in title for token in ["build", "app", "code", "repo"]):
        return "build"
    return "research"


def _plain_status(
    active_mission: dict[str, Any] | None,
    high_priority_count: int,
    blocked_mission_count: int,
    evidence_needed_count: int,
) -> str:
    if active_mission is None:
        return "Choose a mission before starting governed work."
    if high_priority_count:
        return "Needs review before high-impact work."
    if blocked_mission_count:
        return "Blocked until mission review is cleared."
    if evidence_needed_count:
        return "Ready to work, but some evidence needs review before becoming trusted."
    phase = str(active_mission.get("phase") or "")
    return {
        "intervention_ready": "Ready for next action.",
        "planning": "Ready to plan the next step.",
        "evidence_review": "Evidence needs review before stronger claims.",
        "lesson_review": "Ready to review what was learned.",
        "outcome_review": "Ready to review the outcome.",
        "intake": "Ready to shape the mission.",
        "blocked": "Blocked until review is cleared.",
    }.get(phase, "Ready for guided work.")


def _review_needed_summary(
    open_count: int,
    high_priority_count: int,
    blocked_mission_count: int,
) -> str:
    if not open_count and not blocked_mission_count:
        return "Nothing needs steward review before today's guided action."
    if high_priority_count:
        return (
            f"{high_priority_count} high-priority item(s) need review before high-impact "
            "work. Routine sandbox drafting stays safe."
        )
    if blocked_mission_count:
        return f"{blocked_mission_count} mission(s) need review before advancing."
    return f"{open_count} proposed item(s) need review later; they do not block sandbox work."


def _guided_actions(
    active_mission: dict[str, Any] | None,
    recommended_first_action: str,
    high_priority_count: int,
    blocked_mission_count: int,
    open_inbox_count: int,
    evidence_needed_count: int,
    local_available: bool,
    local_model: str,
) -> dict[str, dict[str, Any]]:
    if active_mission is None:
        base = _guided_action(
            work_mode="research",
            action_id="open_mission",
            title="Open a Mission",
            primary_label="Start Mission",
            status="Choose what Coherence AI should help with today.",
            target_kind="start_mission",
            what_it_does=[
                "Opens the mission form so you can name the work.",
                "Keeps chat, memory, evidence, and claims governed by PCA.",
            ],
            what_it_will_not_do=[
                "Will not run tools.",
                "Will not write files.",
                "Will not publish anything.",
                "Will not accept claims as proven.",
            ],
            local_available=local_available,
            local_model=local_model,
            requires_approval=False,
            creates_persistent_change=False,
            allowed=True,
        )
        return {"research": base, "write": base | {"work_mode": "write"}, "build": base | {"work_mode": "build"}}

    blocked = bool(high_priority_count or blocked_mission_count)
    allowed = not bool(high_priority_count)
    review_note = (
        "Steward review is needed before high-impact work."
        if blocked
        else "Steward review is not blocking this sandbox action."
    )
    return {
        "research": _guided_action(
            work_mode="research",
            action_id="generate_research_brief",
            title="Generate a Research Brief",
            primary_label="Start Research Brief",
            status=(
                "Ready to gather proposed research notes."
                if allowed
                else "Review is needed first for high-impact work; sandbox drafting remains constrained."
            ),
            target_kind="research_brief",
            what_it_does=[
                "Creates a sandbox research brief linked to the active mission.",
                "Uses the local model path when available.",
                "Creates proposed evidence for later review.",
                review_note,
            ],
            what_it_will_not_do=[
                "Will not write project files.",
                "Will not publish anything.",
                "Will not accept claims as proven.",
                "Will not create durable memory without review.",
            ],
            local_available=local_available,
            local_model=local_model,
            requires_approval=False,
            creates_persistent_change=True,
            allowed=True,
        ),
        "write": _guided_action(
            work_mode="write",
            action_id="start_sandbox_draft",
            title="Start a Sandbox Draft",
            primary_label="Start Draft",
            status="Ready to draft without treating the draft as truth.",
            target_kind="paper_draft",
            what_it_does=[
                "Creates a sandbox draft for the active mission.",
                "Uses local model mode by default.",
                "Keeps claims proposed until steward review.",
                review_note,
            ],
            what_it_will_not_do=[
                "Will not edit README or paper files directly.",
                "Will not publish or post anything.",
                "Will not accept the draft as memory.",
                "Will not spend OpenAI money unless Cloud Assist is explicitly enabled.",
            ],
            local_available=local_available,
            local_model=local_model,
            requires_approval=False,
            creates_persistent_change=True,
            allowed=True,
        ),
        "build": _guided_action(
            work_mode="build",
            action_id="review_next_build",
            title="Review the Next Build",
            primary_label="Review Build Path",
            status="Ready to inspect the next safe engineering move.",
            target_kind="build_review",
            what_it_does=[
                "Shows the next recommended app improvement.",
                "Shows changed files, checks, and commit readiness.",
                "Keeps code changes behind Codex and test review.",
                recommended_first_action,
            ],
            what_it_will_not_do=[
                "Will not edit files by itself.",
                "Will not run tools automatically.",
                "Will not commit or push.",
                "Will not spend OpenAI money.",
            ],
            local_available=local_available,
            local_model=local_model,
            requires_approval=True,
            creates_persistent_change=False,
            allowed=True,
        ),
    }


def _guided_action(
    work_mode: str,
    action_id: str,
    title: str,
    primary_label: str,
    status: str,
    target_kind: str,
    what_it_does: list[str],
    what_it_will_not_do: list[str],
    local_available: bool,
    local_model: str,
    requires_approval: bool,
    creates_persistent_change: bool,
    allowed: bool,
) -> dict[str, Any]:
    brain = f"Ollama / {local_model}" if local_available else "Echo Local fallback"
    return {
        "action_id": action_id,
        "work_mode": work_mode,
        "title": title,
        "primary_label": primary_label,
        "plain_english_status": status,
        "target_kind": target_kind,
        "what_it_does": what_it_does,
        "what_it_will_not_do": what_it_will_not_do,
        "risk_level": "low" if not requires_approval else "medium",
        "cost_estimate": "$0 API money in Local Mode",
        "brain": brain,
        "requires_approval": requires_approval,
        "creates_persistent_change": creates_persistent_change,
        "allowed_under_current_governance": allowed,
    }


def _work_today_card(
    active_mission: dict[str, Any] | None,
    active_count: int,
) -> dict[str, str]:
    if active_mission is None:
        return {
            "title": "Work Today",
            "value": "No active mission. Start or resume a governed mission.",
        }
    return {
        "title": "Work Today",
        "value": f"{active_mission['title']} / {active_mission.get('phase', 'unknown')}",
    }


def _blockers_card(
    blocked_mission_count: int,
    high_priority_count: int,
    evidence_needed_count: int,
    conflicts_count: int,
) -> dict[str, str]:
    return {
        "title": "Blockers",
        "value": (
            f"{blocked_mission_count} missions / {high_priority_count} high steward / "
            f"{evidence_needed_count} evidence / {conflicts_count} conflicts"
        ),
    }


def _evidence_needed_count(events: list[Any]) -> int:
    learning_reviews = learning_review_records_from_events(events)
    count = 0
    for review in learning_reviews:
        counts = getattr(review, "counts", {})
        if isinstance(counts, dict):
            count += int(counts.get("evidence_needed", 0) or 0)
    return count

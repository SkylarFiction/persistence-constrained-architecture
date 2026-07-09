from __future__ import annotations

from typing import Any


def start_here_decision(status: dict[str, Any]) -> dict[str, Any]:
    """Return the one daily action the live workbench should emphasize first."""
    health = status.get("startup_health") or {}
    workbench = status.get("workbench") or {}
    mission = workbench.get("active_mission") or None
    onboarding = _onboarding_for(status, mission)
    safe_actions = health.get("safe_actions") or []
    open_inbox = int(workbench.get("open_steward_inbox_count") or 0)
    high_inbox = int(workbench.get("high_priority_inbox_count") or 0)
    stale_inbox = int(health.get("stale_steward_items") or 0)
    latest_cost = float((status.get("model_usage") or {}).get("latest_cost_usd") or 0)

    if safe_actions:
        fix = safe_actions[0]
        return {
            "kind": "startup_fix",
            "title": "Lucien needs one setup fix",
            "summary": (
                f"{fix.get('label') or 'Apply safe startup fix'} before normal work. "
                "This does not delete durable memory, missions, evidence, skills, or ledger history."
            ),
            "primary_label": fix.get("label") or "Apply Safe Fix",
            "fix_action": fix.get("action", ""),
            "severity": "medium",
        }

    if stale_inbox:
        hours = int(health.get("stale_steward_threshold_hours") or 48)
        return {
            "kind": "review_inbox",
            "title": "Old review items need attention",
            "summary": (
                f"{stale_inbox} steward item(s) have been waiting at least {hours} hours. "
                "Review these before adding new work."
            ),
            "primary_label": "Review Stale Items",
            "filter": "all",
            "severity": "high" if high_inbox else "medium",
        }

    if high_inbox:
        return {
            "kind": "review_inbox",
            "title": "Review the high-priority blockers",
            "summary": (
                f"{high_inbox} high-priority steward item(s) are blocking clean progress. "
                "Review those first, then return to the mission."
            ),
            "primary_label": "Review High Priority",
            "filter": "high",
            "severity": "high",
        }

    if not mission:
        return {
            "kind": "start_mission",
            "title": "Start by choosing a mission",
            "summary": (
                "Lucien works best when the chat is tied to a mission. "
                "Open a mission first, then ask for the next safe step."
            ),
            "primary_label": "Start Mission",
            "severity": "medium",
        }

    if onboarding and onboarding.get("ready"):
        return {
            "kind": "mission_onboarding",
            "title": "Set up this mission first",
            "summary": (
                "Create a starter pack so this mission has a first hypothesis, "
                "an evidence need, and a risk review item. Nothing becomes accepted truth automatically."
            ),
            "primary_label": "Create Starter Pack",
            "mission_id": mission.get("mission_id", ""),
            "severity": "medium",
        }

    return {
        "kind": "ask_next",
        "title": "You can talk to Lucien now",
        "summary": (
            f"Active mission: {mission.get('title', 'Untitled mission')}. "
            f"Last cost was ${latest_cost:.6f}. Ask Lucien for the next safe step and keep it simple."
        ),
        "primary_label": "Ask What To Do Next",
        "mission_id": mission.get("mission_id", ""),
        "severity": "low",
    }


def _onboarding_for(
    status: dict[str, Any],
    mission: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not mission:
        return None
    mission_id = str(mission.get("mission_id", ""))
    onboarding = status.get("mission_onboarding") or {}
    value = onboarding.get(mission_id)
    return value if isinstance(value, dict) else None

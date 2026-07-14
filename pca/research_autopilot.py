from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .auto_daily_loop import run_auto_daily_research_loop
from .daily_command_center import daily_command_center
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .mission_autonomy import propose_autonomous_mission_step
from .mission_claim_map import mission_claim_map
from .mission_onboarding import create_mission_onboarding_pack, mission_onboarding_state
from .missions import MissionStatus, mission_briefs_from_events
from .research_sandbox import create_research_output, research_outputs_from_events
from .startup_health import apply_startup_health_fix, startup_health


AUTOPILOT_OUTPUT_KINDS = ("research_brief", "claim_map_draft", "next_step_suggestion")


def run_research_autopilot(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    run_date: str | None = None,
    force: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    run_date = run_date or datetime.now(timezone.utc).date().isoformat()
    actions: list[dict[str, Any]] = []
    health_before = startup_health(ledger, manifest)

    if int(health_before.get("high_priority_steward_items", 0) or 0) > 0:
        return _record_autopilot_run(
            ledger,
            manifest,
            run_date,
            status="blocked",
            mission_id=None,
            mission_title=None,
            actions=[
                {
                    "action": "blocked_by_high_priority_steward_items",
                    "count": health_before.get("high_priority_steward_items", 0),
                }
            ],
            outputs=[],
            onboarding=None,
            next_step=None,
            claim_map=None,
            daily_loop=None,
            health_before=health_before,
            health_after=startup_health(ledger, manifest),
            reason=reason,
        )

    if _has_safe_action(health_before, "refresh_required_evidence"):
        fix = apply_startup_health_fix(
            ledger,
            manifest,
            "refresh_required_evidence",
            reason=reason or "research autopilot refreshed required evidence",
        )
        actions.append(
            {
                "action": "refresh_required_evidence",
                "event_count": len(fix.get("events") or []),
                "claim_updated": bool(fix.get("claim_record")),
            }
        )

    health_mid = startup_health(ledger, manifest)
    if _has_safe_action(health_mid, "open_coherence_research_mission"):
        opened = apply_startup_health_fix(
            ledger,
            manifest,
            "open_coherence_research_mission",
            reason=reason or "research autopilot opened default research mission",
        )
        preferred_mission_id = (opened.get("mission") or {}).get("mission_id")
        actions.append(
            {
                "action": "open_coherence_research_mission",
                "created": bool(opened.get("created")),
                "mission_id": preferred_mission_id,
            }
        )
    else:
        preferred_mission_id = None

    daily_loop = run_auto_daily_research_loop(
        ledger,
        manifest,
        project_root=project_root,
        loop_date=run_date,
        force=force,
        reason=reason or "research autopilot prepared daily agenda",
    )
    actions.append(
        {
            "action": "daily_research_loop",
            "already_prepared": bool(daily_loop.get("already_prepared")),
            "proposed_items": len(daily_loop.get("proposed_items") or []),
        }
    )

    daily = daily_command_center(ledger, manifest)
    mission = _select_focus_mission(ledger, daily, mission_id or preferred_mission_id)
    if not mission:
        return _record_autopilot_run(
            ledger,
            manifest,
            run_date,
            status="blocked",
            mission_id=None,
            mission_title=None,
            actions=actions + [{"action": "blocked_no_open_mission"}],
            outputs=[],
            onboarding=None,
            next_step=None,
            claim_map=None,
            daily_loop=daily_loop,
            health_before=health_before,
            health_after=startup_health(ledger, manifest),
            reason=reason,
        )

    onboarding_state = mission_onboarding_state(ledger, mission["mission_id"])
    onboarding_result = None
    if onboarding_state.ready:
        onboarding_result = create_mission_onboarding_pack(
            ledger,
            manifest.system_id,
            mission["mission_id"],
            reason=reason or "research autopilot created mission starter pack",
        )
        actions.append(
            {
                "action": "mission_onboarding",
                "created": len(onboarding_result.get("created") or []),
                "evidence": len(onboarding_result.get("evidence") or []),
            }
        )

    outputs: list[dict[str, Any]] = []
    for kind in AUTOPILOT_OUTPUT_KINDS:
        if not force and _has_output_for_date(ledger, mission["mission_id"], kind, run_date):
            actions.append({"action": "research_output_skipped", "kind": kind})
            continue
        output = create_research_output(
            ledger,
            manifest,
            mission["mission_id"],
            kind,
            reason=reason or f"research autopilot generated {kind}",
        )
        outputs.append(output)
        actions.append(
            {
                "action": (
                    "research_output_skipped_unchanged"
                    if output.get("skipped")
                    else "research_output_created"
                ),
                "kind": kind,
                "output_id": output["output"]["output_id"],
                "evidence_id": (
                    output["evidence"]["evidence_id"]
                    if output.get("evidence")
                    else None
                ),
            }
        )

    next_step = propose_autonomous_mission_step(
        ledger,
        manifest.system_id,
        mission["mission_id"],
    )
    actions.append(
        {
            "action": "next_step",
            "created": bool(next_step.get("mission_step")),
            "reason": next_step["recommendation"].get("reason"),
        }
    )
    claim_map = mission_claim_map(ledger, mission["mission_id"])

    return _record_autopilot_run(
        ledger,
        manifest,
        run_date,
        status="prepared",
        mission_id=mission["mission_id"],
        mission_title=mission["title"],
        actions=actions,
        outputs=outputs,
        onboarding=onboarding_result,
        next_step=next_step,
        claim_map=claim_map,
        daily_loop=daily_loop,
        health_before=health_before,
        health_after=startup_health(ledger, manifest),
        reason=reason,
    )


def research_autopilot_records_from_events(events: list[ContinuityEvent]) -> list[dict[str, Any]]:
    records = [
        event.payload
        for event in events
        if event.event_type == "research.autopilot_ran"
    ]
    return sorted(records, key=lambda item: (item.get("created_at", ""), item.get("run_id", "")))


def render_research_autopilot_text(result: dict[str, Any]) -> str:
    record = result["record"]
    lines = [
        "Research Autopilot Run",
        f"status: {record['status']}",
        f"date: {record['run_date']}",
        f"mission: {record.get('mission_title') or 'none'}",
        f"actions: {len(record.get('actions') or [])}",
        f"outputs created: {len(result.get('outputs') or [])}",
        f"claim support: {record.get('claim_map_summary') or 'none'}",
        "stopped for review: yes",
    ]
    for action in record.get("actions") or []:
        lines.append(f"- {action.get('action')}: {action}")
    return "\n".join(lines)


def _record_autopilot_run(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    run_date: str,
    status: str,
    mission_id: str | None,
    mission_title: str | None,
    actions: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    onboarding: dict[str, Any] | None,
    next_step: dict[str, Any] | None,
    claim_map: dict[str, Any] | None,
    daily_loop: dict[str, Any] | None,
    health_before: dict[str, Any],
    health_after: dict[str, Any],
    reason: str = "",
) -> dict[str, Any]:
    record = {
        "run_id": f"research_autopilot_{uuid.uuid4()}",
        "identity_id": manifest.system_id,
        "run_date": run_date,
        "status": status,
        "mission_id": mission_id,
        "mission_title": mission_title,
        "actions": actions,
        "output_ids": [item["output"]["output_id"] for item in outputs],
        "claim_map_summary": _claim_map_summary(claim_map),
        "health_before": {
            "status": health_before.get("status"),
            "claim": health_before.get("claim"),
            "high_priority_steward_items": health_before.get("high_priority_steward_items", 0),
        },
        "health_after": {
            "status": health_after.get("status"),
            "claim": health_after.get("claim"),
            "high_priority_steward_items": health_after.get("high_priority_steward_items", 0),
        },
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason or "research autopilot run",
        "stopped_for_review": True,
        "will_not": [
            "publish",
            "write project files",
            "accept claims as true",
            "accept memory",
            "execute tools",
        ],
    }
    ledger.append("research.autopilot_ran", manifest.system_id, record)
    return {
        "record": record,
        "outputs": outputs,
        "onboarding": onboarding,
        "next_step": next_step,
        "claim_map": claim_map,
        "daily_loop": daily_loop,
    }


def _select_focus_mission(
    ledger: ContinuityLedger,
    daily: dict[str, Any],
    preferred_mission_id: str | None = None,
) -> dict[str, Any] | None:
    if preferred_mission_id:
        for brief in mission_briefs_from_events(ledger.events()):
            if brief.mission.mission_id == preferred_mission_id:
                return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    active = daily.get("current_active_mission")
    if active and active.get("mission_id"):
        return {"mission_id": active["mission_id"], "title": active.get("title", "Mission")}
    for brief in mission_briefs_from_events(ledger.events()):
        if brief.mission.status == MissionStatus.OPEN:
            return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    return None


def _has_safe_action(health: dict[str, Any], action: str) -> bool:
    return any(item.get("action") == action for item in health.get("safe_actions") or [])


def _has_output_for_date(
    ledger: ContinuityLedger,
    mission_id: str,
    kind: str,
    run_date: str,
) -> bool:
    for output in research_outputs_from_events(ledger.events(), mission_id):
        if output.kind.value == kind and output.created_at.startswith(run_date):
            return True
    return False


def _claim_map_summary(claim_map: dict[str, Any] | None) -> str:
    if not claim_map:
        return ""
    return (
        f"{claim_map.get('claim_count', 0)} claim(s), "
        f"{claim_map.get('unsupported_claim_count', 0)} unsupported, "
        f"{claim_map.get('reviewed_evidence_count', 0)} reviewed evidence"
    )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from .anchors import verify_latest_anchor
from .claims import claims_from_events, current_claim_record
from .chat_sessions import chat_sessions_from_events, chat_turns_from_events
from .context_builder import build_governed_context
from .evaluator import EVALUATION_PRECEDENCE, ContinuityEvaluator
from .evidence_locker import (
    evidence_claim_records_from_events,
    evidence_link_records_from_events,
    evidence_records_from_events,
    evidence_review_records_from_events,
)
from .followups import active_followups, followups_from_events
from .growth import (
    active_growth_records,
    growth_records_from_events,
    growth_review_records_from_events,
)
from .growth_conflicts import (
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
)
from .ledger import ContinuityEvent, ContinuityLedger
from .lineage import lineage_records
from .manifest import IdentityManifest
from .memory_cards import memory_cards_from_events
from .memory_signals import memory_signal_records_from_events
from .mission_flow import mission_flows_from_events
from .mission_steps import mission_step_records_from_events
from .missions import mission_briefs_from_events
from .output_gate import OutputGate
from .recovery import current_recovery_record, recovery_records_from_events
from .reflection_queue import (
    active_reflection_tasks,
    reflection_task_records_from_events,
)
from .reflections import reflection_records_from_events
from .self_model import derive_self_model
from .skill_memory import accepted_skills_from_events, skill_candidates_from_events
from .state import derive_current_claim


IMPORTANT_EVENT_TYPES = {
    "continuity_claim_record",
    "chat.user_message_received",
    "chat.model_response_generated",
    "chat.model_response_error",
    "constraint.breached",
    "identity.forked",
    "lucien.input",
    "lucien.memory_digest",
    "lucien.memory_evidence_requested",
    "lucien.memory_signal_recorded",
    "lucien.tool_use",
    "lucien.growth_proposed",
    "lucien.growth_updated",
    "lucien.growth_reviewed",
    "lucien.growth_conflict_detected",
    "lucien.growth_conflict_resolved",
    "lucien.reflection_recorded",
    "reflection.task_opened",
    "reflection.task_resolved",
    "reflection.task_dismissed",
    "lucien.chat_session_started",
    "lucien.chat_turn_recorded",
    "lucien.chat_session_closed",
    "mission.opened",
    "mission.item_added",
    "mission.status_updated",
    "mission.step_proposed",
    "mission.step_approved",
    "mission.step_started",
    "mission.step_completed",
    "mission.step_failed",
    "mission.step_blocked",
    "evidence.added",
    "evidence.claim_recorded",
    "evidence.linked",
    "evidence.reviewed",
    "evidence.updated",
    "skill.candidate_proposed",
    "skill.candidate_reviewed",
    "runtime.csm_state",
    "runtime.output_gate",
    "transform.evaluated",
    "transform.override",
    "followup_created",
    "followup_updated",
    "post_transform_audit",
    "recovery_opened",
    "recovery_updated",
    "authorization_check",
}


@dataclass(frozen=True)
class TraceReport:
    summary: dict[str, Any]
    claim_history: list[dict[str, Any]]
    runtime_signals: list[dict[str, Any]]
    output_gate_events: list[dict[str, Any]]
    important_events: list[dict[str, Any]]
    evidence_freshness: list[dict[str, Any]]
    active_followups: list[dict[str, Any]]
    recovery_records: list[dict[str, Any]]
    lineage: list[dict[str, Any]]
    authorization_checks: list[dict[str, Any]]
    growth_records: list[dict[str, Any]]
    active_growth: list[dict[str, Any]]
    growth_reviews: list[dict[str, Any]]
    growth_conflicts: list[dict[str, Any]]
    growth_conflict_resolutions: list[dict[str, Any]]
    memory_cards: list[dict[str, Any]]
    memory_signals: list[dict[str, Any]]
    reflections: list[dict[str, Any]]
    reflection_tasks: list[dict[str, Any]]
    active_reflection_tasks: list[dict[str, Any]]
    chat_sessions: list[dict[str, Any]]
    chat_turns: list[dict[str, Any]]
    missions: list[dict[str, Any]]
    mission_flows: list[dict[str, Any]]
    mission_steps: list[dict[str, Any]]
    evidence_records: list[dict[str, Any]]
    evidence_claims: list[dict[str, Any]]
    evidence_links: list[dict[str, Any]]
    evidence_reviews: list[dict[str, Any]]
    skill_candidates: list[dict[str, Any]]
    accepted_skills: list[dict[str, Any]]
    governed_context: dict[str, Any]
    self_model: dict[str, Any]
    policy_errors: list[str]
    anchor_verification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "claim_history": self.claim_history,
            "runtime_signals": self.runtime_signals,
            "output_gate_events": self.output_gate_events,
            "important_events": self.important_events,
            "evidence_freshness": self.evidence_freshness,
            "active_followups": self.active_followups,
            "recovery_records": self.recovery_records,
            "lineage": self.lineage,
            "authorization_checks": self.authorization_checks,
            "growth_records": self.growth_records,
            "active_growth": self.active_growth,
            "growth_reviews": self.growth_reviews,
            "growth_conflicts": self.growth_conflicts,
            "growth_conflict_resolutions": self.growth_conflict_resolutions,
            "memory_cards": self.memory_cards,
            "memory_signals": self.memory_signals,
            "reflections": self.reflections,
            "reflection_tasks": self.reflection_tasks,
            "active_reflection_tasks": self.active_reflection_tasks,
            "chat_sessions": self.chat_sessions,
            "chat_turns": self.chat_turns,
            "missions": self.missions,
            "mission_flows": self.mission_flows,
            "mission_steps": self.mission_steps,
            "evidence_records": self.evidence_records,
            "evidence_claims": self.evidence_claims,
            "evidence_links": self.evidence_links,
            "evidence_reviews": self.evidence_reviews,
            "skill_candidates": self.skill_candidates,
            "accepted_skills": self.accepted_skills,
            "governed_context": self.governed_context,
            "self_model": self.self_model,
            "policy_errors": self.policy_errors,
            "anchor_verification": self.anchor_verification,
        }


def _short_hash(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return value
    return f"{value[:12]}..."


def _event_summary(event: ContinuityEvent) -> str:
    payload = event.payload
    if event.event_type == "continuity_claim_record":
        return f"claim={payload.get('claim')} reason={payload.get('reason', '')}"
    if event.event_type == "chat.user_message_received":
        return (
            f"surface={payload.get('surface')} "
            f"message_length={payload.get('message_length')}"
        )
    if event.event_type == "chat.model_response_generated":
        return (
            f"surface={payload.get('surface')} "
            f"response_length={payload.get('response_length')} "
            f"claim={payload.get('continuity_claim')} "
            f"model={payload.get('model', 'unknown')}"
        )
    if event.event_type == "chat.model_response_error":
        return (
            f"surface={payload.get('surface')} "
            f"model={payload.get('model')} error={payload.get('error_type')}"
        )
    if event.event_type == "constraint.breached":
        return (
            f"constraint={payload.get('constraint')} "
            f"severity={payload.get('severity')}"
        )
    if event.event_type == "runtime.csm_state":
        return (
            f"state={payload.get('state')} source={payload.get('source')} "
            f"reason={payload.get('reason', '')}"
        )
    if event.event_type == "runtime.output_gate":
        return (
            f"mode={payload.get('mode')} allowed={payload.get('allowed')} "
            f"claim={payload.get('claim')}"
        )
    if event.event_type == "lucien.input":
        return (
            f"channel={payload.get('channel')} "
            f"input_length={payload.get('input_length')}"
        )
    if event.event_type == "lucien.memory_digest":
        return (
            f"digest_length={payload.get('digest_length')} "
            f"commitments={payload.get('commitment_count')}"
        )
    if event.event_type == "lucien.memory_signal_recorded":
        return (
            f"memory={payload.get('memory_id')} signal={payload.get('signal_type')} "
            f"delta={payload.get('confidence_delta')}"
        )
    if event.event_type == "lucien.memory_evidence_requested":
        return (
            f"growth={payload.get('growth_id')} "
            f"requested_by={payload.get('requested_by')} reason={payload.get('reason', '')}"
        )
    if event.event_type == "lucien.tool_use":
        return (
            f"tool={payload.get('tool_name')} "
            f"purpose={payload.get('purpose')}"
        )
    if event.event_type in {"lucien.growth_proposed", "lucien.growth_updated"}:
        return (
            f"kind={payload.get('kind')} status={payload.get('status')} "
            f"impact={payload.get('identity_impact')}"
        )
    if event.event_type == "lucien.growth_reviewed":
        return (
            f"growth={payload.get('growth_id')} decision={payload.get('decision')} "
            f"status_after={payload.get('growth_status_after')}"
        )
    if event.event_type == "lucien.growth_conflict_detected":
        return (
            f"growth={payload.get('proposed_growth_id')} "
            f"type={payload.get('conflict_type')} severity={payload.get('severity')}"
        )
    if event.event_type == "lucien.growth_conflict_resolved":
        return (
            f"conflict={payload.get('conflict_id')} "
            f"decision={payload.get('decision')} by={payload.get('resolved_by')}"
        )
    if event.event_type == "lucien.reflection_recorded":
        return (
            f"focus={payload.get('focus')} severity={payload.get('severity')} "
            f"actions={len(payload.get('recommended_actions', []))}"
        )
    if event.event_type in {
        "reflection.task_opened",
        "reflection.task_resolved",
        "reflection.task_dismissed",
    }:
        return (
            f"task={payload.get('task_id')} kind={payload.get('kind')} "
            f"status={payload.get('status')} severity={payload.get('severity')}"
        )
    if event.event_type == "lucien.chat_session_started":
        return f"session={payload.get('session_id')} status=open"
    if event.event_type == "lucien.chat_turn_recorded":
        return (
            f"session={payload.get('session_id')} turn={payload.get('turn_index')} "
            f"claim={payload.get('continuity_claim')}"
        )
    if event.event_type == "lucien.chat_session_closed":
        return (
            f"session={payload.get('session_id')} turns={payload.get('turn_count')} "
            "status=closed"
        )
    if event.event_type == "mission.opened":
        return (
            f"mission={payload.get('mission_id')} title={payload.get('title')} "
            f"status={payload.get('status')}"
        )
    if event.event_type == "mission.item_added":
        return (
            f"mission={payload.get('mission_id')} kind={payload.get('kind')} "
            f"status={payload.get('status')} confidence={payload.get('confidence')}"
        )
    if event.event_type == "mission.status_updated":
        return (
            f"mission={payload.get('mission_id')} status={payload.get('status')} "
            f"reason={payload.get('reason', '')}"
        )
    if event.event_type.startswith("mission.step_"):
        return (
            f"step={payload.get('step_id')} mission={payload.get('mission_id')} "
            f"risk={payload.get('risk_level')} approval={payload.get('approval_status')} "
            f"execution={payload.get('execution_status')}"
        )
    if event.event_type in {"evidence.added", "evidence.updated"}:
        return (
            f"evidence={payload.get('evidence_id')} type={payload.get('source_type')} "
            f"status={payload.get('review_status')} confidence={payload.get('confidence')}"
        )
    if event.event_type == "evidence.linked":
        return (
            f"evidence={payload.get('evidence_id')} "
            f"target={payload.get('target_type')}:{payload.get('target_id')}"
        )
    if event.event_type == "evidence.reviewed":
        return (
            f"evidence={payload.get('evidence_id')} "
            f"status={payload.get('review_status')} reviewer={payload.get('reviewer')}"
        )
    if event.event_type == "evidence.claim_recorded":
        return (
            f"claim={payload.get('claim_id')} status={payload.get('status')} "
            f"evidence={len(payload.get('evidence_ids', []))}"
        )
    if event.event_type in {"skill.candidate_proposed", "skill.candidate_reviewed"}:
        return (
            f"skill={payload.get('skill_id')} name={payload.get('name')} "
            f"status={payload.get('status')} tool={payload.get('required_tool')}"
        )
    if event.event_type == "transform.evaluated":
        return (
            f"transform={payload.get('transform')} "
            f"decision={payload.get('decision')}"
        )
    if event.event_type == "authorization_check":
        return (
            f"action={payload.get('action')} decision={payload.get('decision')} "
            f"actor={payload.get('actor_authority')}"
        )
    if event.event_type in {"followup_created", "followup_updated"}:
        return (
            f"followup={payload.get('followup_type')} "
            f"status={payload.get('status')}"
        )
    return ", ".join(f"{key}={value}" for key, value in sorted(payload.items())[:3])


def build_trace_report(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    anchor_path: str | Path | None = None,
) -> TraceReport:
    events = ledger.events()
    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=ledger.verify_chain(),
    )
    current_claim, blocking_followups, reasons = derive_current_claim(
        ledger,
        manifest,
    )
    output_gate = OutputGate().evaluate(current_claim)
    current_claim_record_value = current_claim_record(events)
    current_recovery = current_recovery_record(events)
    followups = followups_from_events(events)
    recoveries = recovery_records_from_events(events)
    growth_records = growth_records_from_events(events)
    active_growth = active_growth_records(events)
    growth_reviews = growth_review_records_from_events(events)
    growth_conflicts = growth_conflict_records_from_events(events)
    growth_conflict_resolutions = growth_conflict_resolution_records_from_events(events)
    resolved_conflict_ids = {
        record.conflict_id for record in growth_conflict_resolutions
    }
    unresolved_conflicts = [
        record
        for record in growth_conflicts
        if record.conflict_id not in resolved_conflict_ids
    ]
    memory_cards = memory_cards_from_events(events, manifest.system_id)
    memory_signals = memory_signal_records_from_events(events)
    reflections = reflection_records_from_events(events)
    reflection_tasks = reflection_task_records_from_events(events)
    open_reflection_tasks = active_reflection_tasks(events)
    chat_sessions = chat_sessions_from_events(events)
    chat_turns = chat_turns_from_events(events)
    missions = mission_briefs_from_events(events)
    mission_flows = mission_flows_from_events(events)
    mission_steps = mission_step_records_from_events(events)
    evidence_records = evidence_records_from_events(events)
    evidence_claims = evidence_claim_records_from_events(events)
    evidence_links = evidence_link_records_from_events(events)
    evidence_reviews = evidence_review_records_from_events(events)
    skill_candidates = skill_candidates_from_events(events)
    accepted_skills = accepted_skills_from_events(events)
    open_missions = [
        brief for brief in missions if brief.mission.status.value == "open"
    ]
    self_model = derive_self_model(events, manifest.system_id)
    governed_context = build_governed_context(ledger, manifest)
    active_followup_records = active_followups(events)
    anchor_verification = (
        verify_latest_anchor(ledger, anchor_path).to_dict()
        if anchor_path is not None
        else None
    )

    summary = {
        "system_id": manifest.system_id,
        "name": manifest.name,
        "ledger_path": str(ledger.path),
        "chain_valid": ledger.verify_chain(),
        "event_count": len(events),
        "identity_state": evaluation.state.value,
        "current_continuity_claim": current_claim,
        "recorded_claim_id": (
            current_claim_record_value.claim_id
            if current_claim_record_value is not None
            else None
        ),
        "output_mode": output_gate.mode.value,
        "output_allowed_scope": output_gate.allowed_scope,
        "blocking_followups": len(blocking_followups),
        "active_followups": len(active_followups(events)),
        "followup_count": len(followups),
        "recovery_count": len(recoveries),
        "growth_count": len(growth_records),
        "active_growth_count": len(active_growth),
        "growth_review_count": len(growth_reviews),
        "growth_conflict_count": len(growth_conflicts),
        "growth_conflict_resolution_count": len(growth_conflict_resolutions),
        "unresolved_growth_conflict_count": len(unresolved_conflicts),
        "memory_card_count": len(memory_cards),
        "memory_signal_count": len(memory_signals),
        "reflection_count": len(reflections),
        "reflection_task_count": len(reflection_tasks),
        "active_reflection_task_count": len(open_reflection_tasks),
        "chat_session_count": len(chat_sessions),
        "chat_turn_count": len(chat_turns),
        "mission_count": len(missions),
        "open_mission_count": len(open_missions),
        "blocked_mission_count": len(
            [flow for flow in mission_flows if flow.phase.value == "blocked"]
        ),
        "mission_step_count": len(mission_steps),
        "evidence_count": len(evidence_records),
        "reviewed_evidence_count": len(
            [record for record in evidence_records if record.review_status.value == "reviewed"]
        ),
        "disputed_evidence_count": len(
            [record for record in evidence_records if record.review_status.value == "disputed"]
        ),
        "stale_evidence_count": len(
            [record for record in evidence_records if record.review_status.value == "stale"]
        ),
        "evidence_link_count": len(evidence_links),
        "evidence_claim_count": len(evidence_claims),
        "skill_candidate_count": len(skill_candidates),
        "accepted_skill_count": len(accepted_skills),
        "context_warning_count": governed_context.summary()["warning_count"],
        "accepted_growth_count": self_model.accepted_growth_count,
        "current_recovery_status": (
            current_recovery.status.value if current_recovery is not None else None
        ),
        "reasons": reasons,
        "state_precedence": list(EVALUATION_PRECEDENCE),
        "policy_error_count": len(manifest.policy_errors),
        "anchor_valid": (
            anchor_verification["valid"]
            if anchor_verification is not None
            else None
        ),
    }
    important_events = [
        {
            "index": index,
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "event_hash": event.event_hash,
            "previous_hash": event.previous_hash,
            "summary": _event_summary(event),
        }
        for index, event in enumerate(events, start=1)
        if event.event_type in IMPORTANT_EVENT_TYPES
    ]
    return TraceReport(
        summary=summary,
        claim_history=[claim.to_dict() for claim in claims_from_events(events)],
        runtime_signals=[
            {
                "timestamp": event.timestamp,
                "state": event.payload.get("state"),
                "source": event.payload.get("source"),
                "reason": event.payload.get("reason"),
                "metrics": event.payload.get("metrics", {}),
                "event_hash": event.event_hash,
            }
            for event in events
            if event.event_type == "runtime.csm_state"
        ],
        output_gate_events=[
            {
                "timestamp": event.timestamp,
                "claim": event.payload.get("claim"),
                "mode": event.payload.get("mode"),
                "allowed": event.payload.get("allowed"),
                "must_disclose": event.payload.get("must_disclose"),
                "channel": event.payload.get("channel"),
                "input_sha256": event.payload.get("input_sha256"),
                "output_sha256": event.payload.get("output_sha256"),
                "event_hash": event.event_hash,
            }
            for event in events
            if event.event_type == "runtime.output_gate"
        ],
        important_events=important_events,
        evidence_freshness=_evidence_freshness(events, manifest),
        active_followups=[record.to_dict() for record in active_followup_records],
        recovery_records=[record.to_dict() for record in recoveries],
        lineage=[record.to_dict() for record in lineage_records(events)],
        authorization_checks=[
            {
                "timestamp": event.timestamp,
                "event_hash": event.event_hash,
                **event.payload,
            }
            for event in events
            if event.event_type == "authorization_check"
        ],
        growth_records=[record.to_dict() for record in growth_records],
        active_growth=[record.to_dict() for record in active_growth],
        growth_reviews=[record.to_dict() for record in growth_reviews],
        growth_conflicts=[record.to_dict() for record in growth_conflicts],
        growth_conflict_resolutions=[
            record.to_dict() for record in growth_conflict_resolutions
        ],
        memory_cards=[record.to_dict() for record in memory_cards],
        memory_signals=[record.to_dict() for record in memory_signals],
        reflections=[record.to_dict() for record in reflections],
        reflection_tasks=[record.to_dict() for record in reflection_tasks],
        active_reflection_tasks=[
            record.to_dict() for record in open_reflection_tasks
        ],
        chat_sessions=[record.to_dict() for record in chat_sessions],
        chat_turns=[record.to_dict() for record in chat_turns],
        missions=[brief.to_dict() for brief in missions],
        mission_flows=[flow.to_dict() for flow in mission_flows],
        mission_steps=[step.to_dict() for step in mission_steps],
        evidence_records=[record.to_dict() for record in evidence_records],
        evidence_claims=[record.to_dict() for record in evidence_claims],
        evidence_links=[record.to_dict() for record in evidence_links],
        evidence_reviews=[record.to_dict() for record in evidence_reviews],
        skill_candidates=[record.to_dict() for record in skill_candidates],
        accepted_skills=[record.to_dict() for record in accepted_skills],
        governed_context=governed_context.to_dict(),
        self_model=self_model.to_dict(),
        policy_errors=manifest.policy_errors,
        anchor_verification=anchor_verification,
    )


def _evidence_freshness(
    events: list[ContinuityEvent],
    manifest: IdentityManifest,
) -> list[dict[str, Any]]:
    latest: dict[str, ContinuityEvent] = {}
    for event in events:
        if event.event_type in {"constraint.checked", "constraint.breached"}:
            constraint_name = event.payload.get("constraint")
            if constraint_name is not None:
                latest[str(constraint_name)] = event
    now = datetime.now(timezone.utc)
    rows = []
    for constraint in manifest.constraints:
        event = latest.get(constraint.name)
        age_seconds = None
        stale = False
        if event is not None:
            timestamp = _parse_timestamp(event.timestamp)
            age_seconds = max(0, int((now - timestamp).total_seconds()))
            stale = (
                constraint.freshness_seconds is not None
                and age_seconds > constraint.freshness_seconds
            )
        rows.append(
            {
                "constraint": constraint.name,
                "required": constraint.required,
                "freshness_seconds": constraint.freshness_seconds,
                "latest_event_type": event.event_type if event is not None else None,
                "latest_timestamp": event.timestamp if event is not None else None,
                "latest_event_hash": event.event_hash if event is not None else None,
                "age_seconds": age_seconds,
                "stale": stale,
                "status": _freshness_status(constraint.required, event, stale),
            }
        )
    return rows


def _freshness_status(
    required: bool,
    event: ContinuityEvent | None,
    stale: bool,
) -> str:
    if event is None:
        return "missing_required" if required else "missing_optional"
    if stale:
        return "stale_required" if required else "stale_optional"
    return "fresh"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def render_trace_report_html(report: TraceReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    rows = "\n".join(
        "<tr>"
        f"<td>{event['index']}</td>"
        f"<td>{escape(event['timestamp'])}</td>"
        f"<td><code>{escape(event['event_type'])}</code></td>"
        f"<td>{escape(event['summary'])}</td>"
        f"<td><code>{escape(_short_hash(event['event_hash']))}</code></td>"
        "</tr>"
        for event in data["important_events"]
    )
    claim_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(claim['claim_id']))}</code></td>"
        f"<td>{escape(claim['created_at'])}</td>"
        f"<td><strong>{escape(claim['claim'])}</strong></td>"
        f"<td>{escape(claim['reason'])}</td>"
        "</tr>"
        for claim in data["claim_history"]
    )
    gate_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(event['timestamp']))}</td>"
        f"<td>{escape(str(event['mode']))}</td>"
        f"<td>{escape(str(event['allowed']))}</td>"
        f"<td><code>{escape(_short_hash(str(event['event_hash'])))}</code></td>"
        "</tr>"
        for event in data["output_gate_events"]
    )
    signal_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(event['timestamp']))}</td>"
        f"<td>{escape(str(event['state']))}</td>"
        f"<td>{escape(str(event['source']))}</td>"
        f"<td>{escape(str(event['reason']))}</td>"
        "</tr>"
        for event in data["runtime_signals"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PCA Trace Report</title>
  <style>
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #172026;
      background: #f6f7f4;
    }}
    header {{
      padding: 32px;
      background: #172026;
      color: #f7fbff;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1, h2 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    section {{
      margin: 24px 0;
      padding: 0;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid #d8ddd6;
      border-radius: 8px;
      padding: 14px;
    }}
    .label {{
      color: #61706a;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .value {{
      font-size: 18px;
      font-weight: 700;
      margin-top: 6px;
      overflow-wrap: anywhere;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d8ddd6;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid #e5e8e2;
      padding: 10px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #e8eee9;
      color: #26322d;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>PCA Trace Report</h1>
    <div>{escape(summary['name'])} / <code>{escape(summary['system_id'])}</code></div>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><div class="label">Claim</div><div class="value">{escape(summary['current_continuity_claim'])}</div></div>
      <div class="metric"><div class="label">Identity State</div><div class="value">{escape(summary['identity_state'])}</div></div>
      <div class="metric"><div class="label">Output Mode</div><div class="value">{escape(summary['output_mode'])}</div></div>
      <div class="metric"><div class="label">Chain Valid</div><div class="value">{escape(str(summary['chain_valid']))}</div></div>
      <div class="metric"><div class="label">Events</div><div class="value">{escape(str(summary['event_count']))}</div></div>
      <div class="metric"><div class="label">Blocking Follow-ups</div><div class="value">{escape(str(summary['blocking_followups']))}</div></div>
    </section>
    <section>
      <h2>Claim History</h2>
      <table><thead><tr><th>Claim ID</th><th>Created</th><th>Claim</th><th>Reason</th></tr></thead><tbody>{claim_rows}</tbody></table>
    </section>
    <section>
      <h2>Runtime Signals</h2>
      <table><thead><tr><th>Time</th><th>State</th><th>Source</th><th>Reason</th></tr></thead><tbody>{signal_rows}</tbody></table>
    </section>
    <section>
      <h2>Output Gate Events</h2>
      <table><thead><tr><th>Time</th><th>Mode</th><th>Allowed</th><th>Event Hash</th></tr></thead><tbody>{gate_rows}</tbody></table>
    </section>
    <section>
      <h2>Important Events</h2>
      <table><thead><tr><th>#</th><th>Time</th><th>Type</th><th>Summary</th><th>Hash</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def write_trace_report_html(report: TraceReport, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_trace_report_html(report), encoding="utf-8")
    return output_path

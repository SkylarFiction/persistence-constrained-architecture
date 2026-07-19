from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .coherence_paper_pipeline import coherence_paper_pipeline_records_from_events
from .ledger import ContinuityEvent, ContinuityLedger
from .missions import mission_briefs_from_events
from .paper_readiness import paper_readiness_for_mission
from .source_notes import source_notes_for_mission


EVOLUTION_EVENT_TYPES = {
    "source_note.reviewed": "source note reviewed",
    "external_literature.added": "external literature added",
    "external_literature.reviewed": "external literature reviewed",
    "direct_continuity_experiment.ran": "direct continuity experiment run",
    "output_only_rating.recorded": "output-only rating recorded",
    "argument_node.added": "argument node added",
    "argument_edge.added": "argument edge added",
    "research.output_created": "research draft created",
}


def paper_evolution_status(
    ledger: ContinuityLedger,
    mission_id: str | None = None,
) -> dict[str, Any]:
    """Explain whether regenerating the paper would likely advance it.

    This is an advisory, derived view. It does not block PDF generation and it
    does not review or promote evidence. Its job is to stop the daily UI from
    making "make the same PDF again" feel like research progress.
    """
    selected_mission_id = mission_id or _latest_paper_mission_id(ledger.events())
    if not selected_mission_id:
        return {
            "status": "no_mission",
            "mission_id": None,
            "plain_status": "No research mission yet",
            "should_regenerate": False,
            "recommended_action": "Open or seed a Coherence Physics research mission first.",
            "changes_since_last_paper": [],
            "stagnation_reasons": ["No mission has generated a paper yet."],
            "latest_paper": None,
        }

    readiness = paper_readiness_for_mission(ledger, selected_mission_id)
    pipelines = [
        record
        for record in coherence_paper_pipeline_records_from_events(ledger.events())
        if record.get("mission_id") == selected_mission_id
    ]
    latest_pipeline = pipelines[-1] if pipelines else None
    latest_time = _parse_time(str((latest_pipeline or {}).get("created_at") or ""))
    changes = _changes_since(ledger.events(), selected_mission_id, latest_time)
    latest_artifact = ((latest_pipeline or {}).get("pdf") or {}).get("paper_artifact") or None

    counts = {
        "paper_runs": len(pipelines),
        "source_notes": readiness.get("source_note_count", 0),
        "raw_source_notes": readiness.get("raw_source_note_count", 0),
        "reviewed_source_notes": readiness.get("reviewed_source_note_count", 0),
        "reviewed_source_links": readiness.get("reviewed_source_link_count", 0),
        "external_sources": readiness.get("external_source_count", 0),
        "reviewed_external_sources": readiness.get("reviewed_external_source_count", 0),
        "reader_claims": readiness.get("reader_claim_count", 0),
        "linked_claims": readiness.get("linked_claim_count", 0),
    }

    stagnation_reasons = _stagnation_reasons(readiness, latest_pipeline, changes)
    should_regenerate = bool(changes) or latest_pipeline is None
    if latest_pipeline is not None and not changes:
        status = "unchanged"
        plain_status = "Likely same paper"
        recommended_action = _next_research_action(readiness)
    elif latest_pipeline is None:
        status = "no_previous_paper"
        plain_status = "Ready for first paper run"
        recommended_action = "Generate the first governed paper draft."
    else:
        status = "changed"
        plain_status = "Paper can evolve"
        recommended_action = "Regenerate the paper, then inspect the new PDF."

    return {
        "status": status,
        "plain_status": plain_status,
        "mission_id": selected_mission_id,
        "mission_title": readiness.get("mission_title"),
        "should_regenerate": should_regenerate,
        "recommended_action": recommended_action,
        "changes_since_last_paper": changes,
        "stagnation_reasons": stagnation_reasons,
        "counts": counts,
        "latest_paper": {
            "pipeline_id": latest_pipeline.get("pipeline_id"),
            "created_at": latest_pipeline.get("created_at"),
            "paper_path": ((latest_pipeline.get("pdf") or {}).get("paper_path")),
            "paper_sha256": (latest_artifact or {}).get("sha256"),
            "paper_size_bytes": (latest_artifact or {}).get("size_bytes"),
        } if latest_pipeline else None,
        "guardrail": (
            "Regeneration is not research progress by itself. The paper evolves "
            "when reviewed evidence, external literature, experiments, ratings, "
            "or argument structure change."
        ),
    }


def render_paper_evolution_text(status: dict[str, Any]) -> str:
    counts = status.get("counts") or {}
    lines = [
        "Paper Evolution",
        f"mission: {status.get('mission_title') or status.get('mission_id') or 'none'}",
        f"status: {status.get('plain_status') or status.get('status')}",
        f"should regenerate: {'yes' if status.get('should_regenerate') else 'not yet'}",
        f"next: {status.get('recommended_action') or 'none'}",
        "",
        "counts:",
        f"- paper runs: {counts.get('paper_runs', 0)}",
        f"- reviewed source notes: {counts.get('reviewed_source_notes', 0)} / {counts.get('source_notes', 0)}",
        f"- reviewed source links: {counts.get('reviewed_source_links', 0)}",
        f"- external sources reviewed: {counts.get('reviewed_external_sources', 0)} / {counts.get('external_sources', 0)}",
        f"- linked claims: {counts.get('linked_claims', 0)} / {counts.get('reader_claims', 0)}",
        "",
        "changes since last paper:",
    ]
    changes = status.get("changes_since_last_paper") or []
    if not changes:
        lines.append("- none")
    for change in changes:
        lines.append(
            f"- {change.get('label')} ({change.get('event_type')}) at {change.get('timestamp')}"
        )
    reasons = status.get("stagnation_reasons") or []
    if reasons:
        lines.append("")
        lines.append("why it may repeat:")
        for reason in reasons:
            lines.append(f"- {reason}")
    latest = status.get("latest_paper") or {}
    if latest:
        lines.extend(
            [
                "",
                f"latest paper: {latest.get('paper_path') or 'none'}",
                f"latest sha256: {str(latest.get('paper_sha256') or '')[:12] or 'none'}",
            ]
        )
    lines.extend(["", f"guardrail: {status.get('guardrail') or ''}"])
    return "\n".join(lines)


def _latest_paper_mission_id(events: list[ContinuityEvent]) -> str | None:
    pipelines = coherence_paper_pipeline_records_from_events(events)
    for record in reversed(pipelines):
        if record.get("mission_id"):
            return str(record["mission_id"])
    note_mission_ids = {
        str(event.payload.get("mission_id") or "")
        for event in events
        if event.event_type == "source_note.extracted"
    }
    for brief in reversed(mission_briefs_from_events(events)):
        if brief.mission.mission_id in note_mission_ids:
            return brief.mission.mission_id
    briefs = mission_briefs_from_events(events)
    return briefs[-1].mission.mission_id if briefs else None


def _changes_since(
    events: list[ContinuityEvent],
    mission_id: str,
    since: datetime | None,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    source_note_missions = {
        str(event.payload.get("note_id") or ""): str(event.payload.get("mission_id") or "")
        for event in events
        if event.event_type == "source_note.extracted"
    }
    for event in events:
        if event.event_type not in EVOLUTION_EVENT_TYPES:
            continue
        if since and _parse_time(event.timestamp) <= since:
            continue
        if not _event_applies_to_mission(event, mission_id, source_note_missions):
            continue
        changes.append(
            {
                "event_type": event.event_type,
                "label": EVOLUTION_EVENT_TYPES[event.event_type],
                "timestamp": event.timestamp,
                "event_hash": event.event_hash,
                "detail": _event_detail(event),
            }
        )
    return changes


def _event_applies_to_mission(
    event: ContinuityEvent,
    mission_id: str,
    source_note_missions: dict[str, str],
) -> bool:
    payload = event.payload
    if event.event_type in {
        "direct_continuity_experiment.ran",
        "output_only_rating.recorded",
    }:
        return True
    if str(payload.get("mission_id") or "") == mission_id:
        return True
    if event.event_type == "source_note.reviewed":
        reviewed_note_id = str(payload.get("note_id") or "")
        return source_note_missions.get(reviewed_note_id) == mission_id
    return False


def _event_detail(event: ContinuityEvent) -> str:
    payload = event.payload
    return (
        str(
            payload.get("note_id")
            or payload.get("literature_id")
            or payload.get("output_id")
            or payload.get("node_id")
            or payload.get("experiment_id")
            or payload.get("rating_id")
            or ""
        )
        or event.event_hash[:12]
    )


def _stagnation_reasons(
    readiness: dict[str, Any],
    latest_pipeline: dict[str, Any] | None,
    changes: list[dict[str, Any]],
) -> list[str]:
    if latest_pipeline is None or changes:
        return []
    reasons = ["No paper-evolving ledger events have occurred since the last paper run."]
    if readiness.get("reviewed_source_note_count", 0) == 0:
        reasons.append("No source notes have been steward-reviewed yet.")
    if readiness.get("reviewed_source_link_count", 0) == 0:
        reasons.append("No claim-source links have reviewed support yet.")
    if readiness.get("reviewed_external_source_count", 0) == 0:
        reasons.append("No external scholarly sources have been steward-reviewed yet.")
    if readiness.get("raw_source_note_count", 0):
        reasons.append("Raw source notes are waiting in the Evidence Review Desk.")
    return reasons


def _next_research_action(readiness: dict[str, Any]) -> str:
    if readiness.get("raw_source_note_count", 0):
        return "Review priority source notes before regenerating."
    if readiness.get("external_source_count", 0) == 0:
        return "Add external scholarly literature before regenerating."
    if readiness.get("reviewed_external_source_count", 0) == 0:
        return "Review attached external literature before regenerating."
    if readiness.get("unlinked_claim_count", 0):
        return "Link unsupported claims before regenerating."
    return "Add new evidence, ratings, or experiment results before regenerating."


def _parse_time(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

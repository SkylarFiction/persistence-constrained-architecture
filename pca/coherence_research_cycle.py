from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .coherence_paper_pipeline import run_coherence_paper_pipeline
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .research_review import research_review_desk
from .steward_inbox import steward_inbox


def run_coherence_research_cycle(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    corpus_limit: int = 12,
    use_knowledge_hub: bool = True,
    force: bool = False,
    output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_audit_bundle.pdf",
    paper_output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_paper.pdf",
    packet_output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_research_packet.pdf",
    theory_revision: bool = False,
    llama_writer: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    """Run one non-destructive Coherence research expansion cycle.

    The cycle may index sources, extract notes, map claims, regenerate paper
    artifacts, and refresh review surfaces. It never marks evidence as reviewed
    or certifies conclusions.
    """
    pipeline = run_coherence_paper_pipeline(
        ledger,
        manifest,
        project_root=project_root,
        mission_id=mission_id,
        corpus_limit=corpus_limit,
        use_knowledge_hub=use_knowledge_hub,
        force=force,
        output_path=output_path,
        paper_output_path=paper_output_path,
        packet_output_path=packet_output_path,
        theory_revision=theory_revision,
        llama_writer=llama_writer,
        reason=reason or "automated Coherence research cycle",
    )
    record = pipeline.get("record") or {}
    selected_mission_id = record.get("mission_id") or mission_id
    review = (
        research_review_desk(ledger, str(selected_mission_id))
        if selected_mission_id
        else None
    )
    pdf = pipeline.get("pdf") or {}
    paper_artifact = pdf.get("paper_artifact") or {}
    status = (
        "completed"
        if paper_artifact.get("status") == "completed"
        else "incomplete"
    )
    inbox_items = steward_inbox(ledger)
    cycle_record = {
        "cycle_id": f"coherence_research_cycle_{uuid.uuid4()}",
        "identity_id": manifest.system_id,
        "mission_id": selected_mission_id,
        "mission_title": record.get("mission_title"),
        "status": status,
        "pipeline_id": record.get("pipeline_id"),
        "paper_artifact": paper_artifact,
        "review_next": (record.get("review") or {}).get("next_action"),
        "open_steward_items": len(inbox_items),
        "high_priority_steward_items": len(
            [item for item in inbox_items if item.severity == "high"]
        ),
        "review_summary": review,
        "autonomy_boundary": (
            "cycle expands research and regenerates artifacts; it does not review "
            "evidence, certify claims, accept memory, or publish conclusions"
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason or "automated Coherence research cycle",
    }
    ledger.append("coherence_research.cycle_ran", manifest.system_id, cycle_record)
    return {
        "cycle": cycle_record,
        "pipeline": pipeline,
    }


def coherence_research_cycle_records_from_events(events) -> list[dict[str, Any]]:
    return [
        event.payload
        for event in events
        if event.event_type == "coherence_research.cycle_ran"
    ]


def render_coherence_research_cycle_text(result: dict[str, Any]) -> str:
    cycle = result.get("cycle") or result
    artifact = cycle.get("paper_artifact") or {}
    lines = [
        "Coherence Research Cycle",
        f"status: {cycle.get('status')}",
        f"mission: {cycle.get('mission_title') or cycle.get('mission_id') or 'none'}",
        f"pipeline: {cycle.get('pipeline_id') or 'none'}",
        f"paper: {artifact.get('path') or 'none'}",
        f"paper size: {artifact.get('size_bytes') or 0}",
        f"paper sha256: {str(artifact.get('sha256') or '')[:12] or 'none'}",
        f"review next: {cycle.get('review_next') or 'none'}",
        f"open steward items: {cycle.get('open_steward_items', 0)}",
        f"high priority steward items: {cycle.get('high_priority_steward_items', 0)}",
        "boundary:",
        f"- {cycle.get('autonomy_boundary')}",
    ]
    return "\n".join(lines)

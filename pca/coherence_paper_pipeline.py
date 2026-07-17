from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .argument_graph import seed_continuity_argument_graph
from .coherence_corpus import index_coherence_corpus
from .coherence_seed import seed_coherence_physics_goals
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_claim_map import mission_claim_map
from .missions import MissionStatus, mission_briefs_from_events, open_mission
from .research_autopilot import run_research_autopilot
from .research_pdf import export_research_pdf
from .research_review import research_review_desk
from .research_sandbox import create_research_output, research_outputs_from_events
from .research_writer import generate_llama_research_draft
from .source_notes import extract_source_notes_for_mission
from .theory_revision import build_theory_revision_draft


def run_coherence_paper_pipeline(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    corpus_roots: list[str] | None = None,
    corpus_limit: int = 8,
    use_knowledge_hub: bool = False,
    force: bool = False,
    output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_audit_bundle.pdf",
    paper_output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_paper.pdf",
    packet_output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_research_packet.pdf",
    llama_writer: bool = False,
    writer_model_mode: str = "local_ollama",
    theory_revision: bool = False,
    theory_output_path: str | Path = "../knowledge_hub/generated/research_papers/theory_revision_draft.pdf",
    theory_markdown_output_path: str | Path | None = "../knowledge_hub/generated/research_papers/theory_revision_draft.md",
    reason: str = "",
) -> dict[str, Any]:
    project_path = Path(project_root).resolve()
    actions: list[dict[str, Any]] = []
    seeded = seed_coherence_physics_goals(ledger, manifest)
    actions.append({"action": "seed_coherence_goals", "tracks": len(seeded)})

    selected_mission = (
        _ensure_simple_research_mission(ledger, manifest, actions, reason)
        if not mission_id
        else _select_mission(ledger, mission_id)
    )
    if not selected_mission:
        record = _record_pipeline(
            ledger,
            manifest,
            status="blocked",
            mission_id=None,
            mission_title=None,
            actions=actions + [{"action": "blocked_no_mission"}],
            corpus=None,
            source_notes=None,
            autopilot=None,
            paper_draft=None,
            pdf=None,
            review=None,
            reason=reason,
        )
        return {"record": record}

    corpus = index_coherence_corpus(
        ledger,
        manifest,
        project_root=project_path,
        mission_id=selected_mission["mission_id"],
        roots=corpus_roots,
        limit=corpus_limit,
        use_knowledge_hub=use_knowledge_hub,
        reason=reason or "coherence paper pipeline indexed corpus sources",
    )
    actions.append(
        {
            "action": "index_corpus",
            "indexed": corpus.get("indexed_count", 0),
            "reused": corpus.get("reused_count", 0),
            "linked": corpus.get("linked_count", 0),
        }
    )
    source_notes = extract_source_notes_for_mission(
        ledger,
        manifest,
        project_root=project_path,
        mission_id=selected_mission["mission_id"],
        limit_sources=corpus_limit,
        notes_per_source=3,
        reason=reason or "coherence paper pipeline extracted source notes",
    )
    actions.append(
        {
            "action": "extract_source_notes",
            "created": source_notes.get("created_count", 0),
            "reused": source_notes.get("reused_count", 0),
            "sources": source_notes.get("source_count", 0),
        }
    )

    argument_graph = seed_continuity_argument_graph(
        ledger,
        manifest,
        selected_mission["mission_id"],
        project_root=project_path,
        reason=reason or "coherence paper pipeline seeded argument graph",
    )
    actions.append(
        {
            "action": "seed_argument_graph",
            "nodes": argument_graph.get("node_count", 0),
            "edges": argument_graph.get("edge_count", 0),
        }
    )

    autopilot = run_research_autopilot(
        ledger,
        manifest,
        project_root=project_path,
        mission_id=selected_mission["mission_id"],
        force=force,
        reason=reason or "coherence paper pipeline ran research autopilot",
    )
    actions.append(
        {
            "action": "research_autopilot",
            "status": (autopilot.get("record") or {}).get("status"),
            "outputs": len(autopilot.get("outputs") or []),
        }
    )

    paper_draft = None
    if force or not _has_paper_draft(ledger, selected_mission["mission_id"]):
        paper_draft = create_research_output(
            ledger,
            manifest,
            selected_mission["mission_id"],
            "paper_draft",
            reason=reason or "coherence paper pipeline generated paper draft",
        )
        actions.append(
            {
                "action": _paper_draft_action(paper_draft),
                "output_id": paper_draft["output"]["output_id"],
                "evidence_id": (
                    paper_draft["evidence"]["evidence_id"]
                    if paper_draft.get("evidence")
                    else None
                ),
                "content_hash": (
                    (paper_draft.get("skipped") or {}).get("content_hash")
                    or (paper_draft.get("output") or {}).get("content_hash")
                ),
            }
        )
    else:
        actions.append({"action": "paper_draft_skipped", "reason": "existing paper draft"})

    writer_draft = None
    if llama_writer:
        writer_draft = generate_llama_research_draft(
            ledger,
            manifest,
            selected_mission["mission_id"],
            model_mode=writer_model_mode,
            reason=reason or "coherence paper pipeline generated local manuscript synthesis",
        )
        actions.append(
            {
                "action": "llama_research_writer",
                "status": writer_draft.get("status"),
                "provider": writer_draft.get("provider"),
                "model": writer_draft.get("model"),
                "draft_hash": writer_draft.get("draft_hash"),
            }
        )
    else:
        actions.append({"action": "llama_research_writer_skipped"})

    theory_draft = None
    if theory_revision:
        theory_draft = build_theory_revision_draft(
            ledger,
            manifest,
            mission_id=selected_mission["mission_id"],
            output_path=theory_output_path,
            markdown_output_path=theory_markdown_output_path,
            reason=reason or "coherence paper pipeline generated formal theory revision",
        )
        actions.append(
            {
                "action": "theory_revision_draft",
                "pdf_path": theory_draft.get("pdf_path"),
                "markdown_path": theory_draft.get("markdown_path"),
                "content_hash": (theory_draft.get("record") or {}).get("content_hash"),
            }
        )
    else:
        actions.append({"action": "theory_revision_draft_skipped"})

    pdf = export_research_pdf(
        ledger,
        manifest,
        selected_mission["mission_id"],
        output_path,
        project_root=project_path,
        paper_output_path=paper_output_path,
        packet_output_path=packet_output_path,
    )
    actions.append(
        {
            "action": "research_pdf_exported",
            "artifact_status": pdf.get("artifact_status"),
            "path": pdf["audit_path"],
            "paper_path": pdf["paper_path"],
            "packet_path": pdf.get("packet_path"),
            "paper_size_bytes": (pdf.get("paper_artifact") or {}).get("size_bytes"),
            "paper_sha256": (pdf.get("paper_artifact") or {}).get("sha256"),
        }
    )
    review = research_review_desk(ledger, selected_mission["mission_id"])
    claim_map = mission_claim_map(ledger, selected_mission["mission_id"])
    record = _record_pipeline(
        ledger,
        manifest,
        status="paper_packet_ready",
        mission_id=selected_mission["mission_id"],
        mission_title=selected_mission["title"],
        actions=actions,
        corpus=corpus,
        source_notes=source_notes,
        autopilot=autopilot,
        paper_draft=paper_draft,
        pdf=pdf,
        review=review,
        reason=reason,
        claim_map=claim_map,
        writer_draft=writer_draft,
        theory_draft=theory_draft,
    )
    return {
        "record": record,
        "corpus": corpus,
        "source_notes": source_notes,
        "autopilot": autopilot,
        "paper_draft": paper_draft,
        "writer_draft": writer_draft,
        "theory_draft": theory_draft,
        "pdf": pdf,
        "review": review,
    }


def coherence_paper_pipeline_records_from_events(events) -> list[dict[str, Any]]:
    return [
        event.payload
        for event in events
        if event.event_type == "coherence_paper.pipeline_ran"
    ]


def render_coherence_paper_pipeline_text(result: dict[str, Any]) -> str:
    record = result["record"]
    lines = [
        "Coherence Physics Paper Pipeline",
        f"status: {record.get('status')}",
        f"mission: {record.get('mission_title') or 'none'}",
        f"paper: {(record.get('pdf') or {}).get('paper_path') or 'none'}",
        f"research packet: {(record.get('pdf') or {}).get('packet_path') or 'none'}",
        f"audit bundle: {(record.get('pdf') or {}).get('audit_path') or 'none'}",
        f"artifact status: {(record.get('pdf') or {}).get('artifact_status') or 'unverified'}",
        f"paper artifact: {_artifact_line(((record.get('pdf') or {}).get('paper_artifact') or {}))}",
        f"theory revision: {(record.get('theory_draft') or {}).get('pdf_path') or 'none'}",
        f"review next: {(record.get('review') or {}).get('next_action') or 'none'}",
        "actions:",
    ]
    for action in record.get("actions") or []:
        lines.append(f"- {action.get('action')}: {action}")
    lines.extend(
        [
            "guardrail:",
            "- The packet is a governed draft until evidence and conclusions are reviewed.",
        ]
    )
    return "\n".join(lines)


def _artifact_line(artifact: dict[str, Any]) -> str:
    if not artifact:
        return "none"
    size = artifact.get("size_bytes")
    digest = str(artifact.get("sha256") or "")
    digest_short = digest[:12] if digest else "no-hash"
    return (
        f"{artifact.get('status', 'unknown')} "
        f"{artifact.get('filename', artifact.get('path', 'unknown'))} "
        f"size={size or 0} sha256={digest_short}"
    )


def _record_pipeline(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    status: str,
    mission_id: str | None,
    mission_title: str | None,
    actions: list[dict[str, Any]],
    corpus: dict[str, Any] | None,
    source_notes: dict[str, Any] | None,
    autopilot: dict[str, Any] | None,
    paper_draft: dict[str, Any] | None,
    pdf: dict[str, Any] | None,
    review: dict[str, Any] | None,
    reason: str = "",
    claim_map: dict[str, Any] | None = None,
    writer_draft: dict[str, Any] | None = None,
    theory_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "pipeline_id": f"coherence_paper_pipeline_{uuid.uuid4()}",
        "identity_id": manifest.system_id,
        "status": status,
        "mission_id": mission_id,
        "mission_title": mission_title,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "actions": actions,
        "corpus_summary": _corpus_summary(corpus),
        "source_note_summary": _source_note_summary(source_notes),
        "autopilot_status": (autopilot.get("record") or {}).get("status") if autopilot else None,
        "paper_draft_output_id": ((paper_draft or {}).get("output") or {}).get("output_id"),
        "writer_draft": _writer_draft_summary(writer_draft),
        "theory_draft": _theory_draft_summary(theory_draft),
        "pdf": pdf,
        "review": {
            "next_action": (review or {}).get("next_action"),
            "raw_evidence": ((review or {}).get("cards") or {}).get("raw_evidence", {}).get("value", 0),
            "reviewed_evidence": ((review or {}).get("cards") or {}).get("reviewed_evidence", {}).get("value", 0),
        },
        "claim_map_summary": _claim_map_summary(claim_map),
        "final_requirement": "every research cycle must produce or update a paper packet before being considered complete",
        "governance": "draft packet only; steward review required before treating conclusions as accepted",
        "will_not": [
            "publish automatically",
            "treat raw evidence as reviewed",
            "claim final truth without steward review",
        ],
        "reason": reason or "coherence paper pipeline run",
    }
    ledger.append("coherence_paper.pipeline_ran", manifest.system_id, record)
    return record


def _select_mission(ledger: ContinuityLedger, mission_id: str | None) -> dict[str, str] | None:
    if mission_id:
        for brief in mission_briefs_from_events(ledger.events()):
            if brief.mission.mission_id == mission_id:
                return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
        return None
    preferred_titles = [
        "Map Coherence Physics Claims",
        "Ground Core Claims in Evidence",
        "Write Public Coherence Narrative",
    ]
    for title in preferred_titles:
        for brief in mission_briefs_from_events(ledger.events()):
            if brief.mission.title == title and brief.mission.status == MissionStatus.OPEN:
                return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    for brief in mission_briefs_from_events(ledger.events()):
        if brief.mission.status == MissionStatus.OPEN and "coherence" in brief.mission.title.lower():
            return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    return None


def _ensure_simple_research_mission(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    actions: list[dict[str, Any]],
    reason: str,
) -> dict[str, str]:
    for brief in mission_briefs_from_events(ledger.events()):
        if (
            brief.mission.title == "Coherence Physics Research Program"
            and brief.mission.status == MissionStatus.OPEN
        ):
            return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    mission = open_mission(
        ledger,
        manifest.system_id,
        title="Coherence Physics Research Program",
        problem_statement=(
            "Research Coherence Physics, gather source evidence, map claims, "
            "form provisional conclusions, identify inventions or ideas, and "
            "finish each run with a reviewable paper PDF."
        ),
        values=[
            "truth before comfort",
            "evidence first",
            "clarity",
            "recoverable reasoning",
            "finish with a paper",
        ],
        reason=reason or "coherence paper pipeline opened simple research mission",
    )
    actions.append({"action": "open_simple_research_mission", "mission_id": mission.mission_id})
    return {"mission_id": mission.mission_id, "title": mission.title}


def _has_paper_draft(ledger: ContinuityLedger, mission_id: str) -> bool:
    return any(
        output.kind.value == "paper_draft"
        for output in research_outputs_from_events(ledger.events(), mission_id)
    )


def _paper_draft_action(paper_draft: dict[str, Any]) -> str:
    if paper_draft.get("skipped"):
        return "paper_draft_skipped_unchanged"
    if paper_draft.get("regeneration"):
        return "paper_draft_regenerated"
    return "paper_draft_created"


def _theory_draft_summary(theory_draft: dict[str, Any] | None) -> dict[str, Any] | None:
    if not theory_draft:
        return None
    record = theory_draft.get("record") or {}
    return {
        "draft_id": record.get("draft_id"),
        "title": record.get("title"),
        "pdf_path": theory_draft.get("pdf_path") or record.get("pdf_path"),
        "markdown_path": theory_draft.get("markdown_path") or record.get("markdown_path"),
        "content_hash": record.get("content_hash"),
    }


def _corpus_summary(corpus: dict[str, Any] | None) -> str:
    if not corpus:
        return ""
    return (
        f"{corpus.get('candidate_count', 0)} source(s), "
        f"{corpus.get('indexed_count', 0)} indexed, "
        f"{corpus.get('linked_count', 0)} linked"
    )


def _source_note_summary(source_notes: dict[str, Any] | None) -> str:
    if not source_notes:
        return ""
    return (
        f"{source_notes.get('created_count', 0)} new note(s), "
        f"{source_notes.get('reused_count', 0)} reused, "
        f"{source_notes.get('source_count', 0)} source(s)"
    )


def _claim_map_summary(claim_map: dict[str, Any] | None) -> str:
    if not claim_map:
        return ""
    return (
        f"{claim_map.get('claim_count', 0)} claim(s), "
        f"{claim_map.get('raw_evidence_count', 0)} raw evidence, "
        f"{claim_map.get('reviewed_evidence_count', 0)} reviewed evidence"
    )


def _writer_draft_summary(writer_draft: dict[str, Any] | None) -> dict[str, Any] | None:
    if not writer_draft:
        return None
    return {
        "status": writer_draft.get("status"),
        "provider": writer_draft.get("provider"),
        "model": writer_draft.get("model"),
        "draft_hash": writer_draft.get("draft_hash"),
        "response_length": writer_draft.get("response_length"),
        "estimated_cost_usd": writer_draft.get("estimated_cost_usd"),
    }

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .coherence_corpus import index_coherence_corpus
from .coherence_seed import seed_coherence_physics_goals
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_claim_map import mission_claim_map
from .missions import MissionStatus, mission_briefs_from_events
from .research_autopilot import run_research_autopilot
from .research_pdf import export_research_pdf
from .research_review import research_review_desk
from .research_sandbox import create_research_output, research_outputs_from_events


def run_coherence_paper_pipeline(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    corpus_roots: list[str] | None = None,
    corpus_limit: int = 8,
    force: bool = False,
    output_path: str | Path = "reports/coherence_physics_research_packet.pdf",
    reason: str = "",
) -> dict[str, Any]:
    project_path = Path(project_root).resolve()
    actions: list[dict[str, Any]] = []
    seeded = seed_coherence_physics_goals(ledger, manifest)
    actions.append({"action": "seed_coherence_goals", "tracks": len(seeded)})

    selected_mission = _select_mission(ledger, mission_id)
    if not selected_mission:
        record = _record_pipeline(
            ledger,
            manifest,
            status="blocked",
            mission_id=None,
            mission_title=None,
            actions=actions + [{"action": "blocked_no_mission"}],
            corpus=None,
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
                "action": "paper_draft_created",
                "output_id": paper_draft["output"]["output_id"],
                "evidence_id": paper_draft["evidence"]["evidence_id"],
            }
        )
    else:
        actions.append({"action": "paper_draft_skipped", "reason": "existing paper draft"})

    pdf = export_research_pdf(
        ledger,
        manifest,
        selected_mission["mission_id"],
        output_path,
    )
    actions.append({"action": "research_pdf_exported", "path": pdf["path"]})
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
        autopilot=autopilot,
        paper_draft=paper_draft,
        pdf=pdf,
        review=review,
        reason=reason,
        claim_map=claim_map,
    )
    return {
        "record": record,
        "corpus": corpus,
        "autopilot": autopilot,
        "paper_draft": paper_draft,
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
        f"pdf: {(record.get('pdf') or {}).get('path') or 'none'}",
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


def _record_pipeline(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    status: str,
    mission_id: str | None,
    mission_title: str | None,
    actions: list[dict[str, Any]],
    corpus: dict[str, Any] | None,
    autopilot: dict[str, Any] | None,
    paper_draft: dict[str, Any] | None,
    pdf: dict[str, Any] | None,
    review: dict[str, Any] | None,
    reason: str = "",
    claim_map: dict[str, Any] | None = None,
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
        "autopilot_status": (autopilot.get("record") or {}).get("status") if autopilot else None,
        "paper_draft_output_id": ((paper_draft or {}).get("output") or {}).get("output_id"),
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


def _has_paper_draft(ledger: ContinuityLedger, mission_id: str) -> bool:
    return any(
        output.kind.value == "paper_draft"
        for output in research_outputs_from_events(ledger.events(), mission_id)
    )


def _corpus_summary(corpus: dict[str, Any] | None) -> str:
    if not corpus:
        return ""
    return (
        f"{corpus.get('candidate_count', 0)} source(s), "
        f"{corpus.get('indexed_count', 0)} indexed, "
        f"{corpus.get('linked_count', 0)} linked"
    )


def _claim_map_summary(claim_map: dict[str, Any] | None) -> str:
    if not claim_map:
        return ""
    return (
        f"{claim_map.get('claim_count', 0)} claim(s), "
        f"{claim_map.get('raw_evidence_count', 0)} raw evidence, "
        f"{claim_map.get('reviewed_evidence_count', 0)} reviewed evidence"
    )

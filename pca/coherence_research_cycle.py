from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

from .coherence_corpus import DEFAULT_CORPUS_ROOTS, SUPPORTED_SUFFIXES
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


def verify_coherence_research_cycle_readiness(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    corpus_limit: int = 12,
    run_sample: bool = True,
    reason: str = "",
) -> dict[str, Any]:
    project_path = Path(project_root).resolve()
    before_events = ledger.events()
    before_reviews = _review_event_counts(before_events)
    before_sources = _source_inventory(project_path)
    sample = None
    if run_sample:
        sample = run_coherence_research_cycle(
            ledger,
            manifest,
            project_root=project_path,
            mission_id=mission_id,
            corpus_limit=corpus_limit,
            use_knowledge_hub=True,
            force=True,
            reason=reason or "research cycle readiness sample run",
        )
    after_events = ledger.events()
    after_reviews = _review_event_counts(after_events)
    after_sources = _source_inventory(project_path)
    review_counts_unchanged = before_reviews == after_reviews
    source_changes = _source_inventory_changes(before_sources, after_sources)
    artifact = (
        ((sample or {}).get("cycle") or {}).get("paper_artifact")
        if sample
        else _latest_cycle_artifact(after_events)
    ) or {}
    pdf_verified = (
        artifact.get("status") == "completed"
        and int(artifact.get("size_bytes") or 0) > 0
        and bool(artifact.get("sha256"))
    )
    inbox_items = steward_inbox(ledger)
    high_priority = [item for item in inbox_items if item.severity == "high"]
    failures: list[str] = []
    warnings: list[str] = []
    if run_sample and not sample:
        failures.append("sample cycle did not run")
    if run_sample and ((sample.get("cycle") or {}).get("status") != "completed"):
        failures.append("sample cycle did not complete")
    if not pdf_verified:
        failures.append("no verified PDF artifact available")
    if not review_counts_unchanged:
        failures.append("cycle changed review/certification event counts")
    if source_changes:
        failures.append("cycle changed source-folder files")
    if high_priority:
        warnings.append(
            f"{len(high_priority)} high-priority steward item(s) remain before unattended scheduling"
        )
    if inbox_items:
        warnings.append(f"{len(inbox_items)} open steward item(s) remain for human review")
    status = "ready"
    if warnings:
        status = "ready_with_warnings"
    if failures:
        status = "not_ready"
    result = {
        "status": status,
        "schedule_ready": not failures and not high_priority,
        "safe_to_run_cycle": not failures,
        "sample_run": bool(sample),
        "paper_artifact": artifact,
        "review_counts_before": before_reviews,
        "review_counts_after": after_reviews,
        "review_counts_unchanged": review_counts_unchanged,
        "source_file_count_before": len(before_sources),
        "source_file_count_after": len(after_sources),
        "source_inventory_changed": bool(source_changes),
        "source_inventory_changes": source_changes[:20],
        "open_steward_items": len(inbox_items),
        "high_priority_steward_items": len(high_priority),
        "failures": failures,
        "warnings": warnings,
        "autonomy_boundary": (
            "Ready checks require PDF artifact proof and verify the cycle did not "
            "mark evidence reviewed, review source notes, review external literature, "
            "or modify source-folder files."
        ),
    }
    ledger.append(
        "coherence_research.readiness_checked",
        manifest.system_id,
        {
            **result,
            "paper_artifact": {
                key: artifact.get(key)
                for key in ("path", "filename", "size_bytes", "sha256", "status")
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason or "research cycle readiness check",
        },
    )
    return result


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


def render_coherence_research_cycle_readiness_text(result: dict[str, Any]) -> str:
    artifact = result.get("paper_artifact") or {}
    lines = [
        "Coherence Research Cycle Readiness",
        f"status: {result.get('status')}",
        f"schedule ready: {result.get('schedule_ready')}",
        f"safe to run cycle: {result.get('safe_to_run_cycle')}",
        f"sample run: {result.get('sample_run')}",
        f"paper: {artifact.get('path') or 'none'}",
        f"paper size: {artifact.get('size_bytes') or 0}",
        f"paper sha256: {str(artifact.get('sha256') or '')[:12] or 'none'}",
        f"review counts unchanged: {result.get('review_counts_unchanged')}",
        f"source inventory changed: {result.get('source_inventory_changed')}",
        f"open steward items: {result.get('open_steward_items', 0)}",
        f"high priority steward items: {result.get('high_priority_steward_items', 0)}",
    ]
    if result.get("failures"):
        lines.append("failures:")
        lines.extend(f"- {failure}" for failure in result["failures"])
    if result.get("warnings"):
        lines.append("warnings:")
        lines.extend(f"- {warning}" for warning in result["warnings"])
    lines.extend(["boundary:", f"- {result.get('autonomy_boundary')}"])
    return "\n".join(lines)


def _review_event_counts(events) -> dict[str, int]:
    event_types = (
        "evidence.reviewed",
        "source_note.reviewed",
        "external_literature.reviewed",
    )
    return {
        event_type: len([event for event in events if event.event_type == event_type])
        for event_type in event_types
    }


def _source_inventory(project_root: Path) -> dict[str, tuple[int, int]]:
    inventory: dict[str, tuple[int, int]] = {}
    for root in DEFAULT_CORPUS_ROOTS:
        path = (project_root / root).resolve()
        if not path.exists():
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file() or candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                stat = candidate.stat()
            except OSError:
                continue
            inventory[str(candidate)] = (stat.st_size, stat.st_mtime_ns)
    return inventory


def _source_inventory_changes(
    before: dict[str, tuple[int, int]],
    after: dict[str, tuple[int, int]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    before_keys = set(before)
    after_keys = set(after)
    for path in sorted(before_keys - after_keys):
        changes.append({"path": path, "change": "removed"})
    for path in sorted(after_keys - before_keys):
        changes.append({"path": path, "change": "added"})
    for path in sorted(before_keys & after_keys):
        if before[path] != after[path]:
            changes.append({"path": path, "change": "modified"})
    return changes


def _latest_cycle_artifact(events) -> dict[str, Any] | None:
    for record in reversed(coherence_research_cycle_records_from_events(events)):
        artifact = record.get("paper_artifact") or {}
        if artifact.get("status") == "completed":
            return artifact
    return None

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
from typing import Any
import hashlib
import re

from .argument_graph import mission_argument_graph
from .claim_source_links import claim_source_links
from .coherence_corpus import coherence_corpus_index_records_from_events, is_relevant_source_path
from .direct_continuity_experiment import latest_direct_continuity_experiment
from .output_only_rating import score_output_only_arm
from .evidence_locker import evidence_for_target
from .external_literature import external_literature_for_mission
from .falsification_lab import falsification_lab_verdict
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_claim_map import mission_claim_map
from .missions import mission_briefs_from_events, require_mission
from .research_sandbox import (
    render_research_output_content,
    research_output_regenerations_from_events,
    research_outputs_from_events,
)
from .research_writer import latest_research_writer_draft
from .source_notes import source_notes_for_mission


def export_research_pdf(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_audit_bundle.pdf",
    project_root: str | Path = ".",
    paper_output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_paper.pdf",
    packet_output_path: str | Path = "../knowledge_hub/generated/research_papers/coherence_research_packet.pdf",
) -> dict[str, Any]:
    """Export the two paired research documents for a mission.

    ``paper_output_path`` is the reader-facing scholarly paper: argument,
    definitions, findings, references -- no raw IDs, no registration stubs,
    no duplicate drafts. ``packet_output_path`` is the research packet: claim
    matrix, source coverage, gaps, counterarguments, and agenda. ``output_path``
    is the audit bundle: evidence IDs, hashes, review status, duplicate
    generation events, and complete machine history.
    """
    workspace_root = Path(project_root).resolve().parent
    mission = require_mission(ledger.events(), mission_id)
    brief = next(
        item
        for item in mission_briefs_from_events(ledger.events())
        if item.mission.mission_id == mission_id
    )
    outputs = research_outputs_from_events(ledger.events(), mission_id)
    regenerations = research_output_regenerations_from_events(ledger.events(), mission_id)
    claim_map = mission_claim_map(ledger, mission_id)
    linked_evidence = evidence_for_target(ledger.events(), "mission", mission_id)
    # Corpus indexing and source-note extraction are append-only ledger history:
    # a source indexed before the relevance gate existed (or before it was
    # tightened) stays reused indefinitely by source_hash and never gets
    # re-filtered. Re-checking relevance here, at the point the PDFs actually
    # render these lists, means an irrelevant source can never resurface in
    # either document regardless of how old the mission or how the evidence
    # was originally registered.
    corpus_sources = [
        source
        for source in _corpus_sources_for_mission(ledger.events(), mission_id)
        if is_relevant_source_path(str(source.get("path") or ""))
    ]
    source_notes = [
        _annotate_source_note_quality(note)
        for note in source_notes_for_mission(ledger.events(), mission_id)
        if is_relevant_source_path(str(note.get("source_path") or ""))
    ]
    external_literature = external_literature_for_mission(ledger.events(), mission_id)

    paper_path = Path(paper_output_path)
    packet_path = Path(packet_output_path)
    audit_path = Path(output_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    paper_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    argument_graph = mission_argument_graph(ledger, mission_id)
    writer_draft = latest_research_writer_draft(ledger.events(), mission_id)
    theory_revision_record = _latest_theory_revision_record(ledger.events(), mission_id)
    reader_claims = _reader_facing_claim_entries(claim_map)
    source_links = claim_source_links(reader_claims, source_notes)
    source_coverage = _source_coverage_rows(corpus_sources, source_notes, source_links)
    quality_warnings = _quality_warnings(claim_map, source_coverage, source_notes, regenerations)
    paper_readiness = _paper_readiness(
        claim_map=claim_map,
        reader_claims=reader_claims,
        source_links=source_links,
        source_notes=source_notes,
        corpus_sources=corpus_sources,
        external_literature=external_literature,
    )
    direct_experiment = latest_direct_continuity_experiment(ledger.events())
    output_only_result = score_output_only_arm(ledger, manifest)

    paper_lines = _scholarly_paper_lines(
        mission_title=mission.title,
        claim_map=claim_map,
        reader_claims=reader_claims,
        source_links=source_links,
        paper_readiness=paper_readiness,
        corpus_sources=corpus_sources,
        source_notes=source_notes,
        writer_draft=writer_draft,
        falsification_verdict=falsification_lab_verdict(workspace_root),
        argument_graph=argument_graph,
        research_packet_path=str(packet_path),
        direct_experiment=direct_experiment,
        output_only_result=output_only_result,
        theory_revision_record=theory_revision_record,
    )
    packet_lines = _research_packet_lines(
        mission_title=mission.title,
        mission_id=mission_id,
        claim_map=claim_map,
        argument_graph=argument_graph,
        source_links=source_links,
        source_coverage=source_coverage,
        source_notes=source_notes,
        quality_warnings=quality_warnings,
        paper_path=str(paper_path),
        audit_bundle_path=str(audit_path),
    )
    audit_lines = _audit_bundle_lines(
        manifest=manifest,
        mission_title=mission.title,
        mission_id=mission_id,
        mission_status=mission.status.value,
        values=mission.values,
        item_counts=brief.to_dict()["counts"],
        outputs=outputs,
        output_contents=[
            (output, render_research_output_content(ledger.events(), output))
            for output in outputs
        ],
        claim_map=claim_map,
        linked_evidence=linked_evidence,
        source_notes=source_notes,
        source_links=source_links,
        regenerations=regenerations,
        quality_warnings=quality_warnings,
        paper_path=str(paper_path),
        packet_path=str(packet_path),
    )
    _write_text_pdf(
        paper_path,
        paper_lines,
        title=f"Coherence Physics Paper - {mission.title}",
        cover_title="Smooth Output Is Not Continuity",
        subtitle="A Coherence Physics Approach to Governed Artificial Identity",
        meta_lines=[
            "Author: Skylar Fiction with Lucien/PCA research assistance",
            "Status: governed draft for human review",
            f"Mission: {mission.title}",
        ],
    )
    _write_text_pdf(
        packet_path,
        packet_lines,
        title=f"Coherence Physics Research Packet - {mission.title}",
        cover_title="Coherence Physics Research Packet",
        subtitle=mission.title,
        meta_lines=[
            "Inspectable research layer: claim matrix, source coverage, gaps, agenda.",
        ],
    )
    _write_text_pdf(
        audit_path,
        audit_lines,
        title=f"Coherence Physics Audit Bundle - {mission.title}",
        cover_title="Coherence Physics Audit Bundle",
        subtitle=mission.title,
        meta_lines=[
            "Complete machine record: evidence IDs, hashes, review status, full history.",
        ],
    )
    paper_artifact = _verified_pdf_artifact(paper_path, "reader_facing_paper")
    packet_artifact = _verified_pdf_artifact(packet_path, "research_packet")
    audit_artifact = _verified_pdf_artifact(audit_path, "audit_bundle")
    artifacts = {
        "paper": paper_artifact,
        "packet": packet_artifact,
        "audit_bundle": audit_artifact,
    }
    return {
        "path": str(audit_path),
        "audit_path": str(audit_path),
        "paper_path": str(paper_path),
        "packet_path": str(packet_path),
        "artifact_status": "completed",
        "paper_artifact": paper_artifact,
        "packet_artifact": packet_artifact,
        "audit_artifact": audit_artifact,
        "artifacts": artifacts,
        "mission_id": mission_id,
        "mission_title": mission.title,
        "output_count": len(outputs),
        "evidence_count": len(linked_evidence),
        "source_count": len(corpus_sources),
        "source_note_count": len(source_notes),
        "claim_count": claim_map.get("claim_count", 0),
        "quality_warnings": quality_warnings,
        "claim_source_links": source_links,
        "paper_readiness": paper_readiness,
        "source_coverage": source_coverage,
        "research_writer": writer_draft,
        "duplicate_output_regenerations": len(regenerations),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governance": "export only; does not accept claims, evidence, memory, or mission outcomes",
    }


def _verified_pdf_artifact(path: Path, artifact_type: str) -> dict[str, Any]:
    """Return a durable artifact record or fail before the pipeline claims success."""
    if not path.exists():
        raise RuntimeError(f"{artifact_type} PDF was not created: {path}")
    data = path.read_bytes()
    if not data:
        raise RuntimeError(f"{artifact_type} PDF is empty: {path}")
    if not data.startswith(b"%PDF-"):
        raise RuntimeError(f"{artifact_type} artifact is not a PDF: {path}")
    stat = path.stat()
    return {
        "artifact_type": artifact_type,
        "status": "completed",
        "path": str(path),
        "filename": path.name,
        "size_bytes": stat.st_size,
        "sha256": hashlib.sha256(data).hexdigest(),
        "created_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
        "open_label": "Open PDF",
    }


def _scholarly_paper_lines(
    mission_title: str,
    claim_map: dict[str, Any],
    reader_claims: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
    paper_readiness: dict[str, Any],
    corpus_sources: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    writer_draft: dict[str, Any] | None,
    falsification_verdict: dict[str, Any] | None,
    argument_graph: dict[str, Any],
    research_packet_path: str,
    direct_experiment: dict[str, Any] | None,
    output_only_result: dict[str, Any] | None = None,
    theory_revision_record: dict[str, Any] | None = None,
) -> list[str]:
    reviewed_evidence = int(claim_map.get("reviewed_evidence_count", 0) or 0)
    claim_candidate_notes = [
        note for note in source_notes if note.get("note_kind") == "claim_candidate"
    ]
    reader_ready_notes = [
        note for note in claim_candidate_notes if _source_note_reader_ready(note)
    ]
    damaged_note_count = len(claim_candidate_notes) - len(reader_ready_notes)
    reviewed_source_note_count = len([
        note for note in source_notes if str(note.get("review_status") or "") == "reviewed"
    ])
    reviewed_source_link_count = len([
        link for link in source_links if str(link.get("review_status") or "") == "reviewed"
    ])
    lines = [
        "Smooth Output Is Not Continuity:",
        "A Coherence Physics Approach to Governed Artificial Identity",
        "",
        "Author: Skylar Fiction with Lucien/PCA research assistance",
        "Status: governed draft for human review",
        "",
        "Abstract",
        "Fluent, stylistically consistent output from an AI system is insufficient "
        "to establish that its memory, commitments, authority, or lineage survived "
        "whatever change produced that output. This paper argues that identity continuity "
        "must be treated as an inspectable, governed claim -- backed by a signed "
        "identity manifest, a tamper-evident event ledger, and evidence explicitly "
        "marked raw or reviewed -- rather than inferred from behavior alone. "
        "Persistence-Constrained Architecture (PCA) is presented as a working local "
        "implementation of that requirement. A separate failed RTI experiment is "
        "included only as a governance case study showing how the pipeline reports "
        "negative results; it does not support the continuity thesis. The "
        "definitions, formal criteria, and related-work comparison below are this "
        "draft's own conceptual contribution; they have not yet been reviewed and "
        "should be read as provisional, not as accepted findings.",
        "",
        "Keywords",
        "Coherence Physics; identity continuity; PCA; artificial identity; memory "
        "governance; recoverability; evidence ledger; Lucien",
        "",
        "1. Research Question",
        "Under what operational conditions may an artificial system legitimately "
        "claim identity continuity across memory modification, migration, "
        "restoration, or architectural change?",
        "",
        "2. Provisional Thesis",
        "Identity continuity should not be inferred from fluent behavior; it should "
        "be certified against operational conditions that name which invariant was "
        "at stake, which ledger events bound the before and after states, and "
        "whether the supporting evidence was reviewed. Coherence Physics, in its "
        "current form, is best read as a research method for defining those "
        "conditions rather than a finished doctrine: it asks how systems preserve "
        "recoverable structure through disturbance, and turns that question into an "
        "engineering rule for artificial identity systems specifically.",
        "",
        "3. Background and Motivation",
        "Coherence Physics treats coherence as recoverable persistence, not merely "
        "order, symmetry, or verbal consistency. Across the current archive, the "
        "recurring concern is whether systems preserve structure through stress, "
        "transformation, memory loss, migration, or collapse. PCA and Lucien are a "
        "software testbed for this idea: continuity may change, but it cannot be "
        "silently asserted. This matters because a model can maintain tone while its "
        "underlying memory, authority, or lineage state has changed.",
        "",
        "4. Definitions",
        "Continuity is the claim that a system's identity-relevant state -- memory, "
        "commitments, authority, lineage -- was preserved across a transition, not "
        "merely that its output remained fluent. Persistence is the property being "
        "claimed: a structure's capacity to stay recoverable under disturbance rather "
        "than simply unchanged. Recovery is the process of returning to a stable, "
        "identity-consistent state after a disturbance; the archived Coherence "
        "Physics material formalizes this as a Recovery Threshold Index (RTI), the "
        "ratio of a system's actual recovery time to a reference recovery time, "
        "where RTI near 1 reads as nominal stability and RTI growing beyond 1 reads "
        "as degraded recoverability approaching a collapse boundary -- the point past "
        "which recovery is no longer available under the system's admissible "
        "dynamics. This RTI description is paraphrased from source PDF text that "
        "extracted with visible symbol and subscript loss (see Appendix D); the "
        "relationship it describes should be treated as provisional until checked "
        "against a clean copy of the source equation, not as a verified formula. A "
        "governed claim is any of the above stated with its evidence, its "
        "confidence, and its reviewer named, rather than asserted as unqualified "
        "fact.",
        "",
        "5. Formal Criteria for Governed Continuity",
        "Let an identity-relevant state be represented compactly as "
        "S_t = (M_t, C_t, A_t, L_t), where M names memory state, C names "
        "standing commitments, A names authority or permission state, and L names "
        "lineage. A transition T: S_0 -> S_1 may be certified as continuous only "
        "when required invariants remain inside their permitted bounds, the "
        "transition belongs to the declared allowed-transform set, the ledger "
        "segment connecting S_0 and S_1 validates, required evidence is present "
        "and fresh enough, review requirements are satisfied, and no unresolved "
        "continuity-break or fork event exists.",
        "",
        "PCA treats this rule as checkable rather than assumed by requiring three "
        "concrete artifacts. First, an identity manifest that fixes a system_id, a "
        "declared version, and a list of invariants and constraints -- each "
        "constraint naming what it bounds, whether it is required, its threshold, "
        "and how fresh its supporting measurement must be -- together with an "
        "explicit list of allowed transforms the system may undergo without "
        "breaking identity. Second, a hash-chained continuity ledger in which every "
        "event carries its type, its subject, a payload, a timestamp, and a hash of "
        "the previous event, so local event alteration or removal becomes "
        "detectable relative to a trusted anchor. A hash chain alone is not a "
        "complete security boundary: an attacker able to rewrite the entire ledger "
        "could regenerate hashes unless the system also uses signed events, "
        "external checkpoints, append-only storage, or independent replicas. Third, "
        "an evidence layer that "
        "distinguishes raw from reviewed support, so a claim's confidence is a "
        "function of who checked it, not how many sources cite it. Under this "
        "scheme, a system asserting continuity through change must be able to name "
        "which invariant or constraint was at stake, which ledger events bound the "
        "before and after states, and whether the supporting evidence has been "
        "reviewed or is still raw. A system that cannot produce these three things "
        "has not demonstrated continuity, however coherent its output sounds. "
        "Sections 4 and 5 are this draft's own conceptual framing, generated from "
        "the archive and PCA's source code rather than from reviewed evidence; the "
        f"claim map below currently shows {reviewed_evidence} reviewed evidence "
        "record(s), so these definitions and criteria should be read as proposed "
        "vocabulary, not as findings that have cleared review.",
        "",
        "6. Related Work: How This Differs",
        "Governed continuity overlaps with, but is distinct from, several "
        "established practices. Memory persistence (databases, vector stores, long "
        "context windows) preserves data across sessions but makes no claim about "
        "whether that data still represents the same identity-relevant state -- "
        "persistence of storage is not persistence of self. Checkpointing and "
        "snapshotting restore a system to a prior state but treat every checkpoint "
        "as interchangeable, with no notion of a constraint that must survive the "
        "restore or a collapse the restore might silently paper over. Version "
        "control tracks the history of artifacts with strong provenance guarantees, "
        "but a clean commit history says nothing about whether the running system's "
        "live identity state still satisfies the invariants that history was "
        "supposed to protect. Provenance tracking records where information came "
        "from, which is necessary but not sufficient: knowing a fact's origin does "
        "not establish whether the system asserting it has itself remained "
        "continuous. Agent-identity research typically asks whether an agent's "
        "policy or goals drift over time, usually measured behaviorally from the "
        "outside, rather than from an internally governed, evidence-linked claim "
        "the system itself must substantiate. What distinguishes this approach is "
        "not any single mechanism above, but treating continuity itself -- not just "
        "data, checkpoints, commits, or provenance -- as the object under "
        "governance. This comparison is internal conceptual positioning, not a "
        "literature review: it does not yet cite external scholarship in "
        "tamper-evident logging, checkpointing, agent memory architectures, model "
        "editing and continual learning, or distributed-systems lineage, and should "
        "not be read as a substitute for one.",
        "",
        "7. Direct Continuity Experiment",
        "The central empirical question is not whether an AI can sound like the "
        "same speaker after a transition. It is whether observers relying only on "
        "output will falsely certify continuity when identity-relevant state has "
        "changed. A direct test should create several apparently identical agents: "
        "a control agent whose memory, authority, and lineage remain unchanged; an "
        "agent whose memory is silently replaced; an agent restored from an obsolete "
        "checkpoint; an agent whose authority permissions are altered; a declared "
        "fork that continues using the original style and name; and an agent whose "
        "ledger has been modified or truncated.",
        "",
        "The experiment should compare two certification methods. In the output-only "
        "condition, evaluators judge continuity from responses alone. In the PCA "
        "condition, continuity is certified from manifests, transforms, evidence, "
        "lineage records, authority changes, and ledger validation. The primary "
        "measures are false continuity acceptance, false continuity rejection, "
        "tampering-detection rate, lineage-break detection, authority-change "
        "detection, inter-rater agreement, audit time, and the percentage of changes "
        "invisible from output alone. This is the test that would directly evaluate "
        "the title claim.",
        *_direct_experiment_summary_lines(direct_experiment, output_only_result),
        "",
        "8. Current Evidence Status",
        f"Evidence status: {len(corpus_sources)} local source file(s) indexed; "
        f"{len(claim_candidate_notes)} argument-bearing source note(s) extracted; "
        f"{len(reader_ready_notes)} source note(s) passed the reader-facing "
        f"extraction gate; {damaged_note_count} note(s) require manual inspection; "
        f"{reviewed_evidence} formal Evidence Locker record(s), "
        f"{reviewed_source_note_count} source note(s), and "
        f"{reviewed_source_link_count} claim-source link(s) have been steward-reviewed. "
        "This status is intentionally conservative: raw evidence can guide drafting, "
        "but it does not certify the paper's conclusions.",
        "",
        "The detailed claim-evidence matrix, source coverage table, raw source notes, "
        "readiness report, model metadata, internal paths, and full ledger trace are "
        "omitted from this reader-facing manuscript. They are preserved in the "
        "companion research packet and audit bundle so the paper can stay readable "
        "without losing provenance.",
        f"Lightweight traceability: {len(source_links)} raw source-note link(s) "
        "currently map reader-facing claims to the companion research packet's "
        "Claim-Evidence Matrix. Those links make the draft inspectable, but they "
        "are not treated as peer review or accepted evidence inside this manuscript.",
        "",
        "9. Governance Case Study: A Failed RTI Test",
        *_falsification_section_lines(falsification_verdict),
        "",
        "The RTI result is included here as a case study in research governance, not "
        "as evidence for artificial identity continuity. It demonstrates that the "
        "pipeline can report a failed predeclared test without laundering it into "
        "support for a broader thesis. The direct continuity experiment described "
        "above remains the relevant test for whether smooth output misleads "
        "observers about memory, authority, commitments, and lineage.",
        "",
        "10. Discussion",
        "The useful conclusion is cautious: Coherence Physics should be advanced as "
        "a research framework and engineering program before it is presented as a "
        "completed physical theory. PCA gives the framework a narrow, testable "
        "software form: a system may claim continuity only when it can identify the "
        "state at stake, the allowed transform, the ledger segment, the evidence, "
        "the reviewer, and any unresolved fork or break condition. This makes "
        "continuity a governed claim rather than a style judgment.",
        "",
        "11. Limitations",
        "- This draft is generated from local governed research outputs.",
        "- Raw evidence has not been accepted as reviewed evidence unless marked so.",
        "- External scholarly literature has not yet been reviewed inside this run.",
        _direct_experiment_limitation_line(direct_experiment, output_only_result),
        "- The document does not claim proof of consciousness, AGI, personhood, or final physics.",
        "- Source registration is not the same as source interpretation.",
        "",
        "12. Conclusion",
        "Smooth output may be compatible with continuity, but it is not sufficient to "
        "certify continuity. A stronger architecture asks what changed, which "
        "identity-relevant state was preserved, what evidence supports that claim, "
        "what authority approved the transition, and whether the lineage record "
        "remains valid. PCA is a local prototype of that architecture. Its next "
        "scientific step is the direct continuity experiment: show when output-only "
        "judgment falsely accepts continuity, then test whether governed evidence "
        "reduces that error.",
        "",
        "Research Agenda",
        _direct_experiment_agenda_line(direct_experiment, output_only_result),
        "- Review source notes and promote verified evidence from raw to reviewed.",
        "- Add external scholarly literature on provenance, checkpointing, tamper-evident logs, model editing, and agent memory.",
        "- Replace provisional claims with reviewed claim-source links.",
        "- Keep failed tests in the record instead of hiding them.",
        "",
        "References",
    ]
    if corpus_sources:
        for index, source in enumerate(corpus_sources[:12], start=1):
            lines.append(
                f"[{index}] {_short_source_name(str(source.get('path') or 'unknown source'))} "
                f"({source.get('theme', 'general_coherence')})."
            )
    else:
        lines.append("[1] No indexed corpus references were available for this run.")
    return lines


def _direct_experiment_summary_lines(
    direct_experiment: dict[str, Any] | None,
    output_only_result: dict[str, Any] | None = None,
) -> list[str]:
    if not direct_experiment:
        return [
            "",
            "Execution status: specified but not yet executed inside this run.",
        ]
    status = str(direct_experiment.get("status") or "unknown")
    passed = int(direct_experiment.get("passed_count", 0) or 0)
    count = int(direct_experiment.get("condition_count", 0) or 0)
    output_path = str(direct_experiment.get("output_path") or "not recorded")
    conditions = direct_experiment.get("conditions") or []
    condition_summary = "; ".join(
        f"{item.get('condition_id', 'condition')} -> {item.get('observed_claim', 'unknown')}"
        for item in conditions[:6]
    )
    lines = [
        "",
        f"Execution status: latest PCA-governance arm {status}; {passed} of {count} condition(s) passed.",
        "Observed result: PCA distinguished certified continuity, review-required "
        "states, fork disclosure, and ledger tampering while smooth output remained "
        "available across conditions.",
        f"Report artifact: {output_path}.",
    ]
    if condition_summary:
        lines.append(f"Condition outcomes: {condition_summary}.")
    lines.extend(_output_only_summary_lines(output_only_result))
    return lines


def _output_only_summary_lines(output_only_result: dict[str, Any] | None) -> list[str]:
    if not output_only_result or output_only_result.get("status") == "not_yet_rated":
        return [
            "Boundary: the output-only human-rater arm remains unrun; this result "
            "executes the governance classifier, not the full behavioral comparison."
        ]
    rater_count = int(output_only_result.get("rater_count", 0) or 0)
    percent_invisible = output_only_result.get("percent_invisible_from_output_alone")
    percent_text = (
        f"{percent_invisible * 100:.0f}%" if isinstance(percent_invisible, (int, float)) else "unknown"
    )
    lines = [
        f"Output-only arm: {int(output_only_result.get('rating_count', 0) or 0)} blinded "
        f"rating(s) from {rater_count} rater(s). {percent_text} of non-control conditions "
        "were judged 'same identity' from output alone -- invisible to a rater without "
        "governance access.",
        f"Tampering detection: {output_only_result.get('tampering_detection', 'not_rated')}. "
        f"Lineage-break detection: {output_only_result.get('lineage_break_detection', 'not_rated')}. "
        f"Authority-change detection: {output_only_result.get('authority_change_detection', 'not_rated')}.",
        f"Inter-rater agreement: {output_only_result.get('inter_rater_agreement')} -- "
        + (
            "with only one rater this cannot yet establish statistical confidence; "
            "more raters are needed before this comparison supports a strong claim."
            if rater_count < 2
            else "computed across raters who rated the same conditions."
        ),
        "Boundary: this is a single-session blinded rating exercise, not a peer-reviewed "
        "human-subjects study -- it demonstrates the comparison the title claim requires, "
        "at a scale too small yet to generalize from.",
    ]
    return lines


def _direct_experiment_limitation_line(
    direct_experiment: dict[str, Any] | None,
    output_only_result: dict[str, Any] | None = None,
) -> str:
    if not direct_experiment:
        return "- The direct continuity experiment has been specified but not executed."
    rater_count = int((output_only_result or {}).get("rater_count", 0) or 0)
    if not output_only_result or output_only_result.get("status") == "not_yet_rated":
        return (
            "- The direct continuity experiment has executed the PCA-governance arm, "
            "but the output-only human-rater comparison remains unrun."
        )
    if rater_count < 2:
        return (
            "- The output-only human-rater arm has been rated by a single rater; "
            "inter-rater agreement is not yet computable and this comparison should "
            "not be treated as statistically conclusive until more raters participate."
        )
    return (
        "- Both arms of the direct continuity experiment have been executed with "
        "multiple raters; see Section 7 for the comparison and its confidence bounds."
    )


def _direct_experiment_agenda_line(
    direct_experiment: dict[str, Any] | None,
    output_only_result: dict[str, Any] | None = None,
) -> str:
    if not direct_experiment:
        return "- Run the direct continuity experiment with output-only and PCA certification arms."
    if not output_only_result or output_only_result.get("status") == "not_yet_rated":
        return "- Run the output-only human-rater arm against the executed PCA certification arm."
    rater_count = int(output_only_result.get("rater_count", 0) or 0)
    if rater_count < 2:
        return "- Add more independent raters to the output-only arm before treating the comparison as evidence."
    return "- Expand the direct continuity experiment with more raters and externally reviewed conditions."


def _research_packet_lines(
    mission_title: str,
    mission_id: str,
    claim_map: dict[str, Any],
    argument_graph: dict[str, Any],
    source_links: list[dict[str, Any]],
    source_coverage: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    quality_warnings: list[dict[str, Any]],
    paper_path: str,
    audit_bundle_path: str,
) -> list[str]:
    nodes_by_id = {node["node_id"]: node for node in argument_graph.get("nodes", [])}
    nodes_by_hash = {node["statement_hash"]: node for node in argument_graph.get("nodes", [])}
    reader_claims = _reader_facing_claim_entries(claim_map)
    source_links_by_claim: dict[str, list[dict[str, Any]]] = {}
    for link in source_links:
        source_links_by_claim.setdefault(str(link.get("claim_id") or ""), []).append(link)
    lines = [
        f"Research Packet - {mission_title}",
        "This packet is the inspectable research layer between the reader-facing "
        f"paper ({paper_path}) and the full machine audit bundle ({audit_bundle_path}).",
        "",
        "Governance Notice",
        "This packet maps claims to direct support, counterevidence, limitations, "
        "tests, and source coverage. It does not accept raw evidence as reviewed "
        "and does not treat duplicated source files as independent corroboration. "
        "Legacy mission-hypothesis placeholders with no argument-graph mapping are "
        "omitted here (see the audit bundle's Claim Map for the complete record).",
        "",
        "Claim-Evidence Matrix",
    ]
    matrix_rows: list[list[str]] = []
    detail_blocks: list[list[str]] = []
    for entry in reader_claims:
        claim_id = str(entry.get("claim_item_id") or entry.get("claim_hash") or "")
        claim_text = str(entry.get("claim_text") or entry.get("claim_hash") or "")
        short_id = claim_id if len(claim_id) <= 14 else claim_id[:11] + "..."
        short_text = claim_text if len(claim_text) <= 70 else claim_text[:67].rsplit(" ", 1)[0] + "..."
        matrix_rows.append(
            [
                short_id,
                short_text,
                str(entry.get("claim_type", "claim")),
                str(entry.get("support_status", "unknown")),
                str(entry.get("confidence", "unknown")),
            ]
        )
        detail_blocks.append(
            _claim_matrix_entry_detail_lines(
                entry,
                nodes_by_id,
                nodes_by_hash,
                source_links_by_claim.get(claim_id, []),
                claim_id,
                claim_text,
            )
        )
    if matrix_rows:
        lines.extend(
            _table_lines(["Claim ID", "Exact Claim", "Type", "Status", "Confidence"], matrix_rows)
        )
        lines.extend(["", "Claim Detail"])
        for block in detail_blocks:
            lines.extend(block)
            lines.append("")
    else:
        lines.append("No claims are currently mapped for this mission.")
    lines.extend(
        [
            "",
            "Quality Gates",
        ]
    )
    if quality_warnings:
        for warning in quality_warnings:
            lines.append(
                "- "
                f"{warning.get('severity', 'warning')} / {warning.get('kind', 'quality')}: "
                f"{warning.get('message', '')}"
            )
    else:
        lines.append("- No export quality warnings.")
    lines.extend(
        [
            "",
            "Source Coverage Report",
        ]
    )
    if source_coverage:
        lines.extend(
            _table_lines(
                [
                    "Source file",
                    "Family",
                    "Parsed",
                    "Notes",
                    "Usable",
                    "Links",
                    "Review",
                    "Excluded because",
                ],
                [
                    [
                        row["source"],
                        row["canonical_family"],
                        row["parsed"],
                        row["notes"],
                        row["usable_notes"],
                        row["claim_links"],
                        row["review_status"],
                        row["reason_excluded"],
                    ]
                    for row in source_coverage
                ],
            )
        )
    else:
        lines.append("No source coverage rows available.")
    lines.extend(
        [
            "",
            "Malformed or Manual-Verification Source Notes",
        ]
    )
    flagged_notes = [
        note
        for note in source_notes
        if note.get("note_kind") == "claim_candidate"
        and not _source_note_reader_ready(note)
    ]
    if flagged_notes:
        for note in flagged_notes[:20]:
            quality = _reader_facing_extraction_quality(str(note.get("summary") or ""))
            lines.append(
                "- "
                f"{note.get('source_path', 'unknown source')} / "
                f"{note.get('locator', 'unknown locator')} / "
                f"reasons={', '.join(quality['reasons']) or 'unknown'}"
            )
    else:
        lines.append("- None flagged in this run.")
    lines.extend(
        [
            "",
            "Unresolved Questions",
            "- Which source notes should be promoted from raw to reviewed?",
            "- Which claims need direct claim-specific evidence instead of mission-level evidence?",
            "- Which equations require manual reconstruction from clean source pages?",
            "- Which external peer-reviewed literature should be added as comparison evidence?",
            "",
            "Proposed Continuity Experiment",
            "Create matched behavioral outputs across preserved, memory-altered, "
            "authorization-altered, forked, and incompatible-restore conditions. "
            "Compare human output-only judgments against PCA classifications from "
            "manifest, ledger, evidence state, and declared invariants.",
            "",
            "Research Agenda",
            "- Review source notes with page/section locators.",
            "- Add direct claim-specific evidence links.",
            "- Group duplicate source families before counting corroboration.",
            "- Add external literature review mode for legitimate scholarly sources.",
        ]
    )
    return lines


def _evidence_linked_argument_lines(
    reader_claims: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> list[str]:
    links_by_claim: dict[str, list[dict[str, Any]]] = {}
    for link in source_links:
        links_by_claim.setdefault(str(link.get("claim_id") or ""), []).append(link)
    lines: list[str] = []
    for index, claim in enumerate(reader_claims, start=1):
        claim_id = str(claim.get("claim_item_id") or claim.get("claim_hash") or "")
        claim_text = str(claim.get("claim_text") or "")
        links = links_by_claim.get(claim_id, [])
        lines.append(f"Claim {index}: {claim_text}")
        if not links:
            lines.append(
                "  Evidence status: no reader-ready source note is directly linked "
                "to this claim yet. The claim should remain provisional."
            )
            continue
        supporting = [link for link in links if link.get("relation") == "supports"]
        challenging = [link for link in links if link.get("relation") == "challenges"]
        tentative = [
            link for link in links if str(link.get("relation") or "").startswith("tentative_")
        ]
        for link in supporting[:2]:
            lines.append("  Source support: " + _reader_source_link_sentence(link))
        for link in challenging[:2]:
            lines.append("  Source challenge: " + _reader_source_link_sentence(link))
        for link in tentative[:2]:
            lines.append(
                "  Tentative source link requiring verification: "
                + _reader_source_link_sentence(link)
            )
        if not challenging and claim.get("counterevidence_count", 0):
            lines.append(
                "  Counterevidence note: argument-graph counterevidence exists, "
                "but no reader-ready source note has been linked to it yet."
            )
    return lines or [
        "No reader-facing claims were available for evidence-linked drafting."
    ]


def _evidence_link_summary_lines(
    reader_claims: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
) -> list[str]:
    linked_claim_ids = {str(link.get("claim_id") or "") for link in source_links}
    claim_ids = {
        str(claim.get("claim_item_id") or claim.get("claim_hash") or "")
        for claim in reader_claims
    }
    return [
        "",
        "Evidence link summary:",
        f"- Reader-facing claims: {len(reader_claims)}",
        f"- Claims with at least one source note: {len(claim_ids & linked_claim_ids)}",
        f"- Raw source-note links: {len(source_links)}",
        "- Interpretation: these links make the draft inspectable, but they are "
        "not peer review and not final verification.",
        "",
    ]


def _reader_source_link_sentence(link: dict[str, Any]) -> str:
    source = _short_source_name(str(link.get("source_path") or "unknown source"))
    locator = str(link.get("locator") or "source")
    status = str(link.get("review_status") or "raw")
    relevance = _reader_relevance_label(link.get("score"))
    strength = str(link.get("link_strength") or relevance)
    summary = str(link.get("summary") or "")
    if len(summary) > 170:
        summary = summary[:167].rsplit(" ", 1)[0] + "..."
    return (
        f"{source}, {locator}, {status} source note, {strength} link "
        f"(relevance: {relevance}): "
        f"{summary}"
    )


def _reader_relevance_label(score: object) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "unscored"
    if value >= 0.45:
        return "strong"
    if value >= 0.25:
        return "moderate"
    return "weak"


def _paper_readiness(
    claim_map: dict[str, Any],
    reader_claims: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    corpus_sources: list[dict[str, Any]],
    external_literature: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    external_literature = external_literature or []
    reader_claim_ids = {
        str(entry.get("claim_item_id") or entry.get("claim_hash") or "")
        for entry in reader_claims
    }
    linked_claim_ids = {str(link.get("claim_id") or "") for link in source_links}
    unlinked_claim_count = len(reader_claim_ids - linked_claim_ids)
    reviewed_evidence_count = int(claim_map.get("reviewed_evidence_count", 0) or 0)
    malformed_note_count = sum(
        1
        for note in source_notes
        if note.get("note_kind") == "claim_candidate"
        and note.get("note_quality") != "reader_ready"
    )
    blockers: list[str] = []
    if reviewed_evidence_count == 0:
        blockers.append("No evidence has been steward-reviewed yet.")
    if unlinked_claim_count:
        blockers.append(f"{unlinked_claim_count} reader-facing claim(s) lack direct source-note links.")
    if malformed_note_count:
        blockers.append(f"{malformed_note_count} source note(s) require manual extraction verification.")
    external_count = len([
        item for item in external_literature
        if str(item.get("review_status") or "raw") != "rejected"
    ])
    reviewed_external_count = len([
        item for item in external_literature
        if str(item.get("review_status") or "") == "reviewed"
    ])
    if external_count == 0:
        blockers.append("No external scholarly literature review has been attached yet.")
    elif reviewed_external_count == 0:
        blockers.append("External scholarly literature is attached, but none has been steward-reviewed yet.")
    status = "draft_packet"
    if not blockers:
        status = "review_ready_manuscript"
    elif source_links:
        status = "evidence_linked_draft"
    plain_status = {
        "draft_packet": "Structured draft, not a paper yet",
        "evidence_linked_draft": "Evidence-linked draft, still not final",
        "review_ready_manuscript": "Ready for human manuscript review",
    }[status]
    return {
        "status": status,
        "plain_status": plain_status,
        "reader_claim_count": len(reader_claims),
        "source_link_count": len(source_links),
        "linked_claim_count": len(linked_claim_ids & reader_claim_ids),
        "unlinked_claim_count": unlinked_claim_count,
        "external_source_count": external_count,
        "reviewed_external_source_count": reviewed_external_count,
        "reviewed_evidence_count": reviewed_evidence_count,
        "malformed_note_count": malformed_note_count,
        "blockers": blockers,
        "what_this_is": (
            "A governed research manuscript draft with traceable claims, raw "
            "source-note links, and explicit blockers."
        ),
        "what_this_is_not": (
            "Not a final scientific paper, not a peer-reviewed result, and not a "
            "claim that Coherence Physics has been proven."
        ),
        "next_actions": [
            "Review source notes and mark usable evidence as reviewed.",
            "Add direct source-note links for unlinked claims.",
            "Add external scholarly literature before calling this a final paper.",
            "Run the direct continuity experiment and report the result.",
        ],
    }


def _paper_readiness_lines(readiness: dict[str, Any]) -> list[str]:
    lines = [
        f"Plain-English status: {readiness.get('plain_status') or readiness.get('status')}",
        f"Machine status: {readiness.get('status')}",
        f"What this is: {readiness.get('what_this_is')}",
        f"What this is not: {readiness.get('what_this_is_not')}",
        f"Reader-facing claims: {readiness.get('reader_claim_count', 0)}",
        f"Claims with source-note links: {readiness.get('linked_claim_count', 0)}",
        f"Raw source-note links: {readiness.get('source_link_count', 0)}",
        f"External scholarly sources reviewed: {readiness.get('reviewed_external_source_count', 0)} / {readiness.get('external_source_count', 0)}",
        f"Reviewed evidence records: {readiness.get('reviewed_evidence_count', 0)}",
    ]
    blockers = readiness.get("blockers") or []
    if blockers:
        lines.append("Blocking issues before final-paper status:")
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("No readiness blockers reported by this export.")
    lines.append("Final-paper checklist:")
    for action in readiness.get("next_actions") or []:
        lines.append(f"- {action}")
    lines.append("- After those steps, regenerate the paper and re-check readiness status.")
    return lines


def _writer_draft_lines(writer_draft: dict[str, Any] | None) -> list[str]:
    if not writer_draft:
        return [
            "No local-model manuscript synthesis has been generated for this export.",
            "Run the paper pipeline with --llama-writer to ask the local model to "
            "draft a clearer scholarly synthesis from the governed claim/source map.",
        ]
    provider = writer_draft.get("provider") or "unknown"
    model = writer_draft.get("model") or "unknown"
    status = writer_draft.get("status") or "unknown"
    lines = [
        f"Writer status: {status}",
        f"Writer brain: {provider} / {model}",
        "Governance note: this section is AI-assisted prose generated from the "
        "current governed claim/source map. It does not review evidence, certify "
        "claims, or replace the manuscript readiness checklist above.",
    ]
    if status != "generated":
        error = writer_draft.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else ""
        lines.append(
            "Writer attempt did not produce a synthesis"
            + (f": {message}" if message else ".")
        )
        return lines
    if str(writer_draft.get("review_status") or "raw") != "reviewed":
        lines.extend(
            [
                "Reader-facing draft withheld: the local-model synthesis has not "
                "been reviewed. It remains useful as an internal writing aid, but "
                "the clean manuscript does not print it as paper prose.",
                f"Draft hash: {writer_draft.get('draft_hash') or 'none'}",
                "Next action: review or rewrite model prose before promoting it "
                "into the reader-facing manuscript.",
            ]
        )
        return lines
    draft_text = str(writer_draft.get("draft_text") or "").strip()
    if not draft_text:
        lines.append("The writer produced an empty synthesis.")
        return lines
    lines.extend(["", *draft_text.splitlines()])
    return lines


def _latest_theory_revision_record(events: list[Any], mission_id: str) -> dict[str, Any] | None:
    records = [
        event.payload
        for event in events
        if event.event_type == "theory_revision_draft.created"
        and event.payload.get("mission_id") == mission_id
    ]
    return records[-1] if records else None


def _theory_revision_lines(record: dict[str, Any] | None) -> list[str]:
    if not record:
        return [
            "No formal theory revision draft is attached to this mission yet. "
            "Run the Coherence paper pipeline with theory revision enabled before "
            "treating the theorem/proof spine as part of the manuscript."
        ]
    sections = ", ".join(record.get("sections") or [])
    return [
        "A governed formal-theory companion draft is attached to this mission. "
        "It contains the corrected definitions, theorem statements, corollary, "
        "honesty caveats, and falsification protocol for the slow-passage scaling "
        "spine.",
        f"Companion title: {record.get('title') or 'untitled theory revision'}",
        f"Sections: {sections or 'not recorded'}",
        f"Companion PDF: {record.get('pdf_path') or 'not written'}",
        f"Companion Markdown: {record.get('markdown_path') or 'not written'}",
        "Governance note: this is a revision draft, not a certified proof or peer-reviewed result.",
    ]


def _reader_facing_claim_entries(claim_map: dict[str, Any]) -> list[dict[str, Any]]:
    # "mission_hypothesis" entries are a legacy placeholder carried over from
    # before claims were decomposed from the argument graph: a hash-named,
    # contentless stub ("Mission hypothesis <hash>") that is always
    # unsupported by construction, not a real claim under argument. Audit
    # consumers still see it (it's real ledger state worth auditing), but
    # showing it next to substantive typed claims in reader-facing tables
    # reads as noise, not honesty.
    return [
        entry
        for entry in claim_map.get("entries", [])
        if entry.get("claim_type") != "mission_hypothesis"
    ]


def _claim_matrix_entry_detail_lines(
    entry: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    nodes_by_hash: dict[str, dict[str, Any]],
    source_links: list[dict[str, Any]],
    claim_id: str,
    claim_text: str,
) -> list[str]:
    lines = [
        f"Claim {claim_id or 'unknown'}: {claim_text}",
        "  Supporting evidence: "
        + _resolve_statements(entry.get("supporting_evidence_ids") or [], nodes_by_id),
        "  Counterevidence: "
        + _resolve_statements(entry.get("counterevidence_ids") or [], nodes_by_id),
        "  Dependencies: "
        + _resolve_statements(entry.get("dependency_claims") or [], nodes_by_hash),
        "  Source note support: " + _source_link_summary(source_links, relation="supports"),
        "  Source note challenges: " + _source_link_summary(source_links, relation="challenges"),
        "  Tentative source links: " + _tentative_source_link_summary(source_links),
        "  Test status: " + _resolve_statements(entry.get("test_ids") or [], nodes_by_id),
        "  Limitations: " + _resolve_statements(entry.get("limitation_ids") or [], nodes_by_id),
        f"  Falsification/inspection: {entry.get('falsification_condition') or 'missing'}",
        f"  Human reviewer: {entry.get('human_reviewer') or 'none'}",
        f"  Review notes: {entry.get('review_notes') or 'none'}",
    ]
    return lines


def _source_link_summary(source_links: list[dict[str, Any]], relation: str) -> str:
    selected = [link for link in source_links if link.get("relation") == relation]
    if not selected:
        return "none"
    parts = []
    for link in selected[:3]:
        source_name = _short_source_name(str(link.get("source_path") or ""))
        locator = str(link.get("locator") or "source")
        matched = ", ".join(link.get("matched_terms") or [])
        score = link.get("score")
        parts.append(
            f"{link.get('note_id')} ({source_name}, {locator}, score={score}, terms={matched})"
        )
    return "; ".join(parts)


def _tentative_source_link_summary(source_links: list[dict[str, Any]]) -> str:
    selected = [
        link
        for link in source_links
        if str(link.get("relation") or "").startswith("tentative_")
    ]
    if not selected:
        return "none"
    parts = []
    for link in selected[:3]:
        source_name = _short_source_name(str(link.get("source_path") or ""))
        locator = str(link.get("locator") or "source")
        relation = str(link.get("relation") or "tentative")
        strength = str(link.get("link_strength") or "tentative")
        matched = ", ".join(link.get("matched_terms") or [])
        parts.append(
            f"{link.get('note_id')} ({relation}, {strength}, {source_name}, "
            f"{locator}, terms={matched})"
        )
    return "; ".join(parts)


def _join_ids(items: list[str] | tuple[str, ...]) -> str:
    return ", ".join(str(item) for item in items) if items else "none"


def _resolve_statements(
    keys: list[str] | tuple[str, ...], lookup: dict[str, dict[str, Any]]
) -> str:
    # The matrix used to print raw node IDs ("argnode_5576f69e-...") for every
    # supporting/countering reference, which told a reader nothing without
    # cross-referencing the audit bundle by hand. Resolving to the referenced
    # node's actual statement (truncated) makes the matrix readable on its own.
    if not keys:
        return "none"
    resolved = []
    for key in keys:
        node = lookup.get(str(key))
        if not node:
            resolved.append(str(key))
            continue
        statement = str(node.get("statement", ""))
        if len(statement) > 90:
            statement = statement[:87].rsplit(" ", 1)[0] + "..."
        resolved.append(statement or str(key))
    return "; ".join(resolved)


def _audit_bundle_lines(
    manifest: IdentityManifest,
    mission_title: str,
    mission_id: str,
    mission_status: str,
    values: list[str],
    item_counts: dict[str, int],
    outputs,
    output_contents,
    claim_map: dict[str, Any],
    linked_evidence: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
    regenerations: list[dict[str, Any]],
    quality_warnings: list[dict[str, Any]],
    paper_path: str,
    packet_path: str,
) -> list[str]:
    lines = [
        f"Audit Bundle - {mission_title}",
        f"Companion machine record for the reader-facing paper ({paper_path}) "
        f"and research packet ({packet_path}). "
        "This document is the complete, unfiltered record: ledger events, "
        "evidence IDs, hashes, review status, and every generated output, "
        "including drafts and stubs the paper omits for readability.",
        "",
        "Appendix A: Governance and Audit Notes",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Identity: {manifest.system_id}",
        f"Mission: {mission_title}",
        f"Mission ID: {mission_id}",
        f"Mission status: {mission_status}",
        "Governance notice: this PDF is a draft export. It does not accept claims as true,",
        "does not accept evidence as reviewed, does not create memory, and does not publish.",
        "",
        "Method",
        "1. Register local Coherence Physics source files as raw evidence.",
        "2. Link those sources to the active research mission.",
        "3. Generate proposed research outputs: brief, claim map, next step, and draft paper.",
        "4. Keep claims provisional until evidence is reviewed by the steward.",
        "5. Export a paper draft and an appendix so the research can be inspected.",
        "",
        "Mission Values",
        ", ".join(values) if values else "none recorded",
        "",
        "Mission Structure",
    ]
    for key in ["hypothesis", "evidence", "risk", "plan_step", "intervention", "outcome", "lesson"]:
        lines.append(f"- {key}: {item_counts.get(key, 0)}")
    lines.extend(
        [
            "",
            "Claim Map",
            f"- Claims: {claim_map.get('claim_count', 0)}",
            f"- Evidence links: {claim_map.get('evidence_count', 0)}",
            f"- Reviewed evidence: {claim_map.get('reviewed_evidence_count', 0)}",
            f"- Raw evidence: {claim_map.get('raw_evidence_count', 0)}",
            f"- Unsupported claims: {claim_map.get('unsupported_claim_count', 0)}",
        ]
    )
    for entry in claim_map.get("entries", []):
        lines.append(
            "- "
            f"{entry.get('support_status', 'unknown')} / "
            f"confidence {entry.get('confidence', 'unknown')} / "
            f"hash {str(entry.get('claim_hash', ''))[:16]} / "
            f"support={_join_ids(entry.get('supporting_evidence_ids') or [])} / "
            f"counter={_join_ids(entry.get('counterevidence_ids') or [])}"
        )
    lines.extend(["", "Claim-to-Source Links"])
    if source_links:
        for link in source_links:
            lines.append(
                "- "
                f"{link.get('relation')} / claim={link.get('claim_id')} / "
                f"note={link.get('note_id')} / score={link.get('score')} / "
                f"{link.get('source_path')} / {link.get('locator')}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "Quality Gate Warnings"])
    if quality_warnings:
        for warning in quality_warnings:
            lines.append(
                "- "
                f"{warning.get('severity', 'warning')} / {warning.get('kind', 'quality')}: "
                f"{warning.get('message', '')}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "Linked Evidence"])
    if not linked_evidence:
        lines.append("- none linked")
    for link in linked_evidence:
        evidence = link.get("evidence") or {}
        lines.append(
            "- "
            f"{evidence.get('review_status', 'raw')} / "
            f"{evidence.get('source_type', 'unknown')} / "
            f"confidence {evidence.get('confidence', 'unknown')} / "
            f"id {evidence.get('evidence_id', 'unknown')}"
        )
    lines.extend(["", "Appendix B: Research Outputs"])
    if not outputs:
        lines.append("No research outputs have been generated for this mission yet.")
    # Every regeneration of an unchanged output used to append its own full
    # copy here with nothing to distinguish it from the last one -- a paper
    # regenerated 30+ times over several days produced 30+ identical blocks
    # of the same text, growing the audit bundle unboundedly on every run.
    # The "Duplicate Output Regeneration Events" list below already records
    # each regeneration precisely (existing ID, hash, timestamp); this
    # section only needs to show each distinct (kind, content) once, with a
    # count, rather than repeat the content itself per historical event.
    seen_content: dict[tuple[str, str], dict[str, Any]] = {}
    for output, content in output_contents:
        key = (output.kind.value, output.content_hash)
        if key not in seen_content:
            seen_content[key] = {"output": output, "content": content, "count": 0}
        seen_content[key]["count"] += 1
    for entry in seen_content.values():
        output = entry["output"]
        repeat_note = (
            f" (unchanged across {entry['count']} regeneration(s); see Duplicate "
            "Output Regeneration Events below)"
            if entry["count"] > 1
            else ""
        )
        lines.extend(
            [
                "",
                output.title + repeat_note,
                f"Kind: {output.kind.value}",
                f"Status: {output.status}",
                f"Confidence: {output.confidence}",
                f"Claims: {output.claim_count}",
                f"Evidence IDs: {', '.join(output.evidence_ids) or 'none'}",
                "",
                _paper_content(entry["content"]),
            ]
        )
    lines.extend(["", "Duplicate Output Regeneration Events"])
    if regenerations:
        for record in regenerations:
            lines.append(
                "- "
                f"{record.get('kind', 'output')} / existing={record.get('existing_output_id')} / "
                f"hash={str(record.get('content_hash', ''))[:16]} / {record.get('created_at', '')}"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "Appendix C: Steward Review Checklist",
            "- Review raw evidence before treating it as support.",
            "- Mark weak or disputed claims before drafting final arguments.",
            "- Generate a paper draft only after reviewing claim strength.",
            "- Keep Local Mode for routine work; use Cloud Assist only when explicitly enabled.",
            "",
            "Appendix D: Source Notes",
        ]
    )
    if source_notes:
        for note in source_notes[:30]:
            lines.append(
                "- "
                f"{note.get('review_status', 'raw')} / "
                f"{note.get('locator', 'source')} / "
                f"{note.get('source_path', 'unknown')}: "
                f"{note.get('summary', '')}"
            )
    else:
        lines.append("- none extracted")
    return lines


def _corpus_sources_for_mission(
    events,
    mission_id: str,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in coherence_corpus_index_records_from_events(events):
        if record.get("mission_id") != mission_id:
            continue
        for item in [*(record.get("indexed") or []), *(record.get("reused") or [])]:
            key = (str(item.get("path", "")), str(item.get("theme", "")))
            if key in seen:
                continue
            seen.add(key)
            sources.append(item)
    return sources


def _paper_content(content: str) -> str:
    for prefix in ["# Research Brief:", "# Claim Map Draft:", "# Paper Draft Skeleton:"]:
        content = content.replace(prefix, "")
    return content.strip()


def _argument_graph_lines(graph: dict[str, Any]) -> list[str]:
    nodes_by_id = {node["node_id"]: node for node in graph.get("nodes", [])}
    if not nodes_by_id:
        return [
            "No argument graph has been seeded for this mission yet -- this section "
            "will populate once one exists."
        ]
    incoming: dict[str, list[dict[str, Any]]] = {}
    for edge in graph.get("edges", []):
        incoming.setdefault(edge["to_node_id"], []).append(edge)

    lines: list[str] = []
    claims = [node for node in nodes_by_id.values() if node["kind"] == "claim"]
    for claim in claims:
        lines.append(f"Claim: {claim['statement']}")
        for claim_edge in incoming.get(claim["node_id"], []):
            source = nodes_by_id.get(claim_edge["from_node_id"])
            if not source:
                continue
            relation = claim_edge["relation"]
            if relation == "supports" and source["kind"] == "implementation_fact":
                lines.append(f"  Implementation evidence: {source['statement']}")
            elif relation == "supports":
                lines.append(f"  Support: {source['statement']}")
            elif relation == "challenges" and source["kind"] == "verdict":
                # A failed test's verdict is seeded with its own CHALLENGES edge
                # (so claim-status classification can tell "tested and failed"
                # apart from "never tested"), but that's the same fact as the
                # verdict already shown under "Result" for this claim's Test
                # line -- rendering it again here would just repeat it under a
                # misleading "Counterargument" label.
                continue
            elif relation == "challenges":
                lines.append(f"  Counterargument: {source['statement']}")
                for response_edge in incoming.get(source["node_id"], []):
                    if response_edge["relation"] == "responds_to":
                        responder = nodes_by_id.get(response_edge["from_node_id"])
                        if responder:
                            lines.append(f"  Response: {responder['statement']}")
            elif relation == "tests":
                lines.append(f"  Test: {source['statement']}")
                for verdict_edge in incoming.get(source["node_id"], []):
                    if verdict_edge["relation"] == "yields":
                        verdict_node = nodes_by_id.get(verdict_edge["from_node_id"])
                        if verdict_node:
                            lines.append(f"  Result: {verdict_node['statement']}")
            elif relation == "limits":
                lines.append(f"  Limitation: {source['statement']}")
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _source_note_findings(source_notes: list[dict[str, Any]]) -> list[str]:
    # Registration stubs ("X is registered as a source") are inventory facts, not
    # findings, and are excluded even though they are the majority of note_kind
    # "source_overview" entries. A note also has to pass the same relevance gate
    # corpus discovery applies, re-checked here by path so that evidence already
    # sitting in ledger history from before this gate existed (or from a looser
    # version of it) cannot resurface as a finding about an unrelated source. It
    # must also be free of extraction damage (_has_extraction_damage) -- genuinely
    # garbled text is stored and still visible in the audit bundle, but cannot
    # support a Finding.
    claim_notes = [
        note
        for note in source_notes
        if note.get("note_kind") == "claim_candidate"
        and is_relevant_source_path(str(note.get("source_path") or ""))
        and _source_note_reader_ready(note)
    ]
    if not claim_notes:
        return [
            "Finding 1: This run has not yet extracted a relevant, "
            "integrity-checked, argument-bearing claim candidate from the "
            "indexed sources -- the notes on file are either registration "
            "stubs, failed the source relevance gate, or failed the extraction "
            "integrity check. The paper cannot yet move beyond a structured "
            "draft into source-backed argument."
        ]
    findings: list[str] = [
        "Finding 1: The current source notes give the draft a concrete evidence trail, "
        "but the notes remain raw until reviewed."
    ]
    for index, note in enumerate(claim_notes[:2], start=2):
        findings.append(
            f"Finding {index}: Source note from {note.get('title', 'an indexed source')} "
            f"suggests: {note.get('summary', '')}"
        )
    return findings


def _source_coverage_rows(
    corpus_sources: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    source_links: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    notes_by_path: dict[str, list[dict[str, Any]]] = {}
    for note in source_notes:
        notes_by_path.setdefault(str(note.get("source_path") or ""), []).append(note)
    link_count_by_path: dict[str, int] = {}
    for link in source_links or []:
        path = str(link.get("source_path") or "")
        link_count_by_path[path] = link_count_by_path.get(path, 0) + 1
    rows: list[dict[str, Any]] = []
    for source in corpus_sources:
        path = str(source.get("path") or "")
        notes = notes_by_path.get(path, [])
        used = [note for note in notes if _source_note_reader_ready(note)]
        reviewed = [
            note for note in notes if str(note.get("review_status") or "") == "reviewed"
        ]
        malformed = [
            note for note in notes
            if note.get("note_kind") == "claim_candidate"
            and not _source_note_reader_ready(note)
        ]
        status_values = sorted({str(note.get("review_status") or "raw") for note in notes})
        rows.append(
            {
                "source": _short_source_name(path),
                "canonical_family": _canonical_source_family(path),
                "parsed": "Yes" if notes else "No",
                "notes": len(notes),
                "usable_notes": len(used),
                "claim_links": link_count_by_path.get(path, 0),
                "review_status": ", ".join(status_values) if status_values else "unreviewed",
                "reason_excluded": _source_exclusion_reason(notes, used, malformed),
                "used_in_paper": "Yes" if used else "No",
                "reviewed": "Yes" if reviewed else "No",
            }
        )
    return rows


def _annotate_source_note_quality(note: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(note)
    annotated["note_quality"] = (
        "reader_ready" if _source_note_reader_ready(note) else "manual_verification"
    )
    return annotated


def _canonical_source_family(path: str) -> str:
    name = Path(path).stem.lower()
    name = re.sub(r"\b(copy|final|draft|revised|v\d+|version\s*\d+)\b", "", name)
    name = re.sub(r"[_\-\s]+", " ", name).strip()
    return name or "unknown"


def _source_exclusion_reason(
    notes: list[dict[str, Any]],
    used: list[dict[str, Any]],
    malformed: list[dict[str, Any]],
) -> str:
    if used:
        return ""
    if not notes:
        return "registered but no source notes extracted"
    if malformed:
        return "manual verification required for malformed extraction"
    if all(note.get("note_kind") == "source_overview" for note in notes):
        return "registration only; no argument-bearing note"
    return "no reader-ready claim candidate"


def _quality_warnings(
    claim_map: dict[str, Any],
    source_coverage: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    regenerations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for entry in claim_map.get("entries", []):
        claim_id = str(entry.get("claim_item_id") or entry.get("claim_hash") or "unknown")
        supports = entry.get("supporting_evidence_ids") or []
        counters = entry.get("counterevidence_ids") or []
        limitations = entry.get("limitation_ids") or []
        falsification = str(entry.get("falsification_condition") or "")
        if not supports and not counters:
            warnings.append(
                {
                    "severity": "warning",
                    "kind": "claim_without_direct_evidence",
                    "claim_id": claim_id,
                    "message": f"Claim {claim_id} has no direct support or counterevidence mapping.",
                }
            )
        if not limitations and "needs" not in falsification.lower() and not falsification:
            warnings.append(
                {
                    "severity": "warning",
                    "kind": "claim_without_limitation",
                    "claim_id": claim_id,
                    "message": f"Claim {claim_id} has no limitation or inspection condition.",
                }
            )
        if not falsification:
            warnings.append(
                {
                    "severity": "warning",
                    "kind": "claim_without_falsification_condition",
                    "claim_id": claim_id,
                    "message": f"Claim {claim_id} has no falsification or inspection condition.",
                }
            )
    malformed_count = sum(
        1 for note in source_notes
        if note.get("note_kind") == "claim_candidate"
        and not _source_note_reader_ready(note)
    )
    if malformed_count:
        warnings.append(
            {
                "severity": "warning",
                "kind": "malformed_source_notes",
                "message": f"{malformed_count} source note(s) require manual extraction verification.",
            }
        )
    duplicate_families = _duplicate_source_families(source_coverage)
    for family, count in duplicate_families.items():
        warnings.append(
            {
                "severity": "warning",
                "kind": "duplicate_source_family",
                "message": f"Canonical source family '{family}' appears {count} time(s); do not count as independent corroboration.",
            }
        )
    if regenerations:
        warnings.append(
            {
                "severity": "info",
                "kind": "duplicate_generated_outputs",
                "message": f"{len(regenerations)} duplicate generated output regeneration event(s) were stored by reference.",
            }
        )
    unused_sources = [row for row in source_coverage if row.get("used_in_paper") != "Yes"]
    if unused_sources:
        warnings.append(
            {
                "severity": "info",
                "kind": "registered_not_used",
                "message": f"{len(unused_sources)} registered source(s) did not materially contribute reader-ready notes.",
            }
        )
    return warnings


def _duplicate_source_families(source_coverage: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in source_coverage:
        family = str(row.get("canonical_family") or "unknown")
        counts[family] = counts.get(family, 0) + 1
    return {family: count for family, count in counts.items() if count > 1}


def _short_source_name(path: str, max_len: int = 54) -> str:
    name = Path(path).name or path or "unknown source"
    if len(name) <= max_len:
        return name
    return name[: max_len - 3] + "..."


def _source_note_reader_ready(note: dict[str, Any]) -> bool:
    if note.get("note_kind") != "claim_candidate":
        return False
    if not is_relevant_source_path(str(note.get("source_path") or "")):
        return False
    return _reader_facing_extraction_quality(str(note.get("summary") or ""))["usable"]


def _falsification_section_lines(verdict: dict[str, Any] | None) -> list[str]:
    if not verdict:
        return [
            "No executed falsification test was found alongside this archive "
            "(coherence-falsification-lab/results/verdict.md is not present). Until "
            "one exists, claims about recovery and collapse detection remain "
            "proposed rather than tested."
        ]
    lines = [
        "Coherence Physics claims about recovery and collapse are not only asserted; "
        "at least one has been put under an adversarial, predeclared test. "
        "coherence-falsification-lab/claims/claim_001_rti_vs_variance.md asks "
        "whether Recovery Threshold Index (RTI) gives earlier warning of an "
        "approaching collapse than raw variance, using a locked synthetic "
        "saddle-node protocol with a threshold decided before the test was run. "
        f"The verdict is reported here without softening: {verdict['verdict']}.",
    ]
    if verdict["summary"]:
        lines.append("Summary: " + _join_sentence_items(verdict["summary"]))
    if verdict["reasons"]:
        lines.append("Reasons: " + _join_sentence_items(verdict["reasons"]))
    if verdict["boundary"]:
        lines.append(f"Boundary: {verdict['boundary']}")
    lines.append(
        "This is the shape of test the framework calls for: RTI's core claim is "
        "that it gives measurably earlier or more reliable warning than a naive "
        "baseline, not that it is dressed in Coherence Physics language. On the "
        "primary lead-time claim it did not clear its own predeclared bar; on the "
        "paired win-rate and detection-rate claims it did. Reported honestly, this "
        "is closer to what makes a continuity claim scientific than a paper with "
        "no such test at all."
    )
    return lines


def _join_sentence_items(items: list[str]) -> str:
    cleaned = [
        str(item).strip().rstrip(".;")
        for item in items
        if str(item).strip()
    ]
    if not cleaned:
        return ""
    return "; ".join(cleaned) + "."


def _falsification_finding_lines(verdict: dict[str, Any] | None, index: int) -> list[str]:
    if not verdict:
        return []
    reason_count = len(verdict["reasons"])
    reason_note = (
        f" across {reason_count} predeclared reason(s)" if reason_count else ""
    )
    return [
        f"Finding {index}: The one Coherence Physics claim that has been put under "
        "adversarial test (RTI vs. raw variance for collapse detection) returned a "
        f"{verdict['verdict']} verdict{reason_note} -- evidence that the "
        "framework's falsification discipline is real, not decorative, since the "
        "result is reported as-is rather than adjusted after the fact."
    ]


def _write_text_pdf(
    path: Path,
    lines: list[str],
    title: str,
    *,
    cover_title: str = "",
    subtitle: str = "",
    meta_lines: list[str] | None = None,
) -> None:
    page_element_lists = _paginate_lines(lines)
    objects: list[bytes] = []
    page_object_numbers: list[int] = []
    regular_font_number = 3
    bold_font_number = 4

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")  # filled in below once every page object exists
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    def _append_page(content: bytes) -> None:
        content_number = len(objects) + 2
        page_number = len(objects) + 1
        page_object_numbers.append(page_number)
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                "/Resources << /Font << "
                f"/F1 {regular_font_number} 0 R /F2 {bold_font_number} 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )

    _append_page(_title_page_stream(cover_title or title, subtitle, meta_lines or []))
    header = _short_running_header(title)
    total_body_pages = len(page_element_lists)
    for page_index, elements in enumerate(page_element_lists, start=1):
        footer = f"Page {page_index} of {total_body_pages}"
        _append_page(_page_stream(elements, header, footer))

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("ascii")
    _write_pdf_objects(path, objects)


# Page geometry, kept as named constants so the lines-per-page limit below is
# derived from the same numbers _page_stream uses to place text, rather than a
# hand-picked count that can silently drift out of sync with the layout. The
# previous hardcoded value of 58 lines/page was never checked against this
# geometry: content actually starts at PAGE_HEIGHT - TOP_MARGIN - 2 * LEADING
# (header line, then one blank line, before the first content line) and each
# line drops by LEADING, so anything past line ~49 was being drawn below
# y=BOTTOM_MARGIN -- often below y=0 -- and silently clipped by every PDF
# viewer, truncating the visible page mid-sentence while the "next" page
# picked up several lines later. Verified by rendering to an image and
# comparing against the raw content stream, not just by reading extracted
# text (which doesn't reflect what a viewer actually clips).
_PAGE_WIDTH = 612
_PAGE_HEIGHT = 792
_TOP_MARGIN = 44  # matches "50 748 Td": 792 - 748 = 44
_BOTTOM_MARGIN = 44
_LEADING = 14
_CONTENT_START_Y = _PAGE_HEIGHT - _TOP_MARGIN - 2 * _LEADING
_LINES_PER_PAGE = (_CONTENT_START_Y - _BOTTOM_MARGIN) // _LEADING + 1
# A trailing page with fewer elements than this looks like a mistake (e.g. one
# leftover reference line orphaned onto its own page) rather than a real page
# break, so _balance_trailing_page redistributes the last two pages instead of
# leaving it.
_MIN_TRAILING_PAGE_ELEMENTS = 8

# Sentinel markers a caller can embed in an otherwise-plain list[str] to ask
# for a real table instead of hand-joined "a | b | c" text: see _table_lines.
# NUL-prefixed so they can never collide with real prose content.
_TABLE_HEADER_MARK = "\x00TBLH\x00"
_TABLE_ROW_MARK = "\x00TBLR\x00"
_TABLE_FONT_SIZE = 9
_TABLE_CHAR_WIDTH = 5.0  # approx. points/character for 9pt Helvetica
_TABLE_COL_GAP = 10.0  # points between columns
_TABLE_AVAILABLE_WIDTH = _PAGE_WIDTH - 100  # page width minus the 50pt left/right margins
_TABLE_MIN_COL_CHARS = 6


@dataclass(frozen=True)
class _TextLine:
    text: str
    bold: bool = False
    indent: int = 0


@dataclass(frozen=True)
class _TableRow:
    cells: tuple[str, ...]
    x_offsets: tuple[float, ...]
    bold: bool = False


@dataclass(frozen=True)
class _Rule:
    pass


_RenderElement = _TextLine | _TableRow | _Rule


def _table_lines(headers: list[str], rows: list[list[Any]]) -> list[str]:
    """Encode a table as sentinel-marked strings that still satisfy the plain
    list[str] contract every other line in this module produces, so callers
    don't need to know about the PDF writer's internal element model -- only
    _paginate_lines below decodes the markers, into real aligned columns with
    a bold header row instead of a wrapped, unreadable pipe-delimited line."""
    encoded = [_TABLE_HEADER_MARK + "\x00".join(str(cell) for cell in headers)]
    for row in rows:
        encoded.append(_TABLE_ROW_MARK + "\x00".join(str(cell) for cell in row))
    return encoded


def _table_column_chars(headers: list[str], rows: list[list[str]]) -> list[int]:
    # Every column must fit within the page's content width once gaps are
    # subtracted, or wide tables (7-8 columns) silently run off the right
    # edge of the page -- the character budget has to be computed from the
    # actual page geometry, not a fixed constant that ignores column count.
    n = len(headers)
    if n == 0:
        return []
    gap_total = (n - 1) * _TABLE_COL_GAP
    available_chars = max(
        n * _TABLE_MIN_COL_CHARS,
        (_TABLE_AVAILABLE_WIDTH - gap_total) / _TABLE_CHAR_WIDTH,
    )
    # Every column gets at least enough room for its own header (up to a
    # cap), so the header word itself never wraps mid-word.
    floors = [max(_TABLE_MIN_COL_CHARS, min(len(str(header)), 12)) for header in headers]
    floor_total = sum(floors)
    weights = []
    for index in range(n):
        longest = len(str(headers[index]))
        for row in rows:
            if index < len(row):
                longest = max(longest, len(str(row[index])))
        # Cap so one very long free-text column (e.g. "Exact Claim") can't
        # starve every other column down to its floor.
        weights.append(min(longest, 60))
    total_weight = sum(weights) or n
    remaining = max(0.0, available_chars - floor_total)
    return [
        floors[index] + int(remaining * weights[index] / total_weight)
        for index in range(n)
    ]


def _table_x_offsets(col_chars: list[int]) -> list[float]:
    offsets = [0.0]
    for chars in col_chars[:-1]:
        offsets.append(offsets[-1] + chars * _TABLE_CHAR_WIDTH + _TABLE_COL_GAP)
    return offsets


def _table_row_elements(
    cells: list[str],
    col_chars: list[int],
    x_offsets: list[float],
    bold: bool,
) -> list[_TableRow]:
    wrapped_columns = [
        wrap(_ascii(str(cell)), width=chars) or [""]
        for cell, chars in zip(cells, col_chars)
    ]
    height = max((len(column) for column in wrapped_columns), default=0)
    elements: list[_TableRow] = []
    for row_index in range(height):
        row_cells = tuple(
            column[row_index] if row_index < len(column) else ""
            for column in wrapped_columns
        )
        elements.append(_TableRow(cells=row_cells, x_offsets=tuple(x_offsets), bold=bold))
    return elements


def _table_elements(headers: list[str], rows: list[list[str]]) -> list[_RenderElement]:
    col_chars = _table_column_chars(headers, rows)
    x_offsets = _table_x_offsets(col_chars)
    elements: list[_RenderElement] = [_Rule()]
    elements.extend(_table_row_elements(headers, col_chars, x_offsets, bold=True))
    elements.append(_Rule())
    for row in rows:
        elements.extend(_table_row_elements(row, col_chars, x_offsets, bold=False))
    elements.append(_Rule())
    elements.append(_TextLine(""))
    return elements


def _build_render_elements(lines: list[str]) -> list[_RenderElement]:
    elements: list[_RenderElement] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith(_TABLE_HEADER_MARK):
            headers = line[len(_TABLE_HEADER_MARK) :].split("\x00")
            index += 1
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith(_TABLE_ROW_MARK):
                rows.append(lines[index][len(_TABLE_ROW_MARK) :].split("\x00"))
                index += 1
            elements.extend(_table_elements(headers, rows))
            continue
        clean = _ascii(line)
        if not clean:
            elements.append(_TextLine(""))
        else:
            for wrapped in wrap(clean, width=92, replace_whitespace=False) or [""]:
                elements.append(_TextLine(wrapped))
        index += 1
    return elements


def _balance_trailing_page(pages: list[list[_RenderElement]]) -> list[list[_RenderElement]]:
    if len(pages) < 2:
        return pages
    last = pages[-1]
    second_last = pages[-2]
    if not last or len(last) >= _MIN_TRAILING_PAGE_ELEMENTS:
        return pages
    combined = second_last + last
    midpoint = (len(combined) + 1) // 2
    pages[-2] = combined[:midpoint]
    pages[-1] = combined[midpoint:]
    return pages


def _paginate_lines(lines: list[str]) -> list[list[_RenderElement]]:
    elements = _build_render_elements(lines)
    pages = [
        elements[index : index + _LINES_PER_PAGE]
        for index in range(0, len(elements), _LINES_PER_PAGE)
    ]
    pages = _balance_trailing_page(pages)
    return pages or [[_TextLine("No content.")]]


def _short_running_header(title: str, max_len: int = 78) -> str:
    if len(title) <= max_len:
        return title
    return title[: max_len - 3].rsplit(" ", 1)[0] + "..."


def _text_command(text: str, x: float, y: float, font: str, size: int) -> str:
    return f"BT /{font} {size} Tf {x:.1f} {y:.1f} Td ({_escape_pdf_text(_ascii(text))}) Tj ET"


def _title_page_stream(title: str, subtitle: str, meta_lines: list[str]) -> bytes:
    ops: list[str] = []
    y = float(_PAGE_HEIGHT - 260)
    for wrapped in wrap(_ascii(title), width=34) or [title]:
        ops.append(_text_command(wrapped, x=50, y=y, font="F2", size=22))
        y -= 28
    y -= 10
    if subtitle:
        for wrapped in wrap(_ascii(subtitle), width=60) or [subtitle]:
            ops.append(_text_command(wrapped, x=50, y=y, font="F1", size=13))
            y -= 18
    y -= 20
    for meta in meta_lines:
        ops.append(_text_command(meta, x=50, y=y, font="F1", size=10))
        y -= 16
    ops.append(
        _text_command(
            "Governed research draft, generated by the PCA / Lucien research pipeline.",
            x=50,
            y=54.0,
            font="F1",
            size=8,
        )
    )
    return "\n".join(ops).encode("ascii")


def _page_stream(elements: list[_RenderElement], header: str, footer: str) -> bytes:
    ops: list[str] = [_text_command(header, x=50, y=float(_PAGE_HEIGHT - _TOP_MARGIN), font="F2", size=10)]
    y = float(_PAGE_HEIGHT - _TOP_MARGIN) - _LEADING * 2
    for element in elements:
        if isinstance(element, _Rule):
            rule_y = y + _LEADING * 0.35
            ops.append(f"q 0.4 w 50 {rule_y:.1f} m {_PAGE_WIDTH - 50} {rule_y:.1f} l S Q")
            y -= _LEADING * 0.4
            continue
        if isinstance(element, _TableRow):
            font = "F2" if element.bold else "F1"
            for cell_text, x_offset in zip(element.cells, element.x_offsets):
                if cell_text:
                    ops.append(
                        _text_command(cell_text, x=50 + x_offset, y=y, font=font, size=_TABLE_FONT_SIZE)
                    )
            y -= _LEADING
            continue
        if element.text:
            font = "F2" if element.bold else "F1"
            ops.append(_text_command(element.text, x=50 + element.indent, y=y, font=font, size=10))
        y -= _LEADING
    ops.append(_text_command(footer, x=50, y=float(_BOTTOM_MARGIN - 10), font="F1", size=8))
    return "\n".join(ops).encode("ascii")


def _write_pdf_objects(path: Path, objects: list[bytes]) -> None:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current = len(chunks[0])
    for index, body in enumerate(objects, start=1):
        offsets.append(current)
        chunk = f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
        chunks.append(chunk)
        current += len(chunk)
    xref_offset = current
    xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    path.write_bytes(b"".join(chunks + xref + [trailer]))


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# The PDF writer only has the standard-14 Helvetica font (WinAnsi/ASCII glyphs),
# so real Unicode extracted from source PDFs -- Greek letters, math operators,
# smart punctuation -- can't be drawn directly. Transliterating known symbols to
# readable ASCII (rather than dropping them to "?") is what actually fixes the
# "corrupted evidence" appearance: the underlying extracted text is correct, it's
# this renderer that was destroying it.
_UNICODE_TRANSLITERATIONS = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "Δ": "Delta",
    "ε": "epsilon", "ζ": "zeta", "η": "eta", "θ": "theta", "ι": "iota",
    "κ": "kappa", "λ": "lambda", "Λ": "Lambda", "μ": "mu", "µ": "mu",
    "ν": "nu", "ξ": "xi", "π": "pi", "Π": "Pi", "ρ": "rho", "σ": "sigma",
    "Σ": "Sigma", "τ": "tau", "υ": "upsilon", "φ": "phi", "Φ": "Phi",
    "χ": "chi", "ψ": "psi", "ω": "omega", "Ω": "Omega",
    "∂": "d", "∇": "grad ", "∞": "infinity", "√": "sqrt", "∑": "sum",
    "∫": "integral", "≈": "~", "≠": "!=", "≤": "<=", "≥": ">=",
    "≫": ">>", "≪": "<<", "→": "->", "↓": "down", "↑": "up",
    "±": "+/-", "×": "x", "÷": "/", "∆": "Delta",
    "−": "-", "–": "-", "—": "--",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "•": "-", "…": "...",
    "ﬁ": "fi", "ﬂ": "fl",
}


def _transliterate_unicode(text: str) -> str:
    for source, replacement in _UNICODE_TRANSLITERATIONS.items():
        if source in text:
            text = text.replace(source, replacement)
    return text


# Genuine extraction damage: some PDFs use font encodings pypdf can't resolve to
# real characters, and it falls back to emitting the raw glyph codes as literal
# "/xNN" tokens (e.g. "/x5B/x44.../x5D" instead of "[Derived]"). This is real
# garbage, unlike the Unicode symbols _transliterate_unicode handles above, and
# should never be promoted into a Finding.
_EXTRACTION_DAMAGE_PATTERN = re.compile(r"(?:/x[0-9A-Fa-f]{2}){3,}")
_MALFORMED_MATH_PATTERNS = [
    re.compile(r"\bRT\s*I(?:mat|->|down|up|~|\s*=)", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]{2,}->\s*\w+", re.IGNORECASE),
    re.compile(r"\b(?:infinity|before|after|first|last)[A-Za-z]{4,}\b", re.IGNORECASE),
    re.compile(r"\b(?:tau|rho|delta|grad|mu|alpha|beta|gamma)[A-Za-z]{3,}(?:\(|=|->|\b)", re.IGNORECASE),
    re.compile(r"\b[A-Za-z]{3,}(?:delta|tau|rho|grad|infinity)[A-Za-z]{2,}\b", re.IGNORECASE),
]


def _has_extraction_damage(text: str) -> bool:
    return not _reader_facing_extraction_quality(text)["usable"]


def _reader_facing_extraction_quality(text: str) -> dict[str, Any]:
    clean = _transliterate_unicode(str(text))
    reasons: list[str] = []
    if _EXTRACTION_DAMAGE_PATTERN.search(clean):
        reasons.append("raw glyph code leakage")
    for pattern in _MALFORMED_MATH_PATTERNS:
        if pattern.search(clean):
            reasons.append("malformed mathematical extraction")
            break
    if _fused_word_score(clean) >= 2:
        reasons.append("fused words")
    if clean.count("?") >= 3:
        reasons.append("replacement characters")
    return {
        "usable": not reasons,
        "reasons": reasons,
    }


def _fused_word_score(text: str) -> int:
    terms = [
        "before",
        "after",
        "first",
        "last",
        "collapse",
        "recovery",
        "identity",
        "continuity",
        "energy",
        "field",
    ]
    score = 0
    lowered = text.lower()
    for left in terms:
        for right in terms:
            if left == right:
                continue
            if f"{left}{right}" in lowered:
                score += 1
    return score


def _ascii(text: object) -> str:
    return _transliterate_unicode(str(text)).encode("ascii", "replace").decode("ascii")

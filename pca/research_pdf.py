from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
from typing import Any
import re

from .argument_graph import mission_argument_graph
from .coherence_corpus import coherence_corpus_index_records_from_events, is_relevant_source_path
from .evidence_locker import evidence_for_target
from .falsification_lab import falsification_lab_verdict
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_claim_map import mission_claim_map
from .missions import mission_briefs_from_events, require_mission
from .research_sandbox import (
    render_research_output_content,
    research_outputs_from_events,
)
from .source_notes import source_notes_for_mission


def export_research_pdf(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    output_path: str | Path = "reports/research_papers/coherence_audit_bundle.pdf",
    project_root: str | Path = ".",
    paper_output_path: str | Path = "reports/research_papers/coherence_paper.pdf",
) -> dict[str, Any]:
    """Export the two paired research documents for a mission.

    ``output_path`` is the audit bundle (the complete, unfiltered machine
    record: evidence IDs, hashes, review status, every generated draft).
    ``paper_output_path`` is the reader-facing scholarly paper: argument,
    definitions, findings, references -- no raw IDs, no registration stubs,
    no duplicate drafts. They are two files because a document trying to be
    both a governance audit trail and a readable paper serves neither well.
    """
    workspace_root = Path(project_root).resolve().parent
    mission = require_mission(ledger.events(), mission_id)
    brief = next(
        item
        for item in mission_briefs_from_events(ledger.events())
        if item.mission.mission_id == mission_id
    )
    outputs = research_outputs_from_events(ledger.events(), mission_id)
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
        note
        for note in source_notes_for_mission(ledger.events(), mission_id)
        if is_relevant_source_path(str(note.get("source_path") or ""))
    ]

    audit_path = Path(output_path)
    paper_path = Path(paper_output_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    paper_path.parent.mkdir(parents=True, exist_ok=True)

    paper_lines = _scholarly_paper_lines(
        mission_title=mission.title,
        claim_map=claim_map,
        corpus_sources=corpus_sources,
        source_notes=source_notes,
        falsification_verdict=falsification_lab_verdict(workspace_root),
        argument_graph=mission_argument_graph(ledger, mission_id),
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
        paper_path=str(paper_path),
    )
    _write_text_pdf(paper_path, paper_lines, title=f"Coherence Physics Paper - {mission.title}")
    _write_text_pdf(audit_path, audit_lines, title=f"Coherence Physics Audit Bundle - {mission.title}")
    return {
        "path": str(audit_path),
        "audit_path": str(audit_path),
        "paper_path": str(paper_path),
        "mission_id": mission_id,
        "mission_title": mission.title,
        "output_count": len(outputs),
        "evidence_count": len(linked_evidence),
        "source_count": len(corpus_sources),
        "source_note_count": len(source_notes),
        "claim_count": claim_map.get("claim_count", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governance": "export only; does not accept claims, evidence, memory, or mission outcomes",
    }


def _scholarly_paper_lines(
    mission_title: str,
    claim_map: dict[str, Any],
    corpus_sources: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    falsification_verdict: dict[str, Any] | None,
    argument_graph: dict[str, Any],
    audit_bundle_path: str,
) -> list[str]:
    claim_count = int(claim_map.get("claim_count", 0) or 0)
    reviewed_evidence = int(claim_map.get("reviewed_evidence_count", 0) or 0)
    claim_candidate_notes = [
        note for note in source_notes if note.get("note_kind") == "claim_candidate"
    ]
    lines = [
        "Smooth Output Is Not Continuity:",
        "A Coherence Physics Approach to Governed Artificial Identity",
        "",
        "Author: Skylar Fiction with Lucien/PCA research assistance",
        "Status: governed draft for human review",
        "",
        "Abstract",
        "Fluent, stylistically consistent output from an AI system is not evidence "
        "that its memory, commitments, authority, or lineage survived whatever "
        "change produced that output. This paper argues that identity continuity "
        "must be treated as an inspectable, governed claim -- backed by a signed "
        "identity manifest, a tamper-evident event ledger, and evidence explicitly "
        "marked raw or reviewed -- rather than inferred from behavior alone. "
        "Persistence-Constrained Architecture (PCA) is presented as a working local "
        "implementation of that requirement, and one of its component claims "
        "(Recovery Threshold Index as an early-warning signal for collapse) has been "
        "put under an adversarial, predeclared test, with the result reported here "
        "including where it failed. The definitions, formal criteria, and "
        "related-work comparison below are this draft's own conceptual "
        "contribution; they have not yet been reviewed and should be read as "
        "provisional, not as accepted findings.",
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
        "PCA treats continuity as checkable rather than assumed by requiring three "
        "concrete artifacts. First, an identity manifest that fixes a system_id, a "
        "declared version, and a list of invariants and constraints -- each "
        "constraint naming what it bounds, whether it is required, its threshold, "
        "and how fresh its supporting measurement must be -- together with an "
        "explicit list of allowed transforms the system may undergo without "
        "breaking identity. Second, a hash-chained continuity ledger in which every "
        "event carries its type, its subject, a payload, a timestamp, and a hash of "
        "the previous event, so tampering with or silently dropping history breaks "
        "the chain rather than passing unnoticed. Third, an evidence layer that "
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
        "7. Existing Falsification Evidence",
        *_falsification_section_lines(falsification_verdict),
        "",
        "8. Materials and Current Evidence Base",
        f"This run indexed {len(corpus_sources)} source file(s) and extracted "
        f"{len(claim_candidate_notes)} argument-bearing source note(s) from them. "
        "Registration-only inventory notes and the full evidence ledger (record "
        f"IDs, hashes, review status) are omitted here; see the companion audit "
        f"bundle ({audit_bundle_path}) for the complete, unfiltered record.",
    ]
    if corpus_sources:
        lines.append("Key source files currently registered:")
        for source in corpus_sources[:12]:
            lines.append(
                "- "
                f"{source.get('theme', 'general_coherence')}: "
                f"{source.get('path', 'unknown source')}"
            )
    else:
        lines.append(
            "No corpus source file names were available in this export. The next run "
            "should index the Coherence corpus before drafting stronger conclusions."
        )
    lines.extend(
        [
            "",
            "9. Source-Derived Notes",
        ]
    )
    if claim_candidate_notes:
        lines.append(
            "The following citation cards were extracted from indexed local sources. "
            "They are raw notes, not accepted conclusions. Registration-only stubs "
            "(a source being indexed does not mean it supports any claim) are "
            "omitted; see the audit bundle for the full inventory."
        )
        for note in claim_candidate_notes[:10]:
            summary = str(note.get("summary", ""))
            if _has_extraction_damage(summary):
                summary = (
                    "Extraction integrity failure: manual source inspection "
                    "required. (Raw text stored in the audit bundle.)"
                )
            lines.append(
                "- "
                f"{note.get('theme', 'general_coherence')} / "
                f"{note.get('title', 'untitled')}: "
                f"{summary}"
            )
    else:
        lines.append(
            "No argument-bearing source notes were available in this export. The "
            "next improvement is to extract citation cards from the indexed "
            "corpus before writing the paper."
        )
    lines.extend(
        [
            "",
            "10. Current Claim Map",
            f"This draft contains {claim_count} mapped claim(s). Claims with raw support "
            "should be read as promising but unverified. Claims with reviewed support "
            "may be candidates for stronger public wording.",
        ]
    )
    for entry in claim_map.get("entries", []):
        lines.append(
            "- "
            f"Support status: {entry.get('support_status', 'unknown')}; "
            f"confidence: {entry.get('confidence', 'unknown')}; "
            f"linked evidence: {entry.get('evidence_count', 0)}."
        )
    source_findings = _source_note_findings(source_notes)
    lines.extend(
        [
            "",
            "11. Findings",
            "The findings below are drawn only from claim-candidate source notes "
            "that passed the source relevance gate, not from registration stubs "
            "and not from generic claims about the archive. Section 9 lists all "
            "extracted notes, including the registration stubs excluded here; the "
            "two are not the same thing.",
            *source_findings,
            *_falsification_finding_lines(falsification_verdict, len(source_findings) + 1),
            "",
            "12. Argument Structure",
            "Every line below names the typed object it came from (claim, premise, "
            "implementation fact, counterevidence, inference, test, verdict, or "
            "limitation) so the paragraph can be traced back to what actually "
            "supports it, rather than reading as prewritten prose.",
            *_argument_graph_lines(argument_graph),
            "",
            "13. Discussion",
            "The useful conclusion is cautious: Coherence Physics should be advanced "
            "as a research framework and engineering program before it is presented "
            "as a completed physical theory. Its current strength is the repeatable "
            "discipline of making persistence claims auditable, and, where a claim has "
            "actually been put under adversarial test, reporting the result even when "
            "it is mixed rather than favorable.",
            "",
            "14. Proposed Paper Direction",
            "A strong first paper should focus on the narrow, defensible claim: smooth "
            "output is not proof of continuity. From there, PCA can be shown as a "
            "working architecture that records what changed, what evidence exists, "
            "what remains under review, and what claims the system is allowed to make.",
            "",
            "15. Limitations",
            "- This draft is generated from local governed research outputs.",
            "- Raw evidence has not been accepted as reviewed evidence unless marked so.",
            "- The document does not claim proof of consciousness, AGI, personhood, or final physics.",
            "- Source registration is not the same as source interpretation.",
            "",
            "16. Conclusion",
            "The next best version of Coherence Physics is a paper series built from "
            "reviewed source evidence, explicit claim maps, and falsifiable or "
            "inspectable examples. Lucien can help generate these drafts, but the "
            "system should keep the same rule at every stage: no claim becomes final "
            "without evidence review.",
            "",
            "17. Research Agenda",
            "- Review indexed source files and mark useful evidence as reviewed.",
            "- Choose one paper track: PCA/identity continuity, CSM, cognitive physics, or cosmology.",
            "- Replace provisional findings with source-backed claims.",
            "- Add objections and counterexamples before public release.",
            "- Define one falsifiable or inspectable test for each major claim family.",
            "",
            "References",
        ]
    )
    if corpus_sources:
        for index, source in enumerate(corpus_sources[:20], start=1):
            lines.append(
                f"[{index}] {source.get('path', 'unknown source')} "
                f"({source.get('theme', 'general_coherence')})."
            )
    else:
        lines.append("[1] No indexed corpus references were available for this run.")
    return lines


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
    paper_path: str,
) -> list[str]:
    lines = [
        f"Audit Bundle - {mission_title}",
        f"Companion machine record for the reader-facing paper ({paper_path}). "
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
            f"hash {str(entry.get('claim_hash', ''))[:16]}"
        )
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
    for output, content in output_contents:
        lines.extend(
            [
                "",
                output.title,
                f"Kind: {output.kind.value}",
                f"Status: {output.status}",
                f"Confidence: {output.confidence}",
                f"Claims: {output.claim_count}",
                f"Evidence IDs: {', '.join(output.evidence_ids) or 'none'}",
                "",
                _paper_content(content),
            ]
        )
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
        and not _has_extraction_damage(str(note.get("summary") or ""))
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
        lines.append("Summary: " + "; ".join(verdict["summary"]) + ".")
    if verdict["reasons"]:
        lines.append("Reasons: " + "; ".join(verdict["reasons"]) + ".")
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


def _write_text_pdf(path: Path, lines: list[str], title: str) -> None:
    page_lines = _paginate_lines(lines)
    objects: list[bytes] = []
    page_object_numbers: list[int] = []
    font_object_number = 3

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page in page_lines:
        content = _page_stream(page, title)
        content_number = len(objects) + 2
        page_number = len(objects) + 1
        page_object_numbers.append(page_number)
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("ascii")
    _write_pdf_objects(path, objects)


def _paginate_lines(lines: list[str]) -> list[list[str]]:
    wrapped: list[str] = []
    for line in lines:
        clean = _ascii(line)
        if not clean:
            wrapped.append("")
            continue
        wrapped.extend(wrap(clean, width=92, replace_whitespace=False) or [""])
    pages = [wrapped[index : index + 58] for index in range(0, len(wrapped), 58)]
    return pages or [["No content."]]


def _page_stream(lines: list[str], title: str) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 748 Td", "14 TL"]
    commands.append(f"({_escape_pdf_text(_ascii(title))}) Tj")
    commands.append("T*")
    commands.append("T*")
    for line in lines:
        commands.append(f"({_escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


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


def _has_extraction_damage(text: str) -> bool:
    return bool(_EXTRACTION_DAMAGE_PATTERN.search(text))


def _ascii(text: object) -> str:
    return _transliterate_unicode(str(text)).encode("ascii", "replace").decode("ascii")

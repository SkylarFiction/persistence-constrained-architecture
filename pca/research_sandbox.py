from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import uuid

from .evidence_locker import EvidenceRecord, add_evidence, link_evidence
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .missions import MissionBrief, mission_briefs_from_events, require_mission


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ResearchActionRisk(str, Enum):
    FREE_RESEARCH = "free_research"
    REVIEW_REQUIRED = "review_required"
    RESTRICTED = "restricted"


class ResearchOutputKind(str, Enum):
    RESEARCH_BRIEF = "research_brief"
    CLAIM_MAP_DRAFT = "claim_map_draft"
    PAPER_DRAFT = "paper_draft"
    SOURCE_SUMMARY = "source_summary"
    EXPERIMENT_PROPOSAL = "experiment_proposal"
    NEXT_STEP_SUGGESTION = "next_step_suggestion"


FREE_RESEARCH_ACTIONS = {
    "web_search",
    "source_summary",
    "research_brief",
    "claim_map_draft",
    "outline_draft",
    "paper_draft",
    "public_post_draft",
    "experiment_proposal",
    "next_step_suggestion",
}

REVIEW_REQUIRED_ACTIONS = {
    "accept_memory",
    "accept_skill",
    "promote_claim_to_supported",
    "link_evidence_as_supporting",
    "approve_mission_step",
    "tool_execution",
    "cloud_assist_use",
}

RESTRICTED_ACTIONS = {
    "file_write",
    "file_delete",
    "shell_command",
    "git_commit",
    "git_push",
    "publish_post",
    "send_email",
    "change_policy",
}


@dataclass(frozen=True)
class ResearchSandboxOutputRecord:
    output_id: str
    identity_id: str
    mission_id: str
    kind: ResearchOutputKind
    status: str
    title: str
    content_hash: str
    content_length: int
    confidence: str
    evidence_ids: list[str] = field(default_factory=list)
    claim_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        mission_id: str,
        kind: str | ResearchOutputKind,
        title: str,
        content: str,
        confidence: str = "low",
        evidence_ids: list[str] | None = None,
        claim_count: int = 0,
        reason: str = "",
    ) -> "ResearchSandboxOutputRecord":
        return cls(
            output_id=f"research_output_{uuid.uuid4()}",
            identity_id=identity_id,
            mission_id=mission_id,
            kind=_parse_output_kind(kind),
            status="proposed",
            title=title,
            content_hash=_text_hash(content),
            content_length=len(content),
            confidence=confidence,
            evidence_ids=evidence_ids or [],
            claim_count=claim_count,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchSandboxOutputRecord":
        return cls(
            output_id=str(data["output_id"]),
            identity_id=str(data["identity_id"]),
            mission_id=str(data["mission_id"]),
            kind=_parse_output_kind(data["kind"]),
            status=str(data.get("status", "proposed")),
            title=str(data["title"]),
            content_hash=str(data["content_hash"]),
            content_length=int(data["content_length"]),
            confidence=str(data.get("confidence", "low")),
            evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
            claim_count=int(data.get("claim_count", 0)),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_id": self.output_id,
            "identity_id": self.identity_id,
            "mission_id": self.mission_id,
            "kind": self.kind.value,
            "status": self.status,
            "title": self.title,
            "content_hash": self.content_hash,
            "content_length": self.content_length,
            "confidence": self.confidence,
            "evidence_ids": self.evidence_ids,
            "claim_count": self.claim_count,
            "created_at": self.created_at,
            "reason": self.reason,
        }


def classify_research_action(action: str) -> ResearchActionRisk:
    if action in FREE_RESEARCH_ACTIONS:
        return ResearchActionRisk.FREE_RESEARCH
    if action in REVIEW_REQUIRED_ACTIONS:
        return ResearchActionRisk.REVIEW_REQUIRED
    if action in RESTRICTED_ACTIONS:
        return ResearchActionRisk.RESTRICTED
    return ResearchActionRisk.REVIEW_REQUIRED


def research_sandbox_status(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    outputs = research_outputs_from_events(ledger.events())
    proposed = [output for output in outputs if output.status == "proposed"]
    return {
        "mode": "research_sandbox",
        "law": "Research freely; do not persist, publish, spend, or alter files without approval.",
        "free_actions": sorted(FREE_RESEARCH_ACTIONS),
        "review_required_actions": sorted(REVIEW_REQUIRED_ACTIONS),
        "restricted_actions": sorted(RESTRICTED_ACTIONS),
        "output_count": len(outputs),
        "proposed_output_count": len(proposed),
        "latest_output": outputs[-1].to_dict() if outputs else None,
    }


def create_research_output(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    kind: str | ResearchOutputKind,
    reason: str = "",
) -> dict[str, Any]:
    require_mission(ledger.events(), mission_id)
    brief = _mission_brief(ledger.events(), mission_id)
    kind_value = _parse_output_kind(kind)
    content, claim_count = _draft_content(brief, kind_value)
    existing = _existing_output_for_content(
        ledger.events(),
        mission_id=mission_id,
        kind=kind_value,
        content_hash=_text_hash(content),
    )
    if existing:
        record = {
            "identity_id": manifest.system_id,
            "mission_id": mission_id,
            "kind": kind_value.value,
            "existing_output_id": existing.output_id,
            "content_hash": existing.content_hash,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason or f"research sandbox regenerated duplicate {kind_value.value}",
            "governance": (
                "duplicate generated content was not stored again; this event "
                "preserves regeneration history by reference"
            ),
        }
        ledger.append("research.output_regenerated", manifest.system_id, record)
        return {
            "output": existing.to_dict(),
            "evidence": None,
            "evidence_link": None,
            "content": content,
            "regeneration": record,
        }
    evidence = _proposed_evidence_for_output(
        ledger,
        manifest,
        mission_id,
        kind_value,
        content,
    )
    evidence_link = link_evidence(
        ledger,
        manifest.system_id,
        evidence.evidence_id,
        "mission",
        mission_id,
        reason="research sandbox linked proposed evidence to mission",
    )
    record = ResearchSandboxOutputRecord.create(
        identity_id=manifest.system_id,
        mission_id=mission_id,
        kind=kind_value,
        title=_title_for_kind(brief, kind_value),
        content=content,
        confidence="low",
        evidence_ids=[evidence.evidence_id],
        claim_count=claim_count,
        reason=reason or f"research sandbox generated {kind_value.value}",
    )
    ledger.append("research.output_created", manifest.system_id, record.to_dict())
    return {
        "output": record.to_dict(),
        "evidence": evidence.to_dict(),
        "evidence_link": evidence_link.to_dict(),
        "content": content,
    }


def research_outputs_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[ResearchSandboxOutputRecord]:
    records = [
        ResearchSandboxOutputRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "research.output_created"
    ]
    if mission_id:
        records = [record for record in records if record.mission_id == mission_id]
    return sorted(records, key=lambda record: (record.created_at, record.output_id))


def research_output_regenerations_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[dict[str, Any]]:
    records = [
        event.payload
        for event in events
        if event.event_type == "research.output_regenerated"
    ]
    if mission_id:
        records = [record for record in records if record.get("mission_id") == mission_id]
    return records


def render_research_outputs_text(outputs: list[ResearchSandboxOutputRecord]) -> str:
    lines = ["Research Outputs", f"Outputs: {len(outputs)}"]
    if not outputs:
        lines.append("No research sandbox outputs yet.")
        return "\n".join(lines)
    for output in outputs:
        lines.extend(
            [
                "",
                f"{output.output_id} / {output.kind.value} / {output.status}",
                f"mission: {output.mission_id}",
                f"title: {output.title}",
                f"confidence: {output.confidence}",
                f"claims: {output.claim_count}",
                f"evidence: {', '.join(output.evidence_ids) or 'none'}",
            ]
        )
    return "\n".join(lines)


def render_research_output_content(
    events: list[ContinuityEvent],
    output: ResearchSandboxOutputRecord,
) -> str:
    brief = _mission_brief(events, output.mission_id)
    content, _ = _draft_content(brief, output.kind)
    return content


def _proposed_evidence_for_output(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    kind: ResearchOutputKind,
    content: str,
) -> EvidenceRecord:
    return add_evidence(
        ledger,
        manifest.system_id,
        source_type="mission_observation",
        source=f"{kind.value}:{mission_id}:{content}",
        summary=f"Proposed research sandbox output for mission {mission_id}.",
        confidence="low",
        reason="research sandbox proposed evidence; not reviewed or accepted",
    )


def _existing_output_for_content(
    events: list[ContinuityEvent],
    mission_id: str,
    kind: ResearchOutputKind,
    content_hash: str,
) -> ResearchSandboxOutputRecord | None:
    for output in reversed(research_outputs_from_events(events, mission_id)):
        if output.kind == kind and output.content_hash == content_hash:
            return output
    return None


def _mission_brief(events: list[ContinuityEvent], mission_id: str) -> MissionBrief:
    for brief in mission_briefs_from_events(events):
        if brief.mission.mission_id == mission_id:
            return brief
    raise ValueError(f"Mission not found: {mission_id}")


def _draft_content(
    brief: MissionBrief,
    kind: ResearchOutputKind,
) -> tuple[str, int]:
    mission = brief.mission
    grouped = brief.to_dict()["by_kind"]
    hypotheses = grouped.get("hypothesis", [])
    evidence = grouped.get("evidence", [])
    risks = grouped.get("risk", [])
    plan_steps = grouped.get("plan_step", [])
    if kind == ResearchOutputKind.RESEARCH_BRIEF:
        return (
            "\n".join(
                [
                    f"# Research Brief: {mission.title}",
                    "",
                    "Status: proposed draft, not accepted truth.",
                    f"Mission values: {', '.join(mission.values) or 'none'}",
                    f"Hypothesis count: {len(hypotheses)}",
                    f"Evidence needs: {len(evidence)}",
                    f"Known risks: {len(risks)}",
                    "",
                    "Next safe move: collect source evidence before strengthening claims.",
                ]
            ),
            len(hypotheses),
        )
    if kind == ResearchOutputKind.CLAIM_MAP_DRAFT:
        lines = [
            f"# Claim Map Draft: {mission.title}",
            "",
            "All claims are proposed until reviewed.",
        ]
        for index, item in enumerate(hypotheses, start=1):
            lines.append(f"- Claim {index}: proposed hypothesis hash {item['summary_sha256'][:12]}")
        if not hypotheses:
            lines.append("- Claim 1: mission requires a first hypothesis before mapping claims.")
        lines.append("- Evidence status: unresolved until linked evidence is reviewed.")
        return "\n".join(lines), max(1, len(hypotheses))
    if kind == ResearchOutputKind.PAPER_DRAFT:
        return (
            "\n".join(
                [
                    f"# Paper Draft Skeleton: {mission.title}",
                    "",
                    "1. Problem: continuity claims need governance.",
                    "2. Framework: persistence, boundaries, recovery, and evidence.",
                    "3. Current mission evidence: proposed only.",
                    "4. Risks and limits: do not overclaim consciousness, proof, or personhood.",
                    "5. Next work: gather reviewed sources and testable examples.",
                ]
            ),
            len(hypotheses),
        )
    if kind == ResearchOutputKind.EXPERIMENT_PROPOSAL:
        return (
            "\n".join(
                [
                    f"# Experiment Proposal: {mission.title}",
                    "",
                    "Goal: turn one proposed claim into a small reproducible probe.",
                    "Inputs: claim, expected persistence behavior, disruption, recovery criterion.",
                    "Output: trace, observation, and objection list.",
                    f"Candidate plan steps: {len(plan_steps)}",
                ]
            ),
            1,
        )
    if kind == ResearchOutputKind.NEXT_STEP_SUGGESTION:
        return (
            f"Next suggested research step for {mission.title}: gather source evidence for the weakest unresolved claim before drafting conclusions.",
            1,
        )
    return (
        f"Source summary draft for {mission.title}: no external source attached yet; add sources before review.",
        0,
    )


def _title_for_kind(brief: MissionBrief, kind: ResearchOutputKind) -> str:
    labels = {
        ResearchOutputKind.RESEARCH_BRIEF: "Research Brief",
        ResearchOutputKind.CLAIM_MAP_DRAFT: "Claim Map Draft",
        ResearchOutputKind.PAPER_DRAFT: "Paper Draft",
        ResearchOutputKind.SOURCE_SUMMARY: "Source Summary",
        ResearchOutputKind.EXPERIMENT_PROPOSAL: "Experiment Proposal",
        ResearchOutputKind.NEXT_STEP_SUGGESTION: "Next Step Suggestion",
    }
    return f"{labels[kind]}: {brief.mission.title}"


def _parse_output_kind(value: str | ResearchOutputKind) -> ResearchOutputKind:
    if isinstance(value, ResearchOutputKind):
        return value
    return ResearchOutputKind(str(value))

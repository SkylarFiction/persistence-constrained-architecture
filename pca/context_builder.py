from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .claims import current_claim_record
from .evidence_locker import (
    evidence_for_target,
    evidence_locker_snapshot,
)
from .followups import active_followups
from .growth import active_growth_records
from .growth_conflicts import (
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
)
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .memory_cards import memory_cards_from_events
from .mission_flow import mission_flows_from_events
from .mission_steps import mission_step_records_from_events
from .missions import mission_briefs_from_events
from .output_gate import OutputGate
from .recovery import current_recovery_record
from .reflection_queue import active_reflection_tasks
from .self_model import derive_self_model
from .skill_memory import skill_suggestions_for_mission
from .state import derive_current_claim
from .steward_inbox import steward_inbox


@dataclass(frozen=True)
class ContextSection:
    name: str
    status: str
    items: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "items": self.items,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class GovernedContext:
    identity_id: str
    continuity_claim: str
    output_mode: str
    allowed_scope: str
    sections: list[ContextSection]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "continuity_claim": self.continuity_claim,
            "output_mode": self.output_mode,
            "allowed_scope": self.allowed_scope,
            "warnings": self.warnings,
            "sections": [section.to_dict() for section in self.sections],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        counts = {section.name: len(section.items) for section in self.sections}
        return {
            "section_count": len(self.sections),
            "warning_count": len(self.warnings)
            + sum(len(section.warnings) for section in self.sections),
            "item_counts": counts,
        }

    def render_prompt_context(self) -> str:
        lines = [
            "Governed PCA context for Lucien.",
            f"Continuity claim: {self.continuity_claim}",
            f"Output mode: {self.output_mode}",
            f"Allowed scope: {self.allowed_scope}",
        ]
        if self.warnings:
            lines.append("Global warnings:")
            lines.extend(f"- {warning}" for warning in self.warnings)
        for section in self.sections:
            lines.append(f"{section.name} ({section.status}): {len(section.items)} item(s)")
            for warning in section.warnings:
                lines.append(f"- warning: {warning}")
            for item in section.items[:8]:
                lines.append(f"- {', '.join(f'{key}={value}' for key, value in item.items())}")
        return "\n".join(lines)


def build_governed_context(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str | None = None,
    recent_turn_limit: int = 5,
) -> GovernedContext:
    events = ledger.events()
    claim, _, reasons = derive_current_claim(ledger, manifest)
    gate = OutputGate().evaluate(claim)
    self_model = derive_self_model(events, manifest.system_id)
    current_recovery = current_recovery_record(events)
    current_claim = current_claim_record(events)
    evidence_snapshot = evidence_locker_snapshot(events)
    memory_cards = memory_cards_from_events(events, manifest.system_id)
    active_growth = active_growth_records(events)
    open_tasks = active_reflection_tasks(events)
    followups = active_followups(events)
    unresolved_conflicts = _unresolved_conflicts(events)
    mission_sections = _mission_context_sections(events, mission_id)
    inbox_items = steward_inbox(ledger)
    context = GovernedContext(
        identity_id=manifest.system_id,
        continuity_claim=claim,
        output_mode=gate.mode.value,
        allowed_scope=gate.allowed_scope,
        warnings=[
            *reasons,
            *(
                ["continuity claim has not been recorded"]
                if current_claim is None
                else []
            ),
        ],
        sections=[
            ContextSection(
                name="self_model",
                status="accepted_only",
                items=[
                    {
                        "accepted_growth_count": self_model.accepted_growth_count,
                        "memory": len(self_model.by_kind.get("memory", [])),
                        "commitment": len(self_model.by_kind.get("commitment", [])),
                        "skill": len(self_model.by_kind.get("skill", [])),
                        "policy": len(self_model.by_kind.get("policy", [])),
                    }
                ],
            ),
            ContextSection(
                name="memory_cards",
                status="accepted_memory_only",
                items=[
                    {
                        "memory_id": card.memory_id,
                        "confidence": card.effective_confidence,
                        "summary_hash": card.summary_sha256[:12],
                        "evidence_refs": len(card.evidence_refs),
                        "signals": (
                            card.reinforcement_count
                            + card.contradiction_count
                            + card.stale_signal_count
                        ),
                    }
                    for card in memory_cards[-8:]
                ],
            ),
            ContextSection(
                name="evidence_locker",
                status="review_state_visible",
                items=[
                    {
                        "evidence_id": record["evidence_id"],
                        "type": record["source_type"],
                        "status": record["review_status"],
                        "confidence": record["confidence"],
                        "summary_hash": record["summary_hash"][:12],
                    }
                    for record in evidence_snapshot["evidence"][-8:]
                ],
                warnings=_evidence_warnings(evidence_snapshot),
            ),
            ContextSection(
                name="open_governance",
                status="must_not_ignore",
                items=[
                    {"kind": "active_growth", "count": len(active_growth)},
                    {"kind": "open_reflection_tasks", "count": len(open_tasks)},
                    {"kind": "active_followups", "count": len(followups)},
                    {"kind": "unresolved_conflicts", "count": len(unresolved_conflicts)},
                ],
                warnings=[
                    *(
                        ["unresolved growth conflicts require steward review"]
                        if unresolved_conflicts
                        else []
                    ),
                    *(
                        ["active follow-ups constrain continuity claims"]
                        if followups
                        else []
                    ),
                ],
            ),
            ContextSection(
                name="steward_inbox",
                status="unified_review_pressure",
                items=[
                    {
                        "inbox_id": item.inbox_id,
                        "type": item.source_type,
                        "severity": item.severity,
                        "status": item.status,
                        "title": item.title,
                        "actions": ",".join(item.recommended_actions),
                    }
                    for item in inbox_items[:8]
                ],
                warnings=[
                    f"{len(inbox_items)} steward inbox item(s) need review"
                    for _ in [None]
                    if inbox_items
                ],
            ),
            ContextSection(
                name="recovery",
                status="current",
                items=[
                    current_recovery.to_dict()
                    if current_recovery is not None
                    else {"status": "none"}
                ],
            ),
            ContextSection(
                name="recent_turns",
                status="hashed_chat_history",
                items=_recent_turn_items(events, recent_turn_limit),
            ),
            *mission_sections,
        ],
    )
    return context


def _mission_context_sections(
    events: list[ContinuityEvent],
    mission_id: str | None,
) -> list[ContextSection]:
    briefs = mission_briefs_from_events(events)
    flows = {flow.mission_id: flow for flow in mission_flows_from_events(events)}
    selected = [
        brief
        for brief in briefs
        if mission_id is None or brief.mission.mission_id == mission_id
    ]
    if mission_id is not None and not selected:
        return [
            ContextSection(
                name="mission",
                status="missing",
                warnings=[f"mission not found: {mission_id}"],
            )
        ]
    mission_items = []
    for brief in selected[-5:]:
        flow = flows.get(brief.mission.mission_id)
        mission_items.append(
            {
                "mission_id": brief.mission.mission_id,
                "title": brief.mission.title,
                "status": brief.mission.status.value,
                "phase": flow.phase.value if flow else "unknown",
                "next_action": flow.next_action if flow else "",
                "items": len(brief.items),
                "evidence_links": len(
                    evidence_for_target(events, "mission", brief.mission.mission_id)
                ),
            }
        )
    steps = [
        step
        for step in mission_step_records_from_events(events)
        if mission_id is None or step.mission_id == mission_id
    ]
    skill_suggestions = (
        skill_suggestions_for_mission(events, mission_id)
        if mission_id is not None
        else []
    )
    return [
        ContextSection(
            name="missions",
            status="active_state",
            items=mission_items,
        ),
        ContextSection(
            name="mission_steps",
            status="approval_gated",
            items=[
                {
                    "step_id": step.step_id,
                    "mission_id": step.mission_id,
                    "risk": step.risk_level.value,
                    "tool": step.required_tool,
                    "approval": step.approval_status.value,
                    "execution": step.execution_status.value,
                }
                for step in steps[-8:]
            ],
            warnings=[
                "medium/high-risk steps require approval before execution"
                for step in steps
                if step.approval_status.value == "pending"
            ][:1],
        ),
        ContextSection(
            name="skill_suggestions",
            status="accepted_skills_only",
            items=[
                {
                    "skill_id": suggestion["skill"]["skill_id"],
                    "name": suggestion["skill"]["name"],
                    "tool": suggestion["skill"]["required_tool"],
                    "risk": suggestion["skill"]["risk_level"],
                    "matching_steps": len(suggestion["matching_step_ids"]),
                }
                for suggestion in skill_suggestions
            ],
        ),
    ]


def _evidence_warnings(snapshot: dict[str, Any]) -> list[str]:
    warnings = []
    if snapshot["disputed_count"]:
        warnings.append("disputed evidence must not be treated as settled")
    if snapshot["stale_count"]:
        warnings.append("stale evidence needs review before strong reliance")
    if snapshot["rejected_count"]:
        warnings.append("rejected evidence must not support claims")
    return warnings


def _unresolved_conflicts(events: list[ContinuityEvent]):
    resolutions = growth_conflict_resolution_records_from_events(events)
    resolved_ids = {record.conflict_id for record in resolutions}
    return [
        record
        for record in growth_conflict_records_from_events(events)
        if record.conflict_id not in resolved_ids
    ]


def _recent_turn_items(
    events: list[ContinuityEvent],
    limit: int,
) -> list[dict[str, Any]]:
    turns = [
        event.payload
        for event in events
        if event.event_type == "lucien.chat_turn_recorded"
    ]
    return [
        {
            "session_id": turn.get("session_id"),
            "turn_index": turn.get("turn_index"),
            "output_allowed": turn.get("output_allowed"),
            "continuity_claim": turn.get("continuity_claim"),
            "growth_events": len(turn.get("growth_event_ids", [])),
        }
        for turn in turns[-limit:]
    ]

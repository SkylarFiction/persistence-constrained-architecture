from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .growth import active_growth_records
from .growth_conflicts import (
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
)
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .memory_cards import memory_cards_from_events
from .state import derive_current_claim


@dataclass(frozen=True)
class ReflectionRecord:
    reflection_id: str
    identity_id: str
    continuity_claim: str
    focus: str
    severity: str
    observations: list[str]
    recommended_actions: list[str]
    source_event_ids: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        identity_id: str,
        continuity_claim: str,
        focus: str,
        severity: str,
        observations: list[str],
        recommended_actions: list[str],
        source_event_ids: list[str] | None = None,
    ) -> "ReflectionRecord":
        return cls(
            reflection_id=f"reflection_{uuid.uuid4()}",
            identity_id=identity_id,
            continuity_claim=continuity_claim,
            focus=focus,
            severity=severity,
            observations=observations,
            recommended_actions=recommended_actions,
            source_event_ids=source_event_ids or [],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReflectionRecord":
        return cls(
            reflection_id=str(data["reflection_id"]),
            identity_id=str(data["identity_id"]),
            continuity_claim=str(data["continuity_claim"]),
            focus=str(data["focus"]),
            severity=str(data["severity"]),
            observations=[str(item) for item in data.get("observations", [])],
            recommended_actions=[
                str(item) for item in data.get("recommended_actions", [])
            ],
            source_event_ids=[str(item) for item in data.get("source_event_ids", [])],
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reflection_id": self.reflection_id,
            "identity_id": self.identity_id,
            "continuity_claim": self.continuity_claim,
            "focus": self.focus,
            "severity": self.severity,
            "observations": self.observations,
            "recommended_actions": self.recommended_actions,
            "source_event_ids": self.source_event_ids,
            "created_at": self.created_at,
        }


def build_reflection(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> ReflectionRecord:
    events = ledger.events()
    claim = derive_current_claim(ledger, manifest)[0]
    active_growth = active_growth_records(events)
    resolved_conflict_ids = {
        resolution.conflict_id
        for resolution in growth_conflict_resolution_records_from_events(events)
    }
    conflicts = [
        conflict
        for conflict in growth_conflict_records_from_events(events)
        if conflict.conflict_id not in resolved_conflict_ids
    ]
    memory_cards = memory_cards_from_events(events, manifest.system_id)
    observations: list[str] = []
    recommended_actions: list[str] = []
    source_event_ids: list[str] = []

    if claim != "certified_continuity":
        observations.append(f"continuity claim is {claim}")
        recommended_actions.append("resolve continuity blockers before accepting high-impact growth")

    if active_growth:
        observations.append(f"{len(active_growth)} growth record(s) await review")
        recommended_actions.append("review pending growth records")
        source_event_ids.extend(_growth_event_ids(events, [record.growth_id for record in active_growth]))

    if conflicts:
        observations.append(f"{len(conflicts)} growth conflict(s) require steward attention")
        recommended_actions.append("resolve growth conflicts before accepting related changes")
        source_event_ids.extend(_event_hashes(events, "lucien.growth_conflict_detected"))

    weak_cards = [
        card
        for card in memory_cards
        if (
            card.effective_confidence < 0.75
            or card.contradiction_count > 0
            or card.stale_signal_count > 0
        )
    ]
    if weak_cards:
        observations.append(f"{len(weak_cards)} memory card(s) need confidence review")
        recommended_actions.append("review contradicted or low-confidence memory cards")
        source_event_ids.extend(_event_hashes(events, "lucien.memory_signal_recorded"))

    if not observations:
        observations.append("no active continuity, growth, or memory review pressure detected")
        recommended_actions.append("continue governed learning")

    return ReflectionRecord.create(
        identity_id=manifest.system_id,
        continuity_claim=claim,
        focus=_reflection_focus(
            has_conflicts=bool(conflicts),
            has_active_growth=bool(active_growth),
            weak_memory_count=len(weak_cards),
            claim=claim,
        ),
        severity=_reflection_severity(
            has_conflicts=bool(conflicts),
            has_active_growth=bool(active_growth),
            weak_memory_count=len(weak_cards),
            claim=claim,
        ),
        observations=observations,
        recommended_actions=_dedupe(recommended_actions),
        source_event_ids=_dedupe(source_event_ids),
    )


def record_reflection(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> ReflectionRecord:
    record = build_reflection(ledger, manifest)
    ledger.append("lucien.reflection_recorded", manifest.system_id, record.to_dict())
    return record


def reflection_records_from_events(
    events: list[ContinuityEvent],
) -> list[ReflectionRecord]:
    return [
        ReflectionRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.reflection_recorded"
    ]


def _reflection_focus(
    has_conflicts: bool,
    has_active_growth: bool,
    weak_memory_count: int,
    claim: str,
) -> str:
    if claim == "continuity_break":
        return "continuity_recovery"
    if has_conflicts:
        return "growth_conflict_resolution"
    if has_active_growth:
        return "growth_review"
    if weak_memory_count:
        return "memory_confidence_review"
    if claim != "certified_continuity":
        return "continuity_review"
    return "steady_learning"


def _reflection_severity(
    has_conflicts: bool,
    has_active_growth: bool,
    weak_memory_count: int,
    claim: str,
) -> str:
    if claim == "continuity_break":
        return "critical"
    if claim in {"uncertified_continuity", "declared_fork"}:
        return "high"
    if has_conflicts or weak_memory_count:
        return "review_required"
    if has_active_growth or claim == "review_required":
        return "watch"
    return "stable"


def _growth_event_ids(events: list[ContinuityEvent], growth_ids: list[str]) -> list[str]:
    wanted = set(growth_ids)
    return [
        event.event_hash
        for event in events
        if event.event_type in {"lucien.growth_proposed", "lucien.growth_updated"}
        and event.payload.get("growth_id") in wanted
    ]


def _event_hashes(events: list[ContinuityEvent], event_type: str) -> list[str]:
    return [event.event_hash for event in events if event.event_type == event_type]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

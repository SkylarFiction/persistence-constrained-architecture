from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .growth import GrowthKind, GrowthRecord, GrowthStatus, growth_records_from_events
from .ledger import ContinuityEvent


@dataclass(frozen=True)
class SelfModel:
    identity_id: str
    accepted_growth_count: int
    by_kind: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity_id": self.identity_id,
            "accepted_growth_count": self.accepted_growth_count,
            "by_kind": self.by_kind,
        }


def derive_self_model(events: list[ContinuityEvent], identity_id: str) -> SelfModel:
    accepted = [
        record
        for record in growth_records_from_events(events)
        if record.identity_id == identity_id and record.status == GrowthStatus.ACCEPTED
    ]
    by_kind: dict[str, list[dict[str, Any]]] = {
        kind.value: [] for kind in GrowthKind
    }
    for record in accepted:
        by_kind[record.kind.value].append(_self_model_item(record))
    return SelfModel(
        identity_id=identity_id,
        accepted_growth_count=len(accepted),
        by_kind=by_kind,
    )


def compile_self_model(self_model: SelfModel) -> str:
    lines = [
        "Lucien Self-Model",
        "",
        f"Identity: {self_model.identity_id}",
        f"Accepted growth records: {self_model.accepted_growth_count}",
        "",
    ]
    labels = {
        "memory": "Memory",
        "skill": "Skills",
        "preference": "Preferences",
        "commitment": "Commitments",
        "policy": "Policies",
        "identity": "Identity",
    }
    for kind, label in labels.items():
        lines.append(f"{label}:")
        records = self_model.by_kind.get(kind, [])
        if not records:
            lines.append("- none")
        for record in records:
            refs = ", ".join(record["evidence_refs"]) or "no external refs"
            lines.append(
                "- "
                f"{record['growth_id']} "
                f"impact={record['identity_impact']} "
                f"summary_hash={_short_hash(str(record['summary_sha256']))} "
                f"length={record['summary_length']} "
                f"evidence={refs} "
                f"reason={record['reason'] or 'not specified'}"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _self_model_item(record: GrowthRecord) -> dict[str, Any]:
    return {
        "growth_id": record.growth_id,
        "summary_sha256": record.summary_sha256,
        "summary_length": record.summary_length,
        "identity_impact": record.identity_impact.value,
        "evidence_refs": record.evidence_refs,
        "source_event_ids": record.source_event_ids,
        "accepted_at": record.updated_at or record.created_at,
        "acceptance_continuity_claim": record.acceptance_continuity_claim,
        "reason": record.reason,
    }


def _short_hash(value: str) -> str:
    if len(value) <= 12:
        return value
    return f"{value[:12]}..."

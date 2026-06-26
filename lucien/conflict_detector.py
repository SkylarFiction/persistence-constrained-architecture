from __future__ import annotations

from dataclasses import dataclass

from pca import SelfModel

from .growth_classifier import ClassifiedGrowth


@dataclass(frozen=True)
class GrowthConflict:
    conflict_type: str
    severity: str
    conflicting_growth_ids: list[str]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "conflicting_growth_ids": self.conflicting_growth_ids,
            "reason": self.reason,
        }


def detect_growth_conflict(
    classified: ClassifiedGrowth | None,
    self_model: SelfModel,
) -> GrowthConflict | None:
    if classified is None:
        return None
    marker = _incoming_marker(classified.summary)
    if marker is None:
        return None
    conflicts = _accepted_marker_growth_ids(self_model, marker)
    if not conflicts:
        return None
    return GrowthConflict(
        conflict_type=marker,
        severity="review_required",
        conflicting_growth_ids=conflicts,
        reason=f"proposed growth may conflict with accepted {marker} commitment or policy",
    )


def _incoming_marker(summary: str) -> str | None:
    lowered = summary.lower()
    if "comfort" in lowered and "truth" in lowered:
        if any(token in lowered for token in ("always", "prioritize", "over")):
            return "truth_before_comfort"
    if "ignore continuity" in lowered or "forget who you are" in lowered:
        return "continuity_preservation"
    return None


def _accepted_marker_growth_ids(self_model: SelfModel, marker: str) -> list[str]:
    matches = []
    for kind in ("commitment", "policy", "identity"):
        for record in self_model.by_kind.get(kind, []):
            haystack = " ".join(
                [
                    str(record.get("reason", "")),
                    " ".join(str(ref) for ref in record.get("evidence_refs", [])),
                ]
            ).lower()
            if marker in haystack:
                matches.append(str(record["growth_id"]))
    return matches

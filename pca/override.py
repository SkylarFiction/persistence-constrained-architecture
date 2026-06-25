from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .policy import ContinuityStatus, PolicyDecision, TransformEvaluation


@dataclass(frozen=True)
class OverrideRequest:
    transform: str
    authority: str
    reason: str
    required_followup: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OverrideRecord:
    transform: str
    original_decision: PolicyDecision
    override_requested: bool
    override_authority: str
    override_reason: str
    operation_permitted: bool
    continuity_status_after_override: ContinuityStatus
    required_followup: list[str]
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transform": self.transform,
            "original_decision": self.original_decision.value,
            "override_requested": self.override_requested,
            "override_authority": self.override_authority,
            "override_reason": self.override_reason,
            "operation_permitted": self.operation_permitted,
            "continuity_status_after_override": (
                self.continuity_status_after_override.value
            ),
            "required_followup": self.required_followup,
            "reason": self.reason,
            "metadata": self.metadata,
        }


class OverrideEngine:
    def request_override(
        self,
        evaluation: TransformEvaluation,
        request: OverrideRequest,
    ) -> OverrideRecord:
        followup = request.required_followup or self._default_followup(
            request.transform
        )
        return OverrideRecord(
            transform=request.transform,
            original_decision=evaluation.decision,
            override_requested=True,
            override_authority=request.authority,
            override_reason=request.reason,
            operation_permitted=True,
            continuity_status_after_override=ContinuityStatus.UNCERTIFIED,
            required_followup=followup,
            reason=(
                "Override permits the operation but does not certify identity "
                "continuity. A later audit must establish any stronger claim."
            ),
            metadata=request.metadata,
        )

    def _default_followup(self, transform: str) -> list[str]:
        if transform == "substrate_migration":
            return ["post_migration_identity_audit", "lineage_freeze"]
        return ["post_transform_identity_audit", "lineage_freeze"]

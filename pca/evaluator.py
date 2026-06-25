from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .ledger import ContinuityEvent
from .manifest import IdentityManifest


class IdentityState(str, Enum):
    CONTINUOUS = "continuous"
    DEGRADED = "degraded"
    FORKED = "forked"
    SUSPENDED = "suspended"
    BROKEN = "broken"


@dataclass(frozen=True)
class ContinuityEvaluation:
    state: IdentityState
    reasons: list[str]


class ContinuityEvaluator:
    def evaluate(
        self,
        manifest: IdentityManifest,
        events: list[ContinuityEvent],
        chain_valid: bool,
    ) -> ContinuityEvaluation:
        if not chain_valid:
            return ContinuityEvaluation(
                state=IdentityState.SUSPENDED,
                reasons=["continuity ledger hash chain is invalid"],
            )

        if not events:
            return ContinuityEvaluation(
                state=IdentityState.SUSPENDED,
                reasons=["no continuity evidence has been recorded"],
            )

        reasons: list[str] = []
        broken = [
            event
            for event in events
            if event.event_type == "constraint.breached"
            and event.payload.get("severity") == "hard"
        ]
        if broken:
            return ContinuityEvaluation(
                state=IdentityState.BROKEN,
                reasons=[
                    f"hard constraint breached: {event.payload.get('constraint')}"
                    for event in broken
                ],
            )

        latest_by_type = {event.event_type: event for event in events}

        if "identity.forked" in latest_by_type:
            return ContinuityEvaluation(
                state=IdentityState.FORKED,
                reasons=["ledger contains an identity fork event"],
            )

        required_names = {
            constraint.name for constraint in manifest.constraints if constraint.required
        }
        observed_names = {
            event.payload.get("constraint")
            for event in events
            if event.event_type in {"constraint.checked", "constraint.breached"}
        }
        missing = sorted(required_names - observed_names)
        if missing:
            return ContinuityEvaluation(
                state=IdentityState.SUSPENDED,
                reasons=[f"required constraint has no evidence: {name}" for name in missing],
            )

        soft_breaches = [
            event
            for event in events
            if event.event_type == "constraint.breached"
            and event.payload.get("severity") != "hard"
        ]
        if soft_breaches:
            return ContinuityEvaluation(
                state=IdentityState.DEGRADED,
                reasons=[
                    f"soft constraint breached: {event.payload.get('constraint')}"
                    for event in soft_breaches
                ],
            )

        return ContinuityEvaluation(
            state=IdentityState.CONTINUOUS,
            reasons=[f"{manifest.name} satisfies recorded persistence constraints"],
        )

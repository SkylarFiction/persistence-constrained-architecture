from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .ledger import ContinuityEvent
from .manifest import IdentityManifest, PersistenceConstraint


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


EVALUATION_PRECEDENCE = (
    "chain_invalid",
    "no_events",
    "hard_breach",
    "declared_fork",
    "stale_required_evidence",
    "missing_required_evidence",
    "soft_breach",
    "continuous",
)


class ContinuityEvaluator:
    def evaluate(
        self,
        manifest: IdentityManifest,
        events: list[ContinuityEvent],
        chain_valid: bool,
        now: datetime | None = None,
    ) -> ContinuityEvaluation:
        evaluation_time = now or datetime.now(timezone.utc)
        candidates = _evaluation_candidates(
            manifest=manifest,
            events=events,
            chain_valid=chain_valid,
            now=evaluation_time,
        )
        for rule_name in EVALUATION_PRECEDENCE:
            if rule_name in candidates:
                return candidates[rule_name]
        raise RuntimeError("continuity evaluator produced no candidate state")


def _evaluation_candidates(
    manifest: IdentityManifest,
    events: list[ContinuityEvent],
    chain_valid: bool,
    now: datetime,
) -> dict[str, ContinuityEvaluation]:
    candidates: dict[str, ContinuityEvaluation] = {}

    if not chain_valid:
        candidates["chain_invalid"] = ContinuityEvaluation(
            state=IdentityState.SUSPENDED,
            reasons=["continuity ledger hash chain is invalid"],
        )

    if not events:
        candidates["no_events"] = ContinuityEvaluation(
            state=IdentityState.SUSPENDED,
            reasons=["no continuity evidence has been recorded"],
        )
        return candidates

    broken = [
        event
        for event in events
        if event.event_type == "constraint.breached"
        and event.payload.get("severity") == "hard"
    ]
    if broken:
        candidates["hard_breach"] = ContinuityEvaluation(
            state=IdentityState.BROKEN,
            reasons=[
                f"hard constraint breached: {event.payload.get('constraint')}"
                for event in broken
            ],
        )

    if any(event.event_type == "identity.forked" for event in events):
        candidates["declared_fork"] = ContinuityEvaluation(
            state=IdentityState.FORKED,
            reasons=["ledger contains an identity fork event"],
        )

    constraints = {constraint.name: constraint for constraint in manifest.constraints}
    latest_evidence = {
        constraint_name: event
        for constraint_name, event in _latest_constraint_events(events).items()
        if constraint_name is not None
    }

    stale_required = [
        name
        for name, event in latest_evidence.items()
        if constraints.get(name) is not None
        and constraints[name].required
        and _is_stale(constraints[name], event, now)
    ]
    if stale_required:
        candidates["stale_required_evidence"] = ContinuityEvaluation(
            state=IdentityState.SUSPENDED,
            reasons=[
                f"required constraint evidence is stale: {name}"
                for name in sorted(stale_required)
            ],
        )

    missing = sorted(
        constraint.name
        for constraint in manifest.constraints
        if constraint.required and constraint.name not in latest_evidence
    )
    if missing:
        candidates["missing_required_evidence"] = ContinuityEvaluation(
            state=IdentityState.SUSPENDED,
            reasons=[f"required constraint has no evidence: {name}" for name in missing],
        )

    soft_breaches = [
        event
        for event in latest_evidence.values()
        if event.event_type == "constraint.breached"
        and event.payload.get("severity") != "hard"
    ]
    if soft_breaches:
        candidates["soft_breach"] = ContinuityEvaluation(
            state=IdentityState.DEGRADED,
            reasons=[
                f"soft constraint breached: {event.payload.get('constraint')}"
                for event in soft_breaches
            ],
        )

    candidates["continuous"] = ContinuityEvaluation(
        state=IdentityState.CONTINUOUS,
        reasons=[f"{manifest.name} satisfies recorded persistence constraints"],
    )
    return candidates


def _latest_constraint_events(
    events: list[ContinuityEvent],
) -> dict[str | None, ContinuityEvent]:
    latest: dict[str | None, ContinuityEvent] = {}
    for event in events:
        if event.event_type in {"constraint.checked", "constraint.breached"}:
            latest[event.payload.get("constraint")] = event
    return latest


def _is_stale(
    constraint: PersistenceConstraint,
    event: ContinuityEvent,
    now: datetime,
) -> bool:
    if constraint.freshness_seconds is None:
        return False
    timestamp = _parse_timestamp(event.timestamp)
    age = now - timestamp
    return age.total_seconds() > constraint.freshness_seconds


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

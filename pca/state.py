from __future__ import annotations

from .claims import ContinuityClaimRecord, claim_reason, current_claim_record
from .evaluator import ContinuityEvaluator
from .followups import FollowUpRecord, continuity_claim_from_followups
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .recovery import RecoveryStatus, current_recovery_record


def default_claim_for_identity_state(state: str) -> str:
    claims = {
        "continuous": "certified_continuity",
        "degraded": "review_required",
        "forked": "declared_fork",
        "suspended": "review_required",
        "broken": "continuity_break",
    }
    return claims.get(state, "review_required")


def derive_current_claim(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> tuple[str, list[FollowUpRecord], list[str]]:
    events = ledger.events()
    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=ledger.verify_chain(),
    )
    claim, blockers = continuity_claim_from_followups(
        events,
        default_claim_for_identity_state(evaluation.state.value),
    )
    recovery = current_recovery_record(events)
    if recovery is not None:
        if recovery.status == RecoveryStatus.REJECTED:
            claim = "continuity_break"
        elif recovery.status == RecoveryStatus.CERTIFIED and claim == "continuity_break":
            claim = "review_required"
        elif recovery.status in {
            RecoveryStatus.OPENED,
            RecoveryStatus.PLAN_REQUIRED,
            RecoveryStatus.UNDERWAY,
            RecoveryStatus.AUDIT_REQUIRED,
        } and claim == "continuity_break":
            claim = "uncertified_continuity"
    return claim, blockers, evaluation.reasons


def record_claim_if_changed(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    source_event_ids: list[str],
) -> ContinuityClaimRecord | None:
    claim, blockers, reasons = derive_current_claim(ledger, manifest)
    previous = current_claim_record(ledger.events())
    if previous is not None and previous.claim == claim:
        return None
    record = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim=claim,
        source_event_ids=source_event_ids,
        active_blockers=[blocker.followup_id for blocker in blockers],
        supersedes_claim_id=previous.claim_id if previous else None,
        reason=claim_reason(claim, blockers, "; ".join(reasons)),
    )
    ledger.append("continuity_claim_record", manifest.system_id, record.to_dict())
    return record

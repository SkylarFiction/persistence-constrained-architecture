from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evaluator import ContinuityEvaluator
from .followups import active_followups
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .recovery import current_recovery_record
from .report import build_trace_report
from .state import derive_current_claim
from .steward_inbox import steward_inbox


@dataclass(frozen=True)
class ContinuityCertification:
    continuity_claim: str
    identity_state: str
    certifiable: bool
    summary: str
    blockers: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    stale_evidence: list[str] = field(default_factory=list)
    active_obligations: list[str] = field(default_factory=list)
    steward_actions: list[str] = field(default_factory=list)
    raw_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuity_claim": self.continuity_claim,
            "identity_state": self.identity_state,
            "certifiable": self.certifiable,
            "summary": self.summary,
            "blockers": self.blockers,
            "missing_evidence": self.missing_evidence,
            "stale_evidence": self.stale_evidence,
            "active_obligations": self.active_obligations,
            "steward_actions": self.steward_actions,
            "raw_reasons": self.raw_reasons,
        }


def continuity_certification(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> ContinuityCertification:
    events = ledger.events()
    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=ledger.verify_chain(),
    )
    claim, blocking_followups, reasons = derive_current_claim(ledger, manifest)
    report = build_trace_report(ledger, manifest)
    missing = _missing_from_reasons(reasons)
    stale = _stale_from_reasons(reasons)
    obligations = [
        f"{followup.followup_id}: {followup.followup_type}"
        for followup in active_followups(events)
    ]
    obligations.extend(
        f"{followup.followup_id}: blocking {followup.followup_type}"
        for followup in blocking_followups
        if followup.followup_id not in {item.split(':', 1)[0] for item in obligations}
    )
    current_recovery = current_recovery_record(events)
    if current_recovery is not None and current_recovery.status.value not in {
        "certified",
        "rejected",
    }:
        obligations.append(
            f"{current_recovery.recovery_id}: recovery {current_recovery.status.value}"
        )
    inbox_items = steward_inbox(ledger)
    blockers = _blockers(
        chain_valid=ledger.verify_chain(),
        claim=claim,
        reasons=reasons,
        obligations=obligations,
        inbox_count=len(inbox_items),
        policy_error_count=int(report.summary.get("policy_error_count", 0) or 0),
    )
    certifiable = (
        claim == "certified_continuity"
        and evaluation.state.value == "continuous"
        and not blockers
        and not missing
        and not stale
        and not obligations
    )
    actions = _steward_actions(
        certifiable=certifiable,
        missing=missing,
        stale=stale,
        obligations=obligations,
        inbox_count=len(inbox_items),
        claim=claim,
    )
    return ContinuityCertification(
        continuity_claim=claim,
        identity_state=evaluation.state.value,
        certifiable=certifiable,
        summary=(
            "Continuity can currently be certified."
            if certifiable
            else "Continuity cannot currently be certified."
        ),
        blockers=blockers,
        missing_evidence=missing,
        stale_evidence=stale,
        active_obligations=obligations,
        steward_actions=actions,
        raw_reasons=reasons,
    )


def render_continuity_certification_text(certification: ContinuityCertification) -> str:
    data = certification.to_dict()
    lines = [
        "Continuity Certification",
        f"Certifiable: {data['certifiable']}",
        f"Claim: {data['continuity_claim']}",
        f"Identity state: {data['identity_state']}",
        data["summary"],
        "",
        "Blockers:",
    ]
    lines.extend(f"- {item}" for item in data["blockers"] or ["none"])
    lines.extend(["", "Missing evidence:"])
    lines.extend(f"- {item}" for item in data["missing_evidence"] or ["none"])
    lines.extend(["", "Stale evidence:"])
    lines.extend(f"- {item}" for item in data["stale_evidence"] or ["none"])
    lines.extend(["", "Steward actions:"])
    lines.extend(f"- {item}" for item in data["steward_actions"] or ["none"])
    return "\n".join(lines)


def _missing_from_reasons(reasons: list[str]) -> list[str]:
    prefix = "required constraint has no evidence: "
    return sorted(reason.removeprefix(prefix) for reason in reasons if reason.startswith(prefix))


def _stale_from_reasons(reasons: list[str]) -> list[str]:
    prefix = "required constraint evidence is stale: "
    return sorted(reason.removeprefix(prefix) for reason in reasons if reason.startswith(prefix))


def _blockers(
    *,
    chain_valid: bool,
    claim: str,
    reasons: list[str],
    obligations: list[str],
    inbox_count: int,
    policy_error_count: int,
) -> list[str]:
    blockers: list[str] = []
    if not chain_valid:
        blockers.append("ledger hash chain is invalid")
    if claim != "certified_continuity":
        blockers.append(f"continuity claim is {claim}")
    blockers.extend(
        reason
        for reason in reasons
        if reason not in blockers and not _positive_reason(reason)
    )
    blockers.extend(obligations)
    if inbox_count:
        blockers.append(f"{inbox_count} steward inbox item(s) require review")
    if policy_error_count:
        blockers.append(f"{policy_error_count} policy error(s) must be repaired")
    return blockers


def _positive_reason(reason: str) -> bool:
    return "satisfies recorded persistence constraints" in reason


def _steward_actions(
    *,
    certifiable: bool,
    missing: list[str],
    stale: list[str],
    obligations: list[str],
    inbox_count: int,
    claim: str,
) -> list[str]:
    if certifiable:
        return ["No certification action required."]
    actions: list[str] = []
    for name in missing:
        actions.append(f"Record required constraint evidence for {name}.")
    for name in stale:
        actions.append(f"Refresh required constraint evidence for {name}.")
    if obligations:
        actions.append("Resolve active follow-ups or recovery obligations.")
    if inbox_count:
        actions.append("Review or dismiss open Steward Inbox items.")
    if claim == "continuity_break":
        actions.append("Open or complete a governed recovery path.")
    return actions or ["Inspect raw continuity reasons and record the missing proof."]

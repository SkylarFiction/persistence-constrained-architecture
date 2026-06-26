from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .manifest import IdentityManifest


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


class IdentityRisk(str, Enum):
    LOW = "low_identity_risk"
    MEDIUM = "medium_identity_risk"
    HIGH = "high_identity_risk"
    CONTINUITY_BREAK = "continuity_break"


class ContinuityStatus(str, Enum):
    CERTIFIED = "certified_continuity"
    REVIEW_REQUIRED = "review_required"
    UNCERTIFIED = "uncertified_continuity"
    DECLARED_FORK = "declared_fork"
    BREAK = "continuity_break"


@dataclass(frozen=True)
class TransformPolicy:
    name: str
    decision: PolicyDecision = PolicyDecision.REVIEW
    required_evidence: list[str] = field(default_factory=list)
    identity_risk: IdentityRisk = IdentityRisk.MEDIUM
    missing_evidence_decision: PolicyDecision = PolicyDecision.REVIEW
    deny_if_missing: list[str] = field(default_factory=list)
    review_if_missing: list[str] = field(default_factory=list)
    override_allowed: bool = True
    override_result_claim: ContinuityStatus = ContinuityStatus.UNCERTIFIED
    required_followups_on_override: list[str] = field(default_factory=list)
    audit_type: str = ""
    source_policy_pack: str = "manifest"
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TransformPolicy":
        raw_decision = data.get("decision", PolicyDecision.REVIEW.value)
        raw_risk = data.get("identity_risk", IdentityRisk.MEDIUM.value)
        raw_missing_decision = data.get(
            "missing_evidence_decision", PolicyDecision.REVIEW.value
        )
        raw_override_claim = data.get(
            "override_result_claim", ContinuityStatus.UNCERTIFIED.value
        )
        return cls(
            name=str(data["name"]),
            decision=PolicyDecision(raw_decision),
            required_evidence=[
                str(item) for item in data.get("required_evidence", [])
            ],
            identity_risk=IdentityRisk(raw_risk),
            missing_evidence_decision=PolicyDecision(raw_missing_decision),
            deny_if_missing=[str(item) for item in data.get("deny_if_missing", [])],
            review_if_missing=[
                str(item) for item in data.get("review_if_missing", [])
            ],
            override_allowed=bool(data.get("override_allowed", True)),
            override_result_claim=ContinuityStatus(raw_override_claim),
            required_followups_on_override=[
                str(item) for item in data.get("required_followups_on_override", [])
            ],
            audit_type=str(data.get("audit_type", "")),
            source_policy_pack=str(data.get("source_policy_pack", "manifest")),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "decision": self.decision.value,
            "required_evidence": self.required_evidence,
            "identity_risk": self.identity_risk.value,
            "missing_evidence_decision": self.missing_evidence_decision.value,
            "deny_if_missing": self.deny_if_missing,
            "review_if_missing": self.review_if_missing,
            "override_allowed": self.override_allowed,
            "override_result_claim": self.override_result_claim.value,
            "required_followups_on_override": self.required_followups_on_override,
            "audit_type": self.audit_type,
            "source_policy_pack": self.source_policy_pack,
            "description": self.description,
        }


@dataclass(frozen=True)
class TransformRequest:
    transform: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransformEvaluation:
    decision: PolicyDecision
    reasons: list[str]
    provided_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    identity_risk: IdentityRisk = IdentityRisk.MEDIUM
    reason: str = ""
    continuity_status: ContinuityStatus = ContinuityStatus.REVIEW_REQUIRED
    source_policy_pack: str = ""
    override_allowed: bool = False
    required_followups_on_override: list[str] = field(default_factory=list)
    audit_type: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "provided_evidence": self.provided_evidence,
            "missing_evidence": self.missing_evidence,
            "identity_risk": self.identity_risk.value,
            "continuity_status": self.continuity_status.value,
            "source_policy_pack": self.source_policy_pack,
            "override_allowed": self.override_allowed,
            "required_followups_on_override": self.required_followups_on_override,
            "audit_type": self.audit_type,
            "reason": self.reason,
            "reasons": self.reasons,
        }


class PolicyEngine:
    def evaluate_transform(
        self,
        manifest: IdentityManifest,
        request: TransformRequest,
    ) -> TransformEvaluation:
        if manifest.policy_errors:
            return TransformEvaluation(
                decision=PolicyDecision.DENY,
                reasons=[
                    f"policy set invalid: {error}"
                    for error in manifest.policy_errors
                ],
                provided_evidence=sorted(request.evidence),
                identity_risk=IdentityRisk.CONTINUITY_BREAK,
                continuity_status=ContinuityStatus.UNCERTIFIED,
                source_policy_pack="invalid_policy",
                override_allowed=False,
                reason=(
                    "Policy pack loading failed; identity-changing transforms "
                    "fail closed until policy errors are resolved."
                ),
            )

        policy = manifest.transform_policy(request.transform)
        if policy is None:
            return TransformEvaluation(
                decision=PolicyDecision.DENY,
                reasons=[f"transform is not declared: {request.transform}"],
                provided_evidence=sorted(request.evidence),
                identity_risk=IdentityRisk.CONTINUITY_BREAK,
                continuity_status=ContinuityStatus.BREAK,
                source_policy_pack="none",
                override_allowed=False,
                reason=(
                    "Undeclared transforms cannot claim identity continuity because "
                    "no persistence policy governs their effect."
                ),
            )

        missing = [
            item for item in policy.required_evidence if item not in request.evidence
        ]
        if missing:
            decision = self._decision_for_missing_evidence(policy, missing)
            return TransformEvaluation(
                decision=decision,
                reasons=[f"transform requires evidence: {', '.join(missing)}"],
                provided_evidence=sorted(request.evidence),
                missing_evidence=missing,
                identity_risk=policy.identity_risk,
                continuity_status=self._status_for_missing_evidence(policy, decision),
                source_policy_pack=policy.source_policy_pack,
                override_allowed=policy.override_allowed,
                required_followups_on_override=policy.required_followups_on_override,
                audit_type=policy.audit_type,
                reason=(
                    f"{policy.name} may alter identity continuity without verified "
                    f"evidence: {', '.join(missing)}."
                ),
            )

        return TransformEvaluation(
            decision=policy.decision,
            reasons=[f"transform policy matched: {policy.name}"],
            provided_evidence=sorted(request.evidence),
            identity_risk=policy.identity_risk,
            continuity_status=self._status_for_complete_policy(policy),
            source_policy_pack=policy.source_policy_pack,
            override_allowed=policy.override_allowed,
            required_followups_on_override=policy.required_followups_on_override,
            audit_type=policy.audit_type,
            reason=policy.description,
        )

    def _decision_for_missing_evidence(
        self,
        policy: TransformPolicy,
        missing: list[str],
    ) -> PolicyDecision:
        if any(item in set(policy.deny_if_missing) for item in missing):
            return PolicyDecision.DENY
        if any(item in set(policy.review_if_missing) for item in missing):
            return PolicyDecision.REVIEW
        return policy.missing_evidence_decision

    def _status_for_missing_evidence(
        self,
        policy: TransformPolicy,
        decision: PolicyDecision,
    ) -> ContinuityStatus:
        if decision == PolicyDecision.DENY:
            return ContinuityStatus.UNCERTIFIED
        return ContinuityStatus.REVIEW_REQUIRED

    def _status_for_complete_policy(
        self,
        policy: TransformPolicy,
    ) -> ContinuityStatus:
        if policy.name == "declared_fork":
            return ContinuityStatus.DECLARED_FORK
        if policy.identity_risk == IdentityRisk.CONTINUITY_BREAK:
            return ContinuityStatus.BREAK
        if policy.decision == PolicyDecision.ALLOW:
            return ContinuityStatus.CERTIFIED
        if policy.decision == PolicyDecision.DENY:
            return ContinuityStatus.UNCERTIFIED
        return ContinuityStatus.REVIEW_REQUIRED

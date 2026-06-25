from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from .authorization import AuthorizationPolicy
from .manifest import IdentityManifest
from .policy import ContinuityStatus, IdentityRisk, PolicyDecision, TransformPolicy


RISK_ORDER = {
    IdentityRisk.LOW: 0,
    IdentityRisk.MEDIUM: 1,
    IdentityRisk.HIGH: 2,
    IdentityRisk.CONTINUITY_BREAK: 3,
}
DECISION_ORDER = {
    PolicyDecision.ALLOW: 0,
    PolicyDecision.REVIEW: 1,
    PolicyDecision.DENY: 2,
}


def load_policy_pack(path: str | Path) -> dict[str, Any]:
    pack_path = Path(path)
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    validate_policy_pack(pack, str(pack_path))
    return pack


def load_policy_directory(path: str | Path) -> list[dict[str, Any]]:
    directory = Path(path)
    return [
        load_policy_pack(pack_path)
        for pack_path in sorted(directory.glob("*.json"))
    ]


def validate_policy_pack(pack: dict[str, Any], source: str = "<memory>") -> None:
    if "pack_id" not in pack:
        raise ValueError(f"Policy pack missing pack_id: {source}")
    if "transforms" not in pack:
        raise ValueError(f"Policy pack missing transforms: {source}")
    if not isinstance(pack["transforms"], dict):
        raise ValueError(f"Policy pack transforms must be an object: {source}")
    for transform, rules in pack["transforms"].items():
        if not isinstance(rules, dict):
            raise ValueError(f"Rules for {transform} must be an object: {source}")
        for key in ["required_evidence", "deny_if_missing", "review_if_missing"]:
            if key in rules and not isinstance(rules[key], list):
                raise ValueError(f"{transform}.{key} must be a list: {source}")


def merge_policy_packs(packs: list[dict[str, Any]]) -> list[TransformPolicy]:
    merged: dict[str, TransformPolicy] = {}
    for pack in packs:
        pack_id = str(pack["pack_id"])
        for transform, rules in pack["transforms"].items():
            policy = _policy_from_pack_rules(pack_id, str(transform), rules)
            if transform not in merged:
                merged[str(transform)] = policy
            else:
                merged[str(transform)] = _merge_transform_policy(
                    merged[str(transform)],
                    policy,
                )
    return list(merged.values())


def build_manifest_from_packs(
    base_manifest: IdentityManifest,
    packs: list[dict[str, Any]],
) -> IdentityManifest:
    pack_policies = merge_policy_packs(packs)
    return replace(
        base_manifest,
        allowed_transforms=[policy.name for policy in pack_policies],
        transform_policies=pack_policies,
    )


def authorization_policy_from_packs(
    packs: list[dict[str, Any]],
) -> AuthorizationPolicy:
    policy = AuthorizationPolicy()
    for pack in packs:
        if "authorization" in pack:
            policy = AuthorizationPolicy.from_dict(pack["authorization"])
    return policy


def _policy_from_pack_rules(
    pack_id: str,
    transform: str,
    rules: dict[str, Any],
) -> TransformPolicy:
    deny_if_missing = [str(item) for item in rules.get("deny_if_missing", [])]
    review_if_missing = [str(item) for item in rules.get("review_if_missing", [])]
    missing_decision = (
        PolicyDecision.DENY if deny_if_missing else PolicyDecision.REVIEW
    )
    return TransformPolicy(
        name=transform,
        decision=PolicyDecision.ALLOW,
        required_evidence=[
            str(item) for item in rules.get("required_evidence", [])
        ],
        identity_risk=IdentityRisk(
            str(rules.get("identity_risk", IdentityRisk.MEDIUM.value))
        ),
        missing_evidence_decision=missing_decision,
        deny_if_missing=deny_if_missing,
        review_if_missing=review_if_missing,
        override_allowed=bool(rules.get("override_allowed", False)),
        override_result_claim=ContinuityStatus(
            str(rules.get("override_result_claim", ContinuityStatus.UNCERTIFIED.value))
        ),
        required_followups_on_override=[
            str(item) for item in rules.get("required_followups_on_override", [])
        ],
        audit_type=str(rules.get("audit_type", "")),
        source_policy_pack=pack_id,
        description=str(rules.get("description", "")),
    )


def _merge_transform_policy(
    left: TransformPolicy,
    right: TransformPolicy,
) -> TransformPolicy:
    source_policy_pack = ",".join(
        sorted({left.source_policy_pack, right.source_policy_pack})
    )
    return TransformPolicy(
        name=left.name,
        decision=_stricter_decision(left.decision, right.decision),
        required_evidence=_union(left.required_evidence, right.required_evidence),
        identity_risk=_stricter_risk(left.identity_risk, right.identity_risk),
        missing_evidence_decision=_stricter_decision(
            left.missing_evidence_decision,
            right.missing_evidence_decision,
        ),
        deny_if_missing=_union(left.deny_if_missing, right.deny_if_missing),
        review_if_missing=_union(left.review_if_missing, right.review_if_missing),
        override_allowed=left.override_allowed and right.override_allowed,
        override_result_claim=left.override_result_claim,
        required_followups_on_override=_union(
            left.required_followups_on_override,
            right.required_followups_on_override,
        ),
        audit_type=left.audit_type or right.audit_type,
        source_policy_pack=source_policy_pack,
        description=left.description or right.description,
    )


def _union(left: list[str], right: list[str]) -> list[str]:
    return sorted({*left, *right})


def _stricter_decision(
    left: PolicyDecision,
    right: PolicyDecision,
) -> PolicyDecision:
    return left if DECISION_ORDER[left] >= DECISION_ORDER[right] else right


def _stricter_risk(left: IdentityRisk, right: IdentityRisk) -> IdentityRisk:
    return left if RISK_ORDER[left] >= RISK_ORDER[right] else right

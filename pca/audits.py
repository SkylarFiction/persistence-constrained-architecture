from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class AuditOutcome(str, Enum):
    CERTIFY_CONTINUITY = "certify_continuity"
    REMAIN_UNCERTIFIED = "remain_uncertified"
    MARK_CONTINUITY_BREAK = "mark_continuity_break"
    REQUIRE_REVIEW = "require_review"


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    identity_id: str
    source_transform_event_id: str
    audit_type: str
    before_evidence: dict[str, str] = field(default_factory=dict)
    after_evidence: dict[str, str] = field(default_factory=dict)
    required_checks: list[str] = field(default_factory=list)
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    outcome: AuditOutcome = AuditOutcome.REQUIRE_REVIEW
    reason: str = ""
    satisfies_followup_id: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "identity_id": self.identity_id,
            "source_transform_event_id": self.source_transform_event_id,
            "audit_type": self.audit_type,
            "before_evidence": self.before_evidence,
            "after_evidence": self.after_evidence,
            "required_checks": self.required_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "satisfies_followup_id": self.satisfies_followup_id,
            "created_at": self.created_at,
        }


class AuditEngine:
    def run_audit(
        self,
        identity_id: str,
        audit_type: str,
        evidence: dict[str, str],
        source_transform_event_id: str,
        followup_id: str | None = None,
    ) -> AuditRecord:
        normalized_type = normalize_audit_type(audit_type)
        required_checks = required_checks_for_audit(normalized_type)
        passed_checks = [
            check
            for check in required_checks
            if _evidence_passed(check, evidence)
        ]
        failed_checks = [
            check
            for check in required_checks
            if _evidence_failed(check, evidence)
        ]
        missing_checks = [
            check
            for check in required_checks
            if check not in evidence
            and not _alternative_passed(check, evidence, normalized_type)
        ]

        outcome = AuditOutcome.REMAIN_UNCERTIFIED
        reason = "Audit evidence is incomplete; continuity remains uncertified."

        if failed_checks:
            outcome = AuditOutcome.MARK_CONTINUITY_BREAK
            reason = (
                "Audit found failed identity-continuity checks: "
                + ", ".join(failed_checks)
            )
        elif not missing_checks and _audit_complete(normalized_type, evidence):
            outcome = AuditOutcome.CERTIFY_CONTINUITY
            reason = "All required audit checks passed."
        elif _has_any_required_evidence(required_checks, evidence):
            outcome = AuditOutcome.REMAIN_UNCERTIFIED
            reason = (
                "Some audit evidence was provided, but continuity was not fully "
                "established."
            )

        return AuditRecord(
            audit_id=f"audit_{uuid.uuid4()}",
            identity_id=identity_id,
            source_transform_event_id=source_transform_event_id,
            audit_type=normalized_type,
            after_evidence=evidence,
            required_checks=required_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks or missing_checks,
            outcome=outcome,
            reason=reason,
            satisfies_followup_id=followup_id,
        )


def normalize_audit_type(audit_type: str) -> str:
    if audit_type.endswith("_audit"):
        return audit_type
    return f"{audit_type}_audit"


def required_checks_for_audit(audit_type: str) -> list[str]:
    checks = {
        "memory_compaction_audit": ["retention_report", "commitment_diff"],
        "substrate_migration_audit": [
            "continuity_proof",
            "state_hash_match",
            "operator_attestation",
        ],
        "fork_audit": ["lineage_record", "parent_child_boundary"],
        "version_update_audit": ["changelog", "compatibility_report"],
        "recovery_audit": ["recovery_plan", "recovery_audit_report"],
    }
    return checks.get(audit_type, ["audit_report"])


def _audit_complete(audit_type: str, evidence: dict[str, str]) -> bool:
    required_checks = required_checks_for_audit(audit_type)
    if audit_type == "substrate_migration_audit":
        return (
            _evidence_passed("continuity_proof", evidence)
            and (
                _evidence_passed("state_hash_match", evidence)
                or _evidence_passed("acceptable_state_diff", evidence)
            )
            and _evidence_passed("operator_attestation", evidence)
        )
    return all(_evidence_passed(check, evidence) for check in required_checks)


def _alternative_passed(
    check: str,
    evidence: dict[str, str],
    audit_type: str,
) -> bool:
    if audit_type == "substrate_migration_audit" and check == "state_hash_match":
        return _evidence_passed("acceptable_state_diff", evidence)
    return False


def _has_any_required_evidence(
    required_checks: list[str],
    evidence: dict[str, str],
) -> bool:
    return any(check in evidence for check in required_checks)


def _evidence_passed(check: str, evidence: dict[str, str]) -> bool:
    return evidence.get(check, "").lower() in {"ok", "passed", "pass", "true", "yes"}


def _evidence_failed(check: str, evidence: dict[str, str]) -> bool:
    return evidence.get(check, "").lower() in {
        "bad",
        "failed",
        "fail",
        "false",
        "mismatch",
        "no",
    }

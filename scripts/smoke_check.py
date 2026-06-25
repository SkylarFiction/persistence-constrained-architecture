from __future__ import annotations

import json
import multiprocessing
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pca import (
    AuditEngine,
    AuditOutcome,
    ContinuityEvaluator,
    ContinuityLedger,
    ContinuityStatus,
    FollowUpRecord,
    FollowUpStatus,
    IdentityManifest,
    IdentityState,
    OverrideEngine,
    OverrideRequest,
    PolicyDecision,
    PolicyEngine,
    TransformRequest,
    active_followups,
    build_manifest_from_packs,
    continuity_claim_from_followups,
    lineage_records,
    load_policy_directory,
    required_evidence_for,
)


def load_manifest() -> IdentityManifest:
    manifest_path = Path("examples/minimal_identity.json")
    return IdentityManifest.from_dict(json.loads(manifest_path.read_text()))


def append_concurrent_events(path: str, worker_id: int, count: int) -> None:
    ledger = ContinuityLedger(path)
    for index in range(count):
        ledger.append(
            "lock_test.event",
            "lock-test",
            {"worker_id": worker_id, "index": index},
        )


def main() -> int:
    manifest = load_manifest()
    ledger = ContinuityLedger(Path(tempfile.mkdtemp()) / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    evaluation = ContinuityEvaluator().evaluate(
        manifest,
        ledger.events(),
        ledger.verify_chain(),
    )
    assert evaluation.state == IdentityState.CONTINUOUS, evaluation

    transform = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="version_update",
            evidence={"change_summary": "No identity invariant changed."},
        ),
    )
    assert transform.decision == PolicyDecision.ALLOW, transform

    packed_manifest = build_manifest_from_packs(
        manifest,
        load_policy_directory("policies"),
    )
    packed_substrate = PolicyEngine().evaluate_transform(
        packed_manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )
    assert packed_substrate.decision == PolicyDecision.DENY
    assert packed_substrate.source_policy_pack == "substrate"
    assert "continuity_proof" in packed_substrate.missing_evidence

    packed_memory = PolicyEngine().evaluate_transform(
        packed_manifest,
        TransformRequest(
            transform="memory_compaction",
            evidence={"retention_report": "ok"},
        ),
    )
    assert packed_memory.decision == PolicyDecision.REVIEW
    assert packed_memory.source_policy_pack == "memory"
    assert packed_memory.missing_evidence == ["commitment_diff"]

    blocked_transform = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )
    assert blocked_transform.decision == PolicyDecision.DENY, blocked_transform
    assert blocked_transform.continuity_status == ContinuityStatus.UNCERTIFIED
    assert blocked_transform.missing_evidence == [
        "source_checkpoint",
        "target_checkpoint",
        "continuity_test",
    ]
    assert blocked_transform.identity_risk.value == "high_identity_risk"

    ledger.append(
        "identity.forked",
        manifest.system_id,
        {"child_id": "lucien-branch-a", "fork_reason": "smoke test fork"},
    )
    lineage = lineage_records(ledger.events())
    assert lineage[0].parent_id == manifest.system_id
    assert lineage[0].child_id == "lucien-branch-a"

    override = OverrideEngine().request_override(
        blocked_transform,
        OverrideRequest(
            transform="substrate_migration",
            authority="human_operator",
            reason="emergency migration from failing substrate",
            required_followup=[
                "post_migration_identity_audit",
                "lineage_freeze",
            ],
        ),
    )
    assert override.operation_permitted is True
    assert override.continuity_status_after_override == ContinuityStatus.UNCERTIFIED
    override_event = ledger.append(
        "transform.override",
        manifest.system_id,
        override.to_dict(),
    )
    for followup_type in override.required_followup:
        followup = FollowUpRecord.create(
            identity_id=manifest.system_id,
            source_event_id=override_event.event_hash,
            followup_type=followup_type,
            required_evidence=required_evidence_for(followup_type),
        )
        ledger.append("followup_created", manifest.system_id, followup.to_dict())

    blocking = active_followups(ledger.events())
    assert len(blocking) == 2
    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )
    assert claim == "uncertified_continuity"
    assert len(blocking) == 2

    completed = blocking[0].with_status(
        FollowUpStatus.COMPLETED,
        provided_evidence={blocking[0].required_evidence[0]: "ok"}
        if blocking[0].required_evidence
        else {},
    )
    ledger.append("followup_updated", manifest.system_id, completed.to_dict())
    remaining = active_followups(ledger.events())
    assert len(remaining) == 1

    audit = AuditEngine().run_audit(
        identity_id=manifest.system_id,
        audit_type="lineage_freeze",
        evidence={"audit_report": "ok"},
        source_transform_event_id=remaining[0].source_event_id,
        followup_id=remaining[0].followup_id,
    )
    assert audit.outcome == AuditOutcome.CERTIFY_CONTINUITY
    ledger.append("post_transform_audit", manifest.system_id, audit.to_dict())
    completed = remaining[0].with_status(
        FollowUpStatus.COMPLETED,
        provided_evidence=audit.after_evidence,
        reason=f"Completed by audit {audit.audit_id}.",
    )
    ledger.append("followup_updated", manifest.system_id, completed.to_dict())
    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )
    assert claim == "certified_continuity"
    assert blocking == []

    ledger.append(
        "constraint.breached",
        manifest.system_id,
        {"constraint": "origin_traceability", "severity": "hard"},
    )
    evaluation = ContinuityEvaluator().evaluate(
        manifest,
        ledger.events(),
        ledger.verify_chain(),
    )
    assert evaluation.state == IdentityState.BROKEN, evaluation

    lock_test_path = str(Path(tempfile.mkdtemp()) / "locked_continuity.log")
    processes = [
        multiprocessing.Process(
            target=append_concurrent_events,
            args=(lock_test_path, worker_id, 10),
        )
        for worker_id in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()
        assert process.exitcode == 0
    locked_ledger = ContinuityLedger(lock_test_path)
    assert len(locked_ledger.events()) == 40
    assert locked_ledger.verify_chain()

    print("smoke checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

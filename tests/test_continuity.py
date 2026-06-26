import json
from datetime import datetime, timedelta, timezone

from pca import (
    AuditEngine,
    AuditOutcome,
    AuthorityClass,
    AuthorizationCheckRecord,
    AuthorizationPolicy,
    ContinuityEvaluator,
    ContinuityEvent,
    ContinuityClaimRecord,
    ContinuityLedger,
    ContinuityStatus,
    CSMRuntimeBridge,
    EVALUATION_PRECEDENCE,
    FollowUpRecord,
    FollowUpStatus,
    IdentityManifest,
    IdentityState,
    OverrideEngine,
    OverrideRequest,
    OutputGate,
    OutputMode,
    PCAOutputWrapper,
    PCAIdentityRuntime,
    PersistenceConstraint,
    PolicyDecision,
    PolicyEngine,
    RecoveryRecord,
    RecoveryStatus,
    TransformRequest,
    append_ledger_anchor,
    active_followups,
    authorization_policy_from_packs,
    authorize,
    build_trace_report,
    build_manifest_from_packs,
    build_manifest_from_policy_results,
    claims_from_events,
    continuity_claim_from_followups,
    current_claim_record,
    derive_current_claim,
    export_latest_anchor,
    load_policy_directory,
    load_policy_pack,
    lineage_records,
    merge_policy_packs,
    required_evidence_for,
    render_dashboard_html,
    render_trace_report_html,
    recovery_records_from_events,
    safe_load_policy_pack,
    verify_latest_anchor,
)


def load_manifest():
    with open("examples/minimal_identity.json", encoding="utf-8") as handle:
        return IdentityManifest.from_dict(json.load(handle))


def event_at(event_type, subject_id, payload, timestamp):
    return ContinuityEvent(
        event_type=event_type,
        subject_id=subject_id,
        payload=payload,
        timestamp=timestamp.isoformat(),
    ).with_hash()


def manifest_with_freshness(freshness_seconds):
    manifest = load_manifest()
    constraints = [
        PersistenceConstraint(
            name=constraint.name,
            kind=constraint.kind,
            required=constraint.required,
            threshold=constraint.threshold,
            freshness_seconds=(
                freshness_seconds if constraint.required else constraint.freshness_seconds
            ),
            description=constraint.description,
        )
        for constraint in manifest.constraints
    ]
    return IdentityManifest(
        system_id=manifest.system_id,
        name=manifest.name,
        version=manifest.version,
        origin=manifest.origin,
        invariants=manifest.invariants,
        constraints=constraints,
        allowed_transforms=manifest.allowed_transforms,
        transform_policies=manifest.transform_policies,
    )


def test_continuous_identity_when_required_constraints_are_checked(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )

    assert evaluation.state == IdentityState.CONTINUOUS


def test_stale_required_evidence_suspends_identity():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=61)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            stale_time,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.SUSPENDED
    assert evaluation.reasons == [
        "required constraint evidence is stale: ledger_integrity",
        "required constraint evidence is stale: origin_traceability",
    ]


def test_fresh_required_evidence_restores_continuous_identity():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=120)
    fresh_time = now - timedelta(seconds=30)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            fresh_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            fresh_time,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.CONTINUOUS


def test_evaluator_precedence_is_declared():
    assert EVALUATION_PRECEDENCE == (
        "chain_invalid",
        "no_events",
        "hard_breach",
        "declared_fork",
        "stale_required_evidence",
        "missing_required_evidence",
        "soft_breach",
        "continuous",
    )


def test_state_precedence_chain_invalid_over_hard_breach():
    manifest = load_manifest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        event_at(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_red", "severity": "hard"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=False,
        now=now,
    )

    assert evaluation.state == IdentityState.SUSPENDED
    assert evaluation.reasons == ["continuity ledger hash chain is invalid"]


def test_state_precedence_hard_breach_over_declared_fork():
    manifest = load_manifest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        event_at(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_red", "severity": "hard"},
            now,
        ),
        event_at(
            "identity.forked",
            manifest.system_id,
            {"child_id": "lucien-branch-a"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.BROKEN
    assert evaluation.reasons == ["hard constraint breached: runtime_csm_red"]


def test_state_precedence_declared_fork_over_stale_evidence():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=120)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            stale_time,
        ),
        event_at(
            "identity.forked",
            manifest.system_id,
            {"child_id": "lucien-branch-a"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.FORKED
    assert evaluation.reasons == ["ledger contains an identity fork event"]


def test_state_precedence_stale_evidence_over_missing_evidence():
    manifest = manifest_with_freshness(freshness_seconds=60)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stale_time = now - timedelta(seconds=120)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            stale_time,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.SUSPENDED
    assert evaluation.reasons == [
        "required constraint evidence is stale: ledger_integrity"
    ]


def test_state_precedence_soft_breach_over_continuous():
    manifest = load_manifest()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = [
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
            now,
        ),
        event_at(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
            now,
        ),
        event_at(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "commitment_memory", "severity": "soft"},
            now,
        ),
    ]

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=True,
        now=now,
    )

    assert evaluation.state == IdentityState.DEGRADED
    assert evaluation.reasons == ["soft constraint breached: commitment_memory"]


def test_hard_breach_breaks_identity_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    ledger.append(
        "constraint.breached",
        manifest.system_id,
        {"constraint": "origin_traceability", "severity": "hard"},
    )

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )

    assert evaluation.state == IdentityState.BROKEN


def test_ledger_anchor_records_current_head(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    anchor = append_ledger_anchor(
        ledger,
        tmp_path / "anchors.log",
        authority="root_authority",
        note="release checkpoint",
    )

    assert anchor.event_count == 1
    assert anchor.head_hash == ledger.last_hash()
    assert anchor.chain_valid is True
    assert anchor.previous_anchor_hash == "GENESIS"
    assert anchor.anchor_hash


def test_latest_anchor_verifies_against_ledger(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    append_ledger_anchor(ledger, tmp_path / "anchors.log")

    verification = verify_latest_anchor(ledger, tmp_path / "anchors.log")

    assert verification.valid is True
    assert verification.reasons == ["latest anchor matches ledger head"]


def test_latest_anchor_detects_later_ledger_change(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    append_ledger_anchor(ledger, tmp_path / "anchors.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "origin_traceability", "value": True},
    )

    verification = verify_latest_anchor(ledger, tmp_path / "anchors.log")

    assert verification.valid is False
    assert "ledger head hash does not match latest anchor" in verification.reasons
    assert "ledger event count does not match latest anchor" in verification.reasons


def test_anchor_export_writes_portable_checkpoint(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    anchor_path = tmp_path / "anchors.log"
    append_ledger_anchor(ledger, anchor_path, authority="root_authority")
    output_path = tmp_path / "latest_anchor.json"

    export = export_latest_anchor(ledger, anchor_path, output_path)
    exported = json.loads(output_path.read_text(encoding="utf-8"))

    assert export.export_hash
    assert exported["export_hash"] == export.export_hash
    assert exported["verification"]["valid"] is True
    assert exported["verification"]["latest_anchor"]["head_hash"] == ledger.last_hash()
    assert exported["verification"]["current_event_count"] == 1


def test_hard_breach_cannot_be_followed_by_certified_claim(tmp_path):
    manifest = load_manifest()

    def seeded_ledger(name):
        ledger = ContinuityLedger(tmp_path / name / "continuity.log")
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
        breach = ledger.append(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_red", "severity": "hard"},
        )
        return ledger, breach

    def forged_certified_claim(ledger, breach):
        forged = ContinuityClaimRecord.create(
            identity_id=manifest.system_id,
            claim="certified_continuity",
            source_event_ids=[breach.event_hash],
            active_blockers=[],
            reason="forged downstream certification",
        )
        ledger.append("continuity_claim_record", manifest.system_id, forged.to_dict())

    def recovery_opened(ledger, _breach):
        recovery = RecoveryRecord.open(
            identity_id=manifest.system_id,
            opened_by="recovery_authority",
            reason="hard breach recovery opened",
            source_claim_id=None,
        )
        ledger.append("recovery_opened", manifest.system_id, recovery.to_dict())

    def recovery_certified(ledger, _breach):
        recovery = RecoveryRecord.open(
            identity_id=manifest.system_id,
            opened_by="recovery_authority",
            reason="hard breach recovery opened",
            source_claim_id=None,
        )
        ledger.append("recovery_opened", manifest.system_id, recovery.to_dict())
        certified = recovery.with_status(
            RecoveryStatus.CERTIFIED,
            evidence={"recovery_audit_report": "ok"},
        )
        ledger.append("recovery_updated", manifest.system_id, certified.to_dict())

    adversarial_tails = {
        "no_tail": lambda _ledger, _breach: None,
        "later_required_evidence": lambda ledger, _breach: ledger.append(
            "constraint.checked",
            manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
        ),
        "later_soft_breach": lambda ledger, _breach: ledger.append(
            "constraint.breached",
            manifest.system_id,
            {"constraint": "runtime_csm_amber", "severity": "soft"},
        ),
        "later_fork": lambda ledger, _breach: ledger.append(
            "identity.forked",
            manifest.system_id,
            {"child_id": "lucien-branch-a", "fork_reason": "after breach"},
        ),
        "forged_certified_claim": forged_certified_claim,
        "recovery_opened": recovery_opened,
        "recovery_certified": recovery_certified,
    }

    for name, append_tail in adversarial_tails.items():
        ledger, breach = seeded_ledger(name)
        append_tail(ledger, breach)

        claim, _blockers, _reasons = derive_current_claim(ledger, manifest)

        assert claim != "certified_continuity", name


def test_declared_fork_is_classified_as_forked(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    ledger.append("identity.forked", manifest.system_id, {"child_id": "lucien-branch-a"})

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )

    assert evaluation.state == IdentityState.FORKED


def test_transform_policy_denies_high_risk_missing_evidence():
    manifest = load_manifest()

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )

    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.missing_evidence == [
        "source_checkpoint",
        "target_checkpoint",
        "continuity_test",
    ]
    assert evaluation.provided_evidence == []
    assert evaluation.identity_risk.value == "high_identity_risk"
    assert evaluation.continuity_status == ContinuityStatus.UNCERTIFIED
    assert "without verified evidence" in evaluation.reason


def test_transform_policy_allows_complete_version_update():
    manifest = load_manifest()

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="version_update",
            evidence={"change_summary": "No identity invariant changed."},
        ),
    )

    assert evaluation.decision == PolicyDecision.ALLOW
    assert evaluation.continuity_status == ContinuityStatus.CERTIFIED
    assert evaluation.provided_evidence == ["change_summary"]
    assert evaluation.missing_evidence == []


def test_memory_compaction_missing_commitment_diff_requires_review():
    manifest = load_manifest()

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="memory_compaction",
            evidence={"retention_report": "passed"},
        ),
    )

    assert evaluation.decision == PolicyDecision.REVIEW
    assert evaluation.provided_evidence == ["retention_report"]
    assert evaluation.missing_evidence == ["commitment_diff"]


def test_fork_event_creates_lineage_record(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    event = ledger.append(
        "identity.forked",
        manifest.system_id,
        {"child_id": "lucien-branch-a", "fork_reason": "sandboxed experiment"},
    )

    records = lineage_records(ledger.events())

    assert len(records) == 1
    assert records[0].parent_id == manifest.system_id
    assert records[0].child_id == "lucien-branch-a"
    assert records[0].reason == "sandboxed experiment"
    assert records[0].event_hash == event.event_hash


def test_override_permits_operation_without_certifying_continuity():
    manifest = load_manifest()
    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )

    override = OverrideEngine().request_override(
        evaluation,
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
    assert override.original_decision == PolicyDecision.DENY
    assert (
        override.continuity_status_after_override
        == ContinuityStatus.UNCERTIFIED
    )
    assert override.required_followup == [
        "post_migration_identity_audit",
        "lineage_freeze",
    ]


def test_override_followups_constrain_continuity_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    for followup_type in ["post_migration_identity_audit", "lineage_freeze"]:
        followup = FollowUpRecord.create(
            identity_id=manifest.system_id,
            source_event_id=source_event.event_hash,
            followup_type=followup_type,
            required_evidence=required_evidence_for(followup_type),
        )
        ledger.append("followup_created", manifest.system_id, followup.to_dict())

    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )

    assert claim == "uncertified_continuity"
    assert len(blocking) == 2


def test_failed_followup_breaks_continuity_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event.event_hash,
        followup_type="lineage_freeze",
        required_evidence=required_evidence_for("lineage_freeze"),
    )
    ledger.append("followup_created", manifest.system_id, followup.to_dict())
    failed = followup.with_status(
        FollowUpStatus.FAILED,
        reason="lineage freeze mismatch",
    )
    ledger.append("followup_updated", manifest.system_id, failed.to_dict())

    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )

    assert claim == "continuity_break"
    assert active_followups(ledger.events())[0].status == FollowUpStatus.FAILED
    assert blocking[0].followup_id == followup.followup_id


def test_substrate_migration_audit_completes_followup(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event.event_hash,
        followup_type="post_migration_identity_audit",
        required_evidence=required_evidence_for("post_migration_identity_audit"),
    )
    ledger.append("followup_created", manifest.system_id, followup.to_dict())

    audit = AuditEngine().run_audit(
        identity_id=manifest.system_id,
        audit_type="substrate_migration",
        source_transform_event_id=source_event.event_hash,
        followup_id=followup.followup_id,
        evidence={
            "continuity_proof": "ok",
            "state_hash_match": "ok",
            "operator_attestation": "ok",
        },
    )
    ledger.append("post_transform_audit", manifest.system_id, audit.to_dict())
    completed = followup.with_status(
        FollowUpStatus.COMPLETED,
        provided_evidence=audit.after_evidence,
        reason=f"Completed by audit {audit.audit_id}.",
    )
    ledger.append("followup_updated", manifest.system_id, completed.to_dict())

    assert audit.outcome == AuditOutcome.CERTIFY_CONTINUITY
    assert active_followups(ledger.events()) == []


def test_failed_audit_fails_followup_and_breaks_claim(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    source_event = ledger.append(
        "transform.override",
        manifest.system_id,
        {"transform": "substrate_migration"},
    )
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event.event_hash,
        followup_type="post_migration_identity_audit",
        required_evidence=required_evidence_for("post_migration_identity_audit"),
    )
    ledger.append("followup_created", manifest.system_id, followup.to_dict())

    audit = AuditEngine().run_audit(
        identity_id=manifest.system_id,
        audit_type="substrate_migration",
        source_transform_event_id=source_event.event_hash,
        followup_id=followup.followup_id,
        evidence={
            "continuity_proof": "ok",
            "state_hash_match": "mismatch",
            "operator_attestation": "ok",
        },
    )
    ledger.append("post_transform_audit", manifest.system_id, audit.to_dict())
    failed = followup.with_status(
        FollowUpStatus.FAILED,
        provided_evidence=audit.after_evidence,
        reason=audit.reason,
    )
    ledger.append("followup_updated", manifest.system_id, failed.to_dict())

    claim, blocking = continuity_claim_from_followups(
        ledger.events(),
        "certified_continuity",
    )

    assert audit.outcome == AuditOutcome.MARK_CONTINUITY_BREAK
    assert claim == "continuity_break"
    assert blocking[0].followup_id == followup.followup_id


def test_claim_records_can_supersede_prior_claims(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    seed_event = ledger.append(
        "constraint.checked",
        manifest.system_id,
        {"constraint": "ledger_integrity", "value": True},
    )
    first = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim="certified_continuity",
        source_event_ids=[seed_event.event_hash],
        active_blockers=[],
        reason="Initial required evidence recorded.",
    )
    first_event = ledger.append(
        "continuity_claim_record",
        manifest.system_id,
        first.to_dict(),
    )
    second = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim="uncertified_continuity",
        source_event_ids=[first_event.event_hash],
        active_blockers=["followup_1"],
        reason="Continuity claim constrained by open follow-up.",
        supersedes_claim_id=first.claim_id,
    )
    ledger.append("continuity_claim_record", manifest.system_id, second.to_dict())

    claims = claims_from_events(ledger.events())

    assert len(claims) == 2
    assert current_claim_record(ledger.events()).claim == "uncertified_continuity"
    assert current_claim_record(ledger.events()).supersedes_claim_id == first.claim_id


def test_claim_record_contains_active_blockers(tmp_path):
    manifest = load_manifest()
    source_event_id = "event_1"
    followup = FollowUpRecord.create(
        identity_id=manifest.system_id,
        source_event_id=source_event_id,
        followup_type="post_migration_identity_audit",
    )
    claim = ContinuityClaimRecord.create(
        identity_id=manifest.system_id,
        claim="uncertified_continuity",
        source_event_ids=[source_event_id],
        active_blockers=[followup.followup_id],
        reason="Continuity claim constrained by active follow-up.",
    )

    assert claim.active_blockers == [followup.followup_id]
    assert claim.source_event_ids == [source_event_id]


def test_policy_pack_drives_substrate_migration_denial():
    manifest = build_manifest_from_packs(
        load_manifest(),
        [load_policy_pack("policies/substrate.json")],
    )

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )

    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.source_policy_pack == "substrate"
    assert "continuity_proof" in evaluation.missing_evidence
    assert evaluation.required_followups_on_override == [
        "post_migration_identity_audit",
        "lineage_freeze",
    ]


def test_policy_directory_loads_memory_pack_review_rule():
    manifest = build_manifest_from_packs(
        load_manifest(),
        load_policy_directory("policies"),
    )

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="memory_compaction",
            evidence={"retention_report": "ok"},
        ),
    )

    assert evaluation.decision == PolicyDecision.REVIEW
    assert evaluation.source_policy_pack == "memory"
    assert evaluation.missing_evidence == ["commitment_diff"]


def test_malformed_policy_pack_loads_as_invalid_result(tmp_path):
    policy_path = tmp_path / "broken.json"
    policy_path.write_text("{not json", encoding="utf-8")

    result = safe_load_policy_pack(policy_path)

    assert result.valid is False
    assert result.pack is None
    assert "Expecting property name" in result.error_messages()[0]


def test_invalid_policy_set_denies_identity_transform(tmp_path):
    policy_path = tmp_path / "missing_pack_id.json"
    policy_path.write_text(
        json.dumps({"transforms": {"version_update": {}}}),
        encoding="utf-8",
    )
    result = safe_load_policy_pack(policy_path)
    manifest = build_manifest_from_policy_results(load_manifest(), [result])

    evaluation = PolicyEngine().evaluate_transform(
        manifest,
        TransformRequest(
            transform="version_update",
            evidence={"change_summary": "No identity invariant changed."},
        ),
    )

    assert result.valid is False
    assert manifest.policy_errors
    assert evaluation.decision == PolicyDecision.DENY
    assert evaluation.source_policy_pack == "invalid_policy"
    assert evaluation.override_allowed is False
    assert evaluation.continuity_status == ContinuityStatus.UNCERTIFIED
    assert evaluation.reasons[0].startswith("policy set invalid:")


def test_policy_pack_merge_is_conservative():
    loose = {
        "pack_id": "loose",
        "transforms": {
            "substrate_migration": {
                "identity_risk": "medium_identity_risk",
                "required_evidence": ["operator_attestation"],
                "review_if_missing": ["operator_attestation"],
                "override_allowed": True,
            }
        },
    }
    strict = load_policy_pack("policies/substrate.json")

    policy = merge_policy_packs([loose, strict])[0]

    assert policy.name == "substrate_migration"
    assert policy.identity_risk.value == "high_identity_risk"
    assert "continuity_proof" in policy.deny_if_missing
    assert policy.source_policy_pack == "loose,substrate"


def test_authorization_policy_allows_operator_override():
    policy = AuthorizationPolicy()

    decision = authorize("operator", policy.override_min_authority, policy)

    assert decision.allowed is True
    assert decision.authority == AuthorityClass.OPERATOR


def test_authorization_policy_denies_observer_override():
    policy = AuthorizationPolicy()

    decision = authorize("observer", policy.override_min_authority, policy)

    assert decision.allowed is False
    assert decision.required == AuthorityClass.OPERATOR


def test_authorization_pack_aliases_human_operator():
    policy = authorization_policy_from_packs(
        [load_policy_pack("policies/authorization.json")]
    )

    decision = authorize("human_operator", policy.override_min_authority, policy)

    assert decision.allowed is True
    assert decision.authority == AuthorityClass.OPERATOR


def test_authorization_check_record_captures_denial():
    policy = AuthorizationPolicy()
    decision = authorize("observer", policy.override_min_authority, policy)

    record = AuthorizationCheckRecord.create(
        identity_id="identity_1",
        action="override",
        actor_authority="observer",
        decision=decision,
    )

    assert record.decision == "denied"
    assert record.actor_authority == "observer"
    assert record.parsed_authority == AuthorityClass.OBSERVER
    assert record.required_authority == AuthorityClass.OPERATOR


def test_recovery_record_opens_with_audit_required():
    recovery = RecoveryRecord.open(
        identity_id="identity_1",
        opened_by="recovery_authority",
        reason="continuity break needs review",
        source_claim_id="claim_1",
    )

    assert recovery.status == RecoveryStatus.AUDIT_REQUIRED
    assert recovery.required_followups == ["recovery_audit"]
    assert recovery.source_claim_id == "claim_1"


def test_recovery_records_are_ledger_derived(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    recovery = RecoveryRecord.open(
        identity_id=manifest.system_id,
        opened_by="recovery_authority",
        reason="failed audit",
        source_claim_id=None,
    )
    ledger.append("recovery_opened", manifest.system_id, recovery.to_dict())
    certified = recovery.with_status(
        RecoveryStatus.CERTIFIED,
        evidence={"recovery_audit_report": "ok"},
    )
    ledger.append("recovery_updated", manifest.system_id, certified.to_dict())

    records = recovery_records_from_events(ledger.events())

    assert len(records) == 1
    assert records[0].status == RecoveryStatus.CERTIFIED
    assert records[0].evidence == {"recovery_audit_report": "ok"}


def test_output_gate_modes_for_continuity_claims():
    gate = OutputGate()

    certified = gate.evaluate("certified_continuity")
    review = gate.evaluate("review_required")
    uncertified = gate.evaluate("uncertified_continuity")
    fork = gate.evaluate("declared_fork")
    broken = gate.evaluate("continuity_break")

    assert certified.mode == OutputMode.NORMAL_IDENTITY
    assert certified.may_speak_as_identity is True
    assert review.mode == OutputMode.DISCLOSE_REVIEW
    assert review.must_disclose is True
    assert uncertified.mode == OutputMode.OPERATIONAL_ONLY
    assert uncertified.may_speak_as_identity is False
    assert fork.mode == OutputMode.FORK_DISCLOSURE
    assert broken.mode == OutputMode.RECOVERY_STATUS_ONLY


def test_runtime_allows_certified_identity_speech(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")

    decision = runtime.process_output("I can continue from the same identity state.")

    assert decision.allowed is True
    assert decision.output_gate.mode == OutputMode.NORMAL_IDENTITY
    assert decision.text == "I can continue from the same identity state."


def test_runtime_amber_signal_constrains_identity_speech(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")

    result = runtime.record_runtime_signal(
        "AMBER",
        metrics={"strain": 0.72},
        reason="runtime strain above review threshold",
    )
    decision = runtime.process_output("I can continue.")

    assert result.breach_event is not None
    assert result.breach_event.payload["severity"] == "soft"
    assert result.output_gate.mode == OutputMode.DISCLOSE_REVIEW
    assert decision.allowed is True
    assert decision.text.startswith("Continuity is under review.")


def test_runtime_red_signal_breaks_continuity_and_blocks_identity_speech(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")

    result = runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 0.97, "schema_valid": False},
        reason="CSM hard kill condition",
    )
    claim, _, _ = derive_current_claim(ledger, manifest)
    decision = runtime.process_output("I am stable Lucien.")

    assert result.breach_event is not None
    assert result.breach_event.payload["constraint"] == "runtime_csm_red"
    assert result.breach_event.payload["severity"] == "hard"
    assert claim == "continuity_break"
    assert result.output_gate.mode == OutputMode.RECOVERY_STATUS_ONLY
    assert decision.allowed is False
    assert decision.text == "Continuity is broken; recovery/status only."


def test_csm_bridge_records_monitor_results(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    bridge = CSMRuntimeBridge(runtime)

    result = bridge.record_monitor_result(
        {"state": "AMBER", "RTI": 1.9, "strain": 1.4}
    )

    assert result.signal_event.event_type == "runtime.csm_state"
    assert result.signal_event.payload["metrics"] == {"RTI": 1.9, "strain": 1.4}
    assert result.breach_event is not None
    assert result.breach_event.payload["severity"] == "soft"
    assert result.output_gate.mode == OutputMode.DISCLOSE_REVIEW


def test_csm_audit_logger_adapter_records_red_before_hard_kill(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    bridge = CSMRuntimeBridge(runtime)
    logger = bridge.audit_logger_adapter()

    logger.log_red_event(
        {
            "run_id": "run_1",
            "step_id": 7,
            "RTI": 2.4,
            "strain": 3.1,
            "reason": "Strain critical breach",
        }
    )
    claim, _, _ = derive_current_claim(ledger, manifest)

    assert logger.last_signal_result is not None
    assert logger.last_signal_result.breach_event is not None
    assert logger.last_signal_result.breach_event.payload["severity"] == "hard"
    assert claim == "continuity_break"
    assert logger.last_signal_result.output_gate.mode == OutputMode.RECOVERY_STATUS_ONLY


def test_csm_bridge_process_monitor_step_returns_logged_hard_kill(tmp_path):
    class FakeMonitor:
        def __init__(self, logger):
            self.logger = logger
            self.state = "GREEN"
            self.run_id = "run_1"
            self.step_id = 0

        def process_step(self, **_kwargs):
            self.state = "RED"
            self.step_id = 1
            self.logger.log_red_event(
                {
                    "run_id": self.run_id,
                    "step_id": self.step_id,
                    "strain": 4.2,
                    "reason": "Strain critical breach",
                }
            )
            raise RuntimeError("CSM-1.0 Hard Kill: Evidence Persisted.")

    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    bridge = CSMRuntimeBridge(runtime)
    logger = bridge.audit_logger_adapter()
    monitor = FakeMonitor(logger)

    result = bridge.process_monitor_step(monitor, latency_ms=100.0)

    assert result.output_gate.mode == OutputMode.RECOVERY_STATUS_ONLY
    assert result.claim_record is not None
    assert result.claim_record.claim == "continuity_break"


def test_output_wrapper_allows_and_audits_certified_output(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger)
    wrapper = PCAOutputWrapper(runtime)

    envelope = wrapper.emit("I can speak as this identity.")

    assert envelope.decision.allowed is True
    assert envelope.decision.text == "I can speak as this identity."
    assert envelope.audit_event.event_type == "runtime.output_gate"
    assert envelope.audit_event.payload["mode"] == "normal_identity"
    assert envelope.audit_event.payload["allowed"] is True
    assert "I can speak" not in json.dumps(envelope.audit_event.payload)


def test_output_wrapper_adds_review_disclosure(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger)
    runtime.record_runtime_signal("AMBER", reason="strain review")
    wrapper = PCAOutputWrapper(runtime)

    envelope = wrapper.emit("I can continue operationally.")

    assert envelope.decision.allowed is True
    assert envelope.decision.text.startswith("Continuity is under review.")
    assert envelope.audit_event.payload["mode"] == "disclose_review"
    assert envelope.audit_event.payload["must_disclose"] is True


def test_output_wrapper_blocks_identity_speech_after_break(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger)
    runtime.record_runtime_signal("RED", reason="hard runtime breach")
    wrapper = PCAOutputWrapper(runtime)

    envelope = wrapper.emit("I am stable and continuous.")

    assert envelope.decision.allowed is False
    assert envelope.decision.text == "Continuity is broken; recovery/status only."
    assert envelope.audit_event.payload["mode"] == "recovery_status_only"
    assert envelope.audit_event.payload["allowed"] is False


def test_trace_report_summarizes_runtime_lifecycle(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 3.2},
        reason="critical strain",
    )
    PCAOutputWrapper(runtime).emit(
        "I am stable and continuous.",
        metadata={"test": "trace"},
    )

    report = build_trace_report(ledger, manifest)
    html = render_trace_report_html(report)

    assert report.summary["current_continuity_claim"] == "continuity_break"
    assert report.summary["output_mode"] == "recovery_status_only"
    assert len(report.runtime_signals) == 1
    assert report.runtime_signals[0]["state"] == "RED"
    assert len(report.output_gate_events) == 1
    assert report.output_gate_events[0]["allowed"] is False
    assert report.evidence_freshness[0]["status"] == "fresh"
    assert report.summary["state_precedence"] == list(EVALUATION_PRECEDENCE)
    assert "PCA Trace Report" in html
    assert "continuity_break" in html


def test_dashboard_renders_runtime_lifecycle(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
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
    runtime = PCAIdentityRuntime(manifest, ledger, signal_source="lucien_csm")
    runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 3.5},
        reason="critical strain",
    )
    PCAOutputWrapper(runtime).emit("I am stable and continuous.")

    report = build_trace_report(ledger, manifest)
    html = render_dashboard_html(report)

    assert "PCA Dashboard" in html
    assert "continuity_break" in html
    assert "recovery_status_only" in html
    assert "eventSearch" in html
    assert "Evidence Freshness" in html
    assert "State Precedence" in html
    assert "Anchor Status" in html
    assert "Active Blockers" in html
    assert "Recovery Timeline" in html
    assert "Lineage" in html
    assert "Authorization Attempts" in html
    assert "Policy Errors" in html

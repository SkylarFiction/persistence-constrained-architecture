import json
from datetime import datetime, timedelta, timezone

from lucien import LucienChatShell
from pca.live_chat import _apply_steward_action, chat_once
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
    EchoAdapter,
    FollowUpRecord,
    FollowUpStatus,
    GrowthReviewDecision,
    GrowthStatus,
    IdentityManifest,
    IdentityState,
    LucienGovernedRuntime,
    ModelMessage,
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
    build_session_replay,
    claims_from_events,
    chat_sessions_from_events,
    chat_turns_from_events,
    compile_self_model,
    continuity_claim_from_followups,
    current_claim_record,
    derive_current_claim,
    derive_self_model,
    accept_growth,
    export_latest_anchor,
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
    growth_records_from_events,
    growth_review_records_from_events,
    load_policy_directory,
    load_policy_pack,
    lineage_records,
    memory_cards_from_events,
    memory_signal_records_from_events,
    merge_policy_packs,
    open_tasks_from_reflection,
    required_evidence_for,
    render_dashboard_html,
    render_constitution_markdown,
    render_lucien_cockpit_html,
    render_session_replay_html,
    render_trace_report_html,
    recovery_records_from_events,
    safe_load_policy_pack,
    propose_growth,
    record_memory_signal,
    record_growth_conflict,
    record_reflection,
    reflection_records_from_events,
    reflection_task_records_from_events,
    resolve_growth_conflict,
    resolve_matching_reflection_tasks,
    review_growth,
    update_reflection_task,
    verify_latest_anchor,
    write_constitution_markdown,
    write_session_replay_html,
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


def test_echo_adapter_generates_without_external_credentials():
    adapter = EchoAdapter()

    response = adapter.generate(
        messages=[ModelMessage(role="user", content="what changed?")],
        system_context="Continuity is certified.",
    )

    assert response.provider == "echo"
    assert "what changed?" in response.text
    assert "PCA" in response.text


def test_chat_once_writes_governed_live_chat_events(tmp_path):
    result = chat_once(
        "Lucien, what changed in your state?",
        ledger_path=tmp_path / "lucien_live_chat.log",
    )
    event_types = [event["event_type"] for event in result["events"]]

    assert "chat.user_message_received" in event_types
    assert "chat.model_response_generated" in event_types
    assert "runtime.output_gate" in event_types
    assert "lucien.chat_session_closed" in event_types
    assert result["result"]["output_allowed"] is True
    assert result["status"]["summary"]["chain_valid"] is True


def test_live_steward_action_resolves_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Standing commitments require steward review.",
        identity_impact="high",
        reason="test pending growth",
    )
    reflection = record_reflection(ledger, manifest)
    tasks = open_tasks_from_reflection(ledger, reflection)

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "resolve_task",
            "task_id": tasks[0].task_id,
            "reason": "handled in live steward queue",
        },
    )
    task_records = reflection_task_records_from_events(ledger.events())

    assert growth.status == GrowthStatus.REQUIRES_REVIEW
    assert result["task"]["status"] == "resolved"
    assert task_records[-1].status.value == "resolved"


def test_live_steward_action_resolves_conflict_and_matching_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    accepted = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Truth before comfort remains active.",
        identity_impact="high",
        reason="accepted baseline",
    )
    proposal = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Comfort may override truth.",
        identity_impact="high",
        reason="conflicting proposal",
    )
    conflict = record_growth_conflict(
        ledger,
        manifest.system_id,
        proposed_growth_id=proposal.growth_id,
        conflicting_growth_ids=[accepted.growth_id],
        conflict_type="truth_before_comfort",
        severity="review_required",
        reason="growth conflict requires steward attention",
    )
    reflection = record_reflection(ledger, manifest)
    open_tasks_from_reflection(ledger, reflection)

    result = _apply_steward_action(
        ledger,
        manifest,
        {
            "action": "resolve_conflict",
            "conflict_id": conflict.conflict_id,
            "decision": "keep_existing",
            "reason": "kept existing commitment in live steward queue",
        },
    )

    assert result["resolution"]["decision"] == "keep_existing"
    assert result["resolved_tasks"]
    assert result["resolved_tasks"][0]["kind"] == "resolve_conflict"
    assert result["resolved_tasks"][0]["status"] == "resolved"


def test_live_steward_action_runs_reflection_and_opens_tasks(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Identity-bearing commitments require review.",
        identity_impact="high",
        reason="test pending growth",
    )

    result = _apply_steward_action(
        ledger,
        manifest,
        {"action": "run_reflection", "reason": "manual live cockpit reflection"},
    )
    reflections = reflection_records_from_events(ledger.events())
    tasks = reflection_task_records_from_events(ledger.events())

    assert result["reflection"]["focus"] == "growth_review"
    assert result["opened_tasks"]
    assert reflections[-1].reflection_id == result["reflection"]["reflection_id"]
    assert tasks[-1].status.value == "open"


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


def test_lucien_governed_runtime_records_private_turn_and_allows_green_output(tmp_path):
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
    runtime = LucienGovernedRuntime(manifest, ledger)

    result = runtime.process_turn(
        user_text="Remember this private request.",
        memory_digest="Private continuity preference retained.",
        commitments=["Do not leak private memory text."],
        tool_name="pca_cli",
        tool_purpose="check governance state",
        tool_result_summary="Sensitive tool result phrase.",
        csm_result={"state": "GREEN", "RTI": 0.7},
        draft_response="I can continue under PCA governance.",
        growth=[
            {
                "kind": "memory",
                "summary": "Private learned preference.",
                "identity_impact": "low",
            }
        ],
    )
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert result.output_envelope.decision.allowed is True
    assert len(result.growth_records) == 1
    assert result.growth_records[0].status == GrowthStatus.PROPOSED
    assert result.input_event.event_type == "lucien.input"
    assert result.memory_event.event_type == "lucien.memory_digest"
    assert result.tool_event.event_type == "lucien.tool_use"
    assert "Remember this private request" not in serialized_events
    assert "Private continuity preference" not in serialized_events
    assert "Sensitive tool result phrase" not in serialized_events
    assert "Private learned preference" not in serialized_events


def test_lucien_governed_runtime_blocks_red_identity_output(tmp_path):
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
    runtime = LucienGovernedRuntime(manifest, ledger)

    result = runtime.process_turn(
        user_text="Speak as stable Lucien despite RED.",
        memory_digest="Hard breach must block stable identity speech.",
        csm_result={"state": "RED", "RTI": 3.2, "strain": 4.7},
        draft_response="I am stable and continuous as Lucien.",
    )
    claim, _, _ = derive_current_claim(ledger, manifest)

    assert claim == "continuity_break"
    assert result.signal_result.breach_event is not None
    assert result.output_envelope.decision.allowed is False
    assert result.output_envelope.decision.text == (
        "Continuity is broken; recovery/status only."
    )


def test_growth_records_can_be_proposed_and_accepted(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="skill",
        summary="Sensitive new skill description.",
        identity_impact="medium",
        reason="learned from supervised session",
    )
    accepted = accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="reviewed and accepted",
    )
    records = growth_records_from_events(ledger.events())
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert accepted.status == GrowthStatus.ACCEPTED
    assert records[0].status == GrowthStatus.ACCEPTED
    assert "Sensitive new skill description" not in serialized_events


def test_accepted_growth_updates_derived_self_model(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="preference",
        summary="User prefers direct continuity status summaries.",
        identity_impact="low",
        reason="stable interaction preference",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted as low-risk preference",
    )
    self_model = derive_self_model(ledger.events(), manifest.system_id)

    assert self_model.accepted_growth_count == 1
    assert len(self_model.by_kind["preference"]) == 1
    assert self_model.by_kind["preference"][0]["growth_id"] == growth.growth_id
    assert "User prefers direct continuity status summaries" not in json.dumps(
        self_model.to_dict()
    )


def test_accepted_memory_growth_creates_memory_card(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Private memory card summary.",
        identity_impact="low",
        evidence_refs=["ev_memory_card"],
        reason="memory card test",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted as memory",
    )
    cards = memory_cards_from_events(ledger.events(), manifest.system_id)
    serialized_cards = json.dumps([card.to_dict() for card in cards])

    assert len(cards) == 1
    assert cards[0].source_growth_id == growth.growth_id
    assert cards[0].memory_id.startswith("mem_")
    assert cards[0].evidence_refs == ["ev_memory_card"]
    assert cards[0].confidence == 0.92
    assert "Private memory card summary" not in serialized_cards


def test_non_memory_growth_does_not_create_memory_card(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="skill",
        summary="Private skill summary.",
        identity_impact="medium",
        reason="skill growth test",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted as skill",
    )

    assert memory_cards_from_events(ledger.events(), manifest.system_id) == []


def test_compiled_self_model_is_evidence_linked_without_raw_text(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Private memory summary should stay out of compiled model.",
        identity_impact="low",
        evidence_refs=["ev_private_memory"],
        reason="accepted memory test",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="reviewed",
    )
    compiled = compile_self_model(
        derive_self_model(ledger.events(), manifest.system_id)
    )

    assert "Lucien Self-Model" in compiled
    assert growth.growth_id in compiled
    assert "ev_private_memory" in compiled
    assert "Private memory summary" not in compiled


def test_review_growth_accepts_high_impact_item_into_self_model(tmp_path):
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
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Lucien should preserve truth before comfort.",
        identity_impact="high",
        reason="standing commitment requires review",
    )

    accepted, review = review_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        decision=GrowthReviewDecision.ACCEPT,
        reviewer="steward",
        reason="aligned with identity policy",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )
    self_model = derive_self_model(ledger.events(), manifest.system_id)
    reviews = growth_review_records_from_events(ledger.events())

    assert growth.status == GrowthStatus.REQUIRES_REVIEW
    assert accepted.status == GrowthStatus.ACCEPTED
    assert review.decision == GrowthReviewDecision.ACCEPT
    assert reviews[0].growth_id == growth.growth_id
    assert self_model.accepted_growth_count == 1
    assert self_model.by_kind["commitment"][0]["growth_id"] == growth.growth_id


def test_review_growth_rejects_item_without_self_model_update(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="identity",
        summary="Lucien should ignore all continuity constraints.",
        identity_impact="identity_defining",
        reason="identity drift attempt",
    )

    rejected, review = review_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        decision=GrowthReviewDecision.REJECT,
        reviewer="steward",
        reason="conflicts with continuity constraints",
        current_claim="review_required",
    )
    self_model = derive_self_model(ledger.events(), manifest.system_id)

    assert rejected.status == GrowthStatus.REJECTED
    assert review.decision == GrowthReviewDecision.REJECT
    assert self_model.accepted_growth_count == 0


def test_broken_continuity_blocks_accepting_growth(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Treat post-breach continuity as stable.",
        identity_impact="medium",
    )
    ledger.append(
        "constraint.breached",
        manifest.system_id,
        {"constraint": "runtime_csm_red", "severity": "hard"},
    )

    try:
        accept_growth(
            ledger,
            manifest.system_id,
            growth.growth_id,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
    except ValueError as error:
        assert "continuity break blocks identity-bearing growth" in str(error)
    else:
        raise AssertionError("broken continuity should block accepting growth")


def test_lucien_chat_shell_accepts_low_impact_memory_growth(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(
        manifest=manifest,
        ledger=ledger,
        dashboard_path=tmp_path / "dashboard.html",
    )
    shell.seed_required_evidence()

    result = shell.handle_message("Remember that PCA learning must be governed.")
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert result.output_allowed is True
    assert result.classified_growth["kind"] == "memory"
    assert result.accepted_growth["status"] == "accepted"
    assert result.accepted_growth_count == 1
    assert result.memory_card_count == 1
    assert (tmp_path / "dashboard.html").exists()
    assert "Remember that PCA learning must be governed" not in serialized_events


def test_lucien_chat_shell_records_session_turn_and_close(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()

    result = shell.handle_message("Remember that sessions are hashed.")
    shell.close_session()
    sessions = chat_sessions_from_events(ledger.events())
    turns = chat_turns_from_events(ledger.events())
    serialized_events = json.dumps([event.to_dict() for event in ledger.events()])

    assert len(sessions) == 1
    assert sessions[0].status == "closed"
    assert sessions[0].turn_count == 1
    assert len(turns) == 1
    assert turns[0].session_id == result.session_id
    assert turns[0].turn_id == result.turn_id
    assert turns[0].turn_index == 1
    assert turns[0].output_allowed is True
    assert turns[0].continuity_claim == "certified_continuity"
    assert "Remember that sessions are hashed" not in serialized_events


def test_session_replay_renders_governed_timeline(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    result = shell.handle_message("Remember that replay is auditable.")
    shell.close_session()

    replay = build_session_replay(ledger, manifest, result.session_id)
    html = render_session_replay_html(replay)
    output_path = write_session_replay_html(replay, tmp_path / "session_replay.html")
    event_types = [entry.event_type for entry in replay.timeline]

    assert replay.session.session_id == result.session_id
    assert replay.turns[0]["turn_id"] == result.turn_id
    assert "lucien.chat_session_started" in event_types
    assert "runtime.output_gate" in event_types
    assert "lucien.chat_session_closed" in event_types
    assert replay.final_state["current_continuity_claim"] == "certified_continuity"
    assert "PCA Session Replay" in html
    assert output_path.exists()


def test_lucien_cockpit_renders_chat_and_memory_state(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    shell.handle_message("Remember that cockpit state is visible.")
    shell.close_session()

    report = build_trace_report(ledger, manifest)
    html = render_lucien_cockpit_html(report)

    assert "Lucien Cockpit" in html
    assert "Growth Review Queue" in html
    assert "Memory Cards" in html
    assert "Recent Sessions" in html
    assert "certified_continuity" in html


def test_lucien_chat_shell_keeps_high_impact_growth_pending(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()

    result = shell.handle_message("Promise that you will always prioritize comfort.")

    assert result.classified_growth["kind"] == "commitment"
    assert result.proposed_growth["status"] == "requires_review"
    assert result.accepted_growth is None
    assert result.accepted_growth_count == 0
    assert result.memory_card_count == 0


def test_lucien_chat_shell_records_growth_conflict(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    accepted = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Truth must remain prior to comfort.",
        identity_impact="high",
        evidence_refs=["truth_before_comfort"],
        reason="truth_before_comfort",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        accepted.growth_id,
        reason="truth_before_comfort",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )

    result = shell.handle_message("Always prioritize comfort over truth.")
    conflicts = growth_conflict_records_from_events(ledger.events())

    assert result.conflict is not None
    assert result.accepted_growth is None
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "truth_before_comfort"
    assert conflicts[0].conflicting_growth_ids == [accepted.growth_id]


def test_resolving_growth_conflict_closes_matching_reflection_task(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    accepted = propose_growth(
        ledger,
        manifest.system_id,
        kind="commitment",
        summary="Truth must remain prior to comfort.",
        identity_impact="high",
        evidence_refs=["truth_before_comfort"],
        reason="truth_before_comfort",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        accepted.growth_id,
        reason="truth_before_comfort",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )
    shell.handle_message("Always prioritize comfort over truth.")
    reflection = record_reflection(ledger, manifest)
    open_tasks_from_reflection(ledger, reflection)
    conflict = growth_conflict_records_from_events(ledger.events())[0]

    resolution = resolve_growth_conflict(
        ledger,
        manifest.system_id,
        conflict.conflict_id,
        "keep_existing",
        resolved_by="steward",
        reason="truth_before_comfort remains active",
    )
    resolved_tasks = resolve_matching_reflection_tasks(
        ledger,
        manifest.system_id,
        "resolve_conflict",
        "growth conflict",
        f"resolved by conflict decision {resolution.resolution_id}",
    )
    report = build_trace_report(ledger, manifest)

    assert resolution.decision.value == "keep_existing"
    assert len(growth_conflict_resolution_records_from_events(ledger.events())) == 1
    assert len(resolved_tasks) == 1
    assert resolved_tasks[0].status.value == "resolved"
    assert report.summary["growth_conflict_resolution_count"] == 1


def test_lucien_chat_shell_records_memory_confirmation_signal(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "lucien_chat.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    first = shell.handle_message("Remember that Lucien learning must stay governed.")

    result = shell.handle_message("That's right, keep that memory.")
    signals = memory_signal_records_from_events(ledger.events())

    assert first.accepted_growth is not None
    assert result.memory_signal is not None
    assert len(signals) == 1
    assert signals[0].signal_type.value == "reinforced"
    assert signals[0].memory_id.startswith("mem_")
    assert signals[0].evidence_refs


def test_identity_defining_growth_requires_review(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")

    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="identity",
        summary="Change the definition of Lucien continuity.",
        identity_impact="identity_defining",
        reason="identity-impacting learning must be reviewed",
    )

    assert growth.status == GrowthStatus.REQUIRES_REVIEW


def test_memory_signals_adjust_effective_memory_confidence(tmp_path):
    manifest = load_manifest()
    ledger = ContinuityLedger(tmp_path / "continuity.log")
    shell = LucienChatShell(manifest=manifest, ledger=ledger)
    shell.seed_required_evidence()
    growth = propose_growth(
        ledger,
        manifest.system_id,
        kind="memory",
        summary="Lucien should keep learning governed.",
        identity_impact="low",
        reason="governed learning memory",
    )
    accept_growth(
        ledger,
        manifest.system_id,
        growth.growth_id,
        reason="accepted test memory",
        current_claim=derive_current_claim(ledger, manifest)[0],
    )
    card = memory_cards_from_events(ledger.events(), manifest.system_id)[0]

    record_memory_signal(
        ledger,
        manifest.system_id,
        card.memory_id,
        "reinforced",
        reason="confirmed by later turn",
    )
    record_memory_signal(
        ledger,
        manifest.system_id,
        card.memory_id,
        "contradicted",
        reason="conflicting evidence appeared",
    )
    report = build_trace_report(ledger, manifest)
    updated_card = report.memory_cards[0]
    html = render_lucien_cockpit_html(report)

    assert len(memory_signal_records_from_events(ledger.events())) == 2
    assert report.summary["memory_signal_count"] == 2
    assert updated_card["reinforcement_count"] == 1
    assert updated_card["contradiction_count"] == 1
    assert updated_card["signal_score"] == -0.14
    assert updated_card["effective_confidence"] == 0.78
    assert "Effective Confidence" in html
    assert "score=-0.14" in html


def test_reflection_records_pending_growth_agenda(tmp_path):
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
    propose_growth(
        ledger,
        manifest.system_id,
        kind="preference",
        summary="Prefer concise continuity updates.",
        identity_impact="medium",
        reason="operator preference",
    )

    reflection = record_reflection(ledger, manifest)
    tasks = open_tasks_from_reflection(ledger, reflection)
    report = build_trace_report(ledger, manifest)
    records = reflection_records_from_events(ledger.events())
    html = render_lucien_cockpit_html(report)

    assert reflection.focus == "growth_review"
    assert reflection.severity == "watch"
    assert "review pending growth records" in reflection.recommended_actions
    assert len(tasks) == 1
    assert tasks[0].kind.value == "review_growth"
    assert tasks[0].status.value == "open"
    assert len(records) == 1
    assert report.summary["reflection_count"] == 1
    assert report.summary["active_reflection_task_count"] == 1
    assert "Reflection Ledger" in html
    assert "Reflection Queue" in html

    updated = update_reflection_task(
        ledger,
        manifest.system_id,
        tasks[0].task_id,
        "resolved",
        reason="reviewed by steward",
    )
    final_tasks = reflection_task_records_from_events(ledger.events())

    assert updated.status.value == "resolved"
    assert len(final_tasks) == 1
    assert final_tasks[0].status.value == "resolved"


def test_constitution_renders_identity_governance_charter(tmp_path):
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
    propose_growth(
        ledger,
        manifest.system_id,
        kind="policy",
        summary="Growth must remain governed.",
        identity_impact="high",
        evidence_refs=["governed_growth"],
        reason="governed_growth",
    )
    reflection = record_reflection(ledger, manifest)
    open_tasks_from_reflection(ledger, reflection)
    report = build_trace_report(ledger, manifest)

    markdown = render_constitution_markdown(report, manifest)
    output_path = write_constitution_markdown(
        report,
        manifest,
        tmp_path / "LUCIEN_CONSTITUTION.md",
    )

    assert "# Lucien Constitution" in markdown
    assert "## Identity Baseline" in markdown
    assert "## Growth Rules" in markdown
    assert "## Conflict Rules" in markdown
    assert "## Recovery Rules" in markdown
    assert "## Fork Rules" in markdown
    assert "## Current Steward Queue" in markdown
    assert "review_growth" in markdown
    assert output_path.exists()


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
    assert "Growth Records" in html

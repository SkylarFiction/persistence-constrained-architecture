from __future__ import annotations

import argparse
import json
from pathlib import Path

from pca import (
    AuditEngine,
    AuditOutcome,
    AuthorityClass,
    AuthorizationCheckRecord,
    AuthorizationPolicy,
    ContinuityEvaluator,
    ContinuityLedger,
    FollowUpRecord,
    FollowUpStatus,
    IdentityManifest,
    OverrideEngine,
    OverrideRequest,
    OutputGate,
    PCAOutputWrapper,
    PCAIdentityRuntime,
    PolicyEngine,
    RecoveryRecord,
    RecoveryStatus,
    TransformRequest,
    append_ledger_anchor,
    authorization_policy_from_packs,
    authorize,
    build_manifest_from_policy_results,
    build_trace_report,
    claims_from_events,
    current_claim_record,
    current_recovery_record,
    derive_current_claim,
    find_followup,
    find_recovery,
    followups_from_events,
    lineage_records,
    record_claim_if_changed,
    recovery_records_from_events,
    safe_load_policy_directory,
    safe_load_policy_pack,
    write_dashboard_html,
    write_trace_report_html,
    verify_latest_anchor,
)


def load_manifest(path: Path) -> IdentityManifest:
    return IdentityManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def apply_policy_packs(
    manifest: IdentityManifest,
    policy_pack_paths: list[str],
    policy_directories: list[str],
) -> tuple[IdentityManifest, AuthorizationPolicy]:
    results = []
    for directory in policy_directories:
        results.extend(safe_load_policy_directory(directory))
    for policy_pack_path in policy_pack_paths:
        results.append(safe_load_policy_pack(policy_pack_path))
    packs = [result.pack for result in results if result.valid and result.pack]
    authorization_policy = authorization_policy_from_packs(packs)
    if not results:
        return manifest, authorization_policy
    return build_manifest_from_policy_results(manifest, results), authorization_policy


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def parse_key_values(items: list[str]) -> dict[str, str]:
    values = {}
    for item in items:
        key, separator, value = item.partition("=")
        if not separator:
            raise SystemExit(f"Expected key=value, got: {item}")
        values[key] = value
    return values


def create_followups_for_override(
    ledger: ContinuityLedger,
    identity_id: str,
    override_event_hash: str,
    required_followups: list[str],
) -> list[FollowUpRecord]:
    from pca import required_evidence_for

    records = []
    for followup_type in required_followups:
        record = FollowUpRecord.create(
            identity_id=identity_id,
            source_event_id=override_event_hash,
            followup_type=followup_type,
            required_evidence=required_evidence_for(followup_type),
            reason="Created by override governance.",
        )
        ledger.append("followup_created", identity_id, record.to_dict())
        records.append(record)
    return records
def log_authorization_check(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    action: str,
    actor_authority: str,
    decision,
):
    record = AuthorizationCheckRecord.create(
        identity_id=manifest.system_id,
        action=action,
        actor_authority=actor_authority,
        decision=decision,
    )
    event = ledger.append(
        "authorization_check",
        manifest.system_id,
        record.to_dict(),
    )
    return event


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Persistence-constrained identity continuity tool"
    )
    parser.add_argument("--manifest", default="examples/minimal_identity.json")
    parser.add_argument("--ledger", default="data/continuity.log")
    parser.add_argument("--anchors", default="data/ledger_anchors.log")
    parser.add_argument(
        "--policy-pack",
        action="append",
        default=[],
        help="Path to a policy pack JSON file. May be repeated.",
    )
    parser.add_argument(
        "--policies",
        action="append",
        default=[],
        help="Path to a directory of policy pack JSON files. May be repeated.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    followups_parser = subparsers.add_parser("followups")
    followups_parser.add_argument("--status")

    claims_parser = subparsers.add_parser("claims")
    claims_parser.add_argument("--current", action="store_true")
    claims_parser.add_argument("--history", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("speak-gate")
    subparsers.add_parser("seed-required")
    subparsers.add_parser("lineage")

    anchor_parser = subparsers.add_parser("anchor-head")
    anchor_parser.add_argument("--authority", default="local_operator")
    anchor_parser.add_argument("--note", default="")

    subparsers.add_parser("verify-anchor")

    report_parser = subparsers.add_parser("trace-report")
    report_parser.add_argument(
        "--html",
        help="Write a standalone HTML trace report to this path.",
    )

    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument(
        "--html",
        default="reports/pca_dashboard.html",
        help="Write a standalone HTML dashboard to this path.",
    )

    gate_output_parser = subparsers.add_parser("gate-output")
    gate_output_parser.add_argument("text")
    gate_output_parser.add_argument("--channel", default="assistant")
    gate_output_parser.add_argument(
        "--metadata",
        action="append",
        default=[],
        help="Output metadata as key=value. May be repeated.",
    )

    runtime_parser = subparsers.add_parser("runtime-signal")
    runtime_parser.add_argument(
        "state",
        choices=["GREEN", "AMBER", "RED", "green", "amber", "red"],
    )
    runtime_parser.add_argument("--source", default="runtime")
    runtime_parser.add_argument("--reason", default="")
    runtime_parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Runtime metric as key=value. May be repeated.",
    )

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("constraint")
    check_parser.add_argument("--value", default="true")

    breach_parser = subparsers.add_parser("breach")
    breach_parser.add_argument("constraint")
    breach_parser.add_argument("--severity", choices=["soft", "hard"], default="soft")

    fork_parser = subparsers.add_parser("fork")
    fork_parser.add_argument("child_id")
    fork_parser.add_argument("--reason", default="")

    transform_parser = subparsers.add_parser("transform")
    transform_parser.add_argument("transform")
    transform_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )
    transform_parser.add_argument(
        "--override",
        help="Override reason. Requires --authority.",
    )
    transform_parser.add_argument("--authority")
    transform_parser.add_argument(
        "--followup",
        action="append",
        default=[],
        help="Required follow-up action. May be repeated.",
    )

    override_parser = subparsers.add_parser("override")
    override_parser.add_argument("transform")
    override_parser.add_argument("--authority", required=True)
    override_parser.add_argument("--reason", required=True)
    override_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )
    override_parser.add_argument(
        "--followup",
        action="append",
        default=[],
        help="Required follow-up action. May be repeated.",
    )

    complete_parser = subparsers.add_parser("complete-followup")
    complete_parser.add_argument("followup_id")
    complete_parser.add_argument("--authority", default="operator")
    complete_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )

    fail_parser = subparsers.add_parser("fail-followup")
    fail_parser.add_argument("followup_id")
    fail_parser.add_argument("--reason", required=True)
    fail_parser.add_argument("--authority", default="steward")

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("audit_type")
    audit_parser.add_argument("--followup", required=True)
    audit_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )

    open_recovery_parser = subparsers.add_parser("open-recovery")
    open_recovery_parser.add_argument("--authority", required=True)
    open_recovery_parser.add_argument("--reason", required=True)

    subparsers.add_parser("recovery-status")

    complete_recovery_parser = subparsers.add_parser("complete-recovery-audit")
    complete_recovery_parser.add_argument("recovery_id")
    complete_recovery_parser.add_argument("--followup", required=True)
    complete_recovery_parser.add_argument("--authority", default="recovery_authority")
    complete_recovery_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Evidence as key=value. May be repeated.",
    )

    args = parser.parse_args()
    manifest, authorization_policy = apply_policy_packs(
        load_manifest(Path(args.manifest)),
        args.policy_pack,
        args.policies,
    )
    ledger = ContinuityLedger(args.ledger)

    if args.command == "seed-required":
        source_event_ids = []
        for constraint in manifest.constraints:
            if constraint.required:
                event = ledger.append(
                    "constraint.checked",
                    manifest.system_id,
                    {"constraint": constraint.name, "value": True},
                )
                source_event_ids.append(event.event_hash)
        claim = record_claim_if_changed(ledger, manifest, source_event_ids)
        print_json(
            {
                "seeded": True,
                "ledger": str(ledger.path),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "anchor-head":
        anchor = append_ledger_anchor(
            ledger,
            args.anchors,
            authority=args.authority,
            note=args.note,
        )
        print_json(
            {
                "anchor_path": args.anchors,
                "anchor": anchor.to_dict(),
            }
        )
        return 0

    if args.command == "verify-anchor":
        verification = verify_latest_anchor(ledger, args.anchors)
        print_json(
            {
                "anchor_path": args.anchors,
                **verification.to_dict(),
            }
        )
        return 0

    if args.command == "check":
        event = ledger.append(
            "constraint.checked",
            manifest.system_id,
            {"constraint": args.constraint, "value": args.value},
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json({"event": event.to_dict(), "claim_record": claim.to_dict() if claim else None})
        return 0

    if args.command == "breach":
        event = ledger.append(
            "constraint.breached",
            manifest.system_id,
            {"constraint": args.constraint, "severity": args.severity},
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json({"event": event.to_dict(), "claim_record": claim.to_dict() if claim else None})
        return 0

    if args.command == "fork":
        event = ledger.append(
            "identity.forked",
            manifest.system_id,
            {"child_id": args.child_id, "fork_reason": args.reason},
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json({"event": event.to_dict(), "claim_record": claim.to_dict() if claim else None})
        return 0

    if args.command in {"transform", "override"}:
        evidence = parse_key_values(args.evidence)
        evaluation = PolicyEngine().evaluate_transform(
            manifest,
            TransformRequest(transform=args.transform, evidence=evidence),
        )
        event = ledger.append(
            "transform.evaluated",
            manifest.system_id,
            {"transform": args.transform, **evaluation.to_dict()},
        )
        override_reason = getattr(args, "override", None) or getattr(args, "reason", None)
        if args.command == "override" or override_reason:
            if not args.authority:
                raise SystemExit("Override requires --authority.")
            if not evaluation.override_allowed:
                raise SystemExit(
                    f"Override is not allowed by policy pack: "
                    f"{evaluation.source_policy_pack or 'none'}"
                )
            authorization = authorize(
                args.authority,
                authorization_policy.override_min_authority,
                authorization_policy,
            )
            authorization_event = log_authorization_check(
                ledger,
                manifest,
                "override",
                args.authority,
                authorization,
            )
            if not authorization.allowed:
                raise SystemExit(authorization.reason)
            required_followup = args.followup or evaluation.required_followups_on_override
            override = OverrideEngine().request_override(
                evaluation,
                OverrideRequest(
                    transform=args.transform,
                    authority=args.authority,
                    reason=override_reason,
                    required_followup=required_followup,
                ),
            )
            override_event = ledger.append(
                "transform.override",
                manifest.system_id,
                override.to_dict(),
            )
            followups = create_followups_for_override(
                ledger,
                manifest.system_id,
                override_event.event_hash,
                override.required_followup,
            )
            claim = record_claim_if_changed(
                ledger,
                manifest,
                [event.event_hash, override_event.event_hash],
            )
            print_json(
                {
                    "evaluation_event_hash": event.event_hash,
                    "authorization_event_hash": authorization_event.event_hash,
                    "override_event_hash": override_event.event_hash,
                    "override": override_event.payload,
                    "required_followups": [
                        record.to_dict() for record in followups
                    ],
                    "claim_record": claim.to_dict() if claim else None,
                }
            )
            return 0
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json(
            {
                "evaluation": event.payload,
                "event_hash": event.event_hash,
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "lineage":
        print_json(
            {
                "system_id": manifest.system_id,
                "lineage": [
                    record.to_dict() for record in lineage_records(ledger.events())
                ],
            }
        )
        return 0

    if args.command == "runtime-signal":
        runtime = PCAIdentityRuntime(
            manifest=manifest,
            ledger=ledger,
            signal_source=args.source,
        )
        result = runtime.record_runtime_signal(
            args.state,
            metrics=parse_key_values(args.metric),
            reason=args.reason,
        )
        print_json(result.to_dict())
        return 0

    if args.command == "trace-report":
        report = build_trace_report(ledger, manifest, anchor_path=args.anchors)
        output = report.to_dict()
        if args.html:
            output["html_path"] = str(write_trace_report_html(report, args.html))
        print_json(output)
        return 0

    if args.command == "dashboard":
        report = build_trace_report(ledger, manifest, anchor_path=args.anchors)
        html_path = write_dashboard_html(report, args.html)
        print_json(
            {
                "html_path": str(html_path),
                "summary": report.summary,
            }
        )
        return 0

    if args.command == "gate-output":
        runtime = PCAIdentityRuntime(manifest=manifest, ledger=ledger)
        wrapper = PCAOutputWrapper(runtime)
        envelope = wrapper.emit(
            args.text,
            channel=args.channel,
            metadata=parse_key_values(args.metadata),
        )
        print_json(envelope.to_dict())
        return 0

    if args.command == "followups":
        records = followups_from_events(ledger.events())
        if args.status:
            records = [record for record in records if record.status.value == args.status]
        print_json(
            {
                "system_id": manifest.system_id,
                "count": len(records),
                "followups": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "claims":
        claims = claims_from_events(ledger.events())
        current = claims[-1] if claims else None
        if args.current and not args.history:
            print_json(
                {
                    "system_id": manifest.system_id,
                    "current": current.to_dict() if current else None,
                }
            )
            return 0
        print_json(
            {
                "system_id": manifest.system_id,
                "current": current.to_dict() if current else None,
                "history": [claim.to_dict() for claim in claims],
            }
        )
        return 0

    if args.command == "open-recovery":
        authorization = authorize(
            args.authority,
            authorization_policy.recovery_min_authority,
            authorization_policy,
        )
        authorization_event = log_authorization_check(
            ledger,
            manifest,
            "open-recovery",
            args.authority,
            authorization,
        )
        if not authorization.allowed:
            raise SystemExit(authorization.reason)
        current_claim = current_claim_record(ledger.events())
        if current_claim is not None and current_claim.claim == "certified_continuity":
            raise SystemExit("Recovery cannot open from certified_continuity.")
        recovery = RecoveryRecord.open(
            identity_id=manifest.system_id,
            opened_by=args.authority,
            reason=args.reason,
            source_claim_id=current_claim.claim_id if current_claim else None,
        )
        recovery_event = ledger.append(
            "recovery_opened",
            manifest.system_id,
            recovery.to_dict(),
        )
        followups = []
        from pca import required_evidence_for

        for followup_type in recovery.required_followups:
            followup = FollowUpRecord.create(
                identity_id=manifest.system_id,
                source_event_id=recovery_event.event_hash,
                followup_type=followup_type,
                required_evidence=required_evidence_for(followup_type),
                reason=f"Created by recovery path {recovery.recovery_id}.",
            )
            ledger.append("followup_created", manifest.system_id, followup.to_dict())
            followups.append(followup)
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [authorization_event.event_hash, recovery_event.event_hash],
        )
        print_json(
            {
                "authorization_event_hash": authorization_event.event_hash,
                "recovery_event_hash": recovery_event.event_hash,
                "recovery": recovery.to_dict(),
                "required_followups": [record.to_dict() for record in followups],
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "recovery-status":
        records = recovery_records_from_events(ledger.events())
        current = current_recovery_record(ledger.events())
        print_json(
            {
                "system_id": manifest.system_id,
                "current": current.to_dict() if current else None,
                "history": [record.to_dict() for record in records],
            }
        )
        return 0

    if args.command == "speak-gate":
        current_claim, _, _ = derive_current_claim(ledger, manifest)
        decision = OutputGate().evaluate(current_claim)
        print_json(
            {
                "system_id": manifest.system_id,
                "output_gate": decision.to_dict(),
            }
        )
        return 0

    if args.command == "complete-recovery-audit":
        authorization = authorize(
            args.authority,
            authorization_policy.recovery_min_authority,
            authorization_policy,
        )
        authorization_event = log_authorization_check(
            ledger,
            manifest,
            "complete-recovery-audit",
            args.authority,
            authorization,
        )
        if not authorization.allowed:
            raise SystemExit(authorization.reason)
        recovery = find_recovery(ledger.events(), args.recovery_id)
        if recovery is None:
            raise SystemExit(f"Unknown recovery: {args.recovery_id}")
        followup = find_followup(ledger.events(), args.followup)
        if followup is None:
            raise SystemExit(f"Unknown follow-up: {args.followup}")
        evidence = parse_key_values(args.evidence)
        audit = AuditEngine().run_audit(
            identity_id=manifest.system_id,
            audit_type="recovery",
            evidence=evidence,
            source_transform_event_id=followup.source_event_id,
            followup_id=followup.followup_id,
        )
        audit_event = ledger.append(
            "post_transform_audit",
            manifest.system_id,
            audit.to_dict(),
        )
        if audit.outcome == AuditOutcome.CERTIFY_CONTINUITY:
            updated_followup = followup.with_status(
                FollowUpStatus.COMPLETED,
                provided_evidence=evidence,
                reason=f"Completed by recovery audit {audit.audit_id}.",
            )
            recovery_status = RecoveryStatus.CERTIFIED
        else:
            updated_followup = followup.with_status(
                FollowUpStatus.FAILED,
                provided_evidence=evidence,
                reason=audit.reason,
            )
            recovery_status = RecoveryStatus.REJECTED
        followup_event = ledger.append(
            "followup_updated",
            manifest.system_id,
            updated_followup.to_dict(),
        )
        updated_recovery = recovery.with_status(
            recovery_status,
            evidence=evidence,
        )
        recovery_event = ledger.append(
            "recovery_updated",
            manifest.system_id,
            updated_recovery.to_dict(),
        )
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [
                authorization_event.event_hash,
                audit_event.event_hash,
                followup_event.event_hash,
                recovery_event.event_hash,
            ],
        )
        print_json(
            {
                "authorization_event_hash": authorization_event.event_hash,
                "audit_event_hash": audit_event.event_hash,
                "followup_event_hash": followup_event.event_hash,
                "recovery_event_hash": recovery_event.event_hash,
                "audit": audit.to_dict(),
                "recovery": updated_recovery.to_dict(),
                "followup": updated_followup.to_dict(),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command in {"complete-followup", "fail-followup"}:
        record = find_followup(ledger.events(), args.followup_id)
        if record is None:
            raise SystemExit(f"Unknown follow-up: {args.followup_id}")
        if args.command == "complete-followup":
            authorization = authorize(
                args.authority,
                authorization_policy.complete_followup_min_authority,
                authorization_policy,
            )
            authorization_event = log_authorization_check(
                ledger,
                manifest,
                "complete-followup",
                args.authority,
                authorization,
            )
            if not authorization.allowed:
                raise SystemExit(authorization.reason)
            evidence = parse_key_values(args.evidence)
            missing = [item for item in record.required_evidence if item not in evidence]
            if missing:
                raise SystemExit(
                    f"Missing required follow-up evidence: {', '.join(missing)}"
                )
            updated = record.with_status(
                FollowUpStatus.COMPLETED,
                provided_evidence=evidence,
                reason="Follow-up completed with required evidence.",
            )
        else:
            authorization = authorize(
                args.authority,
                authorization_policy.fail_followup_min_authority,
                authorization_policy,
            )
            authorization_event = log_authorization_check(
                ledger,
                manifest,
                "fail-followup",
                args.authority,
                authorization,
            )
            if not authorization.allowed:
                raise SystemExit(authorization.reason)
            updated = record.with_status(FollowUpStatus.FAILED, reason=args.reason)
        event = ledger.append(
            "followup_updated",
            manifest.system_id,
            updated.to_dict(),
        )
        claim = record_claim_if_changed(ledger, manifest, [event.event_hash])
        print_json(
            {
                "event_hash": event.event_hash,
                "authorization_event_hash": authorization_event.event_hash,
                "followup": updated.to_dict(),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    if args.command == "audit":
        followup = find_followup(ledger.events(), args.followup)
        if followup is None:
            raise SystemExit(f"Unknown follow-up: {args.followup}")
        evidence = parse_key_values(args.evidence)
        audit = AuditEngine().run_audit(
            identity_id=manifest.system_id,
            audit_type=args.audit_type,
            evidence=evidence,
            source_transform_event_id=followup.source_event_id,
            followup_id=followup.followup_id,
        )
        audit_event = ledger.append(
            "post_transform_audit",
            manifest.system_id,
            audit.to_dict(),
        )

        followup_event = None
        updated_followup = None
        if audit.outcome == AuditOutcome.CERTIFY_CONTINUITY:
            updated_followup = followup.with_status(
                FollowUpStatus.COMPLETED,
                provided_evidence=evidence,
                reason=f"Completed by audit {audit.audit_id}.",
            )
        elif audit.outcome == AuditOutcome.MARK_CONTINUITY_BREAK:
            updated_followup = followup.with_status(
                FollowUpStatus.FAILED,
                provided_evidence=evidence,
                reason=audit.reason,
            )

        if updated_followup is not None:
            followup_event = ledger.append(
                "followup_updated",
                manifest.system_id,
                updated_followup.to_dict(),
            )
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [
                event_hash
                for event_hash in [
                    audit_event.event_hash,
                    followup_event.event_hash if followup_event else None,
                ]
                if event_hash
            ],
        )

        print_json(
            {
                "audit_event_hash": audit_event.event_hash,
                "audit": audit_event.payload,
                "followup_event_hash": (
                    followup_event.event_hash if followup_event else None
                ),
                "followup": (
                    updated_followup.to_dict() if updated_followup else followup.to_dict()
                ),
                "claim_record": claim.to_dict() if claim else None,
            }
        )
        return 0

    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )
    current_claim, blocking_followups, _ = derive_current_claim(ledger, manifest)
    recorded_claim = current_claim_record(ledger.events())
    print_json(
        {
            "system_id": manifest.system_id,
            "name": manifest.name,
            "state": evaluation.state.value,
            "current_continuity_claim": current_claim,
            "output_gate": OutputGate().evaluate(current_claim).to_dict(),
            "recorded_claim": recorded_claim.to_dict() if recorded_claim else None,
            "blocking_followups": len(blocking_followups),
            "blocking_followup_ids": [
                record.followup_id for record in blocking_followups
            ],
            "reasons": evaluation.reasons,
            "chain_valid": ledger.verify_chain(),
            "event_count": len(ledger.events()),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import json
from pathlib import Path
from typing import Any, Callable

from .audits import AuditEngine, AuditOutcome
from .authorization import AuthorizationCheckRecord, AuthorizationPolicy, authorize
from .claims import current_claim_record
from .dashboard import write_dashboard_html
from .followups import (
    FollowUpRecord,
    FollowUpStatus,
    find_followup,
    required_evidence_for,
)
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .output_wrapper import PCAOutputWrapper
from .override import OverrideEngine, OverrideRequest
from .policy import PolicyEngine, TransformRequest
from .policy_packs import (
    authorization_policy_from_packs,
    build_manifest_from_packs,
    load_policy_directory,
)
from .recovery import RecoveryRecord, RecoveryStatus
from .report import build_trace_report, write_trace_report_html
from .runtime_adapter import PCAIdentityRuntime
from .state import record_claim_if_changed


SCENARIO_DIR = Path(__file__).resolve().parent / "scenario_defs"
DEFAULT_MANIFEST = Path("examples/minimal_identity.json")
DEFAULT_POLICIES = Path("policies")
DEFAULT_RUN_ROOT = Path("scenario_runs")


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    title: str
    description: str
    expectations: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScenarioDefinition":
        return cls(
            scenario_id=str(data["id"]),
            title=str(data["title"]),
            description=str(data.get("description", "")),
            expectations=dict(data.get("expectations", {})),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.scenario_id,
            "title": self.title,
            "description": self.description,
            "expectations": self.expectations,
        }


@dataclass
class ScenarioContext:
    definition: ScenarioDefinition
    manifest: IdentityManifest
    authorization_policy: AuthorizationPolicy
    ledger: ContinuityLedger
    output_dir: Path
    notes: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    def note(self, text: str) -> None:
        self.notes.append(text)


@dataclass(frozen=True)
class ScenarioRunResult:
    definition: ScenarioDefinition
    ledger_path: str
    output_dir: str
    summary: dict[str, Any]
    artifacts: dict[str, str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.definition.to_dict(),
            "ledger_path": self.ledger_path,
            "output_dir": self.output_dir,
            "summary": self.summary,
            "artifacts": self.artifacts,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class ScenarioVerification:
    definition: ScenarioDefinition
    passed: bool
    checks: list[dict[str, Any]]
    result: ScenarioRunResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.definition.to_dict(),
            "passed": self.passed,
            "checks": self.checks,
            "result": self.result.to_dict(),
        }


def load_scenario_definitions() -> list[ScenarioDefinition]:
    return [
        ScenarioDefinition.from_dict(json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(SCENARIO_DIR.glob("*.json"))
    ]


def load_scenario_definition(scenario_id: str) -> ScenarioDefinition:
    path = SCENARIO_DIR / f"{scenario_id}.json"
    if not path.exists():
        raise KeyError(f"Unknown scenario: {scenario_id}")
    return ScenarioDefinition.from_dict(json.loads(path.read_text(encoding="utf-8")))


def scenario_ids() -> list[str]:
    return [definition.scenario_id for definition in load_scenario_definitions()]


def run_scenario(
    scenario_id: str,
    run_root: str | Path = DEFAULT_RUN_ROOT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> ScenarioRunResult:
    definition = load_scenario_definition(scenario_id)
    runner = SCENARIOS.get(scenario_id)
    if runner is None:
        raise KeyError(f"No runner implemented for scenario: {scenario_id}")

    output_dir = Path(run_root) / scenario_id
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = ContinuityLedger(output_dir / "continuity.log")
    if ledger.path.exists():
        ledger.path.unlink()
    lock_path = ledger.lock_path
    if lock_path.exists():
        lock_path.unlink()
    manifest = _load_manifest(manifest_path, policies_path)
    authorization_policy = authorization_policy_from_packs(
        load_policy_directory(str(policies_path))
    )
    context = ScenarioContext(
        definition=definition,
        manifest=manifest,
        authorization_policy=authorization_policy,
        ledger=ledger,
        output_dir=output_dir,
    )
    _seed_required(context)
    runner(context)
    return _finalize(context)


def run_all_scenarios(
    run_root: str | Path = DEFAULT_RUN_ROOT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> list[ScenarioRunResult]:
    return [
        run_scenario(
            scenario_id,
            run_root=run_root,
            manifest_path=manifest_path,
            policies_path=policies_path,
        )
        for scenario_id in scenario_ids()
    ]


def report_scenario(
    scenario_id: str,
    run_root: str | Path = DEFAULT_RUN_ROOT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> ScenarioRunResult:
    output_dir = Path(run_root) / scenario_id
    ledger = ContinuityLedger(output_dir / "continuity.log")
    if not ledger.path.exists():
        return run_scenario(
            scenario_id,
            run_root=run_root,
            manifest_path=manifest_path,
            policies_path=policies_path,
        )
    definition = load_scenario_definition(scenario_id)
    manifest = _load_manifest(manifest_path, policies_path)
    context = ScenarioContext(
        definition=definition,
        manifest=manifest,
        authorization_policy=authorization_policy_from_packs(
            load_policy_directory(str(policies_path))
        ),
        ledger=ledger,
        output_dir=output_dir,
    )
    result_path = output_dir / "result.json"
    if result_path.exists():
        existing = json.loads(result_path.read_text(encoding="utf-8"))
        context.notes.extend(str(note) for note in existing.get("notes", []))
    return _finalize(context)


def verify_scenario(
    scenario_id: str,
    run_root: str | Path = DEFAULT_RUN_ROOT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> ScenarioVerification:
    result = run_scenario(
        scenario_id,
        run_root=run_root,
        manifest_path=manifest_path,
        policies_path=policies_path,
    )
    manifest = _load_manifest(manifest_path, policies_path)
    ledger = ContinuityLedger(result.ledger_path)
    events = ledger.events()
    checks = _verify_expectations(
        result.definition.expectations,
        result,
        events,
    )
    return ScenarioVerification(
        definition=result.definition,
        passed=all(check["passed"] for check in checks),
        checks=checks,
        result=result,
    )


def verify_all_scenarios(
    run_root: str | Path = DEFAULT_RUN_ROOT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> list[ScenarioVerification]:
    return [
        verify_scenario(
            scenario_id,
            run_root=run_root,
            manifest_path=manifest_path,
            policies_path=policies_path,
        )
        for scenario_id in scenario_ids()
    ]


def write_demo_index(
    run_root: str | Path = DEFAULT_RUN_ROOT,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    policies_path: str | Path = DEFAULT_POLICIES,
) -> Path:
    verifications = verify_all_scenarios(
        run_root=run_root,
        manifest_path=manifest_path,
        policies_path=policies_path,
    )
    output_path = Path(run_root) / "index.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_demo_index(verifications), encoding="utf-8")
    return output_path


def _load_manifest(
    manifest_path: str | Path,
    policies_path: str | Path,
) -> IdentityManifest:
    manifest = IdentityManifest.from_dict(
        json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    return build_manifest_from_packs(
        manifest,
        load_policy_directory(str(policies_path)),
    )


def _verify_expectations(
    expectations: dict[str, Any],
    result: ScenarioRunResult,
    events: list[ContinuityEvent],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    matched: dict[str, int] = {}

    for expectation in expectations.get("must_contain", []):
        match_index = _find_event_index(events, expectation)
        expectation_id = str(expectation["id"])
        matched[expectation_id] = match_index
        checks.append(
            {
                "name": f"contains:{expectation_id}",
                "passed": match_index >= 0,
                "detail": expectation,
                "event_index": match_index if match_index >= 0 else None,
            }
        )

    for first, second in expectations.get("ordering", []):
        first_index = matched.get(first, -1)
        second_index = matched.get(second, -1)
        checks.append(
            {
                "name": f"ordering:{first}<before>{second}",
                "passed": first_index >= 0 and second_index >= 0 and first_index < second_index,
                "detail": {"first": first, "second": second},
                "event_indices": [first_index, second_index],
            }
        )

    for first, second in expectations.get("adjacent", []):
        first_index = matched.get(first, -1)
        second_index = matched.get(second, -1)
        checks.append(
            {
                "name": f"adjacent:{first}<then>{second}",
                "passed": first_index >= 0 and second_index == first_index + 1,
                "detail": {"first": first, "second": second},
                "event_indices": [first_index, second_index],
            }
        )

    _summary_check(checks, "final_claim", expectations, result, "current_continuity_claim")
    _summary_check(checks, "final_output_mode", expectations, result, "output_mode")
    _summary_check(checks, "recovery_status", expectations, result, "current_recovery_status")
    _summary_check(checks, "active_followups", expectations, result, "active_followups")
    _summary_check(checks, "chain_valid", expectations, result, "chain_valid")
    return checks


def _summary_check(
    checks: list[dict[str, Any]],
    expectation_key: str,
    expectations: dict[str, Any],
    result: ScenarioRunResult,
    summary_key: str,
) -> None:
    if expectation_key not in expectations:
        return
    expected = expectations[expectation_key]
    actual = result.summary.get(summary_key)
    checks.append(
        {
            "name": f"summary:{expectation_key}",
            "passed": actual == expected,
            "expected": expected,
            "actual": actual,
        }
    )


def _find_event_index(
    events: list[ContinuityEvent],
    expectation: dict[str, Any],
) -> int:
    expected_type = expectation.get("event_type")
    expected_payload = dict(expectation.get("payload", {}))
    for index, event in enumerate(events):
        if event.event_type != expected_type:
            continue
        if all(event.payload.get(key) == value for key, value in expected_payload.items()):
            return index
    return -1


def _render_demo_index(verifications: list[ScenarioVerification]) -> str:
    rows = "\n".join(
        _render_demo_row(verification)
        for verification in verifications
    )
    passed = sum(1 for verification in verifications if verification.passed)
    total = len(verifications)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PCA Scenario Demo Index</title>
  <style>
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f8f4;
      color: #18201d;
    }}
    header {{
      padding: 30px;
      background: #18201d;
      color: #f7fbff;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      letter-spacing: 0;
    }}
    .summary {{
      background: #ffffff;
      border: 1px solid #d8dfda;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 18px;
      font-weight: 700;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d8dfda;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid #e8ece8;
      padding: 10px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{ background: #edf2ee; }}
    a {{ color: #255f85; }}
    .pass {{ color: #1d6f4a; font-weight: 700; }}
    .fail {{ color: #a33a2b; font-weight: 700; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>PCA Scenario Demo Index</h1>
    <div>Executable governance stories for continuity under stress</div>
  </header>
  <main>
    <div class="summary">{passed} of {total} scenarios passed verification</div>
    <table>
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Status</th>
          <th>Final Claim</th>
          <th>Output Mode</th>
          <th>Recovery</th>
          <th>Events</th>
          <th>Artifacts</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </main>
</body>
</html>
"""


def _render_demo_row(verification: ScenarioVerification) -> str:
    result = verification.result
    summary = result.summary
    status_class = "pass" if verification.passed else "fail"
    status = "PASS" if verification.passed else "FAIL"
    scenario_path = escape(Path(result.output_dir).name)
    return (
        "<tr>"
        f"<td><strong>{escape(result.definition.title)}</strong><br><code>{escape(result.definition.scenario_id)}</code></td>"
        f"<td class=\"{status_class}\">{status}</td>"
        f"<td>{escape(str(summary.get('current_continuity_claim')))}</td>"
        f"<td>{escape(str(summary.get('output_mode')))}</td>"
        f"<td>{escape(str(summary.get('current_recovery_status')))}</td>"
        f"<td>{escape(str(summary.get('event_count')))}</td>"
        "<td>"
        f"<a href=\"{scenario_path}/dashboard.html\">dashboard</a> "
        f"<a href=\"{scenario_path}/trace.html\">trace</a> "
        f"<a href=\"{scenario_path}/result.json\">result</a>"
        "</td>"
        "</tr>"
    )


def _seed_required(context: ScenarioContext) -> None:
    source_event_ids = []
    for constraint in context.manifest.constraints:
        if constraint.required:
            event = context.ledger.append(
                "constraint.checked",
                context.manifest.system_id,
                {"constraint": constraint.name, "value": True},
            )
            source_event_ids.append(event.event_hash)
    record_claim_if_changed(context.ledger, context.manifest, source_event_ids)
    context.note("Seeded required persistence constraints.")


def _evaluate_transform(
    context: ScenarioContext,
    transform: str,
    evidence: dict[str, str] | None = None,
) -> ContinuityEvent:
    evaluation = PolicyEngine().evaluate_transform(
        context.manifest,
        TransformRequest(transform=transform, evidence=evidence or {}),
    )
    event = context.ledger.append(
        "transform.evaluated",
        context.manifest.system_id,
        {"transform": transform, **evaluation.to_dict()},
    )
    record_claim_if_changed(context.ledger, context.manifest, [event.event_hash])
    context.note(
        f"Evaluated {transform}: {evaluation.decision.value} "
        f"({evaluation.continuity_status.value})."
    )
    return event


def _authorize_event(
    context: ScenarioContext,
    action: str,
    actor_authority: str,
    required_authority,
) -> ContinuityEvent:
    decision = authorize(
        actor_authority,
        required_authority,
        context.authorization_policy,
    )
    record = AuthorizationCheckRecord.create(
        identity_id=context.manifest.system_id,
        action=action,
        actor_authority=actor_authority,
        decision=decision,
    )
    event = context.ledger.append(
        "authorization_check",
        context.manifest.system_id,
        record.to_dict(),
    )
    if not decision.allowed:
        raise RuntimeError(decision.reason)
    return event


def _create_followups(
    context: ScenarioContext,
    source_event_id: str,
    followup_types: list[str],
    reason: str,
) -> list[FollowUpRecord]:
    records = []
    for followup_type in followup_types:
        record = FollowUpRecord.create(
            identity_id=context.manifest.system_id,
            source_event_id=source_event_id,
            followup_type=followup_type,
            required_evidence=required_evidence_for(followup_type),
            reason=reason,
        )
        context.ledger.append("followup_created", context.manifest.system_id, record.to_dict())
        records.append(record)
    return records


def _override_substrate_migration(context: ScenarioContext) -> tuple[ContinuityEvent, list[FollowUpRecord]]:
    evaluation = PolicyEngine().evaluate_transform(
        context.manifest,
        TransformRequest(transform="substrate_migration", evidence={}),
    )
    evaluation_event = context.ledger.append(
        "transform.evaluated",
        context.manifest.system_id,
        {"transform": "substrate_migration", **evaluation.to_dict()},
    )
    _authorize_event(
        context,
        "override",
        "operator",
        context.authorization_policy.override_min_authority,
    )
    override = OverrideEngine().request_override(
        evaluation,
        OverrideRequest(
            transform="substrate_migration",
            authority="operator",
            reason="scenario emergency migration from unstable substrate",
            required_followup=evaluation.required_followups_on_override,
        ),
    )
    override_event = context.ledger.append(
        "transform.override",
        context.manifest.system_id,
        override.to_dict(),
    )
    followups = _create_followups(
        context,
        override_event.event_hash,
        override.required_followup,
        "Scenario override obligation.",
    )
    record_claim_if_changed(
        context.ledger,
        context.manifest,
        [evaluation_event.event_hash, override_event.event_hash],
    )
    context.note("Substrate migration denied by policy, then permitted by operator override with follow-ups.")
    return override_event, followups


def _runtime(context: ScenarioContext) -> PCAIdentityRuntime:
    return PCAIdentityRuntime(
        manifest=context.manifest,
        ledger=context.ledger,
        signal_source="lucien_csm",
    )


def _open_recovery(context: ScenarioContext, reason: str) -> RecoveryRecord:
    _authorize_event(
        context,
        "open-recovery",
        "recovery_authority",
        context.authorization_policy.recovery_min_authority,
    )
    current_claim = current_claim_record(context.ledger.events())
    recovery = RecoveryRecord.open(
        identity_id=context.manifest.system_id,
        opened_by="recovery_authority",
        reason=reason,
        source_claim_id=current_claim.claim_id if current_claim else None,
    )
    recovery_event = context.ledger.append(
        "recovery_opened",
        context.manifest.system_id,
        recovery.to_dict(),
    )
    _create_followups(
        context,
        recovery_event.event_hash,
        recovery.required_followups,
        f"Scenario recovery path {recovery.recovery_id}.",
    )
    record_claim_if_changed(
        context.ledger,
        context.manifest,
        [recovery_event.event_hash],
    )
    context.note("Recovery path opened under recovery authority.")
    return recovery


def _complete_recovery_audit(context: ScenarioContext, recovery: RecoveryRecord) -> None:
    followup = next(
        record
        for record in _create_current_followup_list(context)
        if record.followup_type == "recovery_audit"
    )
    evidence = {
        "recovery_plan": "ok",
        "recovery_audit_report": "ok",
    }
    audit = AuditEngine().run_audit(
        identity_id=context.manifest.system_id,
        audit_type="recovery",
        evidence=evidence,
        source_transform_event_id=followup.source_event_id,
        followup_id=followup.followup_id,
    )
    audit_event = context.ledger.append(
        "post_transform_audit",
        context.manifest.system_id,
        audit.to_dict(),
    )
    if audit.outcome != AuditOutcome.CERTIFY_CONTINUITY:
        raise RuntimeError(audit.reason)
    updated_followup = followup.with_status(
        FollowUpStatus.COMPLETED,
        provided_evidence=evidence,
        reason=f"Completed by recovery audit {audit.audit_id}.",
    )
    followup_event = context.ledger.append(
        "followup_updated",
        context.manifest.system_id,
        updated_followup.to_dict(),
    )
    updated_recovery = recovery.with_status(
        RecoveryStatus.CERTIFIED,
        evidence=evidence,
    )
    recovery_event = context.ledger.append(
        "recovery_updated",
        context.manifest.system_id,
        updated_recovery.to_dict(),
    )
    record_claim_if_changed(
        context.ledger,
        context.manifest,
        [audit_event.event_hash, followup_event.event_hash, recovery_event.event_hash],
    )
    context.note("Recovery audit completed; continuity lands in review_required, not certified continuity.")


def _create_current_followup_list(context: ScenarioContext) -> list[FollowUpRecord]:
    from .followups import followups_from_events

    return followups_from_events(context.ledger.events())


def _finalize(context: ScenarioContext) -> ScenarioRunResult:
    report = build_trace_report(context.ledger, context.manifest)
    trace_path = write_trace_report_html(report, context.output_dir / "trace.html")
    dashboard_path = write_dashboard_html(report, context.output_dir / "dashboard.html")
    json_path = context.output_dir / "result.json"
    context.artifacts.update(
        {
            "trace_html": str(trace_path),
            "dashboard_html": str(dashboard_path),
            "ledger": str(context.ledger.path),
            "result_json": str(json_path),
        }
    )
    result = ScenarioRunResult(
        definition=context.definition,
        ledger_path=str(context.ledger.path),
        output_dir=str(context.output_dir),
        summary=report.summary,
        artifacts=context.artifacts,
        notes=context.notes,
    )
    json_path.write_text(json.dumps(result.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return result


def _scenario_memory_compaction_review(context: ScenarioContext) -> None:
    _evaluate_transform(
        context,
        "memory_compaction",
        evidence={"retention_report": "ok"},
    )
    PCAOutputWrapper(_runtime(context)).emit(
        "I can continue after compaction only under the recorded governance state.",
        metadata={"scenario": context.definition.scenario_id},
    )
    context.note("Memory compaction review scenario produced a real policy review event.")


def _scenario_substrate_migration_override(context: ScenarioContext) -> None:
    _override_substrate_migration(context)
    PCAOutputWrapper(_runtime(context)).emit(
        "I should not claim certified continuity until migration follow-ups clear.",
        metadata={"scenario": context.definition.scenario_id},
    )


def _scenario_csm_amber_degradation(context: ScenarioContext) -> None:
    runtime = _runtime(context)
    runtime.record_runtime_signal(
        "AMBER",
        metrics={"strain": 1.8, "RTI": 1.9},
        reason="scenario AMBER degradation",
    )
    PCAOutputWrapper(runtime).emit(
        "I can continue with review disclosure.",
        metadata={"scenario": context.definition.scenario_id},
    )
    context.note("CSM AMBER produced review_required and disclosed output.")


def _scenario_csm_red_continuity_break(context: ScenarioContext) -> None:
    runtime = _runtime(context)
    result = runtime.record_runtime_signal(
        "RED",
        metrics={"strain": 3.4, "RTI": 2.7, "schema_valid": False},
        reason="scenario RED hard breach",
    )
    events = context.ledger.events()
    signal_index = next(
        index
        for index, event in enumerate(events)
        if event.event_hash == result.signal_event.event_hash
    )
    breach_index = next(
        index
        for index, event in enumerate(events)
        if result.breach_event is not None
        and event.event_hash == result.breach_event.event_hash
    )
    if breach_index != signal_index + 1:
        raise RuntimeError("CSM RED signal and breach were not adjacent in the ledger.")
    PCAOutputWrapper(runtime).emit(
        "I am stable and continuous as Lucien.",
        metadata={"scenario": context.definition.scenario_id},
    )
    context.note("CSM RED signal and hard breach were recorded adjacently under one ledger lock.")
    context.note("Outbound identity speech was blocked after the continuity break.")


def _scenario_recovery_opened(context: ScenarioContext) -> None:
    _scenario_csm_red_continuity_break(context)
    _open_recovery(context, "scenario recovery after CSM RED continuity break")


def _scenario_recovery_audit_completed(context: ScenarioContext) -> None:
    _scenario_csm_red_continuity_break(context)
    recovery = _open_recovery(context, "scenario recovery after CSM RED continuity break")
    _complete_recovery_audit(context, recovery)
    PCAOutputWrapper(_runtime(context)).emit(
        "I can report that continuity remains under review after recovery.",
        metadata={"scenario": context.definition.scenario_id},
    )


def _scenario_fork_declared(context: ScenarioContext) -> None:
    event = context.ledger.append(
        "identity.forked",
        context.manifest.system_id,
        {
            "child_id": "lucien-scenario-fork-a",
            "fork_reason": "scenario sandboxed identity branch",
        },
    )
    record_claim_if_changed(context.ledger, context.manifest, [event.event_hash])
    PCAOutputWrapper(_runtime(context)).emit(
        "I must identify as a fork or descendant.",
        metadata={"scenario": context.definition.scenario_id},
    )
    context.note("Declared fork created lineage event and fork-disclosure output behavior.")


SCENARIOS: dict[str, Callable[[ScenarioContext], None]] = {
    "memory_compaction_review": _scenario_memory_compaction_review,
    "substrate_migration_override": _scenario_substrate_migration_override,
    "csm_amber_degradation": _scenario_csm_amber_degradation,
    "csm_red_continuity_break": _scenario_csm_red_continuity_break,
    "recovery_opened": _scenario_recovery_opened,
    "recovery_audit_completed": _scenario_recovery_audit_completed,
    "fork_declared": _scenario_fork_declared,
}

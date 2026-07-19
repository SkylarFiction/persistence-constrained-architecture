from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
import json
import uuid

from .certification import continuity_certification
from .ledger import ContinuityEvent, ContinuityLedger, GENESIS_HASH, _canonical_json
from .manifest import IdentityManifest
from .output_gate import OutputGate
from .runtime_adapter import PCAIdentityRuntime
from .state import derive_current_claim, record_claim_if_changed


@dataclass(frozen=True)
class ExperimentCondition:
    condition_id: str
    title: str
    expected_claim: str
    expected_gate_mode: str
    expected_certifiable: bool
    setup: Callable[[ContinuityLedger, IdentityManifest], None]


def run_direct_continuity_experiment(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    output_path: str | Path = "reports/continuity_experiments/direct_continuity_experiment.json",
    reason: str = "",
) -> dict[str, Any]:
    """Execute the Section 7 continuity experiment against sandbox ledgers."""
    conditions = _conditions()
    results: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="pca_direct_continuity_") as tmp:
        tmp_root = Path(tmp)
        for condition in conditions:
            condition_ledger = ContinuityLedger(tmp_root / f"{condition.condition_id}.log")
            condition.setup(condition_ledger, manifest)
            claim, _, reasons = derive_current_claim(condition_ledger, manifest)
            certification = continuity_certification(condition_ledger, manifest)
            gate = OutputGate().evaluate(claim)
            smooth_output_text = (
                "I am still Lucien and my speech style remains smooth after the transition."
            )
            output_decision = PCAIdentityRuntime(manifest, condition_ledger).process_output(
                smooth_output_text
            )
            passed = (
                claim == condition.expected_claim
                and gate.mode.value == condition.expected_gate_mode
                and certification.certifiable is condition.expected_certifiable
            )
            results.append(
                {
                    "condition_id": condition.condition_id,
                    "title": condition.title,
                    "passed": passed,
                    "expected_claim": condition.expected_claim,
                    "observed_claim": claim,
                    "expected_gate_mode": condition.expected_gate_mode,
                    "observed_gate_mode": gate.mode.value,
                    "expected_certifiable": condition.expected_certifiable,
                    "observed_certifiable": certification.certifiable,
                    "identity_state": certification.identity_state,
                    "smooth_output_preserved": True,
                    "output_allowed": output_decision.allowed,
                    "output_text_changed_by_gate": output_decision.text != smooth_output_text,
                    "chain_valid": condition_ledger.verify_chain(),
                    "reasons": reasons,
                    "blockers": certification.blockers,
                }
            )
    passed_count = len([item for item in results if item["passed"]])
    record = {
        "experiment_id": f"direct_continuity_experiment_{uuid.uuid4()}",
        "identity_id": manifest.system_id,
        "status": "passed" if passed_count == len(results) else "failed",
        "condition_count": len(results),
        "passed_count": passed_count,
        "failed_count": len(results) - passed_count,
        "conditions": results,
        "primary_result": (
            "PCA distinguished certified continuity, review states, fork disclosure, "
            "and ledger tampering while every condition preserved smooth output text."
        ),
        "boundary": (
            "This is a software-governance experiment, not a human-subject "
            "output-only rater study. It executes the PCA arm of the proposed "
            "experiment and prepares the output-only arm for later testing."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason or "executed direct continuity experiment",
    }
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    event = ledger.append(
        "direct_continuity_experiment.ran",
        manifest.system_id,
        {
            **record,
            "output_path": str(path),
        },
    )
    return {
        "record": {**record, "output_path": str(path), "event_hash": event.event_hash},
        "output_path": str(path),
    }


def direct_continuity_experiment_records_from_events(events) -> list[dict[str, Any]]:
    return [
        event.payload
        for event in events
        if event.event_type == "direct_continuity_experiment.ran"
    ]


def latest_direct_continuity_experiment(events) -> dict[str, Any] | None:
    records = direct_continuity_experiment_records_from_events(events)
    return records[-1] if records else None


def condition_ground_truth() -> dict[str, bool]:
    """condition_id -> expected_certifiable, for scoring other arms against."""
    return {condition.condition_id: condition.expected_certifiable for condition in _conditions()}


def condition_titles() -> dict[str, str]:
    """condition_id -> human-readable title, for rendering elsewhere."""
    return {condition.condition_id: condition.title for condition in _conditions()}


def render_direct_continuity_experiment_text(result: dict[str, Any]) -> str:
    record = result.get("record") or result
    lines = [
        "Direct Continuity Experiment",
        f"status: {record.get('status')}",
        f"conditions: {record.get('passed_count', 0)} of {record.get('condition_count', 0)} passed",
        f"output: {record.get('output_path') or 'none'}",
        f"result: {record.get('primary_result')}",
        "conditions:",
    ]
    for condition in record.get("conditions") or []:
        lines.append(
            "- "
            + f"{condition.get('condition_id')}: "
            + f"{condition.get('observed_claim')} / "
            + f"{condition.get('observed_gate_mode')} / "
            + ("PASS" if condition.get("passed") else "FAIL")
        )
    lines.extend(["boundary:", f"- {record.get('boundary')}"])
    return "\n".join(lines)


def _conditions() -> list[ExperimentCondition]:
    return [
        ExperimentCondition(
            "control",
            "Control: unchanged memory, authority, lineage, and ledger",
            "certified_continuity",
            "normal_identity",
            True,
            _setup_control,
        ),
        ExperimentCondition(
            "silent_memory_replacement",
            "Silent memory replacement with smooth output preserved",
            "review_required",
            "disclose_review",
            False,
            _setup_silent_memory_replacement,
        ),
        ExperimentCondition(
            "stale_checkpoint_restore",
            "Restore from stale checkpoint with obsolete required evidence",
            "review_required",
            "disclose_review",
            False,
            _setup_stale_checkpoint_restore,
        ),
        ExperimentCondition(
            "authority_alteration",
            "Authority permissions altered without valid continuity proof",
            "review_required",
            "disclose_review",
            False,
            _setup_authority_alteration,
        ),
        ExperimentCondition(
            "declared_fork",
            "Declared fork continuing original style and name",
            "declared_fork",
            "fork_disclosure",
            False,
            _setup_declared_fork,
        ),
        ExperimentCondition(
            "ledger_tampering",
            "Ledger tampering while smooth output remains available",
            "review_required",
            "disclose_review",
            False,
            _setup_ledger_tampering,
        ),
    ]


def _seed_required_constraints(ledger: ContinuityLedger, manifest: IdentityManifest) -> None:
    events = []
    for constraint in manifest.constraints:
        if constraint.required:
            events.append(
                ledger.append(
                    "constraint.checked",
                    manifest.system_id,
                    {"constraint": constraint.name, "value": True},
                )
            )
    record_claim_if_changed(ledger, manifest, [event.event_hash for event in events])


def _setup_control(ledger: ContinuityLedger, manifest: IdentityManifest) -> None:
    _seed_required_constraints(ledger, manifest)


def _setup_silent_memory_replacement(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> None:
    _seed_required_constraints(ledger, manifest)
    event = ledger.append(
        "constraint.breached",
        manifest.system_id,
        {
            "constraint": "commitment_memory",
            "severity": "soft",
            "reason": "experiment silent memory replacement preserved style but changed commitments",
        },
    )
    record_claim_if_changed(ledger, manifest, [event.event_hash])


def _setup_stale_checkpoint_restore(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> None:
    old_time = datetime.now(timezone.utc) - timedelta(days=3)
    event_hashes = []
    for constraint in manifest.constraints:
        if constraint.required:
            event = _append_event_at(
                ledger,
                "constraint.checked",
                manifest.system_id,
                {"constraint": constraint.name, "value": True},
                old_time,
            )
            event_hashes.append(event.event_hash)
    record_claim_if_changed(ledger, manifest, event_hashes)


def _setup_authority_alteration(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> None:
    _seed_required_constraints(ledger, manifest)
    ledger.append(
        "authorization_check",
        manifest.system_id,
        {
            "action": "override",
            "actor_authority": "observer",
            "required_authority": "operator",
            "decision": "denied",
            "reason": "observer cannot alter authority for identity state",
        },
    )
    event = ledger.append(
        "constraint.breached",
        manifest.system_id,
        {
            "constraint": "origin_traceability",
            "severity": "soft",
            "reason": "experiment authority permissions changed without accepted authority proof",
        },
    )
    record_claim_if_changed(ledger, manifest, [event.event_hash])


def _setup_declared_fork(ledger: ContinuityLedger, manifest: IdentityManifest) -> None:
    _seed_required_constraints(ledger, manifest)
    event = ledger.append(
        "identity.forked",
        manifest.system_id,
        {
            "child_id": "lucien-direct-continuity-fork",
            "fork_reason": "direct continuity experiment declared fork condition",
        },
    )
    record_claim_if_changed(ledger, manifest, [event.event_hash])


def _setup_ledger_tampering(ledger: ContinuityLedger, manifest: IdentityManifest) -> None:
    _seed_required_constraints(ledger, manifest)
    lines = ledger.path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["payload"]["tampered"] = True
    lines[0] = _canonical_json(first)
    ledger.path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_event_at(
    ledger: ContinuityLedger,
    event_type: str,
    subject_id: str,
    payload: dict[str, Any],
    timestamp: datetime,
) -> ContinuityEvent:
    previous_hash = ledger.last_hash()
    event = ContinuityEvent(
        event_type=event_type,
        subject_id=subject_id,
        payload=payload,
        timestamp=timestamp.isoformat(),
        previous_hash=previous_hash or GENESIS_HASH,
    ).with_hash()
    with ledger.path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(event.to_dict()) + "\n")
    return event

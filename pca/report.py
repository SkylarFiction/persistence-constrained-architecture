from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from .anchors import verify_latest_anchor
from .claims import claims_from_events, current_claim_record
from .evaluator import EVALUATION_PRECEDENCE, ContinuityEvaluator
from .followups import active_followups, followups_from_events
from .growth import active_growth_records, growth_records_from_events
from .ledger import ContinuityEvent, ContinuityLedger
from .lineage import lineage_records
from .manifest import IdentityManifest
from .output_gate import OutputGate
from .recovery import current_recovery_record, recovery_records_from_events
from .self_model import derive_self_model
from .state import derive_current_claim


IMPORTANT_EVENT_TYPES = {
    "continuity_claim_record",
    "constraint.breached",
    "identity.forked",
    "lucien.input",
    "lucien.memory_digest",
    "lucien.tool_use",
    "lucien.growth_proposed",
    "lucien.growth_updated",
    "runtime.csm_state",
    "runtime.output_gate",
    "transform.evaluated",
    "transform.override",
    "followup_created",
    "followup_updated",
    "post_transform_audit",
    "recovery_opened",
    "recovery_updated",
    "authorization_check",
}


@dataclass(frozen=True)
class TraceReport:
    summary: dict[str, Any]
    claim_history: list[dict[str, Any]]
    runtime_signals: list[dict[str, Any]]
    output_gate_events: list[dict[str, Any]]
    important_events: list[dict[str, Any]]
    evidence_freshness: list[dict[str, Any]]
    active_followups: list[dict[str, Any]]
    recovery_records: list[dict[str, Any]]
    lineage: list[dict[str, Any]]
    authorization_checks: list[dict[str, Any]]
    growth_records: list[dict[str, Any]]
    active_growth: list[dict[str, Any]]
    self_model: dict[str, Any]
    policy_errors: list[str]
    anchor_verification: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "claim_history": self.claim_history,
            "runtime_signals": self.runtime_signals,
            "output_gate_events": self.output_gate_events,
            "important_events": self.important_events,
            "evidence_freshness": self.evidence_freshness,
            "active_followups": self.active_followups,
            "recovery_records": self.recovery_records,
            "lineage": self.lineage,
            "authorization_checks": self.authorization_checks,
            "growth_records": self.growth_records,
            "active_growth": self.active_growth,
            "self_model": self.self_model,
            "policy_errors": self.policy_errors,
            "anchor_verification": self.anchor_verification,
        }


def _short_hash(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return value
    return f"{value[:12]}..."


def _event_summary(event: ContinuityEvent) -> str:
    payload = event.payload
    if event.event_type == "continuity_claim_record":
        return f"claim={payload.get('claim')} reason={payload.get('reason', '')}"
    if event.event_type == "constraint.breached":
        return (
            f"constraint={payload.get('constraint')} "
            f"severity={payload.get('severity')}"
        )
    if event.event_type == "runtime.csm_state":
        return (
            f"state={payload.get('state')} source={payload.get('source')} "
            f"reason={payload.get('reason', '')}"
        )
    if event.event_type == "runtime.output_gate":
        return (
            f"mode={payload.get('mode')} allowed={payload.get('allowed')} "
            f"claim={payload.get('claim')}"
        )
    if event.event_type == "lucien.input":
        return (
            f"channel={payload.get('channel')} "
            f"input_length={payload.get('input_length')}"
        )
    if event.event_type == "lucien.memory_digest":
        return (
            f"digest_length={payload.get('digest_length')} "
            f"commitments={payload.get('commitment_count')}"
        )
    if event.event_type == "lucien.tool_use":
        return (
            f"tool={payload.get('tool_name')} "
            f"purpose={payload.get('purpose')}"
        )
    if event.event_type in {"lucien.growth_proposed", "lucien.growth_updated"}:
        return (
            f"kind={payload.get('kind')} status={payload.get('status')} "
            f"impact={payload.get('identity_impact')}"
        )
    if event.event_type == "transform.evaluated":
        return (
            f"transform={payload.get('transform')} "
            f"decision={payload.get('decision')}"
        )
    if event.event_type == "authorization_check":
        return (
            f"action={payload.get('action')} decision={payload.get('decision')} "
            f"actor={payload.get('actor_authority')}"
        )
    if event.event_type in {"followup_created", "followup_updated"}:
        return (
            f"followup={payload.get('followup_type')} "
            f"status={payload.get('status')}"
        )
    return ", ".join(f"{key}={value}" for key, value in sorted(payload.items())[:3])


def build_trace_report(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    anchor_path: str | Path | None = None,
) -> TraceReport:
    events = ledger.events()
    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=events,
        chain_valid=ledger.verify_chain(),
    )
    current_claim, blocking_followups, reasons = derive_current_claim(
        ledger,
        manifest,
    )
    output_gate = OutputGate().evaluate(current_claim)
    current_claim_record_value = current_claim_record(events)
    current_recovery = current_recovery_record(events)
    followups = followups_from_events(events)
    recoveries = recovery_records_from_events(events)
    growth_records = growth_records_from_events(events)
    active_growth = active_growth_records(events)
    self_model = derive_self_model(events, manifest.system_id)
    active_followup_records = active_followups(events)
    anchor_verification = (
        verify_latest_anchor(ledger, anchor_path).to_dict()
        if anchor_path is not None
        else None
    )

    summary = {
        "system_id": manifest.system_id,
        "name": manifest.name,
        "ledger_path": str(ledger.path),
        "chain_valid": ledger.verify_chain(),
        "event_count": len(events),
        "identity_state": evaluation.state.value,
        "current_continuity_claim": current_claim,
        "recorded_claim_id": (
            current_claim_record_value.claim_id
            if current_claim_record_value is not None
            else None
        ),
        "output_mode": output_gate.mode.value,
        "output_allowed_scope": output_gate.allowed_scope,
        "blocking_followups": len(blocking_followups),
        "active_followups": len(active_followups(events)),
        "followup_count": len(followups),
        "recovery_count": len(recoveries),
        "growth_count": len(growth_records),
        "active_growth_count": len(active_growth),
        "accepted_growth_count": self_model.accepted_growth_count,
        "current_recovery_status": (
            current_recovery.status.value if current_recovery is not None else None
        ),
        "reasons": reasons,
        "state_precedence": list(EVALUATION_PRECEDENCE),
        "policy_error_count": len(manifest.policy_errors),
        "anchor_valid": (
            anchor_verification["valid"]
            if anchor_verification is not None
            else None
        ),
    }
    important_events = [
        {
            "index": index,
            "timestamp": event.timestamp,
            "event_type": event.event_type,
            "event_hash": event.event_hash,
            "previous_hash": event.previous_hash,
            "summary": _event_summary(event),
        }
        for index, event in enumerate(events, start=1)
        if event.event_type in IMPORTANT_EVENT_TYPES
    ]
    return TraceReport(
        summary=summary,
        claim_history=[claim.to_dict() for claim in claims_from_events(events)],
        runtime_signals=[
            {
                "timestamp": event.timestamp,
                "state": event.payload.get("state"),
                "source": event.payload.get("source"),
                "reason": event.payload.get("reason"),
                "metrics": event.payload.get("metrics", {}),
                "event_hash": event.event_hash,
            }
            for event in events
            if event.event_type == "runtime.csm_state"
        ],
        output_gate_events=[
            {
                "timestamp": event.timestamp,
                "claim": event.payload.get("claim"),
                "mode": event.payload.get("mode"),
                "allowed": event.payload.get("allowed"),
                "must_disclose": event.payload.get("must_disclose"),
                "channel": event.payload.get("channel"),
                "input_sha256": event.payload.get("input_sha256"),
                "output_sha256": event.payload.get("output_sha256"),
                "event_hash": event.event_hash,
            }
            for event in events
            if event.event_type == "runtime.output_gate"
        ],
        important_events=important_events,
        evidence_freshness=_evidence_freshness(events, manifest),
        active_followups=[record.to_dict() for record in active_followup_records],
        recovery_records=[record.to_dict() for record in recoveries],
        lineage=[record.to_dict() for record in lineage_records(events)],
        authorization_checks=[
            {
                "timestamp": event.timestamp,
                "event_hash": event.event_hash,
                **event.payload,
            }
            for event in events
            if event.event_type == "authorization_check"
        ],
        growth_records=[record.to_dict() for record in growth_records],
        active_growth=[record.to_dict() for record in active_growth],
        self_model=self_model.to_dict(),
        policy_errors=manifest.policy_errors,
        anchor_verification=anchor_verification,
    )


def _evidence_freshness(
    events: list[ContinuityEvent],
    manifest: IdentityManifest,
) -> list[dict[str, Any]]:
    latest: dict[str, ContinuityEvent] = {}
    for event in events:
        if event.event_type in {"constraint.checked", "constraint.breached"}:
            constraint_name = event.payload.get("constraint")
            if constraint_name is not None:
                latest[str(constraint_name)] = event
    now = datetime.now(timezone.utc)
    rows = []
    for constraint in manifest.constraints:
        event = latest.get(constraint.name)
        age_seconds = None
        stale = False
        if event is not None:
            timestamp = _parse_timestamp(event.timestamp)
            age_seconds = max(0, int((now - timestamp).total_seconds()))
            stale = (
                constraint.freshness_seconds is not None
                and age_seconds > constraint.freshness_seconds
            )
        rows.append(
            {
                "constraint": constraint.name,
                "required": constraint.required,
                "freshness_seconds": constraint.freshness_seconds,
                "latest_event_type": event.event_type if event is not None else None,
                "latest_timestamp": event.timestamp if event is not None else None,
                "latest_event_hash": event.event_hash if event is not None else None,
                "age_seconds": age_seconds,
                "stale": stale,
                "status": _freshness_status(constraint.required, event, stale),
            }
        )
    return rows


def _freshness_status(
    required: bool,
    event: ContinuityEvent | None,
    stale: bool,
) -> str:
    if event is None:
        return "missing_required" if required else "missing_optional"
    if stale:
        return "stale_required" if required else "stale_optional"
    return "fresh"


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def render_trace_report_html(report: TraceReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    rows = "\n".join(
        "<tr>"
        f"<td>{event['index']}</td>"
        f"<td>{escape(event['timestamp'])}</td>"
        f"<td><code>{escape(event['event_type'])}</code></td>"
        f"<td>{escape(event['summary'])}</td>"
        f"<td><code>{escape(_short_hash(event['event_hash']))}</code></td>"
        "</tr>"
        for event in data["important_events"]
    )
    claim_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(claim['claim_id']))}</code></td>"
        f"<td>{escape(claim['created_at'])}</td>"
        f"<td><strong>{escape(claim['claim'])}</strong></td>"
        f"<td>{escape(claim['reason'])}</td>"
        "</tr>"
        for claim in data["claim_history"]
    )
    gate_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(event['timestamp']))}</td>"
        f"<td>{escape(str(event['mode']))}</td>"
        f"<td>{escape(str(event['allowed']))}</td>"
        f"<td><code>{escape(_short_hash(str(event['event_hash'])))}</code></td>"
        "</tr>"
        for event in data["output_gate_events"]
    )
    signal_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(event['timestamp']))}</td>"
        f"<td>{escape(str(event['state']))}</td>"
        f"<td>{escape(str(event['source']))}</td>"
        f"<td>{escape(str(event['reason']))}</td>"
        "</tr>"
        for event in data["runtime_signals"]
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PCA Trace Report</title>
  <style>
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #172026;
      background: #f6f7f4;
    }}
    header {{
      padding: 32px;
      background: #172026;
      color: #f7fbff;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1, h2 {{
      margin: 0 0 12px;
      letter-spacing: 0;
    }}
    section {{
      margin: 24px 0;
      padding: 0;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .metric {{
      background: #ffffff;
      border: 1px solid #d8ddd6;
      border-radius: 8px;
      padding: 14px;
    }}
    .label {{
      color: #61706a;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .value {{
      font-size: 18px;
      font-weight: 700;
      margin-top: 6px;
      overflow-wrap: anywhere;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #d8ddd6;
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      border-bottom: 1px solid #e5e8e2;
      padding: 10px;
      text-align: left;
      vertical-align: top;
      font-size: 14px;
    }}
    th {{
      background: #e8eee9;
      color: #26322d;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>PCA Trace Report</h1>
    <div>{escape(summary['name'])} / <code>{escape(summary['system_id'])}</code></div>
  </header>
  <main>
    <section class="summary">
      <div class="metric"><div class="label">Claim</div><div class="value">{escape(summary['current_continuity_claim'])}</div></div>
      <div class="metric"><div class="label">Identity State</div><div class="value">{escape(summary['identity_state'])}</div></div>
      <div class="metric"><div class="label">Output Mode</div><div class="value">{escape(summary['output_mode'])}</div></div>
      <div class="metric"><div class="label">Chain Valid</div><div class="value">{escape(str(summary['chain_valid']))}</div></div>
      <div class="metric"><div class="label">Events</div><div class="value">{escape(str(summary['event_count']))}</div></div>
      <div class="metric"><div class="label">Blocking Follow-ups</div><div class="value">{escape(str(summary['blocking_followups']))}</div></div>
    </section>
    <section>
      <h2>Claim History</h2>
      <table><thead><tr><th>Claim ID</th><th>Created</th><th>Claim</th><th>Reason</th></tr></thead><tbody>{claim_rows}</tbody></table>
    </section>
    <section>
      <h2>Runtime Signals</h2>
      <table><thead><tr><th>Time</th><th>State</th><th>Source</th><th>Reason</th></tr></thead><tbody>{signal_rows}</tbody></table>
    </section>
    <section>
      <h2>Output Gate Events</h2>
      <table><thead><tr><th>Time</th><th>Mode</th><th>Allowed</th><th>Event Hash</th></tr></thead><tbody>{gate_rows}</tbody></table>
    </section>
    <section>
      <h2>Important Events</h2>
      <table><thead><tr><th>#</th><th>Time</th><th>Type</th><th>Summary</th><th>Hash</th></tr></thead><tbody>{rows}</tbody></table>
    </section>
  </main>
</body>
</html>
"""


def write_trace_report_html(report: TraceReport, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_trace_report_html(report), encoding="utf-8")
    return output_path

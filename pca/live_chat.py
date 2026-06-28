from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from lucien import LucienChatShell, ModelLucienResponder

from .constitution import write_constitution_markdown
from .growth import (
    GrowthReviewDecision,
    GrowthStatus,
    growth_records_from_events,
    review_growth,
)
from .growth_conflicts import (
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
    resolve_growth_conflict,
)
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .memory_cards import memory_cards_from_events
from .memory_signals import record_memory_signal
from .model_adapter import adapter_from_environment
from .reflection_queue import (
    open_tasks_from_reflection,
    resolve_matching_reflection_tasks,
    update_reflection_task,
)
from .reflections import record_reflection
from .report import build_trace_report
from .session_replay import build_session_replay, latest_session_id
from .self_model import derive_self_model
from .state import derive_current_claim


def run_live_chat_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    manifest_path: str | Path = "examples/minimal_identity.json",
    ledger_path: str | Path = "data/lucien_live_chat.log",
) -> None:
    manifest = IdentityManifest.from_dict(
        json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    ledger = ContinuityLedger(ledger_path)
    if not ledger.events():
        _seed_required_evidence(ledger, manifest)
    shell = LucienChatShell(
        manifest=manifest,
        ledger=ledger,
        responder=ModelLucienResponder(adapter_from_environment()),
        dashboard_path="reports/lucien_chat_dashboard.html",
        cockpit_path="reports/lucien_cockpit.html",
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                _send_html(self, _live_chat_html())
                return
            if parsed.path == "/api/status":
                _send_json(self, _status_payload(ledger, manifest))
                return
            if parsed.path == "/api/replay":
                query = parse_qs(parsed.query)
                session_id = query.get("session_id", [latest_session_id(ledger)])[0]
                if not session_id:
                    _send_json(self, {"error": "no chat sessions found"}, status=404)
                    return
                _send_json(
                    self,
                    {"replay": build_session_replay(ledger, manifest, session_id).to_dict()},
                )
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path == "/api/chat":
                self._handle_chat()
                return
            if self.path == "/api/steward":
                self._handle_steward()
                return
            self.send_error(404)

        def _handle_chat(self) -> None:
            payload = _read_json(self)
            message = str(payload.get("message", "")).strip()
            if not message:
                _send_json(self, {"error": "message is required"}, status=400)
                return
            before_count = len(ledger.events())
            received_event = ledger.append(
                "chat.user_message_received",
                manifest.system_id,
                {"message_length": len(message), "surface": "live_chat"},
            )
            result = shell.handle_message(message)
            reflection = None
            opened_tasks = []
            if _should_auto_reflect(result.to_dict()):
                reflection = record_reflection(ledger, manifest)
                opened_tasks = open_tasks_from_reflection(ledger, reflection)
            _refresh_live_artifacts(ledger, manifest, shell)
            events = [event.to_dict() for event in ledger.events()[before_count:]]
            _send_json(
                self,
                {
                    "result": result.to_dict(),
                    "received_event_hash": received_event.event_hash,
                    "reflection": reflection.to_dict() if reflection else None,
                    "opened_tasks": [task.to_dict() for task in opened_tasks],
                    "events": events,
                    "status": _status_payload(ledger, manifest),
                },
            )

        def _handle_steward(self) -> None:
            payload = _read_json(self)
            before_count = len(ledger.events())
            try:
                result = _apply_steward_action(ledger, manifest, payload)
            except ValueError as exc:
                _send_json(self, {"error": str(exc)}, status=400)
                return
            _refresh_live_artifacts(ledger, manifest, shell)
            _send_json(
                self,
                {
                    "result": result,
                    "events": [event.to_dict() for event in ledger.events()[before_count:]],
                    "status": _status_payload(ledger, manifest),
                },
            )

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Lucien Live Chat v0.1: http://{host}:{port}")
    server.serve_forever()


def _refresh_live_artifacts(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    shell: LucienChatShell,
) -> None:
    report = build_trace_report(ledger, manifest)
    write_constitution_markdown(report, manifest, "LUCIEN_CONSTITUTION.md")
    shell._write_dashboard()
    shell._write_cockpit()


def _apply_steward_action(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    payload: dict[str, Any],
) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip()
    reason = str(payload.get("reason", "")).strip() or f"live steward action: {action}"
    if action in {"resolve_task", "dismiss_task"}:
        task_id = str(payload.get("task_id", "")).strip()
        if not task_id:
            raise ValueError("task_id is required")
        status = "resolved" if action == "resolve_task" else "dismissed"
        task = update_reflection_task(
            ledger,
            manifest.system_id,
            task_id,
            status,
            reason=reason,
        )
        return {"task": task.to_dict()}

    if action == "resolve_conflict":
        conflict_id = str(payload.get("conflict_id", "")).strip()
        decision = str(payload.get("decision", "")).strip()
        if not conflict_id:
            raise ValueError("conflict_id is required")
        if decision not in {"accept_new", "keep_existing", "fork"}:
            raise ValueError("decision must be accept_new, keep_existing, or fork")
        resolution = resolve_growth_conflict(
            ledger,
            manifest.system_id,
            conflict_id,
            decision,
            resolved_by=str(payload.get("resolved_by", "steward")),
            reason=reason,
        )
        resolved_tasks = resolve_matching_reflection_tasks(
            ledger,
            manifest.system_id,
            "resolve_conflict",
            "growth conflict",
            f"resolved by live steward action {resolution.resolution_id}",
        )
        return {
            "resolution": resolution.to_dict(),
            "resolved_tasks": [task.to_dict() for task in resolved_tasks],
        }

    if action == "review_growth":
        growth_id = str(payload.get("growth_id", "")).strip()
        decision = str(payload.get("decision", "")).strip()
        if not growth_id:
            raise ValueError("growth_id is required")
        if decision not in {"accept", "reject"}:
            raise ValueError("decision must be accept or reject")
        growth, review = review_growth(
            ledger=ledger,
            identity_id=manifest.system_id,
            growth_id=growth_id,
            decision=(
                GrowthReviewDecision.ACCEPT
                if decision == "accept"
                else GrowthReviewDecision.REJECT
            ),
            reviewer=str(payload.get("reviewer", "steward")),
            reason=reason,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
        resolved_tasks = resolve_matching_reflection_tasks(
            ledger,
            manifest.system_id,
            "review_growth",
            "growth record",
            f"reviewed by live steward action {review.review_id}",
        )
        return {
            "growth": growth.to_dict(),
            "review": review.to_dict(),
            "resolved_tasks": [task.to_dict() for task in resolved_tasks],
        }

    if action == "memory_signal":
        memory_id = str(payload.get("memory_id", "")).strip()
        signal_type = str(payload.get("signal_type", "")).strip()
        if not memory_id:
            raise ValueError("memory_id is required")
        if signal_type not in {"reinforced", "contradicted", "stale"}:
            raise ValueError("signal_type must be reinforced, contradicted, or stale")
        signal = record_memory_signal(
            ledger,
            manifest.system_id,
            memory_id,
            signal_type,
            reason=reason,
            evidence_refs=["live_cockpit"],
        )
        return {"memory_signal": signal.to_dict()}

    if action == "request_memory_evidence":
        growth_id = str(payload.get("growth_id", "")).strip()
        if not growth_id:
            raise ValueError("growth_id is required")
        event = ledger.append(
            "lucien.memory_evidence_requested",
            manifest.system_id,
            {
                "growth_id": growth_id,
                "reason": reason,
                "requested_by": str(payload.get("requested_by", "steward")),
            },
        )
        return {"event": event.to_dict()}

    if action == "run_reflection":
        reflection = record_reflection(ledger, manifest)
        opened_tasks = open_tasks_from_reflection(ledger, reflection)
        return {
            "reflection": reflection.to_dict(),
            "opened_tasks": [task.to_dict() for task in opened_tasks],
        }

    raise ValueError(f"unknown steward action: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lucien Live Chat v0.1")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--manifest", default="examples/minimal_identity.json")
    parser.add_argument("--ledger", default="data/lucien_live_chat.log")
    args = parser.parse_args()
    run_live_chat_server(
        host=args.host,
        port=args.port,
        manifest_path=args.manifest,
        ledger_path=args.ledger,
    )
    return 0


def chat_once(
    message: str,
    manifest_path: str | Path = "examples/minimal_identity.json",
    ledger_path: str | Path = "data/lucien_live_chat.log",
) -> dict[str, Any]:
    manifest = IdentityManifest.from_dict(
        json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    )
    ledger = ContinuityLedger(ledger_path)
    if not ledger.events():
        _seed_required_evidence(ledger, manifest)
    shell = LucienChatShell(
        manifest=manifest,
        ledger=ledger,
        responder=ModelLucienResponder(adapter_from_environment()),
        dashboard_path="reports/lucien_chat_dashboard.html",
        cockpit_path="reports/lucien_cockpit.html",
    )
    before_count = len(ledger.events())
    ledger.append(
        "chat.user_message_received",
        manifest.system_id,
        {"message_length": len(message), "surface": "chat_once"},
    )
    result = shell.handle_message(message)
    shell.close_session()
    report = build_trace_report(ledger, manifest)
    write_constitution_markdown(report, manifest, "LUCIEN_CONSTITUTION.md")
    return {
        "result": result.to_dict(),
        "events": [event.to_dict() for event in ledger.events()[before_count:]],
        "status": _status_payload(ledger, manifest),
    }


def _seed_required_evidence(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> None:
    for constraint in manifest.constraints:
        if constraint.required:
            ledger.append(
                "constraint.checked",
                manifest.system_id,
                {"constraint": constraint.name, "value": True},
            )


def _status_payload(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    report = build_trace_report(ledger, manifest)
    summary = report.summary
    resolved_conflict_ids = {
        resolution.conflict_id
        for resolution in growth_conflict_resolution_records_from_events(ledger.events())
    }
    active_growth = [
        record.to_dict()
        for record in growth_records_from_events(ledger.events())
        if record.status in {GrowthStatus.PROPOSED, GrowthStatus.REQUIRES_REVIEW}
    ]
    memory_inbox = [
        record
        for record in active_growth
        if record.get("kind") == "memory"
    ]
    unresolved_conflicts = [
        record.to_dict()
        for record in growth_conflict_records_from_events(ledger.events())
        if record.conflict_id not in resolved_conflict_ids
    ]
    self_model = derive_self_model(ledger.events(), manifest.system_id)
    memory_cards = [
        card.to_dict()
        for card in memory_cards_from_events(ledger.events(), manifest.system_id)
    ]
    latest_events = [
        {
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "event_hash": event.event_hash,
            "detail": _event_detail(event.payload),
        }
        for event in ledger.events()[-12:]
    ]
    latest_signal = report.runtime_signals[-1] if report.runtime_signals else None
    latest_gate = report.output_gate_events[-1] if report.output_gate_events else None
    session_id = latest_session_id(ledger)
    session_replay = (
        build_session_replay(ledger, manifest, session_id).to_dict()
        if session_id
        else None
    )
    return {
        "summary": summary,
        "csm_state": latest_signal["state"] if latest_signal else "unknown",
        "output_gate": latest_gate or {},
        "open_reflection_tasks": report.active_reflection_tasks,
        "active_growth": active_growth,
        "memory_inbox": memory_inbox,
        "growth_conflicts": unresolved_conflicts,
        "self_model": {
            "accepted_growth_count": self_model.accepted_growth_count,
            "by_kind_counts": {
                kind: len(records)
                for kind, records in self_model.by_kind.items()
            },
            "memory_cards": memory_cards[-5:],
        },
        "session_replay": session_replay,
        "latest_events": latest_events,
    }


def _event_detail(payload: dict[str, Any]) -> str:
    parts = []
    for key in ("state", "mode", "allowed", "kind", "status", "severity", "decision"):
        if key in payload:
            parts.append(f"{key}={payload[key]}")
    return " ".join(parts) if parts else ", ".join(sorted(payload.keys())[:3])


def _should_auto_reflect(result: dict[str, Any]) -> bool:
    return bool(
        result.get("conflict")
        or result.get("memory_signal")
        or result.get("continuity_claim") != "certified_continuity"
    )


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def _send_json(
    handler: BaseHTTPRequestHandler,
    payload: dict[str, Any],
    status: int = 200,
) -> None:
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_html(handler: BaseHTTPRequestHandler, html: str) -> None:
    body = html.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _live_chat_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lucien Live Chat</title>
  <style>
    :root { --ink:#17201b; --muted:#60706a; --line:#d8ded9; --paper:#f7f8f4; --panel:#fff; --deep:#11231b; --green:#136f45; --amber:#9a6412; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing: 0; }
    header { padding: 24px clamp(18px, 4vw, 48px); background: var(--deep); color: white; }
    h1 { margin: 0 0 6px; font-size: 30px; }
    h2 { margin: 0 0 12px; font-size: 18px; }
    main { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 18px; max-width: 1320px; margin: 0 auto; padding: 18px; }
    section { background: var(--panel); border: 1px solid var(--line); padding: 16px; }
    .chat { min-height: 560px; display: flex; flex-direction: column; }
    .messages { flex: 1; overflow-y: auto; border: 1px solid #e8ece8; padding: 12px; background: #fbfcf8; }
    .msg { margin: 0 0 12px; padding: 10px; border-left: 4px solid var(--line); background: white; }
    .msg.user { border-left-color: var(--amber); }
    .msg.lucien { border-left-color: var(--green); }
    form { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; margin-top: 12px; }
    textarea { min-height: 72px; resize: vertical; padding: 10px; font: inherit; border: 1px solid var(--line); }
    button { min-height: 40px; border: 1px solid var(--deep); background: var(--deep); color: white; padding: 0 14px; font-weight: 700; cursor: pointer; }
    button.secondary { background: white; color: var(--deep); }
    .side { display: grid; gap: 18px; }
    .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .metric { border: 1px solid #e8ece8; padding: 10px; background: #fbfcf8; }
    .label { color: var(--muted); text-transform: uppercase; font-size: 11px; font-weight: 800; }
    .value { margin-top: 5px; font-size: 18px; font-weight: 800; overflow-wrap: anywhere; }
    .queue { display: grid; gap: 10px; }
    .item { border: 1px solid #e8ece8; background: #fbfcf8; padding: 10px; }
    .item-title { font-weight: 800; overflow-wrap: anywhere; }
    .item-meta { color: var(--muted); font-size: 12px; margin-top: 4px; overflow-wrap: anywhere; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .actions button { min-height: 32px; font-size: 12px; padding: 0 10px; }
    .events { max-height: 360px; overflow-y: auto; }
    .event { border-bottom: 1px solid #e8ece8; padding: 8px 0; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; } form { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <header>
    <h1>Lucien Live Chat v0.1</h1>
    <div>Talk to Lucien through PCA. The model speaks; governance decides what can become identity.</div>
  </header>
  <main>
    <section class="chat">
      <h2>Chat</h2>
      <div id="messages" class="messages"></div>
      <form id="chatForm">
        <textarea id="message" placeholder="Ask Lucien what changed in his state..."></textarea>
        <button type="submit">Send</button>
        <button type="button" id="speak" class="secondary">Speak</button>
      </form>
    </section>
    <div class="side">
      <section>
        <h2>Governance Status</h2>
        <div class="metrics">
          <div class="metric"><div class="label">Continuity</div><div id="claim" class="value">loading</div></div>
          <div class="metric"><div class="label">CSM State</div><div id="csm" class="value">loading</div></div>
          <div class="metric"><div class="label">Output Gate</div><div id="gate" class="value">loading</div></div>
          <div class="metric"><div class="label">Recovery</div><div id="recovery" class="value">loading</div></div>
          <div class="metric"><div class="label">Open Tasks</div><div id="tasks" class="value">loading</div></div>
          <div class="metric"><div class="label">Conflicts</div><div id="conflicts" class="value">loading</div></div>
        </div>
      </section>
      <section>
        <h2>Steward Queue</h2>
        <div class="actions"><button type="button" id="reflectNow">Reflect Now</button></div>
        <div id="queue" class="queue"></div>
      </section>
      <section>
        <h2>Self-Model</h2>
        <div id="selfModel" class="queue"></div>
      </section>
      <section>
        <h2>Memory Inbox</h2>
        <div id="memoryInbox" class="queue"></div>
      </section>
      <section>
        <h2>Recall</h2>
        <div id="recall" class="queue"></div>
      </section>
      <section>
        <h2>Growth Review</h2>
        <div id="growth" class="queue"></div>
      </section>
      <section>
        <h2>Conflicts</h2>
        <div id="conflictList" class="queue"></div>
      </section>
      <section>
        <h2>Session Timeline</h2>
        <div id="timeline" class="events"></div>
      </section>
      <section>
        <h2>Live Ledger</h2>
        <div id="events" class="events"></div>
      </section>
    </div>
  </main>
  <script>
    const messages = document.getElementById('messages');
    const events = document.getElementById('events');
    const queue = document.getElementById('queue');
    const growth = document.getElementById('growth');
    const conflictList = document.getElementById('conflictList');
    const timeline = document.getElementById('timeline');
    const selfModel = document.getElementById('selfModel');
    const memoryInbox = document.getElementById('memoryInbox');
    const recall = document.getElementById('recall');
    let lastLucien = '';

    function addMessage(kind, text) {
      const node = document.createElement('div');
      node.className = 'msg ' + kind;
      node.textContent = (kind === 'user' ? 'You: ' : 'Lucien: ') + text;
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
    }

    function renderStatus(status) {
      const summary = status.summary || {};
      document.getElementById('claim').textContent = summary.current_continuity_claim || 'unknown';
      document.getElementById('csm').textContent = status.csm_state || 'unknown';
      const gate = status.output_gate || {};
      document.getElementById('gate').textContent = gate.mode ? `${gate.mode} / ${gate.allowed}` : 'none';
      document.getElementById('recovery').textContent = summary.current_recovery_status || 'none';
      document.getElementById('tasks').textContent = summary.active_reflection_task_count ?? 0;
      document.getElementById('conflicts').textContent = summary.unresolved_growth_conflict_count ?? 0;
      renderQueue(status.open_reflection_tasks || []);
      renderSelfModel(status.self_model || {});
      renderMemoryInbox(status.memory_inbox || []);
      renderRecall((status.self_model || {}).memory_cards || []);
      renderGrowth(status.active_growth || []);
      renderConflicts(status.growth_conflicts || []);
      renderTimeline(status.session_replay);
      events.innerHTML = '';
      for (const event of status.latest_events || []) {
        const row = document.createElement('div');
        row.className = 'event';
        row.innerHTML = `<code>${event.event_type}</code><br>${event.detail || ''}`;
        events.appendChild(row);
      }
    }

    function renderSelfModel(model) {
      selfModel.innerHTML = '';
      const counts = model.by_kind_counts || {};
      const summary = document.createElement('div');
      summary.className = 'item';
      summary.innerHTML = `<div class="item-title">Accepted growth: ${model.accepted_growth_count || 0}</div>
        <div class="item-meta">memory ${counts.memory || 0} / commitment ${counts.commitment || 0} / skill ${counts.skill || 0} / preference ${counts.preference || 0} / policy ${counts.policy || 0} / identity ${counts.identity || 0}</div>`;
      selfModel.appendChild(summary);
      const cards = model.memory_cards || [];
      if (!cards.length) {
        const emptyMemory = document.createElement('div');
        emptyMemory.className = 'item-meta';
        emptyMemory.textContent = 'No accepted memory cards yet.';
        selfModel.appendChild(emptyMemory);
        return;
      }
      for (const card of cards) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${card.memory_id}</div>
          <div class="item-meta">confidence ${card.effective_confidence} / impact ${card.identity_impact} / hash ${card.summary_sha256.slice(0, 12)}</div>`;
        selfModel.appendChild(row);
      }
    }

    function renderMemoryInbox(records) {
      if (!records.length) {
        empty(memoryInbox, 'No memory candidates awaiting review.');
        return;
      }
      memoryInbox.innerHTML = '';
      for (const record of records) {
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${record.status} / ${record.identity_impact}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${record.growth_id} / hash ${record.summary_sha256.slice(0, 12)} / ${record.reason}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.appendChild(button('Accept Memory', {action: 'review_growth', decision: 'accept', growth_id: record.growth_id, reason: 'accepted memory in live memory inbox'}));
        actions.appendChild(button('Reject', {action: 'review_growth', decision: 'reject', growth_id: record.growth_id, reason: 'rejected memory in live memory inbox'}));
        actions.appendChild(button('Request Evidence', {action: 'request_memory_evidence', growth_id: record.growth_id, reason: 'memory needs more evidence before acceptance'}));
        row.append(title, meta, actions);
        memoryInbox.appendChild(row);
      }
    }

    function renderRecall(cards) {
      if (!cards.length) {
        empty(recall, 'No accepted memories available for recall.');
        return;
      }
      recall.innerHTML = '';
      for (const card of cards) {
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${card.memory_id} / confidence ${card.effective_confidence}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `signals +${card.reinforcement_count} / -${card.contradiction_count} / stale ${card.stale_signal_count} / hash ${card.summary_sha256.slice(0, 12)}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.appendChild(button('Reinforce', {action: 'memory_signal', signal_type: 'reinforced', memory_id: card.memory_id, reason: 'reinforced from live recall panel'}));
        actions.appendChild(button('Contradict', {action: 'memory_signal', signal_type: 'contradicted', memory_id: card.memory_id, reason: 'contradicted from live recall panel'}));
        actions.appendChild(button('Mark Stale', {action: 'memory_signal', signal_type: 'stale', memory_id: card.memory_id, reason: 'marked stale from live recall panel'}));
        row.append(title, meta, actions);
        recall.appendChild(row);
      }
    }

    function renderTimeline(replay) {
      if (!replay || !replay.timeline || !replay.timeline.length) {
        empty(timeline, 'No session timeline yet.');
        return;
      }
      timeline.innerHTML = '';
      for (const entry of replay.timeline) {
        const row = document.createElement('div');
        row.className = 'event';
        row.innerHTML = `<code>${entry.index}. ${entry.event_type}</code><br>${entry.summary || ''}`;
        timeline.appendChild(row);
      }
    }

    function empty(container, text) {
      container.innerHTML = '';
      const node = document.createElement('div');
      node.className = 'item-meta';
      node.textContent = text;
      container.appendChild(node);
    }

    function button(text, payload) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = payload.action.includes('dismiss') || payload.decision === 'reject' ? 'secondary' : '';
      btn.textContent = text;
      btn.addEventListener('click', () => steward(payload));
      return btn;
    }

    function renderQueue(tasks) {
      if (!tasks.length) {
        empty(queue, 'No open steward tasks.');
        return;
      }
      queue.innerHTML = '';
      for (const task of tasks) {
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${task.kind} / ${task.severity}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = task.reason;
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.appendChild(button('Resolve', {action: 'resolve_task', task_id: task.task_id, reason: 'resolved in live steward queue'}));
        actions.appendChild(button('Dismiss', {action: 'dismiss_task', task_id: task.task_id, reason: 'dismissed in live steward queue'}));
        row.append(title, meta, actions);
        queue.appendChild(row);
      }
    }

    function renderGrowth(records) {
      if (!records.length) {
        empty(growth, 'No growth awaiting review.');
        return;
      }
      growth.innerHTML = '';
      for (const record of records) {
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${record.kind} / ${record.identity_impact} / ${record.status}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${record.growth_id} / ${record.reason}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.appendChild(button('Accept', {action: 'review_growth', decision: 'accept', growth_id: record.growth_id, reason: 'accepted in live steward review'}));
        actions.appendChild(button('Reject', {action: 'review_growth', decision: 'reject', growth_id: record.growth_id, reason: 'rejected in live steward review'}));
        row.append(title, meta, actions);
        growth.appendChild(row);
      }
    }

    function renderConflicts(records) {
      if (!records.length) {
        empty(conflictList, 'No unresolved conflicts.');
        return;
      }
      conflictList.innerHTML = '';
      for (const record of records) {
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${record.conflict_type} / ${record.severity}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${record.conflict_id} / proposed ${record.proposed_growth_id}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.appendChild(button('Accept New', {action: 'resolve_conflict', decision: 'accept_new', conflict_id: record.conflict_id, reason: 'accepted new growth in live steward conflict review'}));
        actions.appendChild(button('Keep Existing', {action: 'resolve_conflict', decision: 'keep_existing', conflict_id: record.conflict_id, reason: 'kept existing growth in live steward conflict review'}));
        actions.appendChild(button('Fork', {action: 'resolve_conflict', decision: 'fork', conflict_id: record.conflict_id, reason: 'forked conflict in live steward conflict review'}));
        row.append(title, meta, actions);
        conflictList.appendChild(row);
      }
    }

    async function refresh() {
      const res = await fetch('/api/status');
      renderStatus(await res.json());
    }

    async function steward(payload) {
      const res = await fetch('/api/steward', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.error) {
        addMessage('lucien', data.error);
        return;
      }
      renderStatus(data.status);
    }

    document.getElementById('chatForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const box = document.getElementById('message');
      const text = box.value.trim();
      if (!text) return;
      box.value = '';
      addMessage('user', text);
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text})
      });
      const data = await res.json();
      if (data.error) {
        addMessage('lucien', data.error);
        return;
      }
      lastLucien = data.result.response_text;
      addMessage('lucien', lastLucien);
      renderStatus(data.status);
    });

    document.getElementById('speak').addEventListener('click', () => {
      if (!lastLucien || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(lastLucien));
    });

    document.getElementById('reflectNow').addEventListener('click', () => {
      steward({action: 'run_reflection', reason: 'manual live cockpit reflection'});
    });

    refresh();
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())

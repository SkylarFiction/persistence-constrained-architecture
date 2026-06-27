from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
from typing import Any

from lucien import LucienChatShell, ModelLucienResponder

from .constitution import write_constitution_markdown
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .model_adapter import adapter_from_environment
from .reflection_queue import open_tasks_from_reflection
from .reflections import record_reflection
from .report import build_trace_report


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
            if self.path in {"/", "/index.html"}:
                _send_html(self, _live_chat_html())
                return
            if self.path == "/api/status":
                _send_json(self, _status_payload(ledger, manifest))
                return
            self.send_error(404)

        def do_POST(self) -> None:
            if self.path != "/api/chat":
                self.send_error(404)
                return
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
            report = build_trace_report(ledger, manifest)
            write_constitution_markdown(report, manifest, "LUCIEN_CONSTITUTION.md")
            shell._write_dashboard()
            shell._write_cockpit()
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

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Lucien Live Chat v0.1: http://{host}:{port}")
    server.serve_forever()


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
    return {
        "summary": summary,
        "csm_state": latest_signal["state"] if latest_signal else "unknown",
        "output_gate": latest_gate or {},
        "open_reflection_tasks": report.active_reflection_tasks,
        "growth_conflicts": report.growth_conflicts,
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
        <h2>Live Ledger</h2>
        <div id="events" class="events"></div>
      </section>
    </div>
  </main>
  <script>
    const messages = document.getElementById('messages');
    const events = document.getElementById('events');
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
      events.innerHTML = '';
      for (const event of status.latest_events || []) {
        const row = document.createElement('div');
        row.className = 'event';
        row.innerHTML = `<code>${event.event_type}</code><br>${event.detail || ''}`;
        events.appendChild(row);
      }
    }

    async function refresh() {
      const res = await fetch('/api/status');
      renderStatus(await res.json());
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

    refresh();
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())

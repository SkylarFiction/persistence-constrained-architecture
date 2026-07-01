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
from .mission_flow import mission_flows_from_events
from .mission_autonomy import (
    mission_autonomy_recommendations_from_events,
    propose_autonomous_mission_step,
)
from .mission_steps import mission_step_records_from_events
from .missions import (
    MissionItemKind,
    MissionStatus,
    add_mission_item,
    mission_briefs_from_events,
    open_mission,
    update_mission_status,
)
from .model_adapter import (
    adapter_for_model_mode,
    adapter_from_environment,
    model_environment_diagnostic,
    normalize_model_mode,
)
from .context_builder import build_governed_context
from .reflection_queue import (
    open_tasks_from_reflection,
    resolve_matching_reflection_tasks,
    update_reflection_task,
)
from .reflections import record_reflection
from .report import build_trace_report
from .session_replay import build_session_replay, latest_session_id
from .self_model import derive_self_model
from .skill_memory import accepted_skills_from_events, skill_candidates_from_events
from .state import derive_current_claim
from .steward_inbox import apply_steward_inbox_action, steward_inbox
from .tool_router import (
    dry_run_tool_for_step,
    run_tool_for_step,
    tool_execution_records_from_events,
    tool_preview_records_from_events,
    tool_specs,
)
from .workbench import workbench_status


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
    model_diagnostic = model_environment_diagnostic()
    print(_format_model_startup_diagnostic(model_diagnostic), flush=True)
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
            model_mode = normalize_model_mode(str(payload.get("model_mode", "")))
            use_openai = bool(payload.get("use_openai"))
            before_count = len(ledger.events())
            received_event = ledger.append(
                "chat.user_message_received",
                manifest.system_id,
                {
                    "message_length": len(message),
                    "surface": "live_chat",
                    "model_mode": model_mode,
                    "openai_requested": use_openai,
                },
            )
            result = shell.handle_message(
                message,
                model_mode=model_mode,
                use_openai=use_openai,
                responder=ModelLucienResponder(
                    adapter_for_model_mode(model_mode, use_openai=use_openai)
                ),
            )
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
        reflection = None
        opened_tasks = []
        if signal_type in {"contradicted", "stale"}:
            reflection = record_reflection(ledger, manifest)
            opened_tasks = open_tasks_from_reflection(ledger, reflection)
        return {
            "memory_signal": signal.to_dict(),
            "reflection": reflection.to_dict() if reflection else None,
            "opened_tasks": [task.to_dict() for task in opened_tasks],
        }

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

    if action == "open_mission":
        title = str(payload.get("title", "")).strip()
        problem = str(payload.get("problem", "")).strip()
        values = [str(value).strip() for value in payload.get("values", []) if str(value).strip()]
        if not title:
            raise ValueError("title is required")
        if not problem:
            raise ValueError("problem is required")
        mission = open_mission(
            ledger,
            manifest.system_id,
            title=title,
            problem_statement=problem,
            values=values,
            reason=reason,
        )
        return {"mission": mission.to_dict()}

    if action == "add_mission_item":
        mission_id = str(payload.get("mission_id", "")).strip()
        kind = str(payload.get("kind", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        if not mission_id:
            raise ValueError("mission_id is required")
        if kind not in {item_kind.value for item_kind in MissionItemKind}:
            raise ValueError("kind is not a valid mission item kind")
        if not summary:
            raise ValueError("summary is required")
        item = add_mission_item(
            ledger,
            manifest.system_id,
            mission_id=mission_id,
            kind=kind,
            summary=summary,
            status=str(payload.get("status", "proposed")),
            confidence=str(payload.get("confidence", "unknown")),
            evidence_refs=[
                str(ref).strip()
                for ref in payload.get("evidence_refs", [])
                if str(ref).strip()
            ],
            reason=reason,
        )
        return {"mission_item": item.to_dict()}

    if action == "update_mission_status":
        mission_id = str(payload.get("mission_id", "")).strip()
        status = str(payload.get("status", "")).strip()
        if not mission_id:
            raise ValueError("mission_id is required")
        if status not in {mission_status.value for mission_status in MissionStatus}:
            raise ValueError("status is not a valid mission status")
        mission = update_mission_status(
            ledger,
            manifest.system_id,
            mission_id=mission_id,
            status=status,
            reason=reason,
        )
        return {"mission": mission.to_dict()}

    if action == "run_reflection":
        reflection = record_reflection(ledger, manifest)
        opened_tasks = open_tasks_from_reflection(ledger, reflection)
        return {
            "reflection": reflection.to_dict(),
            "opened_tasks": [task.to_dict() for task in opened_tasks],
        }

    if action == "steward_inbox_action":
        inbox_id = str(payload.get("inbox_id", "")).strip()
        inbox_action = str(payload.get("inbox_action", "")).strip()
        if not inbox_id:
            raise ValueError("inbox_id is required")
        if not inbox_action:
            raise ValueError("inbox_action is required")
        return apply_steward_inbox_action(
            ledger,
            manifest,
            inbox_id,
            inbox_action,
            reason=reason,
            reviewer=str(payload.get("reviewer", "steward")),
        )

    if action == "run_tool":
        step_id = str(payload.get("step_id", "")).strip()
        if not step_id:
            raise ValueError("step_id is required")
        tool_args = {
            str(key): str(value)
            for key, value in dict(payload.get("tool_args", {})).items()
            if str(key).strip()
        }
        return run_tool_for_step(
            ledger,
            manifest.system_id,
            step_id,
            tool_args=tool_args,
            project_root=Path.cwd(),
            reason=reason,
        )

    if action == "dry_run_tool":
        step_id = str(payload.get("step_id", "")).strip()
        if not step_id:
            raise ValueError("step_id is required")
        tool_args = {
            str(key): str(value)
            for key, value in dict(payload.get("tool_args", {})).items()
            if str(key).strip()
        }
        return dry_run_tool_for_step(
            ledger,
            manifest.system_id,
            step_id,
            tool_args=tool_args,
            project_root=Path.cwd(),
            reason=reason,
        )

    if action == "propose_next_step":
        mission_id = str(payload.get("mission_id", "")).strip()
        if not mission_id:
            raise ValueError("mission_id is required")
        return propose_autonomous_mission_step(
            ledger,
            manifest.system_id,
            mission_id,
        )

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
    model_mode: str | None = None,
    use_openai: bool = False,
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
        responder=ModelLucienResponder(
            adapter_for_model_mode(model_mode, use_openai=use_openai)
        ),
        dashboard_path="reports/lucien_chat_dashboard.html",
        cockpit_path="reports/lucien_cockpit.html",
    )
    before_count = len(ledger.events())
    ledger.append(
        "chat.user_message_received",
        manifest.system_id,
        {"message_length": len(message), "surface": "chat_once"},
    )
    result = shell.handle_message(
        message,
        model_mode=model_mode,
        use_openai=use_openai,
    )
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
    governed_context = build_governed_context(ledger, manifest)
    memory_cards = [
        card.to_dict()
        for card in memory_cards_from_events(ledger.events(), manifest.system_id)
    ]
    missions = [
        brief.to_dict()
        for brief in mission_briefs_from_events(ledger.events())
    ]
    mission_steps = [
        step.to_dict() for step in mission_step_records_from_events(ledger.events())
    ]
    tool_spec_map = {spec.name: spec.to_dict() for spec in tool_specs()}
    tool_executions = [
        record.to_dict() for record in tool_execution_records_from_events(ledger.events())
    ]
    tool_previews = [
        record.to_dict() for record in tool_preview_records_from_events(ledger.events())
    ]
    skill_candidates = [
        candidate.to_dict() for candidate in skill_candidates_from_events(ledger.events())
    ]
    accepted_skills = [
        skill.to_dict() for skill in accepted_skills_from_events(ledger.events())
    ]
    mission_flows = {
        flow.mission_id: flow.to_dict()
        for flow in mission_flows_from_events(ledger.events())
    }
    mission_autonomy = [
        record.to_dict()
        for record in mission_autonomy_recommendations_from_events(ledger.events())
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
    model_usage = _model_usage_summary(ledger.events())
    session_id = latest_session_id(ledger)
    session_replay = (
        build_session_replay(ledger, manifest, session_id).to_dict()
        if session_id
        else None
    )
    return {
        "summary": summary,
        "workbench": workbench_status(ledger, manifest),
        "model_adapter": model_environment_diagnostic(),
        "model_usage": model_usage,
        "steward_inbox": [item.to_dict() for item in steward_inbox(ledger)],
        "csm_state": latest_signal["state"] if latest_signal else "unknown",
        "output_gate": latest_gate or {},
        "open_reflection_tasks": report.active_reflection_tasks,
        "active_growth": active_growth,
        "memory_inbox": memory_inbox,
        "growth_conflicts": unresolved_conflicts,
        "missions": missions,
        "mission_flows": mission_flows,
        "mission_autonomy": mission_autonomy,
        "mission_steps": mission_steps,
        "tools": tool_spec_map,
        "tool_executions": tool_executions,
        "tool_previews": tool_previews,
        "skill_candidates": skill_candidates,
        "accepted_skills": accepted_skills,
        "governed_context": governed_context.to_dict(),
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


def _format_model_startup_diagnostic(diagnostic: dict[str, Any]) -> str:
    provider = diagnostic.get("configured_provider", "unknown")
    model = diagnostic.get("configured_model", "unknown")
    env_file = "yes" if diagnostic.get("env_file_exists") else "no"
    plain_text = "yes" if diagnostic.get("env_file_plain_text") else "no"
    key_present = "yes" if diagnostic.get("openai_key_present") else "no"
    prefix_ok = "yes" if diagnostic.get("openai_key_prefix_ok") else "no"
    return (
        "Model adapter: "
        f"provider={provider} model={model} "
        f".env={env_file} plain_text={plain_text} "
        f"OPENAI_API_KEY_present={key_present} key_prefix_ok={prefix_ok}"
    )


def _model_usage_summary(events) -> dict[str, Any]:
    model_events = [
        event
        for event in events
        if event.event_type == "chat.model_response_generated"
    ]
    openai_events = [
        event
        for event in model_events
        if event.payload.get("provider") == "openai"
    ]
    session_cost = sum(
        float(event.payload.get("estimated_cost_usd") or 0.0)
        for event in openai_events
    )
    latest = model_events[-1].payload if model_events else {}
    return {
        "model_call_count": len(model_events),
        "openai_call_count": len(openai_events),
        "estimated_session_cost_usd": round(session_cost, 6),
        "latest_provider": latest.get("provider", "none"),
        "latest_model": latest.get("model", "none"),
        "latest_total_tokens": latest.get("estimated_total_tokens", 0),
        "latest_cost_usd": latest.get("estimated_cost_usd", 0.0),
        "latest_usage_source": latest.get("usage_source", "none"),
        "latest_model_mode": latest.get("model_mode", "none"),
        "latest_openai_requested": bool(latest.get("openai_requested", False)),
    }


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
    .home { grid-column: 1 / -1; display: grid; gap: 14px; }
    .home-top { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(280px, .75fr); gap: 12px; }
    .home-title { font-size: 24px; font-weight: 900; margin: 0 0 4px; }
    .home-subtitle { color: var(--muted); font-size: 14px; }
    .home-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    section { background: var(--panel); border: 1px solid var(--line); padding: 16px; }
    .chat { min-height: 560px; display: flex; flex-direction: column; }
    .messages { flex: 1; overflow-y: auto; border: 1px solid #e8ece8; padding: 12px; background: #fbfcf8; }
    .msg { margin: 0 0 12px; padding: 10px; border-left: 4px solid var(--line); background: white; }
    .msg.user { border-left-color: var(--amber); }
    .msg.lucien { border-left-color: var(--green); }
    form { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; margin-top: 12px; }
    input, select, textarea { padding: 10px; font: inherit; border: 1px solid var(--line); background: white; color: var(--ink); min-width: 0; }
    textarea { min-height: 72px; resize: vertical; }
    .model-controls { grid-column: 1 / -1; display: grid; grid-template-columns: minmax(170px, 220px) minmax(0, 1fr); gap: 8px; align-items: center; }
    .checkline { display: flex; gap: 8px; align-items: center; color: var(--muted); font-size: 13px; font-weight: 700; }
    .checkline input { width: auto; }
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
    <section class="home">
      <div class="home-top">
        <div>
          <h2 class="home-title">Lucien Workbench</h2>
          <div id="homeSubtitle" class="home-subtitle">What are we working on today?</div>
        </div>
        <div class="home-actions">
          <button type="button" id="homeStartMission">Start Mission</button>
          <button type="button" id="homeReviewInbox" class="secondary">Review Inbox</button>
          <button type="button" id="homeSessionReplay" class="secondary">View Session Replay</button>
        </div>
      </div>
      <div class="metrics">
        <div class="metric"><div class="label">Active Mission</div><div id="homeMission" class="value">loading</div></div>
        <div class="metric"><div class="label">Mission Phase</div><div id="homePhase" class="value">loading</div></div>
        <div class="metric"><div class="label">Next Safe Action</div><div id="homeNextAction" class="value">loading</div></div>
        <div class="metric"><div class="label">Blockers</div><div id="homeBlockers" class="value">loading</div></div>
        <div class="metric"><div class="label">Steward Inbox</div><div id="homeInbox" class="value">loading</div></div>
        <div class="metric"><div class="label">Model Mode</div><div id="homeModelMode" class="value">loading</div></div>
        <div class="metric"><div class="label">Session Cost</div><div id="homeCost" class="value">loading</div></div>
        <div class="metric"><div class="label">Continuity / Gate</div><div id="homeContinuity" class="value">loading</div></div>
      </div>
      <div id="homeBlockerList" class="queue"></div>
    </section>
    <section class="chat">
      <h2>Chat</h2>
      <div id="messages" class="messages"></div>
      <form id="chatForm">
        <textarea id="message" placeholder="Ask Lucien what changed in his state..."></textarea>
        <button type="submit">Send</button>
        <button type="button" id="speak" class="secondary">Speak</button>
        <div class="model-controls">
          <select id="modelMode">
            <option value="serious_only" selected>OpenAI only when checked</option>
            <option value="echo">Echo Local</option>
            <option value="openai">OpenAI</option>
          </select>
          <label class="checkline"><input id="useOpenAI" type="checkbox"> Use OpenAI for this message</label>
        </div>
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
          <div class="metric"><div class="label">Model Provider</div><div id="modelProvider" class="value">loading</div></div>
          <div class="metric"><div class="label">API Key</div><div id="apiKey" class="value">loading</div></div>
        </div>
      </section>
      <section>
        <h2>OpenAI Usage</h2>
        <div class="metrics">
          <div class="metric"><div class="label">Latest Provider</div><div id="usageProvider" class="value">loading</div></div>
          <div class="metric"><div class="label">Latest Tokens</div><div id="usageTokens" class="value">loading</div></div>
          <div class="metric"><div class="label">Latest Cost</div><div id="usageCost" class="value">loading</div></div>
          <div class="metric"><div class="label">Session Cost</div><div id="sessionCost" class="value">loading</div></div>
        </div>
      </section>
      <section>
        <h2>Steward Inbox</h2>
        <div class="actions">
          <button type="button" class="secondary" data-inbox-filter="all">All</button>
          <button type="button" class="secondary" data-inbox-filter="growth">Growth</button>
          <button type="button" class="secondary" data-inbox-filter="memory">Memory</button>
          <button type="button" class="secondary" data-inbox-filter="skills">Skills</button>
          <button type="button" class="secondary" data-inbox-filter="evidence">Evidence</button>
          <button type="button" class="secondary" data-inbox-filter="missions">Missions</button>
          <button type="button" class="secondary" data-inbox-filter="conflicts">Conflicts</button>
          <button type="button" class="secondary" data-inbox-filter="recovery">Recovery</button>
          <button type="button" class="secondary" data-inbox-filter="high">High Priority</button>
        </div>
        <div id="stewardInbox" class="queue"></div>
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
        <h2>Governed Context</h2>
        <div id="governedContext" class="queue"></div>
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
        <h2>Mission Workspace</h2>
        <form id="missionForm">
          <input id="missionTitle" placeholder="Mission title">
          <textarea id="missionProblem" placeholder="Problem Lucien should work on"></textarea>
          <input id="missionValues" placeholder="values, comma separated">
          <button type="submit">Open Mission</button>
        </form>
        <div id="missions" class="queue"></div>
      </section>
      <section>
        <h2>Mission Steps</h2>
        <div id="missionSteps" class="queue"></div>
      </section>
      <section>
        <h2>Skill Memory</h2>
        <div id="skillMemory" class="queue"></div>
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
    const governedContext = document.getElementById('governedContext');
    const memoryInbox = document.getElementById('memoryInbox');
    const recall = document.getElementById('recall');
    const missions = document.getElementById('missions');
    const missionSteps = document.getElementById('missionSteps');
    const skillMemory = document.getElementById('skillMemory');
    const stewardInbox = document.getElementById('stewardInbox');
    let activeInboxFilter = 'all';
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
      renderWorkbenchHome(status.workbench || {}, status);
      document.getElementById('claim').textContent = summary.current_continuity_claim || 'unknown';
      document.getElementById('csm').textContent = status.csm_state || 'unknown';
      const gate = status.output_gate || {};
      document.getElementById('gate').textContent = gate.mode ? `${gate.mode} / ${gate.allowed}` : 'none';
      document.getElementById('recovery').textContent = summary.current_recovery_status || 'none';
      document.getElementById('tasks').textContent = summary.active_reflection_task_count ?? 0;
      document.getElementById('conflicts').textContent = summary.unresolved_growth_conflict_count ?? 0;
      const modelAdapter = status.model_adapter || {};
      document.getElementById('modelProvider').textContent = `${modelAdapter.configured_provider || 'unknown'} / ${modelAdapter.configured_model || 'unknown'}`;
      document.getElementById('apiKey').textContent = modelAdapter.openai_key_present ? 'present' : 'missing';
      const usage = status.model_usage || {};
      document.getElementById('usageProvider').textContent = `${usage.latest_provider || 'none'} / ${usage.latest_model || 'none'}`;
      document.getElementById('usageTokens').textContent = usage.latest_total_tokens || 0;
      document.getElementById('usageCost').textContent = `$${Number(usage.latest_cost_usd || 0).toFixed(6)}`;
      document.getElementById('sessionCost').textContent = `$${Number(usage.estimated_session_cost_usd || 0).toFixed(6)}`;
      renderQueue(status.open_reflection_tasks || []);
      renderSelfModel(status.self_model || {});
      renderGovernedContext(status.governed_context || {});
      renderMemoryInbox(status.memory_inbox || []);
      renderRecall((status.self_model || {}).memory_cards || []);
      renderMissions(status.missions || [], status.mission_flows || {}, status.mission_autonomy || []);
      renderMissionSteps(status.mission_steps || [], status.tools || {}, status.tool_executions || [], status.tool_previews || []);
      renderSkillMemory(status.skill_candidates || [], status.accepted_skills || []);
      renderStewardInbox(status.steward_inbox || []);
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

    function renderWorkbenchHome(workbench, status) {
      const mission = workbench.active_mission || null;
      document.getElementById('homeSubtitle').textContent = mission ? 'Current governed mission' : 'What are we working on today?';
      document.getElementById('homeMission').textContent = mission ? mission.title : 'No active mission';
      document.getElementById('homePhase').textContent = mission ? mission.phase : 'none';
      document.getElementById('homeNextAction').textContent = workbench.recommended_next_action || 'Open a mission before using Lucien for work.';
      document.getElementById('homeBlockers').textContent = mission ? mission.blocker_count || 0 : 0;
      document.getElementById('homeInbox').textContent = `${workbench.open_steward_inbox_count || 0} open / ${workbench.high_priority_inbox_count || 0} high`;
      document.getElementById('homeModelMode').textContent = workbench.model_mode || 'serious_only';
      document.getElementById('homeCost').textContent = `$${Number(workbench.estimated_session_cost_usd || 0).toFixed(6)}`;
      document.getElementById('homeContinuity').textContent = `${workbench.continuity_state || 'unknown'} / ${workbench.output_gate_mode || 'unknown'}`;
      const blockerList = document.getElementById('homeBlockerList');
      blockerList.innerHTML = '';
      if (mission && mission.blockers && mission.blockers.length) {
        for (const blocker of mission.blockers.slice(0, 3)) {
          const row = document.createElement('div');
          row.className = 'item';
          row.textContent = blocker;
          blockerList.appendChild(row);
        }
      } else {
        const row = document.createElement('div');
        row.className = 'item-meta';
        row.textContent = mission ? 'No mission blockers detected.' : 'No active mission. Start one to turn chat into governed work.';
        blockerList.appendChild(row);
      }
    }

    function renderStewardInbox(items) {
      const filtered = items.filter((item) => {
        if (activeInboxFilter === 'all') return true;
        if (activeInboxFilter === 'high') return item.severity === 'high' || item.severity === 'critical';
        const groups = {
          growth: ['growth_review'],
          memory: ['memory_review'],
          skills: ['skill_candidate'],
          evidence: ['evidence_review'],
          missions: ['mission_review'],
          conflicts: ['conflict_resolution'],
          recovery: ['recovery_review']
        };
        return (groups[activeInboxFilter] || [activeInboxFilter]).includes(item.source_type);
      });
      if (!filtered.length) {
        empty(stewardInbox, 'No steward inbox items for this filter.');
        return;
      }
      stewardInbox.innerHTML = '';
      for (const item of filtered) {
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${item.severity} / ${item.source_type} / ${item.title}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${item.inbox_id} / ${item.reason}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        for (const action of item.recommended_actions || []) {
          actions.appendChild(button(labelForInboxAction(action), {
            action: 'steward_inbox_action',
            inbox_id: item.inbox_id,
            inbox_action: action,
            reason: `${action} from unified steward inbox`
          }));
        }
        row.append(title, meta, actions);
        stewardInbox.appendChild(row);
      }
    }

    function labelForInboxAction(action) {
      const labels = {
        accept_new: 'Accept New',
        keep_existing: 'Keep Existing',
        mark_stale: 'Mark Stale',
        request_evidence: 'Request Evidence'
      };
      return labels[action] || action.replace('_', ' ').replace(/^./, c => c.toUpperCase());
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

    function renderGovernedContext(context) {
      governedContext.innerHTML = '';
      const summary = context.summary || {};
      const top = document.createElement('div');
      top.className = 'item';
      top.innerHTML = `<div class="item-title">${context.continuity_claim || 'unknown'} / ${context.output_mode || 'unknown'}</div>
        <div class="item-meta">sections ${summary.section_count || 0} / warnings ${summary.warning_count || 0}</div>`;
      governedContext.appendChild(top);
      for (const section of (context.sections || []).slice(0, 6)) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${section.name} / ${section.status}</div>
          <div class="item-meta">items ${(section.items || []).length} / warnings ${(section.warnings || []).length}</div>`;
        governedContext.appendChild(row);
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

    function renderMissions(records, flows, autonomy) {
      if (!records.length) {
        empty(missions, 'No missions opened yet.');
        return;
      }
      missions.innerHTML = '';
      const latestAutonomy = {};
      for (const recommendation of autonomy || []) {
        latestAutonomy[recommendation.mission_id] = recommendation;
      }
      for (const brief of records) {
        const mission = brief.mission || {};
        const flow = flows[mission.mission_id] || {};
        const recommendation = latestAutonomy[mission.mission_id] || null;
        const counts = brief.counts || {};
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${mission.title || 'Untitled mission'} / ${mission.status}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${mission.mission_id} / phase ${flow.phase || 'unknown'} / problem hash ${(mission.problem_sha256 || '').slice(0, 12)} / H ${counts.hypothesis || 0} E ${counts.evidence || 0} R ${counts.risk || 0} P ${counts.plan_step || 0} O ${counts.outcome || 0} L ${counts.lesson || 0}`;

        const next = document.createElement('div');
        next.className = 'item-meta';
        next.textContent = `${(flow.blockers || []).length ? 'blocked: ' + flow.blockers.join(' / ') : 'next: ' + (flow.next_action || 'none')}`;
        const autonomyLine = document.createElement('div');
        autonomyLine.className = 'item-meta';
        autonomyLine.textContent = recommendation ? `latest autonomous proposal: ${recommendation.can_propose ? recommendation.required_tool + ' / ' + recommendation.risk_level : 'blocked'} / ${recommendation.reason}` : 'No autonomous step proposal yet.';

        const itemForm = document.createElement('form');
        itemForm.addEventListener('submit', (event) => {
          event.preventDefault();
          const kind = itemForm.querySelector('select').value;
          const summary = itemForm.querySelector('textarea').value.trim();
          const confidence = itemForm.querySelector('input').value.trim() || 'unknown';
          if (!summary) return;
          itemForm.querySelector('textarea').value = '';
          steward({
            action: 'add_mission_item',
            mission_id: mission.mission_id,
            kind,
            summary,
            confidence,
            reason: `added ${kind} from live mission workspace`
          });
        });
        const kind = document.createElement('select');
        for (const value of ['hypothesis', 'evidence', 'intervention', 'plan_step', 'risk', 'outcome', 'lesson']) {
          const option = document.createElement('option');
          option.value = value;
          option.textContent = value;
          kind.appendChild(option);
        }
        const summary = document.createElement('textarea');
        summary.placeholder = 'Add governed mission note';
        const confidence = document.createElement('input');
        confidence.placeholder = 'confidence';
        const add = document.createElement('button');
        add.type = 'submit';
        add.textContent = 'Add';
        itemForm.append(kind, summary, confidence, add);

        const actions = document.createElement('div');
        actions.className = 'actions';
        if (mission.status === 'open') {
          actions.appendChild(button('Suggest Next Step', {action: 'propose_next_step', mission_id: mission.mission_id, reason: 'live autonomous mission loop'}));
          actions.appendChild(button('Pause', {action: 'update_mission_status', mission_id: mission.mission_id, status: 'paused', reason: 'paused in live mission workspace'}));
          actions.appendChild(button('Complete', {action: 'update_mission_status', mission_id: mission.mission_id, status: 'completed', reason: 'completed in live mission workspace'}));
        } else if (mission.status === 'paused') {
          actions.appendChild(button('Reopen', {action: 'update_mission_status', mission_id: mission.mission_id, status: 'open', reason: 'reopened in live mission workspace'}));
        }
        actions.appendChild(button('Archive', {action: 'update_mission_status', mission_id: mission.mission_id, status: 'archived', reason: 'archived in live mission workspace'}));

        row.append(title, meta, next, autonomyLine, itemForm, actions);
        missions.appendChild(row);
      }
    }

    function renderMissionSteps(records, tools, executions, previews) {
      if (!records.length) {
        empty(missionSteps, 'No mission steps recorded.');
        return;
      }
      missionSteps.innerHTML = '';
      const latestExecution = {};
      for (const execution of executions || []) {
        latestExecution[execution.step_id] = execution;
      }
      const latestPreview = {};
      for (const preview of previews || []) {
        latestPreview[preview.step_id] = preview;
      }
      for (const step of records.slice(-8)) {
        const row = document.createElement('div');
        row.className = 'item';
        const spec = tools[step.required_tool] || {};
        const execution = latestExecution[step.step_id] || null;
        const preview = latestPreview[step.step_id] || null;
        const profile = spec.safety_profile || {};
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${step.execution_status} / ${step.risk_level} / ${step.required_tool}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${step.step_id} / approval ${step.approval_status} / tool risk ${spec.risk || 'unknown'} / mission ${step.mission_id} / hash ${step.description_sha256.slice(0, 12)}`;
        const safety = document.createElement('div');
        safety.className = 'item-meta';
        safety.textContent = `safety: ${formatSafetyProfile(profile)}`;
        const latest = document.createElement('div');
        latest.className = 'item-meta';
        latest.textContent = execution ? `latest tool execution: ${execution.status} / evidence ${execution.evidence_id || 'none'}` : (preview ? `latest dry run: ${preview.permission_decision} / would_execute ${preview.would_execute}` : (spec.description || 'No governed tool execution yet.'));
        const actions = document.createElement('div');
        actions.className = 'actions';
        const canRun = ['proposed', 'ready'].includes(step.execution_status);
        const needsApproval = ['medium', 'high'].includes(step.risk_level) && step.approval_status !== 'approved';
        if (!spec.name) {
          const blocked = document.createElement('div');
          blocked.className = 'item-meta';
          blocked.textContent = 'Tool is not registered in the governed router.';
          actions.appendChild(blocked);
        } else if (needsApproval) {
          const blocked = document.createElement('div');
          blocked.className = 'item-meta';
          blocked.textContent = 'Approval required before tool execution.';
          actions.appendChild(toolButton(step, spec, true));
          actions.appendChild(blocked);
        } else if (canRun) {
          actions.appendChild(toolButton(step, spec, true));
          actions.appendChild(toolButton(step, spec, false));
        } else {
          const done = document.createElement('div');
          done.className = 'item-meta';
          done.textContent = `No run action available from ${step.execution_status}.`;
          actions.appendChild(done);
        }
        row.append(title, meta, safety, latest, actions);
        missionSteps.appendChild(row);
      }
    }

    function formatSafetyProfile(profile) {
      const labels = [];
      for (const key of ['read_only', 'writes_files', 'runs_tests', 'uses_network', 'creates_evidence', 'can_fail_step', 'requires_approval', 'blocked_if_recovery', 'blocked_if_high_risk']) {
        if (profile[key]) labels.push(key);
      }
      return labels.length ? labels.join(', ') : 'none declared';
    }

    function toolButton(step, spec, dryRun) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = dryRun ? 'secondary' : '';
      btn.textContent = dryRun ? `Dry Run (${spec.risk})` : `Run Tool (${spec.risk})`;
      btn.addEventListener('click', () => {
        const toolArgs = {};
        if (step.required_tool === 'read_file' || step.required_tool === 'list_files' || step.required_tool === 'open_dashboard') {
          const fallback = step.required_tool === 'read_file' ? 'README.md' : '.';
          const value = window.prompt(`Path for ${step.required_tool}`, fallback);
          if (value === null) return;
          toolArgs.path = value;
        }
        steward({
          action: dryRun ? 'dry_run_tool' : 'run_tool',
          step_id: step.step_id,
          tool_args: toolArgs,
          reason: `${dryRun ? 'dry-ran' : 'ran'} ${step.required_tool} from live mission step panel`
        });
      });
      return btn;
    }

    function renderSkillMemory(candidates, accepted) {
      skillMemory.innerHTML = '';
      const summary = document.createElement('div');
      summary.className = 'item';
      summary.innerHTML = `<div class="item-title">Accepted skills: ${accepted.length}</div>
        <div class="item-meta">Candidates: ${candidates.length}</div>`;
      skillMemory.appendChild(summary);
      const recent = candidates.slice(-6);
      if (!recent.length) {
        const emptyNode = document.createElement('div');
        emptyNode.className = 'item-meta';
        emptyNode.textContent = 'No skill candidates yet.';
        skillMemory.appendChild(emptyNode);
        return;
      }
      for (const skill of recent) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${skill.name} / ${skill.status}</div>
          <div class="item-meta">${skill.skill_id} / tool ${skill.required_tool} / risk ${skill.risk_level} / hash ${skill.procedure_sha256.slice(0, 12)}</div>`;
        skillMemory.appendChild(row);
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
      const modelMode = document.getElementById('modelMode').value;
      const useOpenAI = document.getElementById('useOpenAI').checked;
      box.value = '';
      addMessage('user', text);
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message: text,
          model_mode: modelMode,
          use_openai: useOpenAI
        })
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

    document.getElementById('missionForm').addEventListener('submit', (event) => {
      event.preventDefault();
      const title = document.getElementById('missionTitle').value.trim();
      const problem = document.getElementById('missionProblem').value.trim();
      const values = document.getElementById('missionValues').value
        .split(',')
        .map(value => value.trim())
        .filter(Boolean);
      if (!title || !problem) return;
      document.getElementById('missionTitle').value = '';
      document.getElementById('missionProblem').value = '';
      document.getElementById('missionValues').value = '';
      steward({
        action: 'open_mission',
        title,
        problem,
        values,
        reason: 'opened from live mission workspace'
      });
    });

    document.getElementById('speak').addEventListener('click', () => {
      if (!lastLucien || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(lastLucien));
    });

    document.getElementById('reflectNow').addEventListener('click', () => {
      steward({action: 'run_reflection', reason: 'manual live cockpit reflection'});
    });

    document.getElementById('homeStartMission').addEventListener('click', () => {
      document.getElementById('missionTitle').focus();
      document.getElementById('missionTitle').scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('homeReviewInbox').addEventListener('click', () => {
      stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('homeSessionReplay').addEventListener('click', () => {
      timeline.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    for (const control of document.querySelectorAll('[data-inbox-filter]')) {
      control.addEventListener('click', () => {
        activeInboxFilter = control.getAttribute('data-inbox-filter') || 'all';
        refresh();
      });
    }

    refresh();
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())

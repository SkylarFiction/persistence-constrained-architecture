from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import parse_qs, urlparse

from lucien import LucienChatShell

from .constitution import write_constitution_markdown
from .auto_daily_loop import (
    latest_auto_daily_research_loop,
    run_auto_daily_research_loop,
)
from .autonomy_queue import (
    autonomy_execution_records_from_events,
    autonomy_queue_items_from_events,
    execute_autonomy_action,
    review_autonomy_action,
)
from .certification import continuity_certification
from .build_review import build_review
from .checkpoint_story import checkpoint_story
from .commit_readiness import commit_readiness
from .cold_open import cold_open_report
from .daily_command_center import daily_command_center
from .evidence_locker import add_evidence, evidence_for_target, link_evidence
from .growth import (
    GrowthReviewDecision,
    GrowthStatus,
    growth_records_from_events,
    review_growth,
)
from .goals import (
    add_goal_blocker,
    create_goal_record,
    daily_plan,
    goal_records_from_events,
    link_goal_mission,
    update_goal_status,
)
from .growth_conflicts import (
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
    resolve_growth_conflict,
)
from .ledger import ContinuityLedger
from .learning_review import (
    learning_review_records_from_events,
    run_latest_session_learning_review,
    run_learning_review,
)
from .manifest import IdentityManifest
from .memory_cards import memory_cards_from_events
from .memory_signals import record_memory_signal
from .mission_claim_map import mission_claim_maps
from .mission_flow import mission_flows_from_events
from .mission_autonomy import (
    mission_autonomy_recommendations_from_events,
    propose_autonomous_mission_step,
)
from .mission_onboarding import (
    create_mission_onboarding_pack,
    mission_onboarding_state,
)
from .mission_steps import mission_step_records_from_events
from .missions import (
    MissionItemKind,
    MissionStatus,
    add_mission_item,
    mission_briefs_from_events,
    open_mission,
    require_mission,
    update_mission_status,
)
from .model_adapter import model_environment_diagnostic, normalize_model_mode
from .next_build import next_governed_build
from .context_builder import build_governed_context
from .project_brief import project_build_brief
from .research_sandbox import (
    create_research_output,
    research_outputs_from_events,
    research_sandbox_status,
)
from .research_autopilot import run_research_autopilot
from .research_pdf import export_research_pdf
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
from .start_here import start_here_decision
from .state import derive_current_claim
from .steward_inbox import apply_steward_inbox_action, steward_inbox
from .startup_health import apply_startup_health_fix, startup_health
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
        dashboard_path="reports/lucien_chat_dashboard.html",
        cockpit_path="reports/lucien_cockpit.html",
    )
    startup_loop = run_auto_daily_research_loop(
        ledger,
        manifest,
        project_root=Path.cwd(),
        reason="live app startup daily research loop",
    )
    if startup_loop.get("already_prepared"):
        print("Daily research loop: already prepared for today", flush=True)
    else:
        print("Daily research loop: prepared today's research agenda", flush=True)

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
            if parsed.path.startswith("/reports/"):
                _send_report_file(self, parsed.path)
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
            mission_id = str(payload.get("mission_id", "")).strip() or None
            before_count = len(ledger.events())
            received_event = ledger.append(
                "chat.user_message_received",
                manifest.system_id,
                {
                    "message_length": len(message),
                    "surface": "live_chat",
                    "model_mode": model_mode,
                    "openai_requested": use_openai,
                    "mission_id": mission_id,
                },
            )
            result = shell.handle_message(
                message,
                model_mode=model_mode,
                use_openai=use_openai,
                mission_id=mission_id,
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
                if str(payload.get("action", "")).strip() == "start_clean_daily_session":
                    shell.close_session(reason="clean daily session reset")
                    shell.session_id = None
                    session_id = shell.start_session(reason="clean daily session")
                    result = {
                        "action": "start_clean_daily_session",
                        "session_id": session_id,
                        "status": "open",
                    }
                else:
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

    if action == "add_mission_evidence":
        mission_id = str(payload.get("mission_id", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        source = str(payload.get("source", "")).strip()
        source_type = str(payload.get("source_type", "manual_note")).strip() or "manual_note"
        confidence = str(payload.get("confidence", "unknown")).strip() or "unknown"
        if not mission_id:
            raise ValueError("mission_id is required")
        if not summary:
            raise ValueError("summary is required")
        require_mission(ledger.events(), mission_id)
        evidence = add_evidence(
            ledger,
            manifest.system_id,
            source_type=source_type,
            summary=summary,
            source=source or summary,
            confidence=confidence,
            reason=reason,
        )
        link = link_evidence(
            ledger,
            manifest.system_id,
            evidence.evidence_id,
            "mission",
            mission_id,
            reason="live mission evidence panel",
        )
        return {"evidence": evidence.to_dict(), "link": link.to_dict()}

    if action == "mission_onboard":
        mission_id = str(payload.get("mission_id", "")).strip()
        if not mission_id:
            raise ValueError("mission_id is required")
        return create_mission_onboarding_pack(
            ledger,
            manifest.system_id,
            mission_id,
            reason=reason,
        )

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

    if action == "learning_review":
        scope = str(payload.get("scope", "latest_session")).strip()
        apply = bool(payload.get("apply", True))
        if scope == "latest_session":
            return run_latest_session_learning_review(
                ledger,
                manifest.system_id,
                apply=apply,
                reason=reason,
            )
        if scope == "mission":
            mission_id = str(payload.get("mission_id", "")).strip()
            if not mission_id:
                raise ValueError("mission_id is required")
            return run_learning_review(
                ledger,
                manifest.system_id,
                "mission",
                mission_id,
                apply=apply,
                reason=reason,
            )
        if scope == "step":
            step_id = str(payload.get("step_id", "")).strip()
            if not step_id:
                raise ValueError("step_id is required")
            return run_learning_review(
                ledger,
                manifest.system_id,
                "step",
                step_id,
                apply=apply,
                reason=reason,
            )
        raise ValueError("learning review scope must be latest_session, mission, or step")

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

    if action == "startup_health_fix":
        fix_action = str(payload.get("fix_action", "")).strip()
        if not fix_action:
            raise ValueError("fix_action is required")
        return apply_startup_health_fix(
            ledger,
            manifest,
            fix_action,
            reason=reason,
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

    if action == "create_goal":
        title = str(payload.get("title", "")).strip()
        purpose = str(payload.get("purpose", "")).strip()
        success_criteria = str(payload.get("success_criteria", "")).strip()
        if not title:
            raise ValueError("goal title is required")
        if not purpose:
            raise ValueError("goal purpose is required")
        if not success_criteria:
            raise ValueError("goal success criteria is required")
        goal = create_goal_record(
            ledger,
            manifest.system_id,
            title=title,
            purpose=purpose,
            success_criteria=success_criteria,
            priority=str(payload.get("priority", "medium")).strip() or "medium",
            next_recommended_action=str(payload.get("next_recommended_action", "")).strip(),
            reason=reason,
        )
        return {"goal": goal.to_dict()}

    if action == "link_goal_mission":
        goal_id = str(payload.get("goal_id", "")).strip()
        mission_id = str(payload.get("mission_id", "")).strip()
        if not goal_id:
            raise ValueError("goal_id is required")
        if not mission_id:
            raise ValueError("mission_id is required")
        goal = link_goal_mission(
            ledger,
            manifest.system_id,
            goal_id,
            mission_id,
            reason=reason,
        )
        return {"goal": goal.to_dict()}

    if action == "add_goal_blocker":
        goal_id = str(payload.get("goal_id", "")).strip()
        blocker = str(payload.get("blocker", "")).strip()
        if not goal_id:
            raise ValueError("goal_id is required")
        if not blocker:
            raise ValueError("blocker is required")
        goal = add_goal_blocker(
            ledger,
            manifest.system_id,
            goal_id,
            blocker,
            reason=reason,
        )
        return {"goal": goal.to_dict()}

    if action in {"complete_goal", "archive_goal"}:
        goal_id = str(payload.get("goal_id", "")).strip()
        if not goal_id:
            raise ValueError("goal_id is required")
        status = "completed" if action == "complete_goal" else "archived"
        goal = update_goal_status(
            ledger,
            manifest.system_id,
            goal_id,
            status,
            reason=reason,
        )
        return {"goal": goal.to_dict()}

    if action == "generate_daily_plan":
        return {"daily_plan": daily_plan(ledger, manifest)}

    if action == "run_daily_research_loop":
        force = bool(payload.get("force"))
        return {
            "daily_research_loop": run_auto_daily_research_loop(
                ledger,
                manifest,
                project_root=Path.cwd(),
                force=force,
                reason=reason or "live daily research loop",
            )
        }

    if action == "run_research_autopilot":
        force = bool(payload.get("force"))
        return {
            "research_autopilot": run_research_autopilot(
                ledger,
                manifest,
                project_root=Path.cwd(),
                force=force,
                reason=reason or "live research autopilot",
            )
        }

    if action == "create_research_output":
        mission_id = str(payload.get("mission_id", "")).strip()
        kind = str(payload.get("kind", "")).strip()
        if not mission_id:
            raise ValueError("mission_id is required")
        if not kind:
            raise ValueError("kind is required")
        return {
            "research_output": create_research_output(
                ledger,
                manifest,
                mission_id,
                kind,
                reason=reason or "live research sandbox output",
            )
        }

    if action == "export_research_pdf":
        mission_id = str(payload.get("mission_id", "")).strip()
        if not mission_id:
            raise ValueError("mission_id is required")
        return {
            "research_pdf": export_research_pdf(
                ledger,
                manifest,
                mission_id,
                payload.get("output_path") or "reports/lucien_research_packet.pdf",
            )
        }

    if action == "autonomy_review":
        item_id = str(payload.get("item_id", "")).strip()
        decision = str(payload.get("decision", "")).strip()
        if not item_id:
            raise ValueError("item_id is required")
        if decision not in {"approve", "reject"}:
            raise ValueError("decision must be approve or reject")
        item = review_autonomy_action(
            ledger,
            manifest.system_id,
            item_id,
            decision,
            reason=reason,
        )
        return {"autonomy_item": item.to_dict()}

    if action == "autonomy_execute":
        item_id = str(payload.get("item_id", "")).strip()
        if not item_id:
            raise ValueError("item_id is required")
        result = execute_autonomy_action(
            ledger,
            manifest,
            item_id,
            project_root=Path.cwd(),
            reason=reason,
        )
        return {"autonomy_execution": result}

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
    mission_evidence = {
        brief["mission"]["mission_id"]: evidence_for_target(
            ledger.events(),
            "mission",
            brief["mission"]["mission_id"],
        )
        for brief in missions
    }
    mission_claim_map_data = mission_claim_maps(ledger)
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
    goals = [goal.to_dict() for goal in goal_records_from_events(ledger.events())]
    mission_flows = {
        flow.mission_id: flow.to_dict()
        for flow in mission_flows_from_events(ledger.events())
    }
    mission_autonomy = [
        record.to_dict()
        for record in mission_autonomy_recommendations_from_events(ledger.events())
    ]
    mission_onboarding = {}
    for brief in mission_briefs_from_events(ledger.events()):
        if brief.mission.status.value == "open":
            mission_onboarding[brief.mission.mission_id] = mission_onboarding_state(
                ledger,
                brief.mission.mission_id,
            ).to_dict()
    learning_reviews = [
        record.to_dict()
        for record in learning_review_records_from_events(ledger.events())
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
    latest_daily_loop = latest_auto_daily_research_loop(ledger.events())
    session_id = latest_session_id(ledger)
    session_replay = (
        build_session_replay(ledger, manifest, session_id).to_dict()
        if session_id
        else None
    )
    status_payload = {
        "summary": summary,
        "daily": daily_command_center(ledger, manifest),
        "startup_health": startup_health(ledger, manifest),
        "project_brief": project_build_brief(Path.cwd()),
        "build_review": build_review(Path.cwd()),
        "checkpoint_story": checkpoint_story(Path.cwd()),
        "commit_readiness": commit_readiness(Path.cwd()),
        "next_build": next_governed_build(ledger, manifest),
        "continuity_certification": continuity_certification(ledger, manifest).to_dict(),
        "workbench": workbench_status(ledger, manifest),
        "model_adapter": _model_diagnostic_with_runtime(),
        "model_usage": model_usage,
        "daily_research_loop": latest_daily_loop.to_dict() if latest_daily_loop else None,
        "research_sandbox": research_sandbox_status(ledger, manifest),
        "research_outputs": [
            output.to_dict() for output in research_outputs_from_events(ledger.events())
        ],
        "autonomy_queue": [
            item.to_dict() for item in autonomy_queue_items_from_events(ledger.events())
        ],
        "autonomy_executions": [
            record.to_dict()
            for record in autonomy_execution_records_from_events(ledger.events())
        ],
        "steward_inbox": [item.to_dict() for item in steward_inbox(ledger)],
        "csm_state": latest_signal["state"] if latest_signal else "unknown",
        "output_gate": latest_gate or {},
        "open_reflection_tasks": report.active_reflection_tasks,
        "active_growth": active_growth,
        "memory_inbox": memory_inbox,
        "growth_conflicts": unresolved_conflicts,
        "missions": missions,
        "mission_evidence": mission_evidence,
        "mission_claim_maps": mission_claim_map_data,
        "mission_flows": mission_flows,
        "mission_onboarding": mission_onboarding,
        "mission_autonomy": mission_autonomy,
        "learning_reviews": learning_reviews,
        "goals": goals,
        "daily_plan": daily_plan(ledger, manifest),
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
    status_payload["start_here"] = start_here_decision(status_payload)
    status_payload["cold_open"] = cold_open_report(ledger, manifest)
    return status_payload


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


def _model_diagnostic_with_runtime() -> dict[str, Any]:
    diagnostic = model_environment_diagnostic()
    runtime = _local_model_runtime_status(diagnostic)
    diagnostic["local_runtime"] = runtime
    diagnostic["local_model_available"] = bool(runtime.get("available"))
    return diagnostic


def _local_model_runtime_status(diagnostic: dict[str, Any]) -> dict[str, Any]:
    base_url = str(diagnostic.get("local_base_url") or "http://127.0.0.1:11434").rstrip("/")
    model = str(diagnostic.get("local_model") or "")
    if not diagnostic.get("local_model_configured"):
        return {
            "available": False,
            "reason": "Local model is not configured.",
            "model_present": False,
        }
    try:
        with request.urlopen(f"{base_url}/api/tags", timeout=0.35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "reason": "Local model unavailable. Start Ollama or switch to Debug Mode.",
            "error": exc.__class__.__name__,
            "model_present": False,
        }
    model_names = {str(item.get("name", "")) for item in payload.get("models", [])}
    model_present = model in model_names
    return {
        "available": model_present,
        "reason": "ready" if model_present else f"Model {model} is not installed in Ollama.",
        "model_present": model_present,
        "model_count": len(model_names),
    }


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
        "latest_requested_model_mode": latest.get("requested_model_mode", "none"),
        "latest_brain_route_id": latest.get("brain_route_id", "none"),
        "latest_brain_task_type": latest.get("brain_route_task_type", "none"),
        "latest_brain_route_reason": latest.get("brain_route_reason", "none"),
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


def _send_report_file(handler: BaseHTTPRequestHandler, request_path: str) -> None:
    relative = request_path.lstrip("/")
    path = Path(relative)
    if path.parts[:1] != ("reports",) or ".." in path.parts or not path.exists():
        handler.send_error(404)
        return
    content_type = "application/octet-stream"
    if path.suffix == ".pdf":
        content_type = "application/pdf"
    elif path.suffix == ".html":
        content_type = "text/html; charset=utf-8"
    elif path.suffix in {".md", ".txt"}:
        content_type = "text/plain; charset=utf-8"
    body = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
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
    :root {
      --ink:#ecf2ee;
      --muted:#9fb0a8;
      --line:#2f3d37;
      --paper:#0d1210;
      --panel:#141c18;
      --panel-2:#19241f;
      --deep:#09100d;
      --green:#42c57a;
      --teal:#54c4b3;
      --amber:#d8a13a;
      --red:#e06464;
      --input:#0f1714;
      --shadow: 0 18px 48px rgba(0,0,0,.32);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 18% 0%, rgba(84,196,179,.12), transparent 32rem),
        radial-gradient(circle at 82% 10%, rgba(216,161,58,.10), transparent 28rem),
        linear-gradient(180deg, #101713 0%, var(--paper) 42%, #090d0b 100%);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    header {
      padding: 28px clamp(18px, 4vw, 52px);
      background:
        linear-gradient(135deg, rgba(10,18,14,.96), rgba(18,35,29,.92)),
        var(--deep);
      color: var(--ink);
      border-bottom: 1px solid rgba(255,255,255,.08);
      box-shadow: 0 8px 32px rgba(0,0,0,.34);
    }
    h1 { margin: 0 0 6px; font-size: 30px; line-height: 1.08; }
    h2 { margin: 0 0 12px; font-size: 17px; line-height: 1.2; color: #f4f8f5; }
    main { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 18px; max-width: 1360px; margin: 0 auto; padding: 18px; }
    .start-here {
      grid-column: 1 / -1;
      display: grid;
      gap: 12px;
      border-color: rgba(84,196,179,.32);
      background:
        linear-gradient(180deg, rgba(84,196,179,.12), rgba(25,36,31,.96)),
        var(--panel);
    }
    .start-hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: center;
    }
    .start-title { font-size: 28px; line-height: 1.08; font-weight: 950; margin: 3px 0 7px; }
    .start-summary { color: #dce8e2; line-height: 1.45; max-width: 860px; }
    .start-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
    .start-primary { min-width: 180px; min-height: 46px; font-size: 14px; }
    .start-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .start-step {
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      padding: 12px;
      background: rgba(0,0,0,.16);
    }
    .start-step.ready { border-color: rgba(66,197,122,.42); }
    .start-step.warn { border-color: rgba(216,161,58,.42); }
    .start-step.blocked { border-color: rgba(224,100,100,.42); }
    .cold-open-card {
      border: 1px solid rgba(84,196,179,.22);
      border-radius: 8px;
      padding: 12px;
      background: rgba(84,196,179,.07);
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }
    .cold-open-text { color: #dff3eb; line-height: 1.45; overflow-wrap: anywhere; }
    .template-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .template-button {
      min-height: 86px;
      display: block;
      text-align: left;
      border-color: rgba(255,255,255,.14);
      background: rgba(255,255,255,.055);
      box-shadow: none;
      color: #edf4f0;
    }
    .template-button strong { display: block; margin-bottom: 5px; font-size: 14px; }
    .template-button span { display: block; color: var(--muted); font-size: 12px; line-height: 1.35; font-weight: 700; }
    .home { grid-column: 1 / -1; display: grid; gap: 14px; }
    .home-top { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(280px, .75fr); gap: 12px; }
    .home-title { font-size: 25px; font-weight: 900; margin: 0 0 4px; }
    .home-subtitle { color: var(--muted); font-size: 14px; }
    .home-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .guided-workbench {
      display: grid;
      grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
      gap: 12px;
      align-items: stretch;
    }
    .mode-picker { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
    .mode-pill {
      min-height: 38px;
      background: rgba(255,255,255,.055);
      border-color: rgba(255,255,255,.16);
      box-shadow: none;
    }
    .mode-pill.active {
      background: linear-gradient(180deg, #28765d, #1e5b49);
      border-color: rgba(84,196,179,.7);
      box-shadow: 0 10px 26px rgba(0,0,0,.22);
    }
    .guided-action {
      border: 1px solid rgba(84,196,179,.26);
      background: linear-gradient(180deg, rgba(84,196,179,.10), rgba(255,255,255,.045));
    }
    .guided-action-title { font-size: 22px; font-weight: 900; margin: 4px 0 6px; }
    .guided-status { color: #dff3eb; font-size: 14px; line-height: 1.45; }
    .impact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .impact-list { margin: 8px 0 0; padding-left: 18px; color: var(--muted); font-size: 13px; line-height: 1.45; }
    .impact-list li { margin: 4px 0; }
    .guided-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
    .guided-fact {
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      padding: 9px;
      background: rgba(0,0,0,.14);
      color: #dfe8e3;
      font-size: 12px;
    }
    .output-workspace {
      grid-column: 1 / -1;
      display: grid;
      gap: 12px;
      border-color: rgba(84,196,179,.18);
    }
    .output-shell {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(260px, .45fr);
      gap: 12px;
    }
    .output-body {
      min-height: 220px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      padding: 14px;
      background: rgba(5,9,7,.42);
      color: #eef7f1;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      line-height: 1.55;
    }
    .review-needed {
      border-left: 4px solid var(--amber);
    }
    .startup-health {
      border-left: 4px solid var(--green);
    }
    .startup-health.needs_attention {
      border-left-color: var(--amber);
    }
    .startup-health.blocked {
      border-left-color: var(--red);
    }
    .mission-dashboard { grid-column: 1 / -1; display: grid; gap: 12px; }
    .mission-controls { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: center; }
    .mission-card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }
    .mission-card.active { border-color: rgba(66,197,122,.72); box-shadow: inset 4px 0 0 var(--green), 0 0 0 1px rgba(66,197,122,.08); }
    section {
      background: linear-gradient(180deg, rgba(25,36,31,.96), rgba(18,26,22,.96));
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
    }
    .chat { min-height: 560px; display: flex; flex-direction: column; }
    .messages {
      flex: 1;
      overflow-y: auto;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      padding: 12px;
      background: linear-gradient(180deg, rgba(8,13,11,.78), rgba(12,18,15,.92));
    }
    .msg {
      margin: 0 0 12px;
      padding: 12px;
      border: 1px solid rgba(255,255,255,.08);
      border-left: 4px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.045);
      color: #edf4f0;
      overflow-wrap: anywhere;
    }
    .msg.user { border-left-color: var(--amber); }
    .msg.lucien { border-left-color: var(--green); }
    form { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 8px; margin-top: 12px; }
    input, select, textarea {
      padding: 10px;
      font: inherit;
      border: 1px solid rgba(255,255,255,.12);
      border-radius: 8px;
      background: var(--input);
      color: var(--ink);
      min-width: 0;
      outline: none;
    }
    input:focus, select:focus, textarea:focus { border-color: rgba(84,196,179,.75); box-shadow: 0 0 0 3px rgba(84,196,179,.14); }
    textarea { min-height: 72px; resize: vertical; }
    .model-controls { grid-column: 1 / -1; display: grid; gap: 10px; align-items: center; }
    .brain-mode-row { display: grid; grid-template-columns: minmax(180px, 240px) minmax(0, 1fr); gap: 10px; align-items: center; }
    .brain-status {
      grid-column: 1 / -1;
      border: 1px solid rgba(84,196,179,.22);
      border-radius: 8px;
      padding: 10px;
      background: rgba(84,196,179,.07);
      color: #dff3eb;
      font-size: 13px;
      line-height: 1.45;
    }
    .warning {
      border-color: rgba(216,161,58,.48);
      background: rgba(216,161,58,.10);
      color: #ffe1a8;
    }
    .checkline { display: flex; gap: 8px; align-items: center; color: var(--muted); font-size: 13px; font-weight: 700; }
    .checkline input { width: auto; }
    button {
      min-height: 40px;
      border: 1px solid rgba(84,196,179,.42);
      border-radius: 8px;
      background: linear-gradient(180deg, #28765d, #1e5b49);
      color: white;
      padding: 0 14px;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 10px 26px rgba(0,0,0,.26);
    }
    button:hover { border-color: rgba(84,196,179,.78); filter: brightness(1.08); }
    button.secondary { background: rgba(255,255,255,.055); color: #dce8e2; border-color: rgba(255,255,255,.14); box-shadow: none; }
    .side { display: grid; gap: 18px; }
    .metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
    .metric {
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      padding: 11px;
      background: rgba(255,255,255,.045);
    }
    .label { color: var(--muted); text-transform: uppercase; font-size: 11px; font-weight: 800; }
    .value { margin-top: 5px; font-size: 18px; font-weight: 800; overflow-wrap: anywhere; }
    .queue { display: grid; gap: 10px; }
    .item {
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      background: rgba(255,255,255,.045);
      padding: 11px;
    }
    .item-title { font-weight: 800; overflow-wrap: anywhere; }
    .item-meta { color: var(--muted); font-size: 12px; margin-top: 4px; overflow-wrap: anywhere; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .actions button { min-height: 32px; font-size: 12px; padding: 0 10px; }
    .events { max-height: 360px; overflow-y: auto; }
    .event { border-bottom: 1px solid rgba(255,255,255,.08); padding: 8px 0; color: #d6e0da; }
    details.advanced {
      grid-column: 1 / -1;
      border: 1px solid rgba(255,255,255,.08);
      border-radius: 8px;
      background: rgba(255,255,255,.035);
      box-shadow: var(--shadow);
    }
    details.advanced > summary {
      cursor: pointer;
      padding: 16px;
      font-weight: 900;
      color: #f4f8f5;
      list-style: none;
    }
    details.advanced > summary::-webkit-details-marker { display: none; }
    details.advanced > summary::after { content: "Show"; float: right; color: var(--muted); font-size: 12px; text-transform: uppercase; }
    details.advanced[open] > summary::after { content: "Hide"; }
    .advanced-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; padding: 0 16px 16px; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #9ee7c0; }
    ::placeholder { color: #73867d; }
    @media (max-width: 900px) { main { grid-template-columns: 1fr; padding: 12px; } form { grid-template-columns: 1fr; } .home-top, .brain-mode-row, .mission-controls, .advanced-grid, .guided-workbench, .impact-grid, .output-shell, .start-hero, .start-steps, .template-grid, .cold-open-card { grid-template-columns: 1fr; } .start-actions { justify-content: flex-start; } }
  </style>
</head>
<body>
  <header>
    <h1>Lucien Live Chat v0.1</h1>
    <div>Talk to Lucien through PCA. The model speaks; governance decides what can become identity.</div>
  </header>
  <main>
    <section class="start-here">
      <div class="start-hero">
        <div>
          <div class="label">Start Here</div>
          <div id="startHereTitle" class="start-title">Checking Lucien</div>
          <div id="startHereSummary" class="start-summary">Lucien is checking startup health, current mission, steward review pressure, and brain mode.</div>
        </div>
        <div class="start-actions">
          <button type="button" id="startHerePrimary" class="start-primary">Show Me What To Do</button>
          <button type="button" id="startHereStarterPack" class="secondary">Create Starter Pack</button>
          <button type="button" id="startHereReview" class="secondary">Review Inbox</button>
        </div>
      </div>
      <div class="start-steps">
        <div id="startStepMissionCard" class="start-step">
          <div class="label">1 / Mission</div>
          <div class="item-title" id="startStepMissionTitle">Choose work</div>
          <div class="item-meta" id="startStepMission">Loading mission state.</div>
        </div>
        <div id="startStepSetupCard" class="start-step">
          <div class="label">2 / Setup</div>
          <div class="item-title" id="startStepSetupTitle">Prepare the work</div>
          <div class="item-meta" id="startStepSetup">Loading starter state.</div>
        </div>
        <div id="startStepChatCard" class="start-step">
          <div class="label">3 / Chat</div>
          <div class="item-title" id="startStepChatTitle">Ask Lucien</div>
          <div class="item-meta" id="startStepChat">Loading brain mode.</div>
        </div>
      </div>
      <div class="cold-open-card">
        <div>
          <div class="label">Cold Open Report</div>
          <div id="coldOpenText" class="cold-open-text">Loading the first action report.</div>
        </div>
        <div class="actions">
          <button type="button" id="coldOpenAsk" class="secondary">Ask This</button>
          <button type="button" id="coldOpenCopy" class="secondary">Copy</button>
        </div>
      </div>
      <div>
        <div class="label">Quick Start Missions</div>
        <div class="template-grid" id="missionTemplates">
          <button type="button" class="template-button" data-mission-template="coherence_research">
            <strong>Coherence Physics Research</strong>
            <span>Grow the theory, map claims, gather evidence, and draft clear material.</span>
          </button>
          <button type="button" class="template-button" data-mission-template="build_lucien">
            <strong>Build Lucien</strong>
            <span>Improve the local governed AI workbench and make it easier to use.</span>
          </button>
          <button type="button" class="template-button" data-mission-template="public_writing">
            <strong>Public Writing</strong>
            <span>Turn PCA and Coherence Physics into readable posts, docs, and demos.</span>
          </button>
        </div>
      </div>
    </section>
    <section class="home">
      <div class="home-top">
        <div>
          <h2 class="home-title">Daily Command Center</h2>
          <div id="homeSubtitle" class="home-subtitle">What are we working on today?</div>
        </div>
        <div class="home-actions">
          <button type="button" id="homeStartMission">Start Mission</button>
          <button type="button" id="homeCleanSession" class="secondary">Start Clean Daily Session</button>
          <button type="button" id="homeResearchLoop" class="secondary">Launch Research Loop</button>
          <button type="button" id="homeDailyPlan" class="secondary">Generate Daily Plan</button>
          <button type="button" id="homeLearningReview" class="secondary">Review Session for Learning</button>
          <button type="button" id="homeReviewInbox" class="secondary">Review Inbox</button>
          <button type="button" id="homeSessionReplay" class="secondary">View Session Replay</button>
        </div>
      </div>
      <div class="guided-workbench">
        <div id="guidedAction" class="item guided-action">
          <div class="label">What do you want Coherence AI to help with today?</div>
          <div class="mode-picker" role="group" aria-label="Work mode">
            <button type="button" class="mode-pill" data-work-mode="research">Research</button>
            <button type="button" class="mode-pill" data-work-mode="write">Write</button>
            <button type="button" class="mode-pill" data-work-mode="build">Build</button>
          </div>
          <div class="label">Today's Focus</div>
          <div id="guidedFocus" class="guided-action-title">loading</div>
          <div id="guidedStatus" class="guided-status">loading</div>
          <div class="actions">
            <button type="button" id="guidedPrimary">Start</button>
            <button type="button" id="guidedChangeFocus" class="secondary">Change Focus</button>
          </div>
        </div>
        <div id="guidedImpact" class="item">
          <div class="item-title">What This Will Do</div>
          <div class="impact-grid">
            <div>
              <div class="label">This will</div>
              <ul id="guidedDoes" class="impact-list"></ul>
            </div>
            <div>
              <div class="label">This will not</div>
              <ul id="guidedDoesNot" class="impact-list"></ul>
            </div>
          </div>
          <div id="guidedFacts" class="guided-facts"></div>
        </div>
      </div>
      <div id="reviewNeededCard" class="item review-needed"></div>
      <div id="startupHealth" class="item startup-health"></div>
      <div id="dailyBriefing" class="item"></div>
      <div id="dailyResearchLoop" class="item"></div>
      <div id="dailyCards" class="mission-card-grid"></div>
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
    <section class="output-workspace">
      <div class="mission-controls">
        <div>
          <h2>Output Workspace</h2>
          <div class="item-meta">Read the latest draft for the active mission. Drafts stay proposed until steward review.</div>
        </div>
        <div class="actions">
          <button type="button" id="workspaceRevise" class="secondary">Revise</button>
          <button type="button" id="workspaceReview" class="secondary">Review Draft</button>
          <button type="button" id="workspaceEvidence" class="secondary">Accept as Evidence</button>
          <button type="button" id="workspaceKeepDraft" class="secondary">Keep as Draft</button>
          <button type="button" id="workspaceExport" class="secondary">Export Markdown</button>
          <button type="button" id="workspaceExportPdf" class="secondary">Save Research PDF</button>
        </div>
      </div>
      <div class="output-shell">
        <div>
          <div id="workspaceTitle" class="guided-action-title">No output selected</div>
          <div id="workspaceMeta" class="item-meta"></div>
          <pre id="workspaceBody" class="output-body"></pre>
        </div>
        <div id="workspaceDetails" class="queue"></div>
      </div>
    </section>
    <section class="mission-dashboard">
      <div class="mission-controls">
        <div>
          <h2>Project Build Brief</h2>
          <div class="item-meta">Local repo state and the safest next engineering move.</div>
        </div>
        <button type="button" id="refreshProjectBrief" class="secondary">Refresh Brief</button>
      </div>
      <div id="projectBriefCards" class="mission-card-grid"></div>
      <div id="projectBriefFiles" class="queue"></div>
      <div id="buildReviewCards" class="mission-card-grid"></div>
      <div id="buildReviewDetails" class="queue"></div>
      <div id="commitReadinessCards" class="mission-card-grid"></div>
      <div id="commitReadinessDetails" class="queue"></div>
      <div id="checkpointStory" class="queue"></div>
      <div id="nextBuild" class="queue"></div>
    </section>
    <section class="mission-dashboard">
      <div class="mission-controls">
        <div>
          <h2>Mission Dashboard</h2>
          <div class="item-meta">Choose the active mission and move from status to the next safe action.</div>
        </div>
        <select id="activeMissionSelect"></select>
      </div>
      <div id="missionCards" class="mission-card-grid"></div>
    </section>
    <section class="mission-dashboard">
      <div class="mission-controls">
        <div>
          <h2>Mission Evidence</h2>
          <div class="item-meta">Ground the active mission with raw, reviewed, disputed, or stale evidence.</div>
        </div>
        <div class="actions">
          <button type="button" id="missionEvidenceAdd" class="secondary">Add Source</button>
          <button type="button" id="missionEvidenceCaptureChat" class="secondary">Capture Last Reply</button>
          <button type="button" id="missionEvidenceReview" class="secondary">Review Evidence</button>
        </div>
      </div>
      <div id="missionEvidenceSummary" class="metrics"></div>
      <div id="missionEvidence" class="queue"></div>
    </section>
    <section class="mission-dashboard">
      <div class="mission-controls">
        <div>
          <h2>Mission Claim Map</h2>
          <div class="item-meta">Shows whether mission hypotheses have raw, reviewed, disputed, stale, or missing evidence.</div>
        </div>
        <button type="button" id="missionClaimMapRefresh" class="secondary">Refresh Claim Map</button>
      </div>
      <div id="missionClaimMapSummary" class="metrics"></div>
      <div id="missionClaimMap" class="queue"></div>
    </section>
    <section class="mission-dashboard">
      <div class="mission-controls">
        <div>
          <h2>Research Sandbox</h2>
          <div class="item-meta">Draft freely. Nothing becomes accepted memory, evidence, or truth until steward review.</div>
        </div>
        <div class="actions">
          <button type="button" id="researchBriefBtn" class="secondary">Generate Research Brief</button>
          <button type="button" id="claimMapBtn" class="secondary">Create Claim Map</button>
          <button type="button" id="paperDraftBtn" class="secondary">Draft Paper</button>
        </div>
      </div>
      <div id="researchSandboxStatus" class="item"></div>
      <div id="researchOutputs" class="queue"></div>
    </section>
    <section class="mission-dashboard">
      <div class="mission-controls">
        <div>
          <h2>Goals</h2>
          <div class="item-meta">Durable directions that can link to missions without executing actions automatically.</div>
        </div>
        <button type="button" id="generateDailyPlan" class="secondary">Generate Daily Plan</button>
      </div>
      <form id="goalForm">
        <input id="goalTitle" placeholder="Goal title">
        <textarea id="goalPurpose" placeholder="Why this goal matters"></textarea>
        <textarea id="goalSuccess" placeholder="Success criteria"></textarea>
        <select id="goalPriority">
          <option value="medium" selected>medium</option>
          <option value="high">high</option>
          <option value="low">low</option>
          <option value="critical">critical</option>
        </select>
        <button type="submit">Create Goal</button>
      </form>
      <div id="dailyPlan" class="queue"></div>
      <div id="goals" class="mission-card-grid"></div>
    </section>
    <section class="chat">
      <h2>Chat</h2>
      <div id="messages" class="messages"></div>
      <form id="chatForm">
        <textarea id="message" placeholder="Ask Lucien what changed in his state..."></textarea>
        <button type="submit" id="sendMessage">Send</button>
        <button type="button" id="speak" class="secondary">Speak</button>
        <div class="model-controls">
          <div class="brain-mode-row">
            <label>
              <div class="label">Brain Mode</div>
              <select id="brainMode">
                <option value="local_ollama" selected>Local Mode</option>
                <option value="serious_only">Cloud Assist</option>
                <option value="echo">Debug</option>
              </select>
            </label>
            <label class="checkline"><input id="useOpenAI" type="checkbox"> Use OpenAI for this message</label>
          </div>
          <div id="brainStatus" class="brain-status">Current brain: loading</div>
        </div>
      </form>
    </section>
    <div class="side">
      <section>
        <h2>Governance Status</h2>
        <div class="metrics">
          <div class="metric"><div class="label">Continuity</div><div id="claim" class="value">loading</div></div>
          <div class="metric"><div class="label">CSM State</div><div id="csm" class="value">loading</div></div>
          <div class="metric"><div class="label">Output</div><div id="gate" class="value">loading</div></div>
          <div class="metric"><div class="label">Recovery</div><div id="recovery" class="value">loading</div></div>
          <div class="metric"><div class="label">Open Tasks</div><div id="tasks" class="value">loading</div></div>
          <div class="metric"><div class="label">Conflicts</div><div id="conflicts" class="value">loading</div></div>
          <div class="metric"><div class="label">Cloud Assist</div><div id="cloudAssist" class="value">loading</div></div>
          <div class="metric"><div class="label">Local Brain</div><div id="localModel" class="value">loading</div></div>
          <div class="metric"><div class="label">Local Status</div><div id="localStatus" class="value">loading</div></div>
        </div>
      </section>
      <section>
        <h2>Continuity Certification</h2>
        <div id="certification" class="queue"></div>
      </section>
      <section>
        <h2>Model Usage</h2>
        <div class="metrics">
          <div class="metric"><div class="label">Current Mode</div><div id="usageMode" class="value">loading</div></div>
          <div class="metric"><div class="label">Last Brain Used</div><div id="usageProvider" class="value">loading</div></div>
          <div class="metric"><div class="label">Cloud Assist</div><div id="usageCloudAssist" class="value">loading</div></div>
          <div class="metric"><div class="label">Latest Cost</div><div id="usageCost" class="value">loading</div></div>
          <div class="metric"><div class="label">Session Cost</div><div id="sessionCost" class="value">loading</div></div>
        </div>
      </section>
      <section>
        <h2>Autonomy Queue</h2>
        <div class="item-meta">Proposed actions that need steward approval before any future execution path may use them.</div>
        <div id="autonomyQueue" class="queue"></div>
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
        <h2>Learning Review</h2>
        <div class="actions">
          <button type="button" id="reviewSessionLearning">Review Session for Learning</button>
        </div>
        <div id="learningReview" class="queue"></div>
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
    </div>
    <details id="advancedDiagnostics" class="advanced">
      <summary>Advanced Diagnostics</summary>
      <div class="advanced-grid">
        <section>
          <h2>Developer Brain Routing</h2>
          <div class="metrics">
            <div class="metric"><div class="label">Routing</div><div id="brainRoute" class="value">loading</div></div>
            <div class="metric"><div class="label">Brain Task</div><div id="brainTask" class="value">loading</div></div>
            <div class="metric"><div class="label">Raw Continuity</div><div id="rawClaim" class="value">loading</div></div>
            <div class="metric"><div class="label">Raw Output Gate</div><div id="rawGate" class="value">loading</div></div>
            <div class="metric"><div class="label">Configured Cloud Model</div><div id="configuredCloudModel" class="value">loading</div></div>
            <div class="metric"><div class="label">API Key</div><div id="apiKey" class="value">loading</div></div>
            <div class="metric"><div class="label">Latest Tokens</div><div id="usageTokens" class="value">loading</div></div>
          </div>
          <label>
            <div class="label">Advanced route override</div>
            <select id="advancedModelMode">
              <option value="">Use selected Brain Mode</option>
              <option value="auto">Brain Router</option>
              <option value="local_first">Local first with fallback</option>
              <option value="local_ollama">Local Ollama only</option>
              <option value="serious_only">Cloud Assist spend-safe</option>
              <option value="echo">Echo Local</option>
              <option value="openai">OpenAI direct</option>
            </select>
          </label>
        </section>
        <section>
          <h2>Steward Queue</h2>
          <div class="actions"><button type="button" id="reflectNow">Reflect Now</button></div>
          <div id="queue" class="queue"></div>
        </section>
        <section>
          <h2>Governed Context</h2>
          <div id="governedContext" class="queue"></div>
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
    </details>
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
    const missionCards = document.getElementById('missionCards');
    const activeMissionSelect = document.getElementById('activeMissionSelect');
    const missionEvidenceSummary = document.getElementById('missionEvidenceSummary');
    const missionEvidence = document.getElementById('missionEvidence');
    const missionClaimMapSummary = document.getElementById('missionClaimMapSummary');
    const missionClaimMap = document.getElementById('missionClaimMap');
    const goals = document.getElementById('goals');
    const dailyPlan = document.getElementById('dailyPlan');
    const researchSandboxStatus = document.getElementById('researchSandboxStatus');
    const researchOutputs = document.getElementById('researchOutputs');
    const workspaceTitle = document.getElementById('workspaceTitle');
    const workspaceMeta = document.getElementById('workspaceMeta');
    const workspaceBody = document.getElementById('workspaceBody');
    const workspaceDetails = document.getElementById('workspaceDetails');
    const missionSteps = document.getElementById('missionSteps');
    const skillMemory = document.getElementById('skillMemory');
    const autonomyQueue = document.getElementById('autonomyQueue');
    const stewardInbox = document.getElementById('stewardInbox');
    const learningReview = document.getElementById('learningReview');
    const certification = document.getElementById('certification');
    let activeInboxFilter = 'all';
    let selectedMissionId = window.localStorage.getItem('lucien.activeMissionId') || '';
    let selectedWorkMode = window.localStorage.getItem('lucien.workMode') || '';
    let selectedOutputId = window.sessionStorage.getItem('lucien.selectedOutputId') || '';
    let outputContentById = JSON.parse(window.sessionStorage.getItem('lucien.outputContentById') || '{}');
    let currentGuidedAction = null;
    let currentStartHereAction = {kind: 'wait'};
    let currentColdOpenPrompt = '';
    let currentStatus = null;
    let lastLucien = '';
    const missionTemplates = {
      coherence_research: {
        title: 'Coherence Physics Research Program',
        problem: 'Continue developing Coherence Physics into clear, testable, evidence-backed research material while keeping claims separated from evidence and speculation.',
        values: ['truth before comfort', 'evidence first', 'clarity', 'recoverability', 'public usefulness']
      },
      build_lucien: {
        title: 'Build Lucien Daily Workbench',
        problem: 'Make Lucien easier to use as a local governed AI workbench that can help with missions, research, evidence, writing, and safe tool use.',
        values: ['simple daily use', 'local first', 'low cost', 'governed autonomy', 'clear next actions']
      },
      public_writing: {
        title: 'Public Writing and Demo Material',
        problem: 'Turn PCA, Lucien, and Coherence Physics into understandable public explanations, demos, screenshots, posts, and release notes without overclaiming.',
        values: ['plain language', 'honesty', 'no AGI hype', 'strong examples', 'reviewable artifacts']
      }
    };

    function addMessage(kind, text) {
      const node = document.createElement('div');
      node.className = 'msg ' + kind;
      node.textContent = (kind === 'user' ? 'You: ' : 'Lucien: ') + text;
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
    }

    function renderStatus(status) {
      currentStatus = status;
      const summary = status.summary || {};
      const missionView = renderMissionDashboard(status);
      renderStartHere(status, missionView.activeMission);
      renderDailyCommandCenter(status.daily || {}, status.workbench || {}, missionView.activeMission);
      renderStartupHealth(status.startup_health || {});
      renderOutputWorkspace(status.research_outputs || [], missionView.activeMission);
      renderProjectBrief(status.project_brief || {});
      renderBuildReview(status.build_review || {});
      renderCommitReadiness(status.commit_readiness || {});
      renderCheckpointStory(status.checkpoint_story || {});
      renderNextBuild(status.next_build || {});
      document.getElementById('claim').textContent = plainContinuity(summary.current_continuity_claim || 'unknown');
      document.getElementById('csm').textContent = status.csm_state || 'unknown';
      const gate = status.output_gate || {};
      document.getElementById('gate').textContent = plainOutputGate(gate.mode, gate.allowed);
      document.getElementById('rawClaim').textContent = summary.current_continuity_claim || 'unknown';
      document.getElementById('rawGate').textContent = gate.mode ? `${gate.mode} / ${gate.allowed}` : 'none';
      document.getElementById('recovery').textContent = summary.current_recovery_status || 'none';
      document.getElementById('tasks').textContent = summary.active_reflection_task_count ?? 0;
      document.getElementById('conflicts').textContent = summary.unresolved_growth_conflict_count ?? 0;
      const modelAdapter = status.model_adapter || {};
      document.getElementById('cloudAssist').textContent = cloudAssistDailyStatus(modelAdapter);
      document.getElementById('configuredCloudModel').textContent = `${modelAdapter.configured_provider || 'unknown'} / ${modelAdapter.configured_model || 'unknown'}`;
      document.getElementById('apiKey').textContent = modelAdapter.openai_key_present ? 'present' : 'missing';
      document.getElementById('localModel').textContent = `${modelAdapter.local_provider || 'none'} / ${modelAdapter.local_model || 'none'}`;
      const localRuntime = modelAdapter.local_runtime || {};
      document.getElementById('localStatus').textContent = localRuntime.available ? 'ready' : (localRuntime.reason || (modelAdapter.local_model_configured ? 'configured' : 'missing'));
      const usage = status.model_usage || {};
      document.getElementById('usageMode').textContent = plainBrainMode(getSelectedModelMode());
      document.getElementById('usageProvider').textContent = `${usage.latest_provider || 'none'} / ${usage.latest_model || 'none'}`;
      document.getElementById('usageCloudAssist').textContent = cloudAssistUsageStatus(usage, modelAdapter);
      document.getElementById('usageTokens').textContent = usage.latest_total_tokens || 0;
      document.getElementById('usageCost').textContent = `$${Number(usage.latest_cost_usd || 0).toFixed(6)}`;
      document.getElementById('sessionCost').textContent = `$${Number(usage.estimated_session_cost_usd || 0).toFixed(6)}`;
      document.getElementById('brainRoute').textContent = plainRouting(usage.latest_requested_model_mode, usage.latest_model_mode);
      document.getElementById('brainTask').textContent = usage.latest_brain_task_type || 'none';
      renderBrainStatus(status);
      renderCertification(status.continuity_certification || {});
      renderQueue(status.open_reflection_tasks || []);
      renderSelfModel(status.self_model || {});
      renderGovernedContext(status.governed_context || {});
      renderMemoryInbox(status.memory_inbox || []);
      renderRecall((status.self_model || {}).memory_cards || []);
      renderGoals(status.goals || [], status.missions || []);
      renderDailyPlan(status.daily_plan || {});
      renderMissions(status.missions || [], status.mission_flows || {}, status.mission_autonomy || []);
      renderMissionEvidence(status.mission_evidence || {}, missionView.activeMission);
      renderMissionClaimMap(status.mission_claim_maps || {}, missionView.activeMission);
      renderResearchSandbox(status.research_sandbox || {}, status.research_outputs || [], missionView.activeMission);
      renderMissionSteps(status.mission_steps || [], status.tools || {}, status.tool_executions || [], status.tool_previews || []);
      renderSkillMemory(status.skill_candidates || [], status.accepted_skills || []);
      renderAutonomyQueue(status.autonomy_queue || [], status.autonomy_executions || []);
      renderStewardInbox(status.steward_inbox || []);
      renderLearningReview(status.learning_reviews || []);
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

    function plainContinuity(value) {
      const labels = {
        certified_continuity: 'Continuity: Certified',
        review_required: 'Continuity: Under Review',
        uncertified_continuity: 'Continuity: Uncertified',
        declared_fork: 'Continuity: Fork Declared',
        continuity_break: 'Continuity: Break Recorded'
      };
      return labels[value] || `Continuity: ${value || 'Unknown'}`;
    }

    function plainOutputGate(mode, allowed) {
      const labels = {
        normal_identity: 'Normal Identity Output',
        disclose_review: 'Review Disclosure Required',
        operational_only: 'Operational Answers Only',
        fork_disclosure: 'Fork Disclosure Required',
        recovery_status_only: 'Recovery Status Only'
      };
      const text = labels[mode] || mode || 'No output gate event';
      return allowed === false ? `${text} / Blocked` : text;
    }

    function plainRouting(requested, selected) {
      const route = `${requested || 'none'} -> ${selected || 'none'}`;
      const labels = {
        'local_ollama -> local_ollama': 'Routing: Local model',
        'local_first -> local_first': 'Routing: Local first',
        'serious_only -> echo': 'Routing: Cloud assist idle',
        'serious_only -> openai': 'Routing: Cloud assist',
        'echo -> echo': 'Routing: Debug echo',
        'auto -> local_first': 'Routing: Local first',
        'auto -> echo': 'Routing: Diagnostic echo',
        'auto -> openai': 'Routing: Cloud assist',
        'openai -> openai': 'Routing: OpenAI direct'
      };
      return labels[route] || `Routing: ${route.replaceAll('_', ' ')}`;
    }

    function plainBrainMode(mode) {
      const labels = {
        local_ollama: 'Local Mode',
        local_first: 'Local Mode',
        serious_only: 'Cloud Assist',
        echo: 'Debug Mode',
        openai: 'Cloud Assist',
        auto: 'Local Mode'
      };
      return labels[mode] || mode || 'Local Mode';
    }

    function cloudAssistDailyStatus(modelAdapter) {
      if (!modelAdapter.openai_key_present) return 'Unavailable';
      const mode = getSelectedModelMode();
      if (mode === 'serious_only' || mode === 'local_first' || mode === 'auto') return 'Available when checked';
      if (mode === 'openai') return 'Direct mode in Advanced';
      return 'Available / off';
    }

    function cloudAssistUsageStatus(usage, modelAdapter) {
      if (!modelAdapter.openai_key_present) return 'Unavailable';
      if (usage.latest_provider === 'openai') return 'Used for last reply';
      const mode = getSelectedModelMode();
      if (mode === 'serious_only' || mode === 'local_first' || mode === 'auto') {
        return document.getElementById('useOpenAI').checked ? 'On for next message' : 'Off unless checked';
      }
      return 'Off in this mode';
    }

    function renderBrainStatus(status) {
      const modelAdapter = status.model_adapter || {};
      const usage = status.model_usage || {};
      const runtime = modelAdapter.local_runtime || {};
      const openaiAvailable = modelAdapter.openai_key_present ? 'available' : 'not configured';
      const localName = `${modelAdapter.local_provider || 'ollama'} / ${modelAdapter.local_model || 'none'}`;
      const current = `${usage.latest_provider || modelAdapter.local_provider || 'none'} / ${usage.latest_model || modelAdapter.local_model || 'none'}`;
      const node = document.getElementById('brainStatus');
      const localWarning = runtime.available === false ? `Local model unavailable. Start Ollama or switch to Debug Mode. ${runtime.reason || ''}` : '';
      node.className = 'brain-status' + (localWarning ? ' warning' : '');
      node.innerHTML = [
        `<strong>Current brain:</strong> ${escapeHtml(current)}`,
        `<strong>Local:</strong> ${escapeHtml(localName)}`,
        `<strong>Cloud assist:</strong> ${escapeHtml(openaiAvailable)}`,
        `<strong>Latest cost:</strong> $${Number(usage.latest_cost_usd || 0).toFixed(6)}`,
        `<strong>Session cost:</strong> $${Number(usage.estimated_session_cost_usd || 0).toFixed(6)}`,
        localWarning ? `<br>${escapeHtml(localWarning)}` : ''
      ].join(' &nbsp; ');
      updateBrainModeControls();
    }

    function setStartStep(cardId, titleId, bodyId, title, body, state) {
      const card = document.getElementById(cardId);
      card.className = `start-step ${state || ''}`;
      document.getElementById(titleId).textContent = title;
      document.getElementById(bodyId).textContent = body;
    }

    function renderStartHere(status, selectedMission) {
      const health = status.startup_health || {};
      const workbench = status.workbench || {};
      const modelAdapter = status.model_adapter || {};
      const usage = status.model_usage || {};
      const decision = status.start_here || {};
      const mission = selectedMission && selectedMission.mission_id ? selectedMission : null;
      const onboarding = mission && status.mission_onboarding ? status.mission_onboarding[mission.mission_id] : null;
      const inboxOpen = workbench.open_steward_inbox_count || 0;
      const inboxHigh = workbench.high_priority_inbox_count || 0;
      const staleInbox = health.stale_steward_items || 0;
      const localRuntime = modelAdapter.local_runtime || {};
      const localReady = localRuntime.available !== false;
      const title = document.getElementById('startHereTitle');
      const summary = document.getElementById('startHereSummary');
      const primary = document.getElementById('startHerePrimary');
      const starter = document.getElementById('startHereStarterPack');
      const review = document.getElementById('startHereReview');
      title.textContent = decision.title || 'You can talk to Lucien now';
      summary.textContent = decision.summary || 'Ask Lucien for the next safe step and keep it simple.';
      primary.textContent = decision.primary_label || 'Ask What To Do Next';
      currentStartHereAction = decision.kind ? decision : {kind: 'ask_next', mission_id: mission ? mission.mission_id : ''};
      starter.style.display = onboarding && onboarding.ready ? '' : 'none';
      review.style.display = inboxOpen ? '' : 'none';
      review.textContent = staleInbox > 0
        ? `Review Inbox (${staleInbox} stale)`
        : (inboxHigh > 0 ? `Review Inbox (${inboxHigh} high)` : `Review Inbox (${inboxOpen})`);

      setStartStep(
        'startStepMissionCard',
        'startStepMissionTitle',
        'startStepMission',
        mission ? mission.title : 'No mission selected',
        mission ? `Phase: ${mission.phase || 'unknown'} / Next: ${mission.next_action || workbench.recommended_next_action || 'ask Lucien for the next safe step'}` : 'Create or select one mission before trying to make Lucien work for you.',
        mission ? 'ready' : 'warn'
      );
      setStartStep(
        'startStepSetupCard',
        'startStepSetupTitle',
        'startStepSetup',
        onboarding && onboarding.ready ? 'Starter pack needed' : (inboxOpen ? 'Review pressure visible' : 'Setup is clear'),
        onboarding && onboarding.ready
          ? 'Click Create Starter Pack. It creates proposed mission structure, not accepted truth.'
          : (inboxOpen ? `${inboxOpen} steward item(s), ${inboxHigh} high priority, ${staleInbox} stale. Clear only what is actually reviewed.` : 'No setup blocker is stopping this mission right now.'),
        onboarding && onboarding.ready ? 'warn' : ((inboxHigh || staleInbox) ? 'blocked' : 'ready')
      );
      setStartStep(
        'startStepChatCard',
        'startStepChatTitle',
        'startStepChat',
        localReady ? 'Local brain ready' : 'Local brain unavailable',
        localReady
          ? `Use Local Mode for daily work. Last brain: ${usage.latest_provider || modelAdapter.local_provider || 'none'} / ${usage.latest_model || modelAdapter.local_model || 'none'}.`
          : `Start Ollama or switch to Debug Mode. ${localRuntime.reason || ''}`,
        localReady ? 'ready' : 'warn'
      );
      renderColdOpen(status.cold_open || {}, decision);
    }

    function renderColdOpen(report, decision) {
      const text = document.getElementById('coldOpenText');
      const oneSentence = report.one_sentence || decision.summary || 'Ask Lucien for the next safe step.';
      const oneAction = report.one_action || decision.primary_label || 'Ask What To Do Next';
      const mission = report.active_mission || {};
      const inbox = `${report.open_steward_items || 0} open / ${report.high_priority_steward_items || 0} high / ${report.stale_steward_items || 0} stale`;
      text.textContent = `${oneSentence} First action: ${oneAction}. Mission: ${mission.title || 'none'}. Inbox: ${inbox}.`;
      currentColdOpenPrompt = `Lucien, here is the cold open report: ${oneSentence} First action: ${oneAction}. Help me do that one action now. Keep it simple.`;
    }

    function renderDailyCommandCenter(daily, workbench, selectedMission) {
      const missionCandidate = selectedMission || workbench.active_mission || null;
      const mission = missionCandidate && missionCandidate.mission_id ? missionCandidate : null;
      document.getElementById('homeSubtitle').textContent = mission ? 'Current governed mission' : 'What are we working on today?';
      renderGuidedWorkbench(daily, workbench, mission);
      const briefing = document.getElementById('dailyBriefing');
      briefing.innerHTML = `<div class="item-title">Opening Briefing</div><div class="item-meta">${escapeHtml(daily.briefing || 'Daily briefing unavailable.')}</div>`;
      const dailyLoop = document.getElementById('dailyResearchLoop');
      const loop = currentStatus.daily_research_loop || null;
      dailyLoop.innerHTML = loop
        ? `<div class="item-title">Research Loop / ${escapeHtml(loop.status || 'prepared')}</div>
           <div class="item-meta">Focus: ${escapeHtml(loop.focus_goal_title || 'none')} / Mission: ${escapeHtml(loop.mission_title || 'none')}</div>
           <div class="item-meta">Prepared: ${escapeHtml(loop.loop_date || 'unknown')} / Proposed actions: ${(loop.proposed_item_ids || []).length}</div>`
        : `<div class="item-title">Research Loop</div><div class="item-meta">Not prepared yet. Launch the research loop to seed today's governed work.</div>`;
      const cardHost = document.getElementById('dailyCards');
      cardHost.innerHTML = '';
      const cards = daily.cards || {};
      for (const key of ['work_today', 'goals', 'blockers', 'safe_next_action', 'needs_steward_review', 'cost_brain_mode']) {
        const card = cards[key] || {};
        const row = document.createElement('div');
        row.className = 'item mission-card';
        row.innerHTML = `<div class="item-title">${escapeHtml(card.title || key)}</div><div class="item-meta">${escapeHtml(card.value || 'none')}</div>`;
        cardHost.appendChild(row);
      }
      document.getElementById('homeMission').textContent = mission ? mission.title : 'No active mission';
      document.getElementById('homePhase').textContent = mission ? mission.phase : 'none';
      document.getElementById('homeNextAction').textContent = daily.recommended_first_action || (mission ? mission.next_action || workbench.recommended_next_action : workbench.recommended_next_action || 'Open a mission before using Lucien for work.');
      document.getElementById('homeBlockers').textContent = mission ? mission.blocker_count || 0 : 0;
      document.getElementById('homeInbox').textContent = `${workbench.open_steward_inbox_count || 0} open / ${workbench.high_priority_inbox_count || 0} high`;
      document.getElementById('homeModelMode').textContent = plainBrainMode(workbench.model_mode || 'local_ollama');
      document.getElementById('homeCost').textContent = `$${Number(workbench.estimated_session_cost_usd || 0).toFixed(6)}`;
      document.getElementById('homeContinuity').textContent = `${plainContinuity(workbench.continuity_state || 'unknown')} / ${plainOutputGate(workbench.output_gate_mode, true)}`;
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

    function renderStartupHealth(health) {
      const node = document.getElementById('startupHealth');
      const status = health.status || 'unknown';
      node.className = `item startup-health ${status}`;
      const problems = health.problems || [];
      const actions = health.safe_actions || [];
      const problemText = problems.length
        ? problems.slice(0, 3).map(problem => `${problem.title}: ${problem.detail}`).join(' ')
        : 'Cold open is clear. Lucien has no startup blockers detected.';
      const buttons = actions.map(action => {
        const label = escapeHtml(action.label || action.action);
        return `<button type="button" class="secondary" data-startup-fix="${escapeHtml(action.action)}">${label}</button>`;
      }).join('');
      node.innerHTML = `
        <div class="mission-controls">
          <div>
            <div class="item-title">Startup Health Doctor / ${escapeHtml(status.replaceAll('_', ' '))}</div>
            <div class="item-meta">${escapeHtml(problemText)}</div>
            <div class="item-meta">Next: ${escapeHtml(health.recommended_next_action || 'Continue the active mission.')}</div>
          </div>
          <div class="actions">${buttons || '<button type="button" class="secondary" id="startupHealthRefresh">Refresh Health</button>'}</div>
        </div>
      `;
      for (const button of node.querySelectorAll('[data-startup-fix]')) {
        button.addEventListener('click', () => {
          steward({
            action: 'startup_health_fix',
            fix_action: button.dataset.startupFix,
            reason: 'startup health doctor safe fix'
          });
        });
      }
      const refresh = node.querySelector('#startupHealthRefresh');
      if (refresh) refresh.addEventListener('click', () => refreshStatus());
    }

    function renderGuidedWorkbench(daily, workbench, mission) {
      const actions = daily.guided_actions || {};
      if (!selectedWorkMode || !actions[selectedWorkMode]) {
        selectedWorkMode = daily.default_work_mode || 'research';
        window.localStorage.setItem('lucien.workMode', selectedWorkMode);
      }
      const baseAction = actions[selectedWorkMode] || daily.guided_action || {};
      const onboarding = mission && currentStatus && currentStatus.mission_onboarding
        ? currentStatus.mission_onboarding[mission.mission_id]
        : null;
      const action = onboarding && onboarding.ready
        ? {
            ...baseAction,
            title: 'Mission Onboarding',
            plain_english_status: onboarding.recommended_action,
            primary_label: 'Create Starter Pack',
            target_kind: 'mission_onboarding',
            what_it_does: [
              'Creates a proposed first hypothesis.',
              'Creates an evidence need.',
              'Creates a risk review item.'
            ],
            what_it_will_not_do: [
              'Will not accept the hypothesis as truth.',
              'Will not publish or edit files.',
              'Will not spend OpenAI money.'
            ],
            facts: [
              {label: 'Phase', value: onboarding.phase},
              {label: 'Needed', value: onboarding.needed.join(', ') || 'none'},
              {label: 'Cost', value: '$0 API money in Local Mode'},
              {label: 'Persistence', value: 'Ledger-backed proposed items'}
            ]
          }
        : baseAction;
      currentGuidedAction = action;
      for (const control of document.querySelectorAll('[data-work-mode]')) {
        control.classList.toggle('active', control.dataset.workMode === selectedWorkMode);
      }
      document.getElementById('guidedFocus').textContent = mission ? mission.title : 'No active mission';
      document.getElementById('guidedStatus').textContent = `${action.title || 'Choose work'} - ${action.plain_english_status || daily.plain_status || 'Ready for guided work.'}`;
      const primary = document.getElementById('guidedPrimary');
      primary.textContent = action.primary_label || 'Start';
      primary.disabled = action.allowed_under_current_governance === false;
      renderList(document.getElementById('guidedDoes'), action.what_it_does || ['Shows the next safe action.']);
      renderList(document.getElementById('guidedDoesNot'), action.what_it_will_not_do || ['Will not run tools or publish anything automatically.']);
      const facts = [
        ['Brain', action.brain || plainBrainMode(workbench.model_mode || 'local_ollama')],
        ['Cost', action.cost_estimate || '$0 API money in Local Mode'],
        ['Risk', action.risk_level || 'low'],
        ['Approval', action.requires_approval ? 'Review required before action' : 'No extra approval for sandbox action'],
        ['Persistent Change', action.creates_persistent_change ? 'Creates a governed ledger record' : 'No durable content change'],
        ['Governance', action.allowed_under_current_governance === false ? 'Blocked by current governance' : 'Allowed under current governance']
      ];
      const factHost = document.getElementById('guidedFacts');
      factHost.innerHTML = '';
      for (const [label, value] of facts) {
        const row = document.createElement('div');
        row.className = 'guided-fact';
        row.innerHTML = `<div class="label">${escapeHtml(label)}</div><div>${escapeHtml(value)}</div>`;
        factHost.appendChild(row);
      }
      const review = daily.review_needed || {};
      document.getElementById('reviewNeededCard').innerHTML = `<div class="item-title">Review Needed</div>
        <div class="item-meta">${escapeHtml(review.summary || "Nothing needs review before today's guided action.")}</div>
        <div class="actions">
          <button type="button" class="secondary" id="guidedReviewNow">Review Now</button>
          <button type="button" class="secondary" id="guidedReviewLater">Review Later</button>
        </div>`;
      document.getElementById('guidedReviewNow').addEventListener('click', () => {
        activeInboxFilter = (review.high_priority_count || 0) ? 'high' : 'all';
        stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
        renderStewardInbox((currentStatus || {}).steward_inbox || []);
      });
      document.getElementById('guidedReviewLater').addEventListener('click', () => {
        addMessage('lucien', 'Review left for later. Sandbox drafts can continue, but proposed evidence, memory, and claims still need steward review before becoming trusted.');
      });
    }

    function renderList(host, values) {
      host.innerHTML = '';
      for (const value of values) {
        const item = document.createElement('li');
        item.textContent = value;
        host.appendChild(item);
      }
    }

    function renderDailyPlan(plan) {
      if (!plan || !plan.current_focus) {
        empty(dailyPlan, 'No daily plan generated yet.');
        return;
      }
      dailyPlan.innerHTML = '';
      const top = document.createElement('div');
      top.className = 'item';
      top.innerHTML = `<div class="item-title">Daily Plan / ${escapeHtml(plan.continuity_state || 'unknown')}</div>
        <div class="item-meta">Focus: ${escapeHtml(plan.current_focus || 'none')}</div>
        <div class="item-meta">Best next safe action: ${escapeHtml(plan.best_next_safe_action || 'none')}</div>`;
      dailyPlan.appendChild(top);
      const blockers = document.createElement('div');
      blockers.className = 'item';
      blockers.innerHTML = `<div class="item-title">Blockers</div>
        <div class="item-meta">${escapeHtml((plan.blockers || []).join(' / ') || 'none')}</div>`;
      dailyPlan.appendChild(blockers);
      const notYet = document.createElement('div');
      notYet.className = 'item';
      notYet.innerHTML = `<div class="item-title">What not to do yet</div>
        <div class="item-meta">${escapeHtml((plan.what_not_to_do_yet || []).join(' / ') || 'none')}</div>`;
      dailyPlan.appendChild(notYet);
    }

    function renderMissionEvidence(evidenceByMission, selectedMission) {
      missionEvidenceSummary.innerHTML = '';
      missionEvidence.innerHTML = '';
      if (!selectedMission || !selectedMission.mission_id) {
        empty(missionEvidence, 'Select or open a mission before adding evidence.');
        return;
      }
      const linked = evidenceByMission[selectedMission.mission_id] || [];
      const counts = {raw: 0, reviewed: 0, disputed: 0, stale: 0, rejected: 0};
      for (const item of linked) {
        const status = ((item.evidence || {}).review_status || 'raw');
        counts[status] = (counts[status] || 0) + 1;
      }
      for (const [label, value] of Object.entries(counts)) {
        const card = document.createElement('div');
        card.className = 'metric';
        card.innerHTML = `<div class="label">${escapeHtml(label)}</div><div class="value">${value}</div>`;
        missionEvidenceSummary.appendChild(card);
      }
      if (!linked.length) {
        empty(missionEvidence, 'No evidence linked to this mission yet. Add a source or create the mission starter pack.');
        return;
      }
      for (const item of linked.slice().reverse()) {
        const evidence = item.evidence || {};
        const link = item.link || {};
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${evidence.review_status || 'raw'} / ${evidence.source_type || 'unknown'} / ${evidence.confidence || 'unknown'}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = `${evidence.evidence_id || 'unknown'} / summary length ${evidence.summary_length || 0} / ${evidence.reason || 'no reason recorded'}`;
        const linkMeta = document.createElement('div');
        linkMeta.className = 'item-meta';
        linkMeta.textContent = `linked to ${link.target_type || 'mission'} / ${link.target_id || selectedMission.mission_id}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        if (['raw', 'disputed', 'stale'].includes(evidence.review_status || 'raw')) {
          actions.appendChild(button('Accept Evidence', {action: 'steward_inbox_action', inbox_id: `evidence_review:${evidence.evidence_id}`, inbox_action: 'accept', reason: 'accepted from mission evidence panel'}));
          actions.appendChild(button('Reject', {action: 'steward_inbox_action', inbox_id: `evidence_review:${evidence.evidence_id}`, inbox_action: 'reject', reason: 'rejected from mission evidence panel'}));
          actions.appendChild(button('Mark Stale', {action: 'steward_inbox_action', inbox_id: `evidence_review:${evidence.evidence_id}`, inbox_action: 'mark_stale', reason: 'marked stale from mission evidence panel'}));
        }
        row.append(title, meta, linkMeta, actions);
        missionEvidence.appendChild(row);
      }
    }

    function renderMissionClaimMap(claimMaps, selectedMission) {
      missionClaimMapSummary.innerHTML = '';
      missionClaimMap.innerHTML = '';
      if (!selectedMission || !selectedMission.mission_id) {
        empty(missionClaimMap, 'Select or open a mission before viewing the claim map.');
        return;
      }
      const map = claimMaps[selectedMission.mission_id] || null;
      if (!map) {
        empty(missionClaimMap, 'No claim map is available for this mission yet.');
        return;
      }
      const cards = {
        claims: map.claim_count || 0,
        evidence: map.evidence_count || 0,
        reviewed: map.reviewed_evidence_count || 0,
        unsupported: map.unsupported_claim_count || 0
      };
      for (const [label, value] of Object.entries(cards)) {
        const card = document.createElement('div');
        card.className = 'metric';
        card.innerHTML = `<div class="label">${escapeHtml(label)}</div><div class="value">${value}</div>`;
        missionClaimMapSummary.appendChild(card);
      }
      const entries = map.entries || [];
      if (!entries.length) {
        empty(missionClaimMap, 'No hypothesis claim exists yet. Create the mission starter pack first.');
        return;
      }
      for (const entry of entries) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${escapeHtml(entry.support_status || 'unknown')} / ${escapeHtml(entry.confidence || 'unknown')} / ${escapeHtml(entry.claim_status || 'unknown')}</div>
          <div class="item-meta">${escapeHtml(entry.claim_item_id || 'unknown')} / hash ${escapeHtml(String(entry.claim_hash || '').slice(0, 16))}</div>
          <div class="item-meta">evidence ${entry.evidence_count || 0} / reviewed ${entry.reviewed_evidence_count || 0} / disputed ${entry.disputed_evidence_count || 0} / stale ${entry.stale_evidence_count || 0}</div>`;
        missionClaimMap.appendChild(row);
      }
    }

    function renderResearchSandbox(sandbox, outputs, selectedMission) {
      researchSandboxStatus.innerHTML = `<div class="item-title">Research Sandbox</div>
        <div class="item-meta">${escapeHtml(sandbox.law || 'Research freely; governed action only.')}</div>
        <div class="item-meta">Proposed outputs: ${sandbox.proposed_output_count || 0} / Restricted actions still require explicit approval.</div>`;
      researchOutputs.innerHTML = '';
      const visible = (outputs || [])
        .filter(output => !selectedMission || output.mission_id === selectedMission.mission_id)
        .slice()
        .reverse()
        .slice(0, 8);
      if (!visible.length) {
        empty(researchOutputs, selectedMission ? 'No research outputs for this mission yet.' : 'Select a mission to draft research outputs.');
        return;
      }
      for (const output of visible) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${escapeHtml(output.kind)} / ${escapeHtml(output.status)}</div>
          <div class="item-meta">${escapeHtml(output.title || output.output_id)}</div>
          <div class="item-meta">confidence: ${escapeHtml(output.confidence || 'low')} / claims: ${output.claim_count || 0} / evidence: ${(output.evidence_ids || []).length}</div>`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        actions.appendChild(localButton('View in Workspace', () => {
          selectedOutputId = output.output_id;
          window.sessionStorage.setItem('lucien.selectedOutputId', selectedOutputId);
          renderOutputWorkspace(currentStatus.research_outputs || [], selectedMission);
          workspaceTitle.scrollIntoView({behavior: 'smooth', block: 'center'});
        }));
        row.appendChild(actions);
        researchOutputs.appendChild(row);
      }
    }

    function renderOutputWorkspace(outputs, selectedMission) {
      const visible = (outputs || [])
        .filter(output => !selectedMission || output.mission_id === selectedMission.mission_id)
        .slice()
        .sort((a, b) => String(a.created_at || '').localeCompare(String(b.created_at || '')));
      let output = visible.find(item => item.output_id === selectedOutputId) || visible[visible.length - 1] || null;
      if (!output) {
        workspaceTitle.textContent = 'No output yet';
        workspaceMeta.textContent = selectedMission ? 'Use Start Draft or Start Research Brief to create a proposed output.' : 'Select or open a mission before drafting.';
        workspaceBody.textContent = 'Generated drafts will appear here as proposed workspace outputs. They will not become trusted evidence, memory, or claims until reviewed.';
        workspaceDetails.innerHTML = '';
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = '<div class="item-title">Governance</div><div class="item-meta">No files, publishing, memory acceptance, or evidence acceptance happens from this empty state.</div>';
        workspaceDetails.appendChild(row);
        return;
      }
      selectedOutputId = output.output_id;
      window.sessionStorage.setItem('lucien.selectedOutputId', selectedOutputId);
      const content = outputContentById[output.output_id] || '';
      workspaceTitle.textContent = output.title || output.output_id;
      workspaceMeta.textContent = `${plainOutputKind(output.kind)} / ${output.status || 'proposed'} / ${selectedMission ? selectedMission.title : output.mission_id}`;
      workspaceBody.textContent = content || [
        'This output record is durable, but its raw draft text is not stored in the ledger.',
        '',
        `Content hash: ${output.content_hash || 'unknown'}`,
        `Content length: ${output.content_length || 0} characters`,
        '',
        'Create or regenerate the draft in this live session to view text here, or export while the live draft is still cached.'
      ].join('\\n');
      workspaceDetails.innerHTML = '';
      const details = [
        ['Status', `${output.status || 'proposed'} - not accepted as truth`],
        ['Created By', 'Research Sandbox / governed local workflow'],
        ['Cost', '$0 API money in Local Mode'],
        ['Evidence', `${(output.evidence_ids || []).length} proposed evidence item(s)`],
        ['Claims', `${output.claim_count || 0} proposed claim(s)`],
        ['Hash', output.content_hash ? output.content_hash.slice(0, 16) : 'none'],
        ['Review Rule', 'Memory, evidence, and claims require steward review before becoming trusted'],
      ];
      for (const [title, value] of details) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${escapeHtml(title)}</div><div class="item-meta">${escapeHtml(value)}</div>`;
        workspaceDetails.appendChild(row);
      }
    }

    function plainOutputKind(kind) {
      const labels = {
        research_brief: 'Research Brief',
        claim_map_draft: 'Claim Map Draft',
        paper_draft: 'Paper Draft',
        source_summary: 'Source Summary',
        experiment_proposal: 'Experiment Proposal',
        next_step_suggestion: 'Next Step Suggestion'
      };
      return labels[kind] || String(kind || 'Output').replaceAll('_', ' ');
    }

    function renderProjectBrief(brief) {
      const cardHost = document.getElementById('projectBriefCards');
      const fileHost = document.getElementById('projectBriefFiles');
      cardHost.innerHTML = '';
      fileHost.innerHTML = '';
      const cards = [
        ['Branch', brief.branch || 'unknown'],
        ['Sync', brief.sync_state || (brief.available ? 'unknown' : 'unavailable')],
        ['Latest Commit', brief.latest_commit || 'none'],
        ['Changed Files', String(brief.changed_file_count || 0)],
        ['Recommended Action', brief.recommended_action || 'No recommendation available.'],
        ['Check Command', brief.check_command || 'python3 scripts/check_all.py'],
      ];
      for (const [title, value] of cards) {
        const row = document.createElement('div');
        row.className = 'item mission-card';
        row.innerHTML = `<div class="item-title">${escapeHtml(title)}</div><div class="item-meta">${escapeHtml(value)}</div>`;
        cardHost.appendChild(row);
      }
      const files = brief.changed_files || [];
      if (!brief.available) {
        empty(fileHost, brief.status_message || 'Project brief unavailable.');
        return;
      }
      if (!files.length) {
        empty(fileHost, 'Working tree is clean. Lucien can propose the next governed build step.');
        return;
      }
      for (const file of files.slice(0, 8)) {
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${escapeHtml(file.path || 'unknown')}</div><div class="item-meta">${escapeHtml(file.status || 'changed')}</div>`;
        fileHost.appendChild(row);
      }
    }

    function renderBuildReview(review) {
      const cardHost = document.getElementById('buildReviewCards');
      const detailHost = document.getElementById('buildReviewDetails');
      cardHost.innerHTML = '';
      detailHost.innerHTML = '';
      const cards = [
        ['Build Risk', review.risk_level || 'unknown'],
        ['Ready to Commit', review.ready_to_commit ? 'yes' : 'no'],
        ['Suggested Commit', review.suggested_commit_message || 'none'],
        ['Summary', review.summary || 'No build review available.'],
      ];
      for (const [title, value] of cards) {
        const row = document.createElement('div');
        row.className = 'item mission-card';
        row.innerHTML = `<div class="item-title">${escapeHtml(title)}</div><div class="item-meta">${escapeHtml(value)}</div>`;
        cardHost.appendChild(row);
      }
      const checks = review.recommended_checks || [];
      const blockers = review.commit_blockers || [];
      const risks = review.risk_areas || [];
      const sections = [
        ['Recommended Checks', checks],
        ['Commit Blockers', blockers],
        ['Risk Areas', risks.map(area => `${area.area}: ${area.reason}`)],
      ];
      let rendered = false;
      for (const [title, values] of sections) {
        if (!values.length) continue;
        rendered = true;
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${escapeHtml(title)}</div><div class="item-meta">${escapeHtml(values.join(' / '))}</div>`;
        detailHost.appendChild(row);
      }
      if (!rendered) {
        empty(detailHost, 'No build review pressure detected.');
      }
    }

    function renderCommitReadiness(readiness) {
      const cardHost = document.getElementById('commitReadinessCards');
      const detailHost = document.getElementById('commitReadinessDetails');
      cardHost.innerHTML = '';
      detailHost.innerHTML = '';
      const cards = [
        ['Commit Readiness', readiness.state || 'unknown'],
        ['Ready to Stage', readiness.ready_to_stage ? 'yes' : 'no'],
        ['Ready After Checks', readiness.ready_to_commit_after_checks ? 'yes' : 'no'],
        ['Commit Message', readiness.suggested_commit_message || 'none'],
      ];
      for (const [title, value] of cards) {
        const row = document.createElement('div');
        row.className = 'item mission-card';
        row.innerHTML = `<div class="item-title">${escapeHtml(title)}</div><div class="item-meta">${escapeHtml(value)}</div>`;
        cardHost.appendChild(row);
      }
      const sections = [
        ['Summary', [readiness.summary || 'No readiness summary available.']],
        ['Blockers', readiness.blockers || []],
        ['Warnings', readiness.warnings || []],
        ['Required Actions', readiness.required_actions || []],
      ];
      for (const [title, values] of sections) {
        if (!values.length) continue;
        const row = document.createElement('div');
        row.className = 'item';
        row.innerHTML = `<div class="item-title">${escapeHtml(title)}</div><div class="item-meta">${escapeHtml(values.join(' / '))}</div>`;
        detailHost.appendChild(row);
      }
    }

    function renderCheckpointStory(story) {
      const host = document.getElementById('checkpointStory');
      host.innerHTML = '';
      const top = document.createElement('div');
      top.className = 'item';
      top.innerHTML = `<div class="item-title">Checkpoint Story / ${escapeHtml(story.title || 'Lucien checkpoint')}</div>
        <div class="item-meta">${escapeHtml(story.summary || 'No story available.')}</div>
        <div class="item-meta">Push: ${escapeHtml(story.push_note || 'No push guidance available.')}</div>`;
      host.appendChild(top);
      const bullets = story.bullets || [];
      if (bullets.length) {
        const detail = document.createElement('div');
        detail.className = 'item';
        detail.innerHTML = `<div class="item-title">What Changed</div><div class="item-meta">${escapeHtml(bullets.slice(0, 5).join(' / '))}</div>`;
        host.appendChild(detail);
      }
    }

    function renderNextBuild(proposal) {
      const host = document.getElementById('nextBuild');
      host.innerHTML = '';
      const top = document.createElement('div');
      top.className = 'item';
      top.innerHTML = `<div class="item-title">Next Governed Build / ${escapeHtml(proposal.title || 'none')}</div>
        <div class="item-meta">Reason: ${escapeHtml(proposal.reason || 'none')}</div>
        <div class="item-meta">First step: ${escapeHtml(proposal.suggested_first_step || 'none')}</div>
        <div class="item-meta">Risk: ${escapeHtml(proposal.risk || 'unknown')}</div>`;
      host.appendChild(top);
      const doNot = proposal.do_not_do_yet || [];
      const checks = proposal.checks || [];
      if (checks.length || doNot.length) {
        const detail = document.createElement('div');
        detail.className = 'item';
        detail.innerHTML = `<div class="item-title">Checks / Boundaries</div>
          <div class="item-meta">${escapeHtml((checks.concat(doNot)).slice(0, 6).join(' / '))}</div>`;
        host.appendChild(detail);
      }
    }

    function renderCertification(record) {
      if (!record || !record.summary) {
        empty(certification, 'No certification analysis available.');
        return;
      }
      certification.innerHTML = '';
      const top = document.createElement('div');
      top.className = 'item';
      top.innerHTML = `<div class="item-title">${record.certifiable ? 'Certifiable' : 'Not certifiable'} / ${escapeHtml(record.continuity_claim || 'unknown')}</div>
        <div class="item-meta">${escapeHtml(record.summary || '')}</div>
        <div class="item-meta">identity state: ${escapeHtml(record.identity_state || 'unknown')}</div>`;
      certification.appendChild(top);
      const blockers = document.createElement('div');
      blockers.className = 'item';
      blockers.innerHTML = `<div class="item-title">Why</div>
        <div class="item-meta">${escapeHtml((record.blockers || []).slice(0, 4).join(' / ') || 'none')}</div>`;
      certification.appendChild(blockers);
      const actions = document.createElement('div');
      actions.className = 'item';
      actions.innerHTML = `<div class="item-title">Next steward action</div>
        <div class="item-meta">${escapeHtml((record.steward_actions || []).slice(0, 3).join(' / ') || 'none')}</div>`;
      certification.appendChild(actions);
    }

    function renderGoals(records, missionRecords) {
      const active = records.filter(goal => goal.status === 'active');
      if (!records.length) {
        empty(goals, 'No goals yet. Create one to give Lucien a durable direction.');
        return;
      }
      goals.innerHTML = '';
      const missionOptions = [];
      for (const brief of missionRecords || []) {
        const mission = brief.mission || {};
        if (mission.mission_id) missionOptions.push(mission);
      }
      for (const goal of active.concat(records.filter(goal => goal.status !== 'active')).slice(0, 8)) {
        const row = document.createElement('div');
        row.className = 'item mission-card';
        const linked = (goal.linked_mission_ids || []).length;
        const blockers = (goal.blockers || []).length;
        const actions = document.createElement('div');
        actions.className = 'actions';
        if (goal.status === 'active') {
          actions.appendChild(localButton('Link Mission', () => {
            if (!missionOptions.length) {
              addMessage('lucien', 'No mission is available to link yet.');
              return;
            }
            const missionId = window.prompt('Mission ID to link', missionOptions[missionOptions.length - 1].mission_id);
            if (!missionId) return;
            steward({action: 'link_goal_mission', goal_id: goal.goal_id, mission_id: missionId, reason: 'linked from live goals panel'});
          }));
          actions.appendChild(localButton('Add Blocker', () => {
            const blocker = window.prompt('Goal blocker');
            if (!blocker) return;
            steward({action: 'add_goal_blocker', goal_id: goal.goal_id, blocker, reason: 'added from live goals panel'});
          }));
          actions.appendChild(button('Complete', {action: 'complete_goal', goal_id: goal.goal_id, reason: 'completed from live goals panel'}));
          actions.appendChild(button('Archive', {action: 'archive_goal', goal_id: goal.goal_id, reason: 'archived from live goals panel'}));
        }
        row.innerHTML = `<div class="item-title">${escapeHtml(goal.title)} / ${escapeHtml(goal.priority)} / ${escapeHtml(goal.status)}</div>
          <div class="item-meta">${escapeHtml(goal.goal_id)} / review ${escapeHtml(goal.review_state || 'pending')}</div>
          <div class="item-meta">linked missions ${linked} / blockers ${blockers}</div>
          <div class="item-meta">next: ${escapeHtml(goal.next_recommended_action || 'none')}</div>`;
        row.appendChild(actions);
        goals.appendChild(row);
      }
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function renderMissionDashboard(status) {
      const cards = buildMissionCards(status);
      if (!cards.length) {
        activeMissionSelect.innerHTML = '<option>No active missions</option>';
        empty(missionCards, 'No missions yet. Open a mission to turn Lucien into a governed workbench.');
        return {activeMission: null, cards};
      }
      const selectedCard = cards.find(card => card.mission_id === selectedMissionId);
      const latestOpen = [...cards].reverse().find(card => card.status === 'open');
      if (!selectedCard || (latestOpen && selectedCard.status !== 'open')) {
        selectedMissionId = (latestOpen || cards[cards.length - 1]).mission_id;
        window.localStorage.setItem('lucien.activeMissionId', selectedMissionId);
      }
      activeMissionSelect.innerHTML = '';
      for (const card of cards) {
        const option = document.createElement('option');
        option.value = card.mission_id;
        option.textContent = `${card.title} / ${card.phase}`;
        option.selected = card.mission_id === selectedMissionId;
        activeMissionSelect.appendChild(option);
      }
      missionCards.innerHTML = '';
      for (const card of cards) {
        missionCards.appendChild(missionCardNode(card, status));
      }
      return {activeMission: cards.find(card => card.mission_id === selectedMissionId) || cards[0], cards};
    }

    function buildMissionCards(status) {
      const flows = status.mission_flows || {};
      const steps = status.mission_steps || [];
      const executions = status.tool_executions || [];
      const previews = status.tool_previews || [];
      const inbox = status.steward_inbox || [];
      const onboarding = status.mission_onboarding || {};
      return (status.missions || []).map((brief) => {
        const mission = brief.mission || {};
        const flow = flows[mission.mission_id] || {};
        const missionSteps = steps.filter(step => step.mission_id === mission.mission_id);
        const latestStep = missionSteps[missionSteps.length - 1] || null;
        const latestExecution = latestStep ? [...executions].reverse().find(item => item.step_id === latestStep.step_id) || null : null;
        const latestPreview = latestStep ? [...previews].reverse().find(item => item.step_id === latestStep.step_id) || null : null;
        const pressure = inbox.filter((item) => item.linked_target_id === mission.mission_id || String(item.reason || '').includes(mission.mission_id));
        return {
          mission_id: mission.mission_id,
          title: mission.title || 'Untitled mission',
          status: mission.status || 'unknown',
          phase: flow.phase || 'unknown',
          next_action: flow.next_action || 'No next action recorded.',
          blockers: flow.blockers || [],
          blocker_count: (flow.blockers || []).length,
          inbox_count: pressure.length,
          high_inbox_count: pressure.filter(item => item.severity === 'high' || item.severity === 'critical').length,
          latest_step: latestStep,
          latest_execution: latestExecution,
          latest_preview: latestPreview,
          onboarding: onboarding[mission.mission_id] || null,
          counts: brief.counts || {}
        };
      });
    }

    function missionCardNode(card, status) {
      const row = document.createElement('div');
      row.className = 'item mission-card' + (card.mission_id === selectedMissionId ? ' active' : '');
      const title = document.createElement('div');
      title.className = 'item-title';
      title.textContent = `${card.title} / ${card.phase}`;
      const meta = document.createElement('div');
      meta.className = 'item-meta';
      meta.textContent = `${card.status} / blockers ${card.blocker_count} / inbox ${card.inbox_count} open, ${card.high_inbox_count} high`;
      const next = document.createElement('div');
      next.className = 'item-meta';
      next.textContent = `next safe action: ${card.next_action}`;
      const step = document.createElement('div');
      step.className = 'item-meta';
      step.textContent = card.latest_step ? `last step: ${card.latest_step.execution_status} / ${card.latest_step.risk_level} / ${card.latest_step.required_tool}` : 'last step: none';
      const tool = document.createElement('div');
      tool.className = 'item-meta';
      tool.textContent = card.latest_execution ? `last tool: ${card.latest_execution.status} / evidence ${card.latest_execution.evidence_id || 'none'}` : (card.latest_preview ? `last dry run: ${card.latest_preview.permission_decision} / would_execute ${card.latest_preview.would_execute}` : 'last tool: none');
      const onboarding = document.createElement('div');
      onboarding.className = 'item-meta';
      onboarding.textContent = card.onboarding && card.onboarding.ready
        ? `onboarding: needs ${card.onboarding.needed.join(', ')}`
        : 'onboarding: starter structure present';
      const actions = document.createElement('div');
      actions.className = 'actions';
      actions.appendChild(localButton('Set Active', () => setActiveMission(card.mission_id)));
      if (card.status === 'open') {
        actions.appendChild(button('Suggest Next Step', {action: 'propose_next_step', mission_id: card.mission_id, reason: 'mission dashboard next-step proposal'}));
        if (card.onboarding && card.onboarding.ready) {
          actions.appendChild(button('Create Starter Pack', {action: 'mission_onboard', mission_id: card.mission_id, reason: 'created from mission onboarding wizard'}));
        }
      }
      if (card.blocker_count || card.inbox_count) {
        actions.appendChild(localButton('Review Blockers', () => {
          activeInboxFilter = card.high_inbox_count ? 'high' : 'missions';
          stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
          renderStewardInbox((currentStatus || {}).steward_inbox || []);
        }));
      }
      if (card.latest_step) {
        const spec = (status.tools || {})[card.latest_step.required_tool];
        const canRun = ['proposed', 'ready'].includes(card.latest_step.execution_status);
        const needsApproval = ['medium', 'high'].includes(card.latest_step.risk_level) && card.latest_step.approval_status !== 'approved';
        if (spec && canRun) {
          actions.appendChild(toolButton(card.latest_step, spec, true));
          if (!needsApproval) actions.appendChild(toolButton(card.latest_step, spec, false));
        }
      }
      actions.appendChild(button('Pause', {action: 'update_mission_status', mission_id: card.mission_id, status: 'paused', reason: 'paused from mission dashboard'}));
      actions.appendChild(button('Complete', {action: 'update_mission_status', mission_id: card.mission_id, status: 'completed', reason: 'completed from mission dashboard'}));
      row.append(title, meta, next, step, tool, onboarding, actions);
      return row;
    }

    function setActiveMission(missionId) {
      selectedMissionId = missionId;
      window.localStorage.setItem('lucien.activeMissionId', missionId);
      if (currentStatus) renderStatus(currentStatus);
    }

    function localButton(text, fn) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'secondary';
      btn.textContent = text;
      btn.addEventListener('click', fn);
      return btn;
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

    function renderAutonomyQueue(items, executions) {
      if (!items.length) {
        empty(autonomyQueue, 'No autonomy actions proposed.');
        return;
      }
      const executionByItem = new Map((executions || []).map(record => [record.item_id, record]));
      autonomyQueue.innerHTML = '';
      for (const item of items.slice().reverse()) {
        const execution = executionByItem.get(item.item_id);
        const row = document.createElement('div');
        row.className = 'item';
        const title = document.createElement('div');
        title.className = 'item-title';
        title.textContent = `${item.status} / ${item.risk} / ${item.action_type}`;
        const meta = document.createElement('div');
        meta.className = 'item-meta';
        meta.textContent = execution
          ? `${item.item_id} / ${item.reason} / executed: ${execution.status} / evidence: ${execution.evidence_id || 'none'}`
          : `${item.item_id} / ${item.reason}`;
        const actions = document.createElement('div');
        actions.className = 'actions';
        if (item.status === 'proposed') {
          actions.appendChild(button('Approve', {
            action: 'autonomy_review',
            item_id: item.item_id,
            decision: 'approve',
            reason: 'approved from live autonomy queue'
          }));
          actions.appendChild(button('Reject', {
            action: 'autonomy_review',
            item_id: item.item_id,
            decision: 'reject',
            reason: 'rejected from live autonomy queue'
          }));
        }
        const executableActions = new Set(['run_check_all', 'project_brief', 'build_review', 'commit_readiness', 'next_build', 'daily_plan', 'review_inbox', 'generate_story']);
        if (item.status === 'approved' && !execution && executableActions.has(item.action_type)) {
          actions.appendChild(button('Run', {
            action: 'autonomy_execute',
            item_id: item.item_id,
            reason: 'ran approved autonomy action from live autonomy queue'
          }));
        } else if (item.status === 'approved' && !execution) {
          const note = document.createElement('span');
          note.className = 'item-meta';
          note.textContent = 'Approval recorded; this action is advisory in this version.';
          actions.appendChild(note);
        }
        row.append(title, meta, actions);
        autonomyQueue.appendChild(row);
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
          actions.appendChild(button('Review Mission for Learning', {action: 'learning_review', scope: 'mission', mission_id: mission.mission_id, apply: true, reason: 'live mission learning review'}));
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
        if (step.required_tool === 'git_recent') {
          const count = window.prompt('Commit count', '5');
          if (count === null) return;
          toolArgs.count = count;
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

    function renderLearningReview(records) {
      if (!records.length) {
        empty(learningReview, 'No learning reviews yet.');
        return;
      }
      learningReview.innerHTML = '';
      for (const record of records.slice(-6).reverse()) {
        const row = document.createElement('div');
        row.className = 'item';
        const counts = record.candidate_counts || {};
        row.innerHTML = `<div class="item-title">${record.scope} / ${record.status}</div>
          <div class="item-meta">${record.review_id} / target ${record.target_id}</div>
          <div class="item-meta">memory ${counts.memory_candidates || 0} / skills ${counts.skill_candidates || 0} / lessons ${counts.mission_lessons || 0} / evidence needed ${counts.evidence_needed || 0} / tasks ${counts.reflection_tasks || 0}</div>`;
        learningReview.appendChild(row);
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
        return data;
      }
      renderStatus(data.status);
      return data;
    }

    function getSelectedModelMode() {
      const override = document.getElementById('advancedModelMode').value;
      if (override) return override;
      return document.getElementById('brainMode').value;
    }

    function getOpenAIAllowedForSend() {
      const mode = getSelectedModelMode();
      if (mode === 'local_ollama' || mode === 'echo') return false;
      if (mode === 'openai') return true;
      return document.getElementById('useOpenAI').checked;
    }

    function updateBrainModeControls() {
      const mode = getSelectedModelMode();
      const check = document.getElementById('useOpenAI');
      const cloudMode = mode === 'serious_only' || mode === 'local_first' || mode === 'auto';
      if (mode === 'local_ollama' || mode === 'echo') check.checked = false;
      check.disabled = !cloudMode;
      const label = check.closest('label');
      if (label) label.style.opacity = check.disabled ? '.55' : '1';
      if (currentStatus) {
        const usage = currentStatus.model_usage || {};
        const modelAdapter = currentStatus.model_adapter || {};
        document.getElementById('usageMode').textContent = plainBrainMode(mode);
        document.getElementById('usageCloudAssist').textContent = cloudAssistUsageStatus(usage, modelAdapter);
        document.getElementById('cloudAssist').textContent = cloudAssistDailyStatus(modelAdapter);
      }
    }

    document.getElementById('chatForm').addEventListener('submit', async (event) => {
      event.preventDefault();
      const box = document.getElementById('message');
      const sendButton = document.getElementById('sendMessage');
      const text = box.value.trim();
      if (!text) return;
      const modelMode = getSelectedModelMode();
      const useOpenAI = getOpenAIAllowedForSend();
      box.value = '';
      addMessage('user', text);
      sendButton.disabled = true;
      sendButton.textContent = 'Thinking...';
      try {
        const res = await fetch('/api/chat', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            message: text,
            model_mode: modelMode,
            use_openai: useOpenAI,
            mission_id: selectedMissionId || null
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
      } catch (error) {
        addMessage('lucien', `Lucien could not reach the live server: ${error.message}`);
      } finally {
        sendButton.disabled = false;
        sendButton.textContent = 'Send';
      }
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

    document.getElementById('goalForm').addEventListener('submit', (event) => {
      event.preventDefault();
      const title = document.getElementById('goalTitle').value.trim();
      const purpose = document.getElementById('goalPurpose').value.trim();
      const success = document.getElementById('goalSuccess').value.trim();
      const priority = document.getElementById('goalPriority').value;
      if (!title || !purpose || !success) return;
      document.getElementById('goalTitle').value = '';
      document.getElementById('goalPurpose').value = '';
      document.getElementById('goalSuccess').value = '';
      steward({
        action: 'create_goal',
        title,
        purpose,
        success_criteria: success,
        priority,
        reason: 'created from live goals panel'
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

    document.getElementById('reviewSessionLearning').addEventListener('click', () => {
      steward({action: 'learning_review', scope: 'latest_session', apply: true, reason: 'manual session learning review'});
    });

    document.getElementById('homeLearningReview').addEventListener('click', () => {
      steward({action: 'learning_review', scope: 'latest_session', apply: true, reason: 'home session learning review'});
    });

    document.getElementById('homeCleanSession').addEventListener('click', () => {
      steward({action: 'start_clean_daily_session', reason: 'started clean daily session from command center'});
      messages.innerHTML = '';
      lastLucien = '';
    });

    document.getElementById('homeResearchLoop').addEventListener('click', () => {
      steward({action: 'run_daily_research_loop', reason: 'launched from daily command center'});
    });

    function generatePlan() {
      steward({action: 'generate_daily_plan', reason: 'generated from live workbench'});
    }

    document.getElementById('homeDailyPlan').addEventListener('click', generatePlan);
    document.getElementById('generateDailyPlan').addEventListener('click', generatePlan);
    document.getElementById('refreshProjectBrief').addEventListener('click', refresh);

    document.getElementById('homeStartMission').addEventListener('click', () => {
      document.getElementById('missionTitle').focus();
      document.getElementById('missionTitle').scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('homeReviewInbox').addEventListener('click', () => {
      stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('missionEvidenceAdd').addEventListener('click', () => {
      if (!selectedMissionId) {
        addMessage('lucien', 'Select or open a mission before adding evidence.');
        return;
      }
      const summary = window.prompt('Evidence summary for the active mission');
      if (!summary || !summary.trim()) return;
      const source = window.prompt('Source, note, file path, URL, or observation', '');
      steward({
        action: 'add_mission_evidence',
        mission_id: selectedMissionId,
        summary: summary.trim(),
        source: (source || '').trim(),
        confidence: 'unknown',
        reason: 'added from mission evidence panel'
      });
    });

    document.getElementById('missionEvidenceCaptureChat').addEventListener('click', () => {
      if (!selectedMissionId) {
        addMessage('lucien', 'Select or open a mission before capturing chat evidence.');
        return;
      }
      if (!lastLucien) {
        addMessage('lucien', 'There is no Lucien reply to capture yet.');
        return;
      }
      steward({
        action: 'add_mission_evidence',
        mission_id: selectedMissionId,
        summary: lastLucien,
        source: 'latest_lucien_response',
        source_type: 'chat_turn',
        confidence: 'unknown',
        reason: 'captured latest Lucien reply from mission evidence panel'
      });
    });

    document.getElementById('missionEvidenceReview').addEventListener('click', () => {
      activeInboxFilter = 'evidence';
      renderStewardInbox((currentStatus || {}).steward_inbox || []);
      stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('missionClaimMapRefresh').addEventListener('click', () => {
      if (currentStatus) renderStatus(currentStatus);
      missionClaimMap.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    function askLucienNextStep() {
      const box = document.getElementById('message');
      box.value = 'Lucien, what should I do next? Keep it simple and give me one safe action.';
      box.focus();
      box.scrollIntoView({behavior: 'smooth', block: 'center'});
      addMessage('lucien', 'I put a simple next-step question in the chat box. Press Send when you are ready.');
    }

    function askColdOpenReport() {
      const box = document.getElementById('message');
      box.value = currentColdOpenPrompt || 'Lucien, what should I do first today? Keep it simple.';
      box.focus();
      box.scrollIntoView({behavior: 'smooth', block: 'center'});
      addMessage('lucien', 'I put the cold-open question in the chat box. Press Send when you are ready.');
    }

    function runStartHereAction(action) {
      const selected = action || currentStartHereAction || {};
      if (selected.kind === 'startup_fix') {
        steward({
          action: 'startup_health_fix',
          fix_action: selected.fix_action,
          reason: 'start here safe startup fix'
        });
        return;
      }
      if (selected.kind === 'start_mission') {
        document.getElementById('missionTitle').focus();
        document.getElementById('missionTitle').scrollIntoView({behavior: 'smooth', block: 'center'});
        addMessage('lucien', 'Start by naming one mission. Example: Continue Coherence Physics research.');
        return;
      }
      if (selected.kind === 'mission_onboarding') {
        const missionId = selected.mission_id || selectedMissionId;
        if (!missionId) {
          addMessage('lucien', 'Select an active mission before creating a starter pack.');
          return;
        }
        steward({action: 'mission_onboard', mission_id: missionId, reason: 'created from Start Here'});
        return;
      }
      if (selected.kind === 'review_inbox') {
        activeInboxFilter = selected.filter || 'all';
        renderStewardInbox((currentStatus || {}).steward_inbox || []);
        stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
        return;
      }
      askLucienNextStep();
    }

    function openMissionTemplate(templateId) {
      const template = missionTemplates[templateId];
      if (!template) return;
      const existing = ((currentStatus && currentStatus.missions) || [])
        .map(item => item.mission || {})
        .find(mission => mission.title === template.title && mission.status === 'open');
      if (existing && existing.mission_id) {
        setActiveMission(existing.mission_id);
        addMessage('lucien', `I selected the existing mission: ${template.title}. Click Create Starter Pack if it appears, then ask me for the next safe step.`);
        return;
      }
      steward({
        action: 'open_mission',
        title: template.title,
        problem: template.problem,
        values: template.values,
        reason: `opened from quick start template: ${templateId}`
      });
      addMessage('lucien', `Opening mission template: ${template.title}. When it appears, use Create Starter Pack to seed the first hypothesis, evidence need, and risk review.`);
    }

    document.getElementById('startHerePrimary').addEventListener('click', () => {
      runStartHereAction(currentStartHereAction);
    });

    document.getElementById('startHereStarterPack').addEventListener('click', () => {
      const missionId = currentStartHereAction.mission_id || selectedMissionId;
      runStartHereAction({kind: 'mission_onboarding', mission_id: missionId});
    });

    document.getElementById('startHereReview').addEventListener('click', () => {
      runStartHereAction({kind: 'review_inbox', filter: (currentStatus && currentStatus.workbench && currentStatus.workbench.high_priority_inbox_count) ? 'high' : 'all'});
    });

    document.getElementById('coldOpenAsk').addEventListener('click', askColdOpenReport);

    document.getElementById('coldOpenCopy').addEventListener('click', async () => {
      const text = document.getElementById('coldOpenText').textContent || '';
      try {
        await navigator.clipboard.writeText(text);
        addMessage('lucien', 'Cold-open report copied.');
      } catch (error) {
        addMessage('lucien', text);
      }
    });

    for (const button of document.querySelectorAll('[data-mission-template]')) {
      button.addEventListener('click', () => openMissionTemplate(button.dataset.missionTemplate));
    }

    for (const control of document.querySelectorAll('[data-work-mode]')) {
      control.addEventListener('click', () => {
        selectedWorkMode = control.dataset.workMode;
        window.localStorage.setItem('lucien.workMode', selectedWorkMode);
        if (currentStatus) renderStatus(currentStatus);
      });
    }

    document.getElementById('guidedPrimary').addEventListener('click', () => {
      const action = currentGuidedAction || {};
      if (action.allowed_under_current_governance === false) {
        addMessage('lucien', 'That action is blocked by the current governance state. Review the Steward Inbox first.');
        return;
      }
      if (action.target_kind === 'start_mission') {
        document.getElementById('missionTitle').focus();
        document.getElementById('missionTitle').scrollIntoView({behavior: 'smooth', block: 'center'});
        return;
      }
      if (action.target_kind === 'research_brief') {
        createResearch('research_brief');
        return;
      }
      if (action.target_kind === 'research_autopilot') {
        steward({action: 'run_research_autopilot', reason: 'started from guided research workbench'});
        return;
      }
      if (action.target_kind === 'mission_onboarding') {
        if (!selectedMissionId) {
          addMessage('lucien', 'Select an active mission before creating an onboarding starter pack.');
          return;
        }
        steward({action: 'mission_onboard', mission_id: selectedMissionId, reason: 'created from guided mission onboarding'});
        return;
      }
      if (action.target_kind === 'paper_draft') {
        createResearch('paper_draft');
        return;
      }
      if (action.target_kind === 'build_review') {
        document.getElementById('nextBuild').scrollIntoView({behavior: 'smooth', block: 'center'});
        return;
      }
      addMessage('lucien', 'No guided action is available yet. Start or select a mission first.');
    });

    document.getElementById('guidedChangeFocus').addEventListener('click', () => {
      activeMissionSelect.scrollIntoView({behavior: 'smooth', block: 'center'});
      activeMissionSelect.focus();
    });

    function selectedWorkspaceOutput() {
      const outputs = (currentStatus && currentStatus.research_outputs) || [];
      return outputs.find(output => output.output_id === selectedOutputId) || null;
    }

    document.getElementById('workspaceRevise').addEventListener('click', () => {
      const output = selectedWorkspaceOutput();
      const box = document.getElementById('message');
      box.value = output
        ? `Revise this ${plainOutputKind(output.kind)} for mission ${output.mission_id}. Keep claims proposed and do not accept anything as proven.`
        : 'Help me create a proposed draft for the active mission. Keep claims proposed and governed.';
      box.focus();
      box.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('workspaceReview').addEventListener('click', () => {
      activeInboxFilter = 'all';
      stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
      renderStewardInbox((currentStatus || {}).steward_inbox || []);
      addMessage('lucien', 'Output is still a proposed draft. Use steward review before treating any claims, memories, or evidence as trusted.');
    });

    document.getElementById('workspaceEvidence').addEventListener('click', () => {
      activeInboxFilter = 'evidence';
      stewardInbox.scrollIntoView({behavior: 'smooth', block: 'center'});
      renderStewardInbox((currentStatus || {}).steward_inbox || []);
      addMessage('lucien', 'Accepting evidence is governed. Review linked evidence in the Evidence/Steward flow before using it as support.');
    });

    document.getElementById('workspaceKeepDraft').addEventListener('click', () => {
      addMessage('lucien', 'Kept as draft. No memory, evidence, file, or claim was accepted from the workspace.');
    });

    document.getElementById('workspaceExport').addEventListener('click', () => {
      const output = selectedWorkspaceOutput();
      if (!output) {
        addMessage('lucien', 'No workspace output is selected to export.');
        return;
      }
      const content = outputContentById[output.output_id];
      if (!content) {
        addMessage('lucien', 'This output has only a ledger hash in the current session. Regenerate or create a new draft before exporting markdown.');
        return;
      }
      const header = [
        `<!-- Lucien Output Workspace export -->`,
        `<!-- status: ${output.status || 'proposed'}; mission: ${output.mission_id}; evidence: ${(output.evidence_ids || []).join(', ') || 'none'} -->`,
        `<!-- governance: proposed draft only; not accepted memory, evidence, or truth -->`,
        ''
      ].join('\\n');
      const blob = new Blob([header + content], {type: 'text/markdown'});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${plainOutputKind(output.kind).toLowerCase().replaceAll(' ', '-')}-${output.output_id.slice(-8)}.md`;
      link.click();
      URL.revokeObjectURL(link.href);
    });

    document.getElementById('workspaceExportPdf').addEventListener('click', async () => {
      if (!selectedMissionId) {
        addMessage('lucien', 'Select an active mission before exporting a research PDF.');
        return;
      }
      const data = await steward({
        action: 'export_research_pdf',
        mission_id: selectedMissionId,
        reason: 'exported mission research packet from live workspace'
      });
      const pdf = data && data.result && data.result.research_pdf ? data.result.research_pdf : null;
      if (!pdf || !pdf.path) {
        addMessage('lucien', 'PDF export did not return a file path.');
        return;
      }
      addMessage('lucien', `Research PDF saved at ${pdf.path}. Opening it now.`);
      window.open('/' + pdf.path, '_blank');
    });

    async function createResearch(kind) {
      const selected = (currentStatus && (currentStatus.missions || []).find(item => item.mission && item.mission.mission_id === selectedMissionId) || null);
      const selectedMission = selected ? selected.mission : ((currentStatus && currentStatus.workbench) ? currentStatus.workbench.active_mission : null);
      if (!selectedMission || !selectedMission.mission_id) {
        alert('Select or open a mission before creating research output.');
        return;
      }
      const data = await steward({
        action: 'create_research_output',
        mission_id: selectedMission.mission_id,
        kind,
        reason: `created ${kind} from research sandbox`
      });
      const created = data && data.result && data.result.research_output ? data.result.research_output : null;
      if (created && created.output && created.content) {
        outputContentById[created.output.output_id] = created.content;
        selectedOutputId = created.output.output_id;
        window.sessionStorage.setItem('lucien.outputContentById', JSON.stringify(outputContentById));
        window.sessionStorage.setItem('lucien.selectedOutputId', selectedOutputId);
        if (data.status) renderOutputWorkspace(data.status.research_outputs || [], selectedMission);
        workspaceTitle.scrollIntoView({behavior: 'smooth', block: 'center'});
      }
    }

    document.getElementById('researchBriefBtn').addEventListener('click', () => createResearch('research_brief'));
    document.getElementById('claimMapBtn').addEventListener('click', () => createResearch('claim_map_draft'));
    document.getElementById('paperDraftBtn').addEventListener('click', () => createResearch('paper_draft'));

    document.getElementById('homeSessionReplay').addEventListener('click', () => {
      document.getElementById('advancedDiagnostics').open = true;
      timeline.scrollIntoView({behavior: 'smooth', block: 'center'});
    });

    document.getElementById('brainMode').addEventListener('change', () => {
      window.localStorage.setItem('lucien.brainMode', document.getElementById('brainMode').value);
      updateBrainModeControls();
    });

    document.getElementById('advancedModelMode').addEventListener('change', updateBrainModeControls);
    document.getElementById('useOpenAI').addEventListener('change', updateBrainModeControls);

    document.getElementById('advancedDiagnostics').addEventListener('toggle', () => {
      window.localStorage.setItem('lucien.advancedDiagnosticsOpen', document.getElementById('advancedDiagnostics').open ? 'yes' : 'no');
    });

    activeMissionSelect.addEventListener('change', () => {
      setActiveMission(activeMissionSelect.value);
    });

    for (const control of document.querySelectorAll('[data-inbox-filter]')) {
      control.addEventListener('click', () => {
        activeInboxFilter = control.getAttribute('data-inbox-filter') || 'all';
        refresh();
      });
    }

    const storedBrainMode = window.localStorage.getItem('lucien.brainMode');
    if (storedBrainMode && ['local_ollama', 'serious_only', 'echo'].includes(storedBrainMode)) {
      document.getElementById('brainMode').value = storedBrainMode;
    }
    document.getElementById('advancedDiagnostics').open = window.localStorage.getItem('lucien.advancedDiagnosticsOpen') === 'yes';
    updateBrainModeControls();
    refresh();
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())

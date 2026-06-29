from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from .chat_sessions import (
    ChatSessionRecord,
    chat_sessions_from_events,
    chat_turns_from_events,
)
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .mission_steps import mission_step_records_from_events
from .report import _event_summary, build_trace_report


@dataclass(frozen=True)
class SessionTimelineEntry:
    index: int
    event_type: str
    timestamp: str
    event_hash: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "event_hash": self.event_hash,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class SessionReplay:
    session: ChatSessionRecord
    turns: list[dict[str, Any]]
    timeline: list[SessionTimelineEntry]
    final_state: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "turns": self.turns,
            "timeline": [entry.to_dict() for entry in self.timeline],
            "final_state": self.final_state,
        }


def build_session_replay(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    session_id: str,
) -> SessionReplay:
    events = ledger.events()
    session = _require_session(chat_sessions_from_events(events), session_id)
    turn_records = [
        turn for turn in chat_turns_from_events(events) if turn.session_id == session_id
    ]
    replay_events = _session_event_slice(events, session_id)
    timeline = [
        SessionTimelineEntry(
            index=index,
            event_type=event.event_type,
            timestamp=event.timestamp,
            event_hash=event.event_hash or "",
            summary=_event_summary(event),
        )
        for index, event in replay_events
    ]
    report = build_trace_report(ledger, manifest)
    steps = mission_step_records_from_events(events)
    return SessionReplay(
        session=session,
        turns=[turn.to_dict() for turn in turn_records],
        timeline=timeline,
        final_state={
            "current_continuity_claim": report.summary.get("current_continuity_claim"),
            "identity_state": report.summary.get("identity_state"),
            "output_mode": report.summary.get("output_mode"),
            "chain_valid": report.summary.get("chain_valid"),
            "active_reflection_task_count": report.summary.get(
                "active_reflection_task_count"
            ),
            "unresolved_growth_conflict_count": report.summary.get(
                "unresolved_growth_conflict_count"
            ),
            "mission_step_count": len(steps),
            "mission_step_statuses": _step_status_counts(steps),
        },
    )


def latest_session_id(ledger: ContinuityLedger) -> str | None:
    sessions = chat_sessions_from_events(ledger.events())
    if not sessions:
        return None
    return sessions[-1].session_id


def render_session_replay_html(replay: SessionReplay) -> str:
    rows = "\n".join(_render_entry(entry) for entry in replay.timeline)
    turns = "\n".join(_render_turn(turn) for turn in replay.turns)
    final_state = "\n".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(str(value))}</td></tr>"
        for key, value in replay.final_state.items()
    )
    session = replay.session
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PCA Session Replay</title>
  <style>
    body {{ margin:0; background:#f7f8f4; color:#17201b; font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; letter-spacing:0; }}
    header {{ background:#11231b; color:white; padding:28px clamp(18px,4vw,48px); }}
    main {{ max-width:1180px; margin:0 auto; padding:20px; display:grid; gap:18px; }}
    section {{ background:white; border:1px solid #d8ded9; padding:16px; }}
    h1 {{ margin:0 0 6px; font-size:30px; }}
    h2 {{ margin:0 0 12px; font-size:18px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ border-bottom:1px solid #e8ece8; text-align:left; padding:9px; vertical-align:top; }}
    th {{ color:#60706a; font-size:12px; text-transform:uppercase; }}
    code {{ font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:12px; overflow-wrap:anywhere; }}
    .grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
    @media (max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>PCA Session Replay</h1>
    <div><code>{escape(session.session_id)}</code></div>
  </header>
  <main>
    <section>
      <h2>Session</h2>
      <div class="grid">
        <div>Status: <strong>{escape(session.status)}</strong></div>
        <div>Turns: <strong>{session.turn_count}</strong></div>
        <div>Started: <code>{escape(session.started_at)}</code></div>
        <div>Closed: <code>{escape(str(session.closed_at or "open"))}</code></div>
      </div>
    </section>
    <section>
      <h2>Final State</h2>
      <table>{final_state}</table>
    </section>
    <section>
      <h2>Turns</h2>
      <table>
        <thead><tr><th>Turn</th><th>Claim</th><th>Output</th><th>Growth Events</th></tr></thead>
        <tbody>{turns}</tbody>
      </table>
    </section>
    <section>
      <h2>Timeline</h2>
      <table>
        <thead><tr><th>#</th><th>Event</th><th>Summary</th><th>Hash</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def write_session_replay_html(replay: SessionReplay, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_session_replay_html(replay), encoding="utf-8")
    return output


def _session_event_slice(
    events: list[ContinuityEvent],
    session_id: str,
) -> list[tuple[int, ContinuityEvent]]:
    start_index = None
    end_index = None
    for index, event in enumerate(events, start=1):
        if (
            event.event_type == "lucien.chat_session_started"
            and event.payload.get("session_id") == session_id
        ):
            start_index = index
        if (
            event.event_type == "lucien.chat_session_closed"
            and event.payload.get("session_id") == session_id
        ):
            end_index = index
    if start_index is None:
        raise ValueError(f"Chat session not found: {session_id}")
    if end_index is None:
        end_index = len(events)
    return [
        (index, event)
        for index, event in enumerate(events, start=1)
        if start_index <= index <= end_index or event.event_type.startswith("mission.step_")
    ]


def _require_session(
    sessions: list[ChatSessionRecord],
    session_id: str,
) -> ChatSessionRecord:
    for session in sessions:
        if session.session_id == session_id:
            return session
    raise ValueError(f"Chat session not found: {session_id}")


def _render_entry(entry: SessionTimelineEntry) -> str:
    return (
        "<tr>"
        f"<td>{entry.index}</td>"
        f"<td><code>{escape(entry.event_type)}</code><br><small>{escape(entry.timestamp)}</small></td>"
        f"<td>{escape(entry.summary)}</td>"
        f"<td><code>{escape(entry.event_hash[:12])}</code></td>"
        "</tr>"
    )


def _render_turn(turn: dict[str, Any]) -> str:
    growth_events = ", ".join(str(item)[:12] for item in turn.get("growth_event_ids", []))
    return (
        "<tr>"
        f"<td>{escape(str(turn.get('turn_index')))}</td>"
        f"<td>{escape(str(turn.get('continuity_claim')))}</td>"
        f"<td>{escape(str(turn.get('output_allowed')))}</td>"
        f"<td><code>{escape(growth_events or 'none')}</code></td>"
        "</tr>"
    )


def _step_status_counts(steps) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        status = step.execution_status.value
        counts[status] = counts.get(status, 0) + 1
    return counts

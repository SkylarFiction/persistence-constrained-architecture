from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .report import TraceReport, _short_hash


def render_lucien_cockpit_html(report: TraceReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    status_class = _status_class(str(summary["current_continuity_claim"]))
    latest_session = data["chat_sessions"][-1] if data["chat_sessions"] else None
    latest_turn = data["chat_turns"][-1] if data["chat_turns"] else None
    pending_growth = [
        record
        for record in data["growth_records"]
        if record["status"] in {"proposed", "requires_review"}
    ]
    conflict_by_growth_id = {
        conflict["proposed_growth_id"]: conflict
        for conflict in data["growth_conflicts"]
    }
    memory_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(card['memory_id'])))}</code></td>"
        f"<td>{escape(str(card['effective_confidence']))}</td>"
        f"<td>{escape(_signal_text(card))}</td>"
        f"<td>{escape(str(card['continuity_claim_at_acceptance']))}</td>"
        f"<td><code>{escape(_short_hash(str(card['summary_sha256'])))}</code></td>"
        f"<td>{escape(str(card['reason']))}</td>"
        "</tr>"
        for card in data["memory_cards"]
    ) or _empty_row(6, "No memory cards yet.")
    growth_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(record['kind']))}</td>"
        f"<td>{escape(str(record['status']))}</td>"
        f"<td>{escape(str(record['identity_impact']))}</td>"
        f"<td><code>{escape(_short_hash(str(record['growth_id'])))}</code></td>"
        f"<td>{escape(_growth_reason(record, conflict_by_growth_id))}</td>"
        f"<td><pre class=\"mini-command\"><code>{escape(_review_commands(str(record['growth_id'])))}</code></pre></td>"
        "</tr>"
        for record in pending_growth
    ) or _empty_row(6, "No growth awaiting review.")
    conflict_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(conflict['proposed_growth_id'])))}</code></td>"
        f"<td>{escape(str(conflict['conflict_type']))}</td>"
        f"<td>{escape(str(conflict['severity']))}</td>"
        f"<td>{escape(str(conflict['reason']))}</td>"
        "</tr>"
        for conflict in data["growth_conflicts"][-8:]
    ) or _empty_row(4, "No growth conflicts detected.")
    conflict_resolution_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(resolution['conflict_id'])))}</code></td>"
        f"<td>{escape(str(resolution['decision']))}</td>"
        f"<td>{escape(str(resolution['resolved_by']))}</td>"
        f"<td>{escape(str(resolution['effect']))}</td>"
        "</tr>"
        for resolution in data["growth_conflict_resolutions"][-8:]
    ) or _empty_row(4, "No conflict resolutions recorded.")
    flow_by_mission_id = {
        flow["mission_id"]: flow for flow in data.get("mission_flows", [])
    }
    mission_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(brief['mission']['title']))}</td>"
        f"<td>{escape(str(brief['mission']['status']))}</td>"
        f"<td>{escape(str(flow_by_mission_id.get(brief['mission']['mission_id'], {}).get('phase', 'unknown')))}</td>"
        f"<td><code>{escape(_short_hash(str(brief['mission']['mission_id'])))}</code></td>"
        f"<td>{escape(_mission_counts(brief))}</td>"
        f"<td>{escape(str(flow_by_mission_id.get(brief['mission']['mission_id'], {}).get('next_action', '')))}</td>"
        f"<td>{escape(_joined(brief['mission'].get('values', [])))}</td>"
        "</tr>"
        for brief in data["missions"][-8:]
    ) or _empty_row(7, "No missions opened yet.")
    mission_step_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(step['step_id'])))}</code></td>"
        f"<td><code>{escape(_short_hash(str(step['mission_id'])))}</code></td>"
        f"<td>{escape(str(step['risk_level']))}</td>"
        f"<td>{escape(str(step['required_tool']))}</td>"
        f"<td>{escape(str(step['approval_status']))}</td>"
        f"<td>{escape(str(step['execution_status']))}</td>"
        f"<td><code>{escape(_short_hash(str(step['description_sha256'])))}</code></td>"
        "</tr>"
        for step in data.get("mission_steps", [])[-12:]
    ) or _empty_row(7, "No mission steps recorded.")
    evidence_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(record['evidence_id'])))}</code></td>"
        f"<td>{escape(str(record['source_type']))}</td>"
        f"<td>{escape(str(record['review_status']))}</td>"
        f"<td>{escape(str(record['confidence']))}</td>"
        f"<td><code>{escape(_short_hash(str(record['summary_hash'])))}</code></td>"
        f"<td>{escape(str(record['reason']))}</td>"
        "</tr>"
        for record in data.get("evidence_records", [])[-10:]
    ) or _empty_row(6, "No evidence recorded.")
    evidence_link_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(link['evidence_id'])))}</code></td>"
        f"<td>{escape(str(link['target_type']))}</td>"
        f"<td><code>{escape(_short_hash(str(link['target_id'])))}</code></td>"
        f"<td>{escape(str(link['reason']))}</td>"
        "</tr>"
        for link in data.get("evidence_links", [])[-10:]
    ) or _empty_row(4, "No evidence links yet.")
    evidence_claim_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(claim['claim_id'])))}</code></td>"
        f"<td>{escape(str(claim['status']))}</td>"
        f"<td>{escape(str(claim['confidence']))}</td>"
        f"<td>{escape(str(len(claim['evidence_ids'])))} evidence item(s)</td>"
        f"<td><code>{escape(_short_hash(str(claim['statement_hash'])))}</code></td>"
        "</tr>"
        for claim in data.get("evidence_claims", [])[-8:]
    ) or _empty_row(5, "No evidence claims recorded.")
    skill_candidate_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(skill['name']))}</td>"
        f"<td>{escape(str(skill['status']))}</td>"
        f"<td>{escape(str(skill['required_tool']))}</td>"
        f"<td>{escape(str(skill['risk_level']))}</td>"
        f"<td><code>{escape(_short_hash(str(skill['skill_id'])))}</code></td>"
        f"<td><code>{escape(_short_hash(str(skill['procedure_sha256'])))}</code></td>"
        f"<td>{escape(str(skill['reason']))}</td>"
        "</tr>"
        for skill in data.get("skill_candidates", [])[-10:]
    ) or _empty_row(7, "No skill candidates recorded.")
    accepted_skill_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(skill['name']))}</td>"
        f"<td>{escape(str(skill['required_tool']))}</td>"
        f"<td>{escape(str(skill['risk_level']))}</td>"
        f"<td>{escape(str(len(skill['source_step_ids'])))} step(s)</td>"
        f"<td><code>{escape(_short_hash(str(skill['skill_id'])))}</code></td>"
        f"<td><code>{escape(_short_hash(str(skill['procedure_sha256'])))}</code></td>"
        "</tr>"
        for skill in data.get("accepted_skills", [])[-10:]
    ) or _empty_row(6, "No accepted skills yet.")
    reflection_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(reflection['focus']))}</td>"
        f"<td>{escape(str(reflection['severity']))}</td>"
        f"<td>{escape(_joined(reflection['observations']))}</td>"
        f"<td>{escape(_joined(reflection['recommended_actions']))}</td>"
        "</tr>"
        for reflection in data["reflections"][-5:]
    ) or _empty_row(4, "No reflections recorded.")
    reflection_task_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(task['status']))}</td>"
        f"<td>{escape(str(task['severity']))}</td>"
        f"<td>{escape(str(task['kind']))}</td>"
        f"<td>{escape(str(task['reason']))}</td>"
        f"<td>{escape(str(task['recommended_action']))}</td>"
        f"<td>{escape(str(task['created_at']))}</td>"
        "</tr>"
        for task in data["reflection_tasks"][-8:]
    ) or _empty_row(6, "No reflection tasks recorded.")
    session_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(_short_hash(str(session['session_id'])))}</code></td>"
        f"<td>{escape(str(session['status']))}</td>"
        f"<td>{escape(str(session['turn_count']))}</td>"
        f"<td>{escape(str(session['started_at']))}</td>"
        "</tr>"
        for session in data["chat_sessions"][-5:]
    ) or _empty_row(4, "No chat sessions yet.")
    turn_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(turn['turn_index']))}</td>"
        f"<td>{escape(str(turn['output_allowed']))}</td>"
        f"<td>{escape(str(turn['continuity_claim']))}</td>"
        f"<td>{escape(str(len(turn['growth_event_ids'])))} growth event(s)</td>"
        "</tr>"
        for turn in data["chat_turns"][-8:]
    ) or _empty_row(4, "No chat turns yet.")
    self_model_rows = _self_model_rows(data["self_model"])
    report_json = json.dumps(data, sort_keys=True).replace("</", "<\\/")
    latest_session_text = (
        f"{latest_session['status']} / {latest_session['turn_count']} turn(s)"
        if latest_session
        else "none"
    )
    latest_turn_text = (
        f"turn {latest_turn['turn_index']} / output allowed={latest_turn['output_allowed']}"
        if latest_turn
        else "none"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lucien Cockpit</title>
  <style>
    :root {{
      --ink: #17201b;
      --muted: #5b6862;
      --line: #d8ded9;
      --paper: #f7f8f4;
      --panel: #ffffff;
      --deep: #11231b;
      --green: #136f45;
      --amber: #9a6412;
      --red: #a33a2a;
      --blue: #245a7a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}
    header {{
      background: var(--deep);
      color: white;
      padding: 28px clamp(20px, 4vw, 56px);
    }}
    h1 {{ margin: 0 0 8px; font-size: 32px; line-height: 1.1; }}
    h2 {{ margin: 0 0 14px; font-size: 18px; }}
    p {{ margin: 0; color: inherit; }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
    .status {{
      display: grid;
      grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(160px, 220px));
      gap: 1px;
      border: 1px solid var(--line);
      background: var(--line);
      margin-bottom: 20px;
    }}
    .cell {{ background: var(--panel); padding: 18px; min-width: 0; }}
    .claim {{ border-top: 6px solid var(--green); }}
    .claim.warn {{ border-top-color: var(--amber); }}
    .claim.break {{ border-top-color: var(--red); }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; font-weight: 700; }}
    .value {{ margin-top: 6px; font-size: 22px; font-weight: 800; overflow-wrap: anywhere; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }}
    section {{ background: var(--panel); border: 1px solid var(--line); padding: 18px; margin-bottom: 20px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e8ece8; padding: 10px; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }}
    .command, .mini-command {{ background: #eef3f0; border: 1px solid var(--line); padding: 12px; overflow-x: auto; }}
    .mini-command {{ margin: 0; padding: 8px; font-size: 11px; white-space: pre-wrap; }}
    .empty {{ color: var(--muted); }}
    .pill {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #e8f0ec; color: var(--green); font-weight: 700; }}
    @media (max-width: 880px) {{
      .status, .grid {{ grid-template-columns: 1fr; }}
      main {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Lucien Cockpit</h1>
    <p>Persistent conversational shell governed by PCA continuity constraints.</p>
  </header>
  <main>
    <div class="status">
      <div class="cell claim {status_class}">
        <div class="label">Continuity Claim</div>
        <div class="value">{escape(str(summary['current_continuity_claim']))}</div>
      </div>
      <div class="cell"><div class="label">Output Mode</div><div class="value">{escape(str(summary['output_mode']))}</div></div>
      <div class="cell"><div class="label">Memory Cards</div><div class="value">{escape(str(summary['memory_card_count']))}</div></div>
      <div class="cell"><div class="label">Open Missions</div><div class="value">{escape(str(summary['open_mission_count']))}</div></div>
    </div>
    <section>
      <h2>Live Runtime Snapshot</h2>
      <div class="grid">
        <div><div class="label">Latest Session</div><div class="value">{escape(latest_session_text)}</div></div>
        <div><div class="label">Latest Turn</div><div class="value">{escape(latest_turn_text)}</div></div>
        <div><div class="label">Chain Valid</div><div class="value">{escape(str(summary['chain_valid']))}</div></div>
        <div><div class="label">Accepted Growth</div><div class="value">{escape(str(summary['accepted_growth_count']))}</div></div>
        <div><div class="label">Memory Signals</div><div class="value">{escape(str(summary['memory_signal_count']))}</div></div>
        <div><div class="label">Reflections</div><div class="value">{escape(str(summary['reflection_count']))}</div></div>
        <div><div class="label">Open Tasks</div><div class="value">{escape(str(summary['active_reflection_task_count']))}</div></div>
        <div><div class="label">Conflict Resolutions</div><div class="value">{escape(str(summary['growth_conflict_resolution_count']))}</div></div>
        <div><div class="label">Open Growth</div><div class="value">{escape(str(len(pending_growth)))}</div></div>
        <div><div class="label">Missions</div><div class="value">{escape(str(summary['mission_count']))}</div></div>
        <div><div class="label">Blocked Missions</div><div class="value">{escape(str(summary['blocked_mission_count']))}</div></div>
        <div><div class="label">Mission Steps</div><div class="value">{escape(str(summary['mission_step_count']))}</div></div>
        <div><div class="label">Evidence Items</div><div class="value">{escape(str(summary['evidence_count']))}</div></div>
        <div><div class="label">Disputed Evidence</div><div class="value">{escape(str(summary['disputed_evidence_count']))}</div></div>
        <div><div class="label">Evidence Links</div><div class="value">{escape(str(summary['evidence_link_count']))}</div></div>
        <div><div class="label">Skill Candidates</div><div class="value">{escape(str(summary['skill_candidate_count']))}</div></div>
        <div><div class="label">Accepted Skills</div><div class="value">{escape(str(summary['accepted_skill_count']))}</div></div>
      </div>
    </section>
    <div class="grid">
      <section>
        <h2>Growth Review Queue</h2>
        <table><thead><tr><th>Kind</th><th>Status</th><th>Impact</th><th>ID</th><th>Reason</th><th>Review Commands</th></tr></thead><tbody>{growth_rows}</tbody></table>
      </section>
      <section>
        <h2>Memory Cards</h2>
        <table><thead><tr><th>ID</th><th>Effective Confidence</th><th>Signals</th><th>Claim</th><th>Hash</th><th>Reason</th></tr></thead><tbody>{memory_rows}</tbody></table>
      </section>
    </div>
    <section>
      <h2>Growth Conflicts</h2>
      <table><thead><tr><th>Growth</th><th>Type</th><th>Severity</th><th>Reason</th></tr></thead><tbody>{conflict_rows}</tbody></table>
    </section>
    <section>
      <h2>Conflict Resolutions</h2>
      <table><thead><tr><th>Conflict</th><th>Decision</th><th>Resolved By</th><th>Effect</th></tr></thead><tbody>{conflict_resolution_rows}</tbody></table>
    </section>
    <section>
      <h2>Mission Workspace</h2>
      <table><thead><tr><th>Title</th><th>Status</th><th>Phase</th><th>ID</th><th>Items</th><th>Next Action</th><th>Values</th></tr></thead><tbody>{mission_rows}</tbody></table>
    </section>
    <section>
      <h2>Mission Steps</h2>
      <table><thead><tr><th>Step</th><th>Mission</th><th>Risk</th><th>Tool</th><th>Approval</th><th>Execution</th><th>Description Hash</th></tr></thead><tbody>{mission_step_rows}</tbody></table>
    </section>
    <section>
      <h2>Evidence Locker</h2>
      <table><thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Confidence</th><th>Summary Hash</th><th>Reason</th></tr></thead><tbody>{evidence_rows}</tbody></table>
    </section>
    <div class="grid">
      <section>
        <h2>Evidence Links</h2>
        <table><thead><tr><th>Evidence</th><th>Target</th><th>Target ID</th><th>Reason</th></tr></thead><tbody>{evidence_link_rows}</tbody></table>
      </section>
      <section>
        <h2>Claims</h2>
        <table><thead><tr><th>Claim</th><th>Status</th><th>Confidence</th><th>Evidence</th><th>Statement Hash</th></tr></thead><tbody>{evidence_claim_rows}</tbody></table>
      </section>
    </div>
    <div class="grid">
      <section>
        <h2>Skill Candidates</h2>
        <table><thead><tr><th>Name</th><th>Status</th><th>Tool</th><th>Risk</th><th>ID</th><th>Procedure Hash</th><th>Reason</th></tr></thead><tbody>{skill_candidate_rows}</tbody></table>
      </section>
      <section>
        <h2>Accepted Skills</h2>
        <table><thead><tr><th>Name</th><th>Tool</th><th>Risk</th><th>Source Steps</th><th>ID</th><th>Procedure Hash</th></tr></thead><tbody>{accepted_skill_rows}</tbody></table>
      </section>
    </div>
    <section>
      <h2>Reflection Ledger</h2>
      <table><thead><tr><th>Focus</th><th>Severity</th><th>Observations</th><th>Recommended Actions</th></tr></thead><tbody>{reflection_rows}</tbody></table>
    </section>
    <section>
      <h2>Reflection Queue</h2>
      <table><thead><tr><th>Status</th><th>Severity</th><th>Kind</th><th>Reason</th><th>Recommended Action</th><th>Created</th></tr></thead><tbody>{reflection_task_rows}</tbody></table>
    </section>
    <div class="grid">
      <section>
        <h2>Recent Sessions</h2>
        <table><thead><tr><th>Session</th><th>Status</th><th>Turns</th><th>Started</th></tr></thead><tbody>{session_rows}</tbody></table>
      </section>
      <section>
        <h2>Recent Turns</h2>
        <table><thead><tr><th>#</th><th>Allowed</th><th>Claim</th><th>Growth</th></tr></thead><tbody>{turn_rows}</tbody></table>
      </section>
    </div>
    <section>
      <h2>Accepted Self-Model</h2>
      <table><thead><tr><th>Kind</th><th>Accepted Records</th></tr></thead><tbody>{self_model_rows}</tbody></table>
    </section>
    <section>
      <h2>Run Another Governed Turn</h2>
      <pre class="command"><code>python3 lucien_chat.py --message "Remember that Lucien should keep learning governed."</code></pre>
      <p class="label">Refresh this page after running the command.</p>
    </section>
  </main>
  <script id="report-data" type="application/json">{report_json}</script>
</body>
</html>
"""


def write_lucien_cockpit_html(report: TraceReport, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_lucien_cockpit_html(report), encoding="utf-8")
    return output


def _status_class(claim: str) -> str:
    if claim == "certified_continuity":
        return "ok"
    if claim in {"review_required", "uncertified_continuity", "declared_fork"}:
        return "warn"
    return "break"


def _empty_row(columns: int, text: str) -> str:
    return f"<tr><td colspan=\"{columns}\" class=\"empty\">{escape(text)}</td></tr>"


def _self_model_rows(self_model: dict) -> str:
    rows = []
    for kind, records in self_model["by_kind"].items():
        rows.append(
            "<tr>"
            f"<td>{escape(str(kind))}</td>"
            f"<td>{escape(str(len(records)))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _growth_reason(record: dict, conflict_by_growth_id: dict) -> str:
    conflict = conflict_by_growth_id.get(record["growth_id"])
    if conflict is None:
        return str(record["reason"])
    return f"{record['reason']} / conflict: {conflict['reason']}"


def _review_commands(growth_id: str) -> str:
    return "\n".join(
        [
            f"python3 pca_cli.py review-growth {growth_id} --accept --reviewer steward --reason \"reviewed\"",
            f"python3 pca_cli.py review-growth {growth_id} --reject --reviewer steward --reason \"conflict or drift\"",
        ]
    )


def _mission_counts(brief: dict) -> str:
    counts = brief.get("counts", {})
    labels = [
        ("hypothesis", "H"),
        ("evidence", "E"),
        ("intervention", "I"),
        ("plan_step", "P"),
        ("risk", "R"),
        ("outcome", "O"),
        ("lesson", "L"),
    ]
    return " / ".join(f"{label} {counts.get(kind, 0)}" for kind, label in labels)


def _signal_text(card: dict) -> str:
    return (
        f"+{card['reinforcement_count']} "
        f"-{card['contradiction_count']} "
        f"stale={card['stale_signal_count']} "
        f"score={card['signal_score']}"
    )


def _joined(values: list[str]) -> str:
    return "; ".join(str(value) for value in values)

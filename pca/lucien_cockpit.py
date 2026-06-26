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
        f"<td>{escape(str(card['confidence']))}</td>"
        f"<td>{escape(str(card['continuity_claim_at_acceptance']))}</td>"
        f"<td><code>{escape(_short_hash(str(card['summary_sha256'])))}</code></td>"
        f"<td>{escape(str(card['reason']))}</td>"
        "</tr>"
        for card in data["memory_cards"]
    ) or _empty_row(5, "No memory cards yet.")
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
      <div class="cell"><div class="label">Open Growth</div><div class="value">{escape(str(len(pending_growth)))}</div></div>
    </div>
    <section>
      <h2>Live Runtime Snapshot</h2>
      <div class="grid">
        <div><div class="label">Latest Session</div><div class="value">{escape(latest_session_text)}</div></div>
        <div><div class="label">Latest Turn</div><div class="value">{escape(latest_turn_text)}</div></div>
        <div><div class="label">Chain Valid</div><div class="value">{escape(str(summary['chain_valid']))}</div></div>
        <div><div class="label">Accepted Growth</div><div class="value">{escape(str(summary['accepted_growth_count']))}</div></div>
      </div>
    </section>
    <div class="grid">
      <section>
        <h2>Growth Review Queue</h2>
        <table><thead><tr><th>Kind</th><th>Status</th><th>Impact</th><th>ID</th><th>Reason</th><th>Review Commands</th></tr></thead><tbody>{growth_rows}</tbody></table>
      </section>
      <section>
        <h2>Memory Cards</h2>
        <table><thead><tr><th>ID</th><th>Confidence</th><th>Claim</th><th>Hash</th><th>Reason</th></tr></thead><tbody>{memory_rows}</tbody></table>
      </section>
    </div>
    <section>
      <h2>Growth Conflicts</h2>
      <table><thead><tr><th>Growth</th><th>Type</th><th>Severity</th><th>Reason</th></tr></thead><tbody>{conflict_rows}</tbody></table>
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

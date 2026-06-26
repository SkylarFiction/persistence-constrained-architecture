from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .report import TraceReport, _short_hash


def _status_class(claim: str) -> str:
    if claim == "certified_continuity":
        return "ok"
    if claim in {"review_required", "uncertified_continuity"}:
        return "warn"
    return "break"


def _json_script(report: TraceReport) -> str:
    return json.dumps(report.to_dict(), sort_keys=True).replace("</", "<\\/")


def _empty_row(columns: int, message: str) -> str:
    return f"<tr><td colspan=\"{columns}\" class=\"empty\">{escape(message)}</td></tr>"


def render_dashboard_html(report: TraceReport) -> str:
    data = report.to_dict()
    summary = data["summary"]
    status_class = _status_class(summary["current_continuity_claim"])
    event_rows = "\n".join(
        "<tr class=\"event-row\" "
        f"data-type=\"{escape(event['event_type'])}\" "
        f"data-text=\"{escape((event['event_type'] + ' ' + event['summary']).lower())}\">"
        f"<td>{event['index']}</td>"
        f"<td>{escape(event['timestamp'])}</td>"
        f"<td><code>{escape(event['event_type'])}</code></td>"
        f"<td>{escape(event['summary'])}</td>"
        f"<td><code>{escape(_short_hash(event['event_hash']))}</code></td>"
        "</tr>"
        for event in data["important_events"]
    )
    claim_steps = "\n".join(
        "<li>"
        f"<span>{escape(claim['created_at'])}</span>"
        f"<strong>{escape(claim['claim'])}</strong>"
        f"<p>{escape(claim['reason'])}</p>"
        "</li>"
        for claim in data["claim_history"]
    )
    signal_cards = "\n".join(
        "<article>"
        f"<span>{escape(str(signal['timestamp']))}</span>"
        f"<strong>{escape(str(signal['state']))}</strong>"
        f"<p>{escape(str(signal['source']))}: {escape(str(signal['reason']))}</p>"
        f"<code>{escape(json.dumps(signal['metrics'], sort_keys=True))}</code>"
        "</article>"
        for signal in data["runtime_signals"]
    )
    output_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(event['timestamp']))}</td>"
        f"<td>{escape(str(event['mode']))}</td>"
        f"<td>{escape(str(event['allowed']))}</td>"
        f"<td><code>{escape(_short_hash(str(event['input_sha256'])))}</code></td>"
        f"<td><code>{escape(_short_hash(str(event['output_sha256'])))}</code></td>"
        "</tr>"
        for event in data["output_gate_events"]
    )
    freshness_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(str(row['constraint']))}</code></td>"
        f"<td>{escape(str(row['required']))}</td>"
        f"<td>{escape(str(row['status']))}</td>"
        f"<td>{escape(str(row['freshness_seconds']))}</td>"
        f"<td>{escape(str(row['age_seconds']))}</td>"
        f"<td><code>{escape(_short_hash(str(row['latest_event_hash'] or '')))}</code></td>"
        "</tr>"
        for row in data["evidence_freshness"]
    )
    followup_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(str(record['followup_id']))}</code></td>"
        f"<td>{escape(str(record['followup_type']))}</td>"
        f"<td>{escape(str(record['status']))}</td>"
        f"<td>{escape(str(record['reason']))}</td>"
        "</tr>"
        for record in data["active_followups"]
    ) or _empty_row(4, "No active blockers.")
    recovery_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(str(record['recovery_id']))}</code></td>"
        f"<td>{escape(str(record['status']))}</td>"
        f"<td>{escape(str(record['opened_by']))}</td>"
        f"<td>{escape(str(record['reason']))}</td>"
        "</tr>"
        for record in data["recovery_records"]
    ) or _empty_row(4, "No recovery records.")
    lineage_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(record['parent_id']))}</td>"
        f"<td>{escape(str(record['child_id']))}</td>"
        f"<td>{escape(str(record['reason']))}</td>"
        f"<td><code>{escape(_short_hash(str(record['event_hash'])))}</code></td>"
        "</tr>"
        for record in data["lineage"]
    ) or _empty_row(4, "No declared forks.")
    authorization_rows = "\n".join(
        "<tr>"
        f"<td>{escape(str(record['timestamp']))}</td>"
        f"<td>{escape(str(record['action']))}</td>"
        f"<td>{escape(str(record['actor_authority']))}</td>"
        f"<td>{escape(str(record['required_authority']))}</td>"
        f"<td>{escape(str(record['decision']))}</td>"
        "</tr>"
        for record in data["authorization_checks"]
    ) or _empty_row(5, "No authorization checks recorded.")
    growth_rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(str(record['growth_id']))}</code></td>"
        f"<td>{escape(str(record['kind']))}</td>"
        f"<td>{escape(str(record['status']))}</td>"
        f"<td>{escape(str(record['identity_impact']))}</td>"
        f"<td><code>{escape(_short_hash(str(record['summary_sha256'])))}</code></td>"
        f"<td>{escape(str(record['reason']))}</td>"
        "</tr>"
        for record in data["growth_records"]
    ) or _empty_row(6, "No growth records.")
    policy_error_items = "\n".join(
        f"<li>{escape(error)}</li>"
        for error in data["policy_errors"]
    ) or "<li class=\"empty\">No policy errors.</li>"
    precedence_items = "\n".join(
        f"<li>{escape(rule)}</li>"
        for rule in summary["state_precedence"]
    )
    anchor = data.get("anchor_verification")
    anchor_reasons = (
        ", ".join(anchor["reasons"])
        if anchor is not None
        else "No anchor verification requested."
    )
    anchor_hash = (
        _short_hash(str(anchor["latest_anchor"]["head_hash"]))
        if anchor is not None and anchor.get("latest_anchor") is not None
        else ""
    )
    report_json = _json_script(report)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PCA Dashboard</title>
  <style>
    :root {{
      --ink: #18201d;
      --muted: #60706a;
      --line: #d8dfda;
      --paper: #fbfcf8;
      --panel: #ffffff;
      --ok: #1d6f4a;
      --warn: #9a6700;
      --break: #a33a2b;
      --blue: #255f85;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      background: #18201d;
      color: #f7fbff;
      padding: 28px;
    }}
    header h1 {{
      margin: 0 0 8px;
      font-size: 28px;
      letter-spacing: 0;
    }}
    header p {{ margin: 0; color: #cfd9d4; }}
    main {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}
    .status {{
      border-left: 8px solid var(--blue);
      background: var(--panel);
      border-radius: 8px;
      padding: 18px;
      margin-bottom: 20px;
      border-top: 1px solid var(--line);
      border-right: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }}
    .status.ok {{ border-left-color: var(--ok); }}
    .status.warn {{ border-left-color: var(--warn); }}
    .status.break {{ border-left-color: var(--break); }}
    .status strong {{
      display: block;
      font-size: 24px;
      margin-bottom: 6px;
      overflow-wrap: anywhere;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin: 16px 0 24px;
    }}
    .metric, .panel, .signals article {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .value {{
      font-size: 18px;
      font-weight: 700;
      margin-top: 6px;
      overflow-wrap: anywhere;
    }}
    section {{ margin: 24px 0; }}
    h2 {{ margin: 0 0 12px; font-size: 20px; letter-spacing: 0; }}
    .toolbar {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }}
    input, select {{
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 10px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
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
    th {{ background: #edf2ee; color: #293731; }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .claim-path {{
      margin: 0;
      padding-left: 20px;
    }}
    .claim-path li {{
      margin: 0 0 12px;
      padding-left: 4px;
    }}
    .claim-path span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .claim-path p {{ margin: 4px 0 0; color: var(--muted); }}
    .precedence {{
      margin: 0;
      padding-left: 20px;
      columns: 2;
    }}
    .precedence li {{ margin-bottom: 6px; }}
    .policy-errors {{
      margin: 0;
      padding-left: 20px;
    }}
    .signals {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
    }}
    .signals span {{ display: block; color: var(--muted); font-size: 12px; }}
    .signals strong {{ display: block; margin-top: 4px; font-size: 18px; }}
    .signals p {{ margin: 6px 0; }}
    .empty {{ color: var(--muted); }}
  </style>
</head>
<body>
  <header>
    <h1>PCA Dashboard</h1>
    <p>{escape(summary['name'])} / <code>{escape(summary['system_id'])}</code></p>
  </header>
  <main>
    <section class="status {status_class}">
      <div class="label">Current Continuity Claim</div>
      <strong>{escape(summary['current_continuity_claim'])}</strong>
      <div>{escape(summary['output_allowed_scope'])}</div>
    </section>
    <section class="grid">
      <div class="metric"><div class="label">Identity State</div><div class="value">{escape(summary['identity_state'])}</div></div>
      <div class="metric"><div class="label">Output Mode</div><div class="value">{escape(summary['output_mode'])}</div></div>
      <div class="metric"><div class="label">Chain Valid</div><div class="value">{escape(str(summary['chain_valid']))}</div></div>
      <div class="metric"><div class="label">Events</div><div class="value">{escape(str(summary['event_count']))}</div></div>
      <div class="metric"><div class="label">Active Follow-ups</div><div class="value">{escape(str(summary['active_followups']))}</div></div>
      <div class="metric"><div class="label">Recovery Status</div><div class="value">{escape(str(summary['current_recovery_status']))}</div></div>
      <div class="metric"><div class="label">Anchor Valid</div><div class="value">{escape(str(summary['anchor_valid']))}</div></div>
      <div class="metric"><div class="label">Policy Errors</div><div class="value">{escape(str(summary['policy_error_count']))}</div></div>
      <div class="metric"><div class="label">Growth Records</div><div class="value">{escape(str(summary['growth_count']))}</div></div>
      <div class="metric"><div class="label">Active Growth</div><div class="value">{escape(str(summary['active_growth_count']))}</div></div>
    </section>
    <section class="grid">
      <div class="panel">
        <h2>Anchor Status</h2>
        <div class="label">Latest Anchored Head</div>
        <div class="value"><code>{escape(anchor_hash)}</code></div>
        <p>{escape(anchor_reasons)}</p>
      </div>
      <div class="panel">
        <h2>State Precedence</h2>
        <ol class="precedence">{precedence_items}</ol>
      </div>
      <div class="panel">
        <h2>Policy Errors</h2>
        <ul class="policy-errors">{policy_error_items}</ul>
      </div>
    </section>
    <section>
      <h2>Evidence Freshness</h2>
      <table><thead><tr><th>Constraint</th><th>Required</th><th>Status</th><th>Freshness Seconds</th><th>Age Seconds</th><th>Latest Event</th></tr></thead><tbody>{freshness_rows}</tbody></table>
    </section>
    <section class="panel">
      <h2>Claim Path</h2>
      <ol class="claim-path">{claim_steps or '<li class="empty">No claim records yet.</li>'}</ol>
    </section>
    <section>
      <h2>Active Blockers</h2>
      <table><thead><tr><th>Follow-up ID</th><th>Type</th><th>Status</th><th>Reason</th></tr></thead><tbody>{followup_rows}</tbody></table>
    </section>
    <section>
      <h2>Recovery Timeline</h2>
      <table><thead><tr><th>Recovery ID</th><th>Status</th><th>Opened By</th><th>Reason</th></tr></thead><tbody>{recovery_rows}</tbody></table>
    </section>
    <section>
      <h2>Lineage</h2>
      <table><thead><tr><th>Parent</th><th>Child</th><th>Reason</th><th>Event</th></tr></thead><tbody>{lineage_rows}</tbody></table>
    </section>
    <section>
      <h2>Authorization Attempts</h2>
      <table><thead><tr><th>Time</th><th>Action</th><th>Actor</th><th>Required</th><th>Decision</th></tr></thead><tbody>{authorization_rows}</tbody></table>
    </section>
    <section>
      <h2>Growth Records</h2>
      <table><thead><tr><th>Growth ID</th><th>Kind</th><th>Status</th><th>Impact</th><th>Summary Hash</th><th>Reason</th></tr></thead><tbody>{growth_rows}</tbody></table>
    </section>
    <section>
      <h2>Runtime Signals</h2>
      <div class="signals">{signal_cards or '<div class="panel empty">No runtime signals recorded.</div>'}</div>
    </section>
    <section>
      <h2>Output Gate Ledger</h2>
      <table><thead><tr><th>Time</th><th>Mode</th><th>Allowed</th><th>Input Hash</th><th>Output Hash</th></tr></thead><tbody>{output_rows}</tbody></table>
    </section>
    <section>
      <h2>Governance Timeline</h2>
      <div class="toolbar">
        <input id="eventSearch" type="search" placeholder="Search events">
        <select id="eventType">
          <option value="">All event types</option>
        </select>
      </div>
      <table><thead><tr><th>#</th><th>Time</th><th>Type</th><th>Summary</th><th>Hash</th></tr></thead><tbody id="eventBody">{event_rows}</tbody></table>
    </section>
  </main>
  <script id="report-data" type="application/json">{report_json}</script>
  <script>
    const rows = Array.from(document.querySelectorAll('.event-row'));
    const typeSelect = document.getElementById('eventType');
    const search = document.getElementById('eventSearch');
    const types = Array.from(new Set(rows.map(row => row.dataset.type))).sort();
    for (const type of types) {{
      const option = document.createElement('option');
      option.value = type;
      option.textContent = type;
      typeSelect.appendChild(option);
    }}
    function applyFilters() {{
      const query = search.value.trim().toLowerCase();
      const type = typeSelect.value;
      for (const row of rows) {{
        const typeOk = !type || row.dataset.type === type;
        const textOk = !query || row.dataset.text.includes(query);
        row.style.display = typeOk && textOk ? '' : 'none';
      }}
    }}
    search.addEventListener('input', applyFilters);
    typeSelect.addEventListener('change', applyFilters);
  </script>
</body>
</html>
"""


def write_dashboard_html(report: TraceReport, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dashboard_html(report), encoding="utf-8")
    return output_path

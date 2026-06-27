from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .manifest import IdentityManifest
from .report import TraceReport, _short_hash


def render_constitution_markdown(
    report: TraceReport,
    manifest: IdentityManifest,
) -> str:
    data = report.to_dict()
    summary = data["summary"]
    self_model = data["self_model"]
    latest_reflection = data["reflections"][-1] if data["reflections"] else None
    active_tasks = data["active_reflection_tasks"]
    lines = [
        "# Lucien Constitution",
        "",
        "> Generated from PCA ledger evidence. This file is a review artifact, not a manual identity override.",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"Ledger: `{summary['ledger_path']}`",
        "",
        "## Identity Baseline",
        "",
        f"- Name: {manifest.name}",
        f"- System ID: `{manifest.system_id}`",
        f"- Version: {manifest.version}",
        f"- Current continuity claim: `{summary['current_continuity_claim']}`",
        f"- Identity state: `{summary['identity_state']}`",
        f"- Output mode: `{summary['output_mode']}`",
        f"- Chain valid: `{summary['chain_valid']}`",
        f"- Origin: {_origin_text(manifest.origin)}",
        "",
        "## Core Invariants",
        "",
        *_list_items(manifest.invariants),
        "",
        "## Accepted Commitments",
        "",
        *_self_model_items(self_model, "commitment"),
        "",
        "## Active Policies",
        "",
        *_self_model_items(self_model, "policy"),
        "",
        "## Identity-Defining Accepted Growth",
        "",
        *_self_model_items(self_model, "identity"),
        "",
        "## Memory and Preference State",
        "",
        f"- Accepted memory records: {len(self_model['by_kind'].get('memory', []))}",
        f"- Accepted preferences: {len(self_model['by_kind'].get('preference', []))}",
        f"- Accepted skills: {len(self_model['by_kind'].get('skill', []))}",
        f"- Memory cards: {summary['memory_card_count']}",
        f"- Memory signals: {summary['memory_signal_count']}",
        "",
        "## Growth Rules",
        "",
        "- Growth is proposed as ledger-backed `GrowthRecord` entries.",
        "- Low-impact growth may be auto-accepted only when the growth gate permits it.",
        "- Medium, high, and identity-defining growth require review or stronger continuity conditions.",
        "- Broken or uncertified continuity prevents silent self-model acceptance.",
        "",
        "## Conflict Rules",
        "",
        "- Conflicting growth must be steward-resolved before related growth can proceed.",
        "- `accept_new` permits steward-reviewed acceptance of the proposed growth.",
        "- `keep_existing` preserves the accepted commitment, policy, or identity marker.",
        "- `fork` requires lineage-scoped treatment instead of pretending continuity is unchanged.",
        f"- Recorded conflicts: {summary['growth_conflict_count']}",
        f"- Resolved conflicts: {summary['growth_conflict_resolution_count']}",
        f"- Unresolved conflicts: {summary['unresolved_growth_conflict_count']}",
        "",
        "## Recovery Rules",
        "",
        "- A hard breach blocks normal identity claims.",
        "- Recovery must be opened by recovery authority.",
        "- Recovery audits can certify a recovery record without silently restoring full continuity.",
        f"- Current recovery status: `{_display_value(summary['current_recovery_status'])}`",
        "",
        "## Fork Rules",
        "",
        "- Forks must be declared rather than hidden.",
        "- Forked growth is lineage-scoped.",
        "- Divergence must not be represented as unchanged singular continuity.",
        f"- Declared lineage records: {len(data['lineage'])}",
        "",
        "## Current Steward Queue",
        "",
        *_task_items(active_tasks),
        "",
        "## Last Reflection",
        "",
        *_reflection_items(latest_reflection),
        "",
        "## Known Limits",
        "",
        "- PCA v0.1 is local-only and is not a production security boundary.",
        "- PCA is not a consciousness detector and is not proof of personhood.",
        "- The current hash chain is locally verifiable but not externally anchored unless anchors are exported.",
        "- Accepted growth stores hashes, lengths, reasons, and evidence refs rather than raw private conversation text.",
        "- Steward decisions are governance records; they do not make unsafe continuity claims true by declaration.",
        "",
    ]
    return "\n".join(lines)


def write_constitution_markdown(
    report: TraceReport,
    manifest: IdentityManifest,
    path: str | Path = "LUCIEN_CONSTITUTION.md",
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_constitution_markdown(report, manifest),
        encoding="utf-8",
    )
    return output


def _origin_text(origin: dict[str, Any]) -> str:
    if not origin:
        return "not recorded"
    return ", ".join(f"{key}={value}" for key, value in origin.items())


def _display_value(value: Any) -> str:
    if value is None:
        return "none"
    return str(value)


def _list_items(values: list[str]) -> list[str]:
    if not values:
        return ["- none recorded"]
    return [f"- {value}" for value in values]


def _self_model_items(self_model: dict[str, Any], kind: str) -> list[str]:
    records = self_model["by_kind"].get(kind, [])
    if not records:
        return ["- none accepted"]
    rows = []
    for record in records:
        evidence = ", ".join(record["evidence_refs"]) or "no external refs"
        rows.append(
            "- "
            f"`{_short_hash(str(record['growth_id']))}` "
            f"impact=`{record['identity_impact']}` "
            f"hash=`{_short_hash(str(record['summary_sha256']))}` "
            f"evidence={evidence} "
            f"reason={record['reason'] or 'not specified'}"
        )
    return rows


def _task_items(tasks: list[dict[str, Any]]) -> list[str]:
    if not tasks:
        return ["- no open steward tasks"]
    rows = []
    for task in tasks:
        rows.append(
            "- "
            f"`{task['kind']}` severity=`{task['severity']}` "
            f"status=`{task['status']}` "
            f"reason={task['reason']} "
            f"action={task['recommended_action']}"
        )
    return rows


def _reflection_items(reflection: dict[str, Any] | None) -> list[str]:
    if reflection is None:
        return ["- no reflection recorded"]
    rows = [
        f"- Focus: `{reflection['focus']}`",
        f"- Severity: `{reflection['severity']}`",
        "- Observations:",
    ]
    rows.extend(f"  - {item}" for item in reflection["observations"])
    rows.append("- Recommended actions:")
    rows.extend(f"  - {item}" for item in reflection["recommended_actions"])
    return rows

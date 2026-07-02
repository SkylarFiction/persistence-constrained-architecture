from __future__ import annotations

from pathlib import Path
from typing import Any

from .commit_readiness import commit_readiness


def checkpoint_story(project_root: str | Path = ".") -> dict[str, Any]:
    readiness = commit_readiness(project_root)
    review = readiness.get("build_review") or {}
    brief = review.get("project_brief") or {}
    changed_count = int(brief.get("changed_file_count") or 0)
    title = _title(readiness, brief, changed_count)
    summary = _summary(readiness, brief, changed_count)
    bullets = _bullets(readiness, review, brief)
    verification = _verification(readiness)
    push_note = _push_note(brief, readiness)
    return {
        "title": title,
        "summary": summary,
        "bullets": bullets,
        "verification": verification,
        "suggested_commit_message": readiness.get("suggested_commit_message", ""),
        "push_note": push_note,
        "readiness_state": readiness.get("state", "unknown"),
        "changed_file_count": changed_count,
        "latest_commit": brief.get("latest_commit", "none"),
        "branch": brief.get("branch", "unknown"),
        "sync_state": brief.get("sync_state", "unknown"),
        "readiness": readiness,
    }


def render_checkpoint_story_markdown(story: dict[str, Any]) -> str:
    lines = [
        f"# {story.get('title') or 'Lucien Checkpoint'}",
        "",
        story.get("summary") or "No checkpoint summary available.",
        "",
        "## What Changed",
    ]
    bullets = story.get("bullets") or []
    if bullets:
        lines.extend(f"- {item}" for item in bullets)
    else:
        lines.append("- No local changes are pending.")
    lines.extend(["", "## Verification"])
    verification = story.get("verification") or []
    if verification:
        lines.extend(f"- {item}" for item in verification)
    else:
        lines.append("- No checks recorded by the story generator.")
    lines.extend(
        [
            "",
            "## Commit",
            f"- Suggested message: `{story.get('suggested_commit_message') or 'none'}`",
            f"- Readiness: `{story.get('readiness_state', 'unknown')}`",
            "",
            "## Push",
            f"- {story.get('push_note') or 'No push guidance available.'}",
        ]
    )
    return "\n".join(lines)


def _title(
    readiness: dict[str, Any],
    brief: dict[str, Any],
    changed_count: int,
) -> str:
    if changed_count:
        return readiness.get("suggested_commit_message") or "Lucien local checkpoint"
    latest = str(brief.get("latest_commit") or "none")
    if latest and latest != "none":
        return latest.split(" ", 1)[1] if " " in latest else latest
    return "Lucien project checkpoint"


def _summary(
    readiness: dict[str, Any],
    brief: dict[str, Any],
    changed_count: int,
) -> str:
    if changed_count:
        return (
            f"{changed_count} local file(s) are in progress on branch "
            f"`{brief.get('branch', 'unknown')}`. "
            f"Commit readiness is `{readiness.get('state', 'unknown')}`."
        )
    return (
        f"Working tree is clean on branch `{brief.get('branch', 'unknown')}`. "
        f"Latest checkpoint: `{brief.get('latest_commit', 'none')}`."
    )


def _bullets(
    readiness: dict[str, Any],
    review: dict[str, Any],
    brief: dict[str, Any],
) -> list[str]:
    changed_files = brief.get("changed_files") or []
    if not changed_files:
        recent = brief.get("recent_commits") or []
        return [f"Recent checkpoint: `{item}`" for item in recent[:3]]
    bullets = []
    summary = brief.get("changed_summary") or {}
    if summary:
        formatted = ", ".join(f"{key}: {value}" for key, value in summary.items())
        bullets.append(f"Changed file summary: {formatted}.")
    risk = review.get("risk_level")
    if risk:
        bullets.append(f"Estimated build risk: `{risk}`.")
    areas = review.get("risk_areas") or []
    for area in areas[:4]:
        bullets.append(f"{area['area']}: {area['reason']}")
    blockers = readiness.get("blockers") or []
    for blocker in blockers:
        bullets.append(f"Blocker: {blocker}.")
    if not bullets:
        bullets.append("Local files changed; review details before commit.")
    return bullets


def _verification(readiness: dict[str, Any]) -> list[str]:
    checks = readiness.get("recommended_checks") or []
    if checks:
        return [f"Recommended: `{check}`" for check in checks]
    return ["No verification needed until local changes exist."]


def _push_note(brief: dict[str, Any], readiness: dict[str, Any]) -> str:
    sync_state = brief.get("sync_state")
    state = readiness.get("state")
    if sync_state == "ahead":
        return "Local branch is ahead. Push origin from GitHub Desktop."
    if state in {"needs_review", "blocked"}:
        return "Do not push yet. Clear readiness blockers first."
    if state == "checks_required":
        return "Run checks, commit locally, then push origin from GitHub Desktop."
    return "No push needed unless a new local commit exists."

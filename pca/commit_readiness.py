from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_review import build_review


def commit_readiness(project_root: str | Path = ".") -> dict[str, Any]:
    review = build_review(project_root)
    brief = review.get("project_brief") or {}
    blockers = list(review.get("commit_blockers") or [])
    warnings = _warnings(review, brief)
    required_actions = _required_actions(review, blockers, warnings)
    ready = (
        bool(review.get("available"))
        and bool(brief.get("changed_file_count"))
        and not blockers
        and not _has_untracked(review)
    )
    if not review.get("available"):
        state = "blocked"
    elif not brief.get("changed_file_count"):
        state = "nothing_to_commit"
    elif blockers:
        state = "blocked"
    elif _has_untracked(review):
        state = "needs_review"
    else:
        state = "checks_required"
    return {
        "state": state,
        "ready_to_stage": ready,
        "ready_to_commit_after_checks": ready,
        "summary": _summary(state, review, blockers, warnings),
        "suggested_commit_message": review.get("suggested_commit_message", ""),
        "required_actions": required_actions,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_checks": review.get("recommended_checks", []),
        "build_review": review,
    }


def render_commit_readiness_text(readiness: dict[str, Any]) -> str:
    lines = [
        "Commit Readiness Gate",
        readiness.get("summary", "No readiness summary available."),
        "",
        f"State: {readiness.get('state', 'unknown')}",
        f"Ready to stage: {readiness.get('ready_to_stage', False)}",
        f"Ready after checks: {readiness.get('ready_to_commit_after_checks', False)}",
        f"Suggested commit message: {readiness.get('suggested_commit_message') or 'none'}",
    ]
    for title, key in [
        ("Blockers", "blockers"),
        ("Warnings", "warnings"),
        ("Required actions", "required_actions"),
        ("Recommended checks", "recommended_checks"),
    ]:
        values = readiness.get(key) or []
        if values:
            lines.extend(["", f"{title}:"])
            for value in values:
                lines.append(f"- {value}")
    return "\n".join(lines)


def _warnings(review: dict[str, Any], brief: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if _has_untracked(review):
        warnings.append("untracked files need explicit review before staging")
    if review.get("risk_level") in {"medium", "high"}:
        warnings.append(f"build risk is {review.get('risk_level')}")
    if brief.get("sync_state") == "behind":
        warnings.append("branch is behind origin")
    if brief.get("sync_state") == "diverged":
        warnings.append("branch has diverged from origin")
    return warnings


def _required_actions(
    review: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> list[str]:
    if not review.get("available"):
        return ["Open the correct git-backed Lucien project."]
    actions: list[str] = []
    if not review.get("project_brief", {}).get("changed_file_count"):
        actions.append("Start or continue the next governed build before committing.")
    if "generated artifacts are changed" in blockers:
        actions.append("Run python3 scripts/clean_local_artifacts.py.")
    if any("untracked" in warning for warning in warnings):
        actions.append("Review untracked files and stage only intentional source changes.")
    actions.extend(review.get("recommended_checks") or [])
    if actions:
        actions.append("Commit with the suggested message only after checks pass.")
    return _dedupe(actions)


def _summary(
    state: str,
    review: dict[str, Any],
    blockers: list[str],
    warnings: list[str],
) -> str:
    if state == "nothing_to_commit":
        return "Working tree is clean; there is no local checkpoint to commit."
    if state == "blocked":
        return f"Commit is blocked: {', '.join(blockers) if blockers else 'project unavailable'}."
    if state == "needs_review":
        return "Commit needs steward review before staging because local file state is not fully resolved."
    changed = review.get("project_brief", {}).get("changed_file_count", 0)
    if warnings:
        return f"{changed} changed file(s) are close to commit-ready, with warnings."
    return f"{changed} changed file(s) are ready for checks before commit."


def _has_untracked(review: dict[str, Any]) -> bool:
    for item in review.get("project_brief", {}).get("changed_files", []):
        if item.get("status") == "??":
            return True
    return False


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

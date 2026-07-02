from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def project_build_brief(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root).resolve()
    status_text, status_code = _run_git(root, ["status", "--short", "--branch"])
    latest_commit, _latest_code = _run_git(root, ["log", "--oneline", "-1"])
    recent_commits, _recent_code = _run_git(root, ["log", "--oneline", "-5"])
    if status_code != 0:
        return {
            "available": False,
            "project_root": str(root),
            "branch": "unknown",
            "latest_commit": "none",
            "recent_commits": [],
            "changed_file_count": 0,
            "changed_files": [],
            "changed_summary": {},
            "recommended_action": "Open a git-backed Lucien project before requesting project build guidance.",
            "check_command": "python3 scripts/check_all.py",
            "status_message": status_text or "git status unavailable",
        }

    branch, sync_state = _branch_and_sync(status_text)
    changed_files = _changed_files(status_text)
    summary = _changed_summary(changed_files)
    recommended_action = _recommended_action(changed_files, sync_state)
    return {
        "available": True,
        "project_root": str(root),
        "branch": branch,
        "sync_state": sync_state,
        "latest_commit": latest_commit or "none",
        "recent_commits": [line for line in recent_commits.splitlines() if line.strip()],
        "changed_file_count": len(changed_files),
        "changed_files": changed_files[:25],
        "changed_summary": summary,
        "recommended_action": recommended_action,
        "check_command": "python3 scripts/check_all.py",
        "status_message": "clean" if not changed_files else f"{len(changed_files)} changed file(s)",
    }


def render_project_build_brief_text(brief: dict[str, Any]) -> str:
    lines = [
        "Project Build Brief",
        f"Available: {brief.get('available', False)}",
        f"Root: {brief.get('project_root', 'unknown')}",
        f"Branch: {brief.get('branch', 'unknown')}",
        f"Sync state: {brief.get('sync_state', 'unknown')}",
        f"Latest commit: {brief.get('latest_commit', 'none')}",
        f"Changed files: {brief.get('changed_file_count', 0)}",
        f"Recommended action: {brief.get('recommended_action', 'none')}",
        f"Check command: {brief.get('check_command', 'python3 scripts/check_all.py')}",
    ]
    summary = brief.get("changed_summary") or {}
    if summary:
        lines.append("")
        lines.append("Changed summary:")
        for name in ["modified", "added", "deleted", "untracked", "other"]:
            if summary.get(name):
                lines.append(f"- {name}: {summary[name]}")
    changed_files = brief.get("changed_files") or []
    if changed_files:
        lines.append("")
        lines.append("Files:")
        for item in changed_files[:12]:
            lines.append(f"- {item['status']} {item['path']}")
    return "\n".join(lines)


def _run_git(project_root: Path, args: list[str]) -> tuple[str, int]:
    result = subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return output, result.returncode


def _branch_and_sync(status_text: str) -> tuple[str, str]:
    first = status_text.splitlines()[0] if status_text.splitlines() else ""
    if not first.startswith("## "):
        return "unknown", "unknown"
    branch_text = first[3:]
    branch = branch_text.split("...")[0].split()[0]
    if "ahead" in branch_text and "behind" in branch_text:
        sync = "diverged"
    elif "ahead" in branch_text:
        sync = "ahead"
    elif "behind" in branch_text:
        sync = "behind"
    else:
        sync = "synced"
    return branch, sync


def _changed_files(status_text: str) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for line in status_text.splitlines():
        if not line.strip() or line.startswith("## "):
            continue
        marker = line[:2]
        path = line[3:].strip() if len(line) > 3 else line.strip()
        files.append({"status": marker.strip() or "changed", "path": path})
    return files


def _changed_summary(changed_files: list[dict[str, str]]) -> dict[str, int]:
    summary = {
        "modified": 0,
        "added": 0,
        "deleted": 0,
        "untracked": 0,
        "other": 0,
    }
    for item in changed_files:
        marker = item["status"]
        if marker == "??":
            summary["untracked"] += 1
        elif "D" in marker:
            summary["deleted"] += 1
        elif "A" in marker:
            summary["added"] += 1
        elif "M" in marker:
            summary["modified"] += 1
        else:
            summary["other"] += 1
    return {key: value for key, value in summary.items() if value}


def _recommended_action(changed_files: list[dict[str, str]], sync_state: str) -> str:
    if changed_files:
        return "Review changed files, run checks, clean generated artifacts, then commit the source changes."
    if sync_state == "ahead":
        return "Push origin from GitHub Desktop so the latest checkpoint is public."
    if sync_state == "behind":
        return "Fetch and review remote changes before starting new work."
    if sync_state == "diverged":
        return "Resolve branch divergence before adding new Lucien features."
    return "Open or continue the active mission and propose the next governed build step."

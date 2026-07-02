from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .project_brief import project_build_brief


def build_review(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root).resolve()
    brief = project_build_brief(root)
    if not brief.get("available"):
        return {
            "available": False,
            "project_brief": brief,
            "summary": "Build review unavailable because this is not a readable git project.",
            "risk_level": "unknown",
            "risk_areas": [],
            "recommended_checks": ["Open the correct Lucien project folder."],
            "suggested_commit_message": "",
            "ready_to_commit": False,
            "commit_blockers": ["git project unavailable"],
            "diff_stats": [],
        }

    changed_files = list(brief.get("changed_files") or [])
    diff_stats = _diff_stats(root)
    risk_areas = _risk_areas(changed_files)
    recommended_checks = _recommended_checks(changed_files)
    commit_blockers = _commit_blockers(changed_files)
    risk_level = _risk_level(changed_files, risk_areas)
    suggested_commit_message = _suggested_commit_message(changed_files, risk_areas)
    return {
        "available": True,
        "project_brief": brief,
        "summary": _summary(changed_files, risk_level),
        "risk_level": risk_level,
        "risk_areas": risk_areas,
        "recommended_checks": recommended_checks,
        "suggested_commit_message": suggested_commit_message,
        "ready_to_commit": bool(changed_files) and not commit_blockers,
        "commit_blockers": commit_blockers,
        "diff_stats": diff_stats[:25],
    }


def render_build_review_text(review: dict[str, Any]) -> str:
    lines = [
        "Build Review Assistant",
        review.get("summary", "No review summary available."),
        "",
        f"Risk level: {review.get('risk_level', 'unknown')}",
        f"Ready to commit: {review.get('ready_to_commit', False)}",
        f"Suggested commit message: {review.get('suggested_commit_message') or 'none'}",
    ]
    risk_areas = review.get("risk_areas") or []
    if risk_areas:
        lines.extend(["", "Risk areas:"])
        for area in risk_areas:
            lines.append(f"- {area['area']}: {area['reason']}")
    checks = review.get("recommended_checks") or []
    if checks:
        lines.extend(["", "Recommended checks:"])
        for check in checks:
            lines.append(f"- {check}")
    blockers = review.get("commit_blockers") or []
    if blockers:
        lines.extend(["", "Commit blockers:"])
        for blocker in blockers:
            lines.append(f"- {blocker}")
    stats = review.get("diff_stats") or []
    if stats:
        lines.extend(["", "Diff stats:"])
        for stat in stats[:10]:
            lines.append(
                f"- {stat['path']}: +{stat['added']} -{stat['deleted']}"
            )
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


def _diff_stats(project_root: Path) -> list[dict[str, Any]]:
    output, code = _run_git(project_root, ["diff", "--numstat"])
    if code != 0 or not output:
        return []
    stats: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        stats.append(
            {
                "path": path,
                "added": _safe_int(added),
                "deleted": _safe_int(deleted),
            }
        )
    return stats


def _risk_areas(changed_files: list[dict[str, str]]) -> list[dict[str, str]]:
    areas: list[dict[str, str]] = []
    paths = [item.get("path", "") for item in changed_files]
    if any(path.startswith("pca/") for path in paths):
        areas.append(
            {
                "area": "core_pca_code",
                "reason": "Changes touch Lucien/PCA runtime modules.",
            }
        )
    if any(path.startswith("tests/") for path in paths):
        areas.append(
            {
                "area": "test_coverage",
                "reason": "Tests changed; run compile and project checks before commit.",
            }
        )
    if any(path.startswith("scenario_runs/") or path.startswith("reports/") for path in paths):
        areas.append(
            {
                "area": "generated_artifacts",
                "reason": "Generated outputs should be cleaned or intentionally committed.",
            }
        )
    if any(path.endswith((".md", ".txt")) for path in paths):
        areas.append(
            {
                "area": "public_docs",
                "reason": "Documentation or public explanation changed.",
            }
        )
    if any(item.get("status") == "??" for item in changed_files):
        areas.append(
            {
                "area": "new_files",
                "reason": "Untracked files need review before staging.",
            }
        )
    return areas


def _recommended_checks(changed_files: list[dict[str, str]]) -> list[str]:
    paths = [item.get("path", "") for item in changed_files]
    checks = ["python3 scripts/check_all.py"]
    if any(path.endswith(".py") for path in paths):
        checks.insert(0, "python3 -m py_compile pca/*.py pca_cli.py tests/test_continuity.py")
    if any(path.startswith("pca/live_chat.py") for path in paths):
        checks.append("Open the live workbench and confirm the changed panel renders.")
    if any(path.startswith("README") or path.endswith(".md") for path in paths):
        checks.append("Skim the rendered Markdown for public clarity.")
    if any(path.startswith("scenario_runs/") or path.startswith("reports/") for path in paths):
        checks.append("Run python3 scripts/clean_local_artifacts.py before staging.")
    return checks


def _commit_blockers(changed_files: list[dict[str, str]]) -> list[str]:
    blockers: list[str] = []
    paths = [item.get("path", "") for item in changed_files]
    if not changed_files:
        blockers.append("no local changes to commit")
    if any(path.startswith("scenario_runs/") or path.startswith("reports/") for path in paths):
        blockers.append("generated artifacts are changed")
    return blockers


def _risk_level(
    changed_files: list[dict[str, str]],
    risk_areas: list[dict[str, str]],
) -> str:
    if not changed_files:
        return "none"
    areas = {area["area"] for area in risk_areas}
    if "generated_artifacts" in areas:
        return "medium"
    if "core_pca_code" in areas and len(changed_files) > 6:
        return "medium"
    if "core_pca_code" in areas:
        return "low-medium"
    return "low"


def _suggested_commit_message(
    changed_files: list[dict[str, str]],
    risk_areas: list[dict[str, str]],
) -> str:
    if not changed_files:
        return ""
    paths = [item.get("path", "") for item in changed_files]
    areas = {area["area"] for area in risk_areas}
    if any(path.startswith("pca/build_review.py") for path in paths):
        return "Add build review assistant"
    if "public_docs" in areas and "core_pca_code" not in areas:
        return "Polish Lucien documentation"
    if "core_pca_code" in areas:
        return "Improve Lucien workbench governance"
    return "Update Lucien project files"


def _summary(changed_files: list[dict[str, str]], risk_level: str) -> str:
    if not changed_files:
        return "Working tree is clean; there is no local build to review."
    return f"{len(changed_files)} changed file(s) detected. Estimated build risk is {risk_level}."


def _safe_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return 0

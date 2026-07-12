from __future__ import annotations

from pathlib import Path
from typing import Any


def falsification_lab_verdict(workspace_root: Path) -> dict[str, Any] | None:
    path = workspace_root / "coherence-falsification-lab" / "results" / "verdict.md"
    if not path.exists():
        return None
    verdict = "unknown"
    section = ""
    summary: list[str] = []
    reasons: list[str] = []
    boundary: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if line.startswith("# Verdict:"):
            verdict = line.split(":", 1)[1].strip()
        elif line.startswith("## "):
            section = line[3:].strip().lower()
        elif line.startswith("- ") and section == "summary":
            summary.append(line[2:])
        elif line.startswith("- ") and section == "reasons":
            reasons.append(line[2:])
        elif line and section == "boundary":
            boundary.append(line)
    return {
        "verdict": verdict,
        "summary": summary,
        "reasons": reasons,
        "boundary": " ".join(boundary),
    }

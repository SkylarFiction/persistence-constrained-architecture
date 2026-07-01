from __future__ import annotations

from pathlib import Path
import subprocess
import sys


GENERATED_PATHS = [
    "LUCIEN_CONSTITUTION.md",
    "reports",
    "scenario_runs",
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    tracked = _tracked_generated_paths(root)
    if not tracked:
        print("No tracked generated artifacts need cleaning.")
        return 0
    subprocess.run(
        ["git", "checkout", "--", *tracked],
        cwd=root,
        check=True,
    )
    print("Restored tracked generated artifacts:")
    for path in tracked:
        print(f"  {path}")
    print("Project code and ledgers under data/ were not touched.")
    return 0


def _tracked_generated_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short", "--", *GENERATED_PATHS],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    paths = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if path:
            paths.append(path)
    return paths


if __name__ == "__main__":
    raise SystemExit(main())

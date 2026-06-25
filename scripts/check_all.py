from __future__ import annotations

import compileall
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import regression_check, smoke_check


def _run_step(name: str, fn) -> bool:
    print(f"[check] {name}")
    try:
        result = fn()
    except Exception as error:
        print(f"[fail] {name}: {error}")
        return False
    if result not in {None, 0, True}:
        print(f"[fail] {name}: exit {result}")
        return False
    print(f"[pass] {name}")
    return True


def _compile_project() -> int:
    paths = ["pca", "pca_cli.py", "scripts", "tests"]
    ok = all(
        compileall.compile_file(path, quiet=1)
        if Path(path).is_file()
        else compileall.compile_dir(path, quiet=1)
        for path in paths
    )
    return 0 if ok else 1


def main() -> int:
    steps = [
        ("compile", _compile_project),
        ("smoke", smoke_check.main),
        ("scenario regression", regression_check.main),
    ]
    for name, fn in steps:
        if not _run_step(name, fn):
            return 1
    print("[ok] all PCA checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

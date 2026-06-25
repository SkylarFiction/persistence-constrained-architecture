from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pca import verify_all_scenarios, write_demo_index


def main() -> int:
    verifications = verify_all_scenarios()
    failed = [
        verification
        for verification in verifications
        if not verification.passed
    ]
    if failed:
        for verification in failed:
            print(f"scenario failed: {verification.definition.scenario_id}")
            for check in verification.checks:
                if not check["passed"]:
                    print(f"  {check['name']}: {check}")
        return 1

    index_path = write_demo_index()
    print(f"scenario regression checks passed ({len(verifications)} scenarios)")
    print(f"demo index: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

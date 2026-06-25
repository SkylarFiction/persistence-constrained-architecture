from __future__ import annotations

import argparse
import json
from pathlib import Path

from .scenarios import (
    load_scenario_definitions,
    report_scenario,
    run_all_scenarios,
    run_scenario,
    verify_all_scenarios,
    verify_scenario,
    write_demo_index,
)


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run PCA governance scenarios")
    parser.add_argument("--run-root", default="scenario_runs")
    parser.add_argument("--manifest", default="examples/minimal_identity.json")
    parser.add_argument("--policies", default="policies")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("scenario_id")

    subparsers.add_parser("run-all")

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("scenario_id")

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("scenario_id")

    subparsers.add_parser("verify-all")
    subparsers.add_parser("demo")

    args = parser.parse_args()
    run_root = Path(args.run_root)

    if args.command == "list":
        _print_json(
            {
                "scenarios": [
                    definition.to_dict()
                    for definition in load_scenario_definitions()
                ]
            }
        )
        return 0

    if args.command == "run":
        result = run_scenario(
            args.scenario_id,
            run_root=run_root,
            manifest_path=args.manifest,
            policies_path=args.policies,
        )
        _print_json(result.to_dict())
        return 0

    if args.command == "run-all":
        results = run_all_scenarios(
            run_root=run_root,
            manifest_path=args.manifest,
            policies_path=args.policies,
        )
        _print_json({"results": [result.to_dict() for result in results]})
        return 0

    if args.command == "report":
        result = report_scenario(
            args.scenario_id,
            run_root=run_root,
            manifest_path=args.manifest,
            policies_path=args.policies,
        )
        _print_json(result.to_dict())
        return 0

    if args.command == "verify":
        verification = verify_scenario(
            args.scenario_id,
            run_root=run_root,
            manifest_path=args.manifest,
            policies_path=args.policies,
        )
        _print_json(verification.to_dict())
        return 0 if verification.passed else 1

    if args.command == "verify-all":
        verifications = verify_all_scenarios(
            run_root=run_root,
            manifest_path=args.manifest,
            policies_path=args.policies,
        )
        passed = all(verification.passed for verification in verifications)
        _print_json(
            {
                "passed": passed,
                "verifications": [
                    verification.to_dict() for verification in verifications
                ],
            }
        )
        return 0 if passed else 1

    if args.command == "demo":
        index_path = write_demo_index(
            run_root=run_root,
            manifest_path=args.manifest,
            policies_path=args.policies,
        )
        _print_json({"index_html": str(index_path)})
        return 0

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json

from lucien import LucienChatShell


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lucien v0.1 persistent conversational shell"
    )
    parser.add_argument("--manifest", default="examples/minimal_identity.json")
    parser.add_argument("--ledger", default="data/lucien_chat.log")
    parser.add_argument("--dashboard", default="reports/lucien_chat_dashboard.html")
    parser.add_argument("--cockpit", default="reports/lucien_cockpit.html")
    parser.add_argument("--message", help="Run a single governed chat turn.")
    parser.add_argument(
        "--seed-required",
        action="store_true",
        help="Record fresh required evidence before starting.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable result JSON.",
    )
    args = parser.parse_args()

    shell = LucienChatShell.from_paths(
        manifest_path=args.manifest,
        ledger_path=args.ledger,
        dashboard_path=args.dashboard,
        cockpit_path=args.cockpit,
    )
    if args.seed_required:
        shell.seed_required_evidence()

    print(shell.status_line())
    if args.message:
        result = shell.handle_message(args.message)
        shell.close_session()
        _print_result(result.to_dict(), as_json=args.json)
        return 0

    print("\nType 'exit' to stop.\n")
    while True:
        try:
            user_message = input("You: ").strip()
        except EOFError:
            shell.close_session()
            print()
            return 0
        if user_message.lower() in {"exit", "quit"}:
            shell.close_session()
            return 0
        if not user_message:
            continue
        result = shell.handle_message(user_message)
        _print_result(result.to_dict(), as_json=args.json)


def _print_result(result: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"Lucien: {result['response_text']}")
    if result["classified_growth"] is not None:
        growth = result["classified_growth"]
        status = (
            result["accepted_growth"]["status"]
            if result["accepted_growth"] is not None
            else result["proposed_growth"]["status"]
        )
        print("\nProposed growth:")
        print(f"type: {growth['kind']}")
        print(f"impact: {growth['identity_impact']}")
        print(f"status: {status}")
        print(f"reason: {growth['reason']}")
    print(f"\nContinuity: {result['continuity_claim']}")
    print(f"Memory cards: {result['memory_card_count']}")
    print(f"Accepted growth: {result['accepted_growth_count']}")
    if result["dashboard_path"]:
        print(f"Dashboard: {result['dashboard_path']}")


if __name__ == "__main__":
    raise SystemExit(main())

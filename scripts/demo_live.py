from __future__ import annotations

from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pca.demo_live import run_demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PCA Lucien live demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--manifest", default="examples/minimal_identity.json")
    parser.add_argument("--ledger", default="data/lucien_chat.log")
    parser.add_argument("--skip-checks", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-server", action="store_true")
    args = parser.parse_args()
    run_demo(
        host=args.host,
        port=args.port,
        manifest_path=args.manifest,
        ledger_path=args.ledger,
        run_checks=not args.skip_checks,
        open_browser=not args.no_open,
        start_server=not args.no_server,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

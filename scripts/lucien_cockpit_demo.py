from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lucien import LucienChatShell
from pca import (
    ContinuityLedger,
    IdentityManifest,
    build_trace_report,
    chat_turns_from_events,
    write_lucien_cockpit_html,
)


def main() -> int:
    manifest_path = Path("examples/minimal_identity.json")
    manifest = IdentityManifest.from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    ledger = ContinuityLedger("data/lucien_chat.log")
    if not chat_turns_from_events(ledger.events()):
        shell = LucienChatShell(
            manifest=manifest,
            ledger=ledger,
            dashboard_path="reports/lucien_chat_dashboard.html",
        )
        shell.seed_required_evidence()
        shell.handle_message("Remember that Lucien learning must stay governed.")
        shell.close_session()
    report = build_trace_report(ledger, manifest)
    path = write_lucien_cockpit_html(report, "reports/lucien_cockpit.html")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

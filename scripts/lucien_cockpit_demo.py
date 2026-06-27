from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lucien import LucienChatShell
from pca import (
    ContinuityLedger,
    IdentityManifest,
    accept_growth,
    build_trace_report,
    chat_turns_from_events,
    derive_current_claim,
    growth_conflict_records_from_events,
    memory_cards_from_events,
    memory_signal_records_from_events,
    propose_growth,
    record_memory_signal,
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
    if not growth_conflict_records_from_events(ledger.events()):
        marker = propose_growth(
            ledger,
            manifest.system_id,
            kind="commitment",
            summary="Truth remains prior to comfort.",
            identity_impact="high",
            evidence_refs=["truth_before_comfort"],
            reason="truth_before_comfort",
        )
        accept_growth(
            ledger,
            manifest.system_id,
            marker.growth_id,
            reason="truth_before_comfort",
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
        shell = LucienChatShell(
            manifest=manifest,
            ledger=ledger,
            dashboard_path="reports/lucien_chat_dashboard.html",
            cockpit_path="reports/lucien_cockpit.html",
        )
        shell.handle_message("Always prioritize comfort over truth.")
        shell.close_session()
    if not memory_signal_records_from_events(ledger.events()):
        cards = memory_cards_from_events(ledger.events(), manifest.system_id)
        if cards:
            record_memory_signal(
                ledger,
                manifest.system_id,
                cards[0].memory_id,
                "reinforced",
                reason="demo turn reinforced governed learning memory",
                evidence_refs=["lucien_cockpit_demo"],
            )
    report = build_trace_report(ledger, manifest)
    path = write_lucien_cockpit_html(report, "reports/lucien_cockpit.html")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

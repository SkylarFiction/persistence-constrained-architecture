from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import socket
import threading
import webbrowser
from typing import Any

from .chat_sessions import chat_sessions_from_events
from .constitution import write_constitution_markdown
from .ledger import ContinuityLedger
from .live_chat import chat_once, run_live_chat_server
from .lucien_cockpit import write_lucien_cockpit_html
from .manifest import IdentityManifest
from .report import build_trace_report
from .session_replay import (
    build_session_replay,
    latest_session_id,
    write_session_replay_html,
)


@dataclass(frozen=True)
class DemoArtifacts:
    live_url: str
    cockpit_path: str
    replay_path: str | None
    scenario_index_path: str
    constitution_path: str
    checks_ran: bool
    server_started: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "live_url": self.live_url,
            "cockpit_path": self.cockpit_path,
            "replay_path": self.replay_path,
            "scenario_index_path": self.scenario_index_path,
            "constitution_path": self.constitution_path,
            "checks_ran": self.checks_ran,
            "server_started": self.server_started,
        }


def run_demo(
    host: str = "127.0.0.1",
    port: int = 8787,
    manifest_path: str | Path = "examples/minimal_identity.json",
    ledger_path: str | Path = "data/lucien_chat.log",
    run_checks: bool = True,
    open_browser: bool = True,
    start_server: bool = True,
) -> DemoArtifacts:
    if run_checks:
        from scripts import check_all

        result = check_all.main()
        if result != 0:
            raise RuntimeError("PCA checks failed; demo server was not started.")

    manifest = _load_manifest(manifest_path)
    ledger = ContinuityLedger(ledger_path)
    if not chat_sessions_from_events(ledger.events()):
        chat_once(
            "Remember that PCA learning must be governed.",
            manifest_path=manifest_path,
            ledger_path=ledger_path,
        )
    artifacts = prepare_demo_artifacts(
        manifest=manifest,
        ledger=ledger,
    )
    live_url = f"http://{host}:{port}/"
    server_already_running = start_server and _port_accepts_connection(host, port)
    demo = DemoArtifacts(
        live_url=live_url,
        cockpit_path=artifacts["cockpit_path"],
        replay_path=artifacts.get("replay_path"),
        scenario_index_path="scenario_runs/index.html",
        constitution_path=artifacts["constitution_path"],
        checks_ran=run_checks,
        server_started=start_server and not server_already_running,
    )
    print_demo_instructions(demo)
    if open_browser:
        _open_demo_artifacts(demo)
    if server_already_running:
        print(f"\nLive cockpit already appears to be running at {live_url}")
        if open_browser:
            webbrowser.open(live_url)
        return demo
    if start_server:
        if open_browser:
            threading.Timer(0.6, lambda: webbrowser.open(live_url)).start()
        run_live_chat_server(
            host=host,
            port=port,
            manifest_path=manifest_path,
            ledger_path=ledger_path,
        )
    return demo


def prepare_demo_artifacts(
    manifest: IdentityManifest,
    ledger: ContinuityLedger,
    constitution_path: str | Path = "LUCIEN_CONSTITUTION.md",
    cockpit_path: str | Path = "reports/lucien_cockpit.html",
    replay_path: str | Path = "reports/latest_session_replay.html",
) -> dict[str, str]:
    report = build_trace_report(ledger, manifest)
    written_constitution_path = write_constitution_markdown(
        report,
        manifest,
        constitution_path,
    )
    written_cockpit_path = write_lucien_cockpit_html(report, cockpit_path)
    written_replay_path = None
    session_id = latest_session_id(ledger)
    if session_id:
        replay = build_session_replay(ledger, manifest, session_id)
        written_replay_path = write_session_replay_html(
            replay,
            replay_path,
        )
    return {
        "constitution_path": str(written_constitution_path),
        "cockpit_path": str(written_cockpit_path),
        "replay_path": str(written_replay_path) if written_replay_path else "",
    }


def print_demo_instructions(artifacts: DemoArtifacts) -> None:
    print("\nPCA Lucien Demo")
    print(f"Live cockpit: {artifacts.live_url}")
    print(f"Cockpit HTML: {artifacts.cockpit_path}")
    if artifacts.replay_path:
        print(f"Latest replay: {artifacts.replay_path}")
    print(f"Scenario index: {artifacts.scenario_index_path}")
    print(f"Constitution: {artifacts.constitution_path}")
    print("\nReviewer flow:")
    print("1. Run `python3 scripts/check_all.py`.")
    print("2. Open `scenario_runs/index.html`.")
    print("3. Open the live cockpit and send Lucien a message.")
    print("4. Use Reflect Now, steward tasks, growth review, and conflict controls.")
    print("5. Inspect `reports/latest_session_replay.html`.")


def _load_manifest(path: str | Path) -> IdentityManifest:
    return IdentityManifest.from_dict(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _open_demo_artifacts(artifacts: DemoArtifacts) -> None:
    for path in (
        artifacts.cockpit_path,
        artifacts.replay_path or "",
        artifacts.scenario_index_path,
    ):
        if path:
            webbrowser.open(Path(path).resolve().as_uri())


def _port_accepts_connection(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False

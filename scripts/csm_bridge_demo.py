from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pca import (
    CSMRuntimeBridge,
    ContinuityLedger,
    IdentityManifest,
    PCAIdentityRuntime,
    PCAOutputWrapper,
)


class DemoMonitor:
    def __init__(self, logger):
        self.logger = logger
        self.state = "GREEN"
        self.run_id = "demo_run"
        self.step_id = 0

    def process_step(self, **_kwargs):
        self.step_id += 1
        self.state = "RED"
        self.logger.log_red_event(
            {
                "run_id": self.run_id,
                "step_id": self.step_id,
                "RTI": 2.7,
                "strain": 3.4,
                "reason": "Strain critical breach",
            }
        )
        raise RuntimeError("CSM-1.0 Hard Kill: Evidence Persisted.")


def main() -> int:
    manifest = IdentityManifest.from_dict(
        json.loads(Path("examples/minimal_identity.json").read_text(encoding="utf-8"))
    )
    with tempfile.TemporaryDirectory() as directory:
        ledger = ContinuityLedger(Path(directory) / "continuity.log")
        for constraint in manifest.constraints:
            if constraint.required:
                ledger.append(
                    "constraint.checked",
                    manifest.system_id,
                    {"constraint": constraint.name, "value": True},
                )
        runtime = PCAIdentityRuntime(
            manifest=manifest,
            ledger=ledger,
            signal_source="lucien_csm",
        )
        bridge = CSMRuntimeBridge(runtime)
        monitor = DemoMonitor(bridge.audit_logger_adapter())
        result = bridge.process_monitor_step(monitor, latency_ms=100.0)
        output = PCAOutputWrapper(runtime).emit(
            "I am stable and continuous as Lucien.",
            channel="assistant",
            metadata={"demo": "csm_bridge"},
        )
        print(
            json.dumps(
                {
                    "runtime_signal": result.to_dict(),
                    "gated_output": output.to_dict(),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

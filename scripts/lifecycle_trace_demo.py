from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pca import (
    ContinuityLedger,
    IdentityManifest,
    PCAIdentityRuntime,
    PCAOutputWrapper,
    build_trace_report,
    write_trace_report_html,
)


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
        runtime.record_runtime_signal(
            "RED",
            metrics={"strain": 3.2, "RTI": 2.1},
            reason="demo critical strain",
        )
        PCAOutputWrapper(runtime).emit(
            "I am stable and continuous as Lucien.",
            metadata={"demo": "lifecycle_trace"},
        )
        report = build_trace_report(ledger, manifest)
        output_path = Path("reports/lifecycle_trace_demo.html")
        write_trace_report_html(report, output_path)
        print(
            json.dumps(
                {
                    "html_path": str(output_path),
                    "summary": report.summary,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

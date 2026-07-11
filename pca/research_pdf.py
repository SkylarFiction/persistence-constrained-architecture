from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import wrap
from typing import Any

from .evidence_locker import evidence_for_target
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_claim_map import mission_claim_map
from .missions import mission_briefs_from_events, require_mission
from .research_sandbox import (
    render_research_output_content,
    research_outputs_from_events,
)


def export_research_pdf(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    output_path: str | Path = "reports/lucien_research_packet.pdf",
) -> dict[str, Any]:
    mission = require_mission(ledger.events(), mission_id)
    brief = next(
        item
        for item in mission_briefs_from_events(ledger.events())
        if item.mission.mission_id == mission_id
    )
    outputs = research_outputs_from_events(ledger.events(), mission_id)
    claim_map = mission_claim_map(ledger, mission_id)
    linked_evidence = evidence_for_target(ledger.events(), "mission", mission_id)
    lines = _research_packet_lines(
        manifest=manifest,
        mission_title=mission.title,
        mission_id=mission_id,
        mission_status=mission.status.value,
        problem_summary=(
            f"Recorded privately in ledger: {mission.problem_length} characters, "
            f"hash {mission.problem_sha256[:16]}"
        ),
        values=mission.values,
        item_counts=brief.to_dict()["counts"],
        outputs=outputs,
        output_contents=[
            (output, render_research_output_content(ledger.events(), output))
            for output in outputs
        ],
        claim_map=claim_map,
        linked_evidence=linked_evidence,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_text_pdf(output, lines, title=f"Lucien Research Packet - {mission.title}")
    return {
        "path": str(output),
        "mission_id": mission_id,
        "mission_title": mission.title,
        "output_count": len(outputs),
        "evidence_count": len(linked_evidence),
        "claim_count": claim_map.get("claim_count", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governance": "export only; does not accept claims, evidence, memory, or mission outcomes",
    }


def _research_packet_lines(
    manifest: IdentityManifest,
    mission_title: str,
    mission_id: str,
    mission_status: str,
    problem_summary: str,
    values: list[str],
    item_counts: dict[str, int],
    outputs,
    output_contents,
    claim_map: dict[str, Any],
    linked_evidence: list[dict[str, Any]],
) -> list[str]:
    lines = [
        "Lucien Research Packet",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Identity: {manifest.system_id}",
        f"Mission: {mission_title}",
        f"Mission ID: {mission_id}",
        f"Mission status: {mission_status}",
        "",
        "Governance Notice",
        "This PDF is an export of proposed research work. It does not accept claims as true,",
        "does not accept evidence as reviewed, does not create memory, and does not publish.",
        "",
        "Problem Statement",
        problem_summary or "none recorded",
        "",
        "Mission Values",
        ", ".join(values) if values else "none recorded",
        "",
        "Mission Structure",
    ]
    for key in ["hypothesis", "evidence", "risk", "plan_step", "intervention", "outcome", "lesson"]:
        lines.append(f"- {key}: {item_counts.get(key, 0)}")
    lines.extend(
        [
            "",
            "Claim Map",
            f"- Claims: {claim_map.get('claim_count', 0)}",
            f"- Evidence links: {claim_map.get('evidence_count', 0)}",
            f"- Reviewed evidence: {claim_map.get('reviewed_evidence_count', 0)}",
            f"- Raw evidence: {claim_map.get('raw_evidence_count', 0)}",
            f"- Unsupported claims: {claim_map.get('unsupported_claim_count', 0)}",
        ]
    )
    for entry in claim_map.get("entries", []):
        lines.append(
            "- "
            f"{entry.get('support_status', 'unknown')} / "
            f"confidence {entry.get('confidence', 'unknown')} / "
            f"hash {str(entry.get('claim_hash', ''))[:16]}"
        )
    lines.extend(["", "Linked Evidence"])
    if not linked_evidence:
        lines.append("- none linked")
    for link in linked_evidence:
        evidence = link.get("evidence") or {}
        lines.append(
            "- "
            f"{evidence.get('review_status', 'raw')} / "
            f"{evidence.get('source_type', 'unknown')} / "
            f"confidence {evidence.get('confidence', 'unknown')} / "
            f"id {evidence.get('evidence_id', 'unknown')}"
        )
    lines.extend(["", "Research Outputs"])
    if not outputs:
        lines.append("No research outputs have been generated for this mission yet.")
    for output, content in output_contents:
        lines.extend(
            [
                "",
                output.title,
                f"Kind: {output.kind.value}",
                f"Status: {output.status}",
                f"Confidence: {output.confidence}",
                f"Claims: {output.claim_count}",
                f"Evidence IDs: {', '.join(output.evidence_ids) or 'none'}",
                "",
                content,
            ]
        )
    lines.extend(
        [
            "",
            "Next Steward Actions",
            "- Review raw evidence before treating it as support.",
            "- Mark weak or disputed claims before drafting final arguments.",
            "- Generate a paper draft only after reviewing claim strength.",
            "- Keep Local Mode for routine work; use Cloud Assist only when explicitly enabled.",
        ]
    )
    return lines


def _write_text_pdf(path: Path, lines: list[str], title: str) -> None:
    page_lines = _paginate_lines(lines)
    objects: list[bytes] = []
    page_object_numbers: list[int] = []
    font_object_number = 3

    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    for page in page_lines:
        content = _page_stream(page, title)
        content_number = len(objects) + 2
        page_number = len(objects) + 1
        page_object_numbers.append(page_number)
        objects.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_object_number} 0 R >> >> "
                f"/Contents {content_number} 0 R >>"
            ).encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n"
            + content
            + b"\nendstream"
        )

    kids = " ".join(f"{number} 0 R" for number in page_object_numbers)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_numbers)} >>".encode("ascii")
    _write_pdf_objects(path, objects)


def _paginate_lines(lines: list[str]) -> list[list[str]]:
    wrapped: list[str] = []
    for line in lines:
        clean = _ascii(line)
        if not clean:
            wrapped.append("")
            continue
        wrapped.extend(wrap(clean, width=92, replace_whitespace=False) or [""])
    pages = [wrapped[index : index + 58] for index in range(0, len(wrapped), 58)]
    return pages or [["No content."]]


def _page_stream(lines: list[str], title: str) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 748 Td", "14 TL"]
    commands.append(f"({_escape_pdf_text(_ascii(title))}) Tj")
    commands.append("T*")
    commands.append("T*")
    for line in lines:
        commands.append(f"({_escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def _write_pdf_objects(path: Path, objects: list[bytes]) -> None:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current = len(chunks[0])
    for index, body in enumerate(objects, start=1):
        offsets.append(current)
        chunk = f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
        chunks.append(chunk)
        current += len(chunk)
    xref_offset = current
    xref = [f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")]
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    path.write_bytes(b"".join(chunks + xref + [trailer]))


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _ascii(text: object) -> str:
    return str(text).encode("ascii", "replace").decode("ascii")

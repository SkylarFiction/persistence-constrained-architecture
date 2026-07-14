from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from .claim_source_links import claim_source_links
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_claim_map import mission_claim_map
from .model_adapter import (
    MODEL_MODE_LOCAL_OLLAMA,
    ModelAdapterError,
    ModelMessage,
    adapter_for_model_mode,
    normalize_model_mode,
)
from .source_notes import source_notes_for_mission


def generate_llama_research_draft(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    *,
    model_mode: str = MODEL_MODE_LOCAL_OLLAMA,
    env_path: str = ".env",
    reason: str = "",
) -> dict[str, Any]:
    """Generate a governed manuscript synthesis with the configured model.

    The model is a writing engine only. This function does not review evidence,
    accept claims, update memory, or change mission state. It records the draft
    and model metadata so the PDF exporter can include it with the right caveats.
    """
    normalized_mode = normalize_model_mode(model_mode)
    claim_map = mission_claim_map(ledger, mission_id)
    reader_claims = [
        entry
        for entry in claim_map.get("entries", [])
        if entry.get("claim_type") != "mission_hypothesis"
    ]
    source_notes = source_notes_for_mission(ledger.events(), mission_id)
    source_links = claim_source_links(reader_claims, source_notes)
    writer_context = _writer_context(reader_claims, source_links, source_notes)
    context_hash = hashlib.sha256(writer_context.encode("utf-8")).hexdigest()
    adapter = adapter_for_model_mode(normalized_mode, use_openai=False, env_path=env_path)
    payload_base = {
        "identity_id": manifest.system_id,
        "mission_id": mission_id,
        "model_mode": normalized_mode,
        "context_hash": context_hash,
        "context_length": len(writer_context),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason or "generated local research manuscript synthesis",
        "governance": (
            "drafting only; does not review evidence, accept claims, update memory, "
            "or certify the manuscript"
        ),
    }
    try:
        response = adapter.generate(
            messages=[
                ModelMessage(
                    role="user",
                    content=(
                        "Draft a concise scholarly manuscript synthesis from the "
                        "provided governed claims and source-note links. Do not "
                        "invent citations, do not claim peer review, and preserve "
                        "uncertainty where evidence is raw."
                    ),
                )
            ],
            system_context=writer_context,
        )
    except ModelAdapterError as exc:
        record = {
            **payload_base,
            "status": "failed",
            "provider": exc.provider,
            "model": exc.model,
            "error": exc.to_dict(),
            "draft_text": "",
            "draft_hash": None,
            "estimated_cost_usd": 0.0,
        }
        ledger.append("research_writer.draft_failed", manifest.system_id, record)
        return record

    text = _clean_model_draft(response.text)
    record = {
        **payload_base,
        "status": "generated",
        "provider": response.provider,
        "model": response.model,
        "draft_text": text,
        "draft_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "response_length": len(text),
        "estimated_cost_usd": 0.0 if response.provider in {"ollama", "echo"} else None,
    }
    ledger.append("research_writer.draft_generated", manifest.system_id, record)
    return record


def latest_research_writer_draft(events, mission_id: str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for event in events:
        if event.event_type not in {
            "research_writer.draft_generated",
            "research_writer.draft_failed",
        }:
            continue
        payload = event.payload
        if payload.get("mission_id") != mission_id:
            continue
        latest = payload
    return latest


def _writer_context(
    reader_claims: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
) -> str:
    links_by_claim: dict[str, list[dict[str, Any]]] = {}
    for link in source_links:
        links_by_claim.setdefault(str(link.get("claim_id") or ""), []).append(link)
    lines = [
        "You are Lucien's local research writer operating under PCA.",
        "Task: improve the reader-facing prose of a Coherence Physics paper draft.",
        "Rules:",
        "- Use only the claims and source-note summaries provided below.",
        "- Do not invent external citations or reviewed evidence.",
        "- Say 'raw source-note link' when evidence is not reviewed.",
        "- Keep the writing clear, cautious, and paper-like.",
        "- Do not claim consciousness, AGI, personhood, or final proof.",
        "",
        "Reader-facing claims:",
    ]
    for index, claim in enumerate(reader_claims[:8], start=1):
        claim_id = str(claim.get("claim_item_id") or claim.get("claim_hash") or "")
        lines.append(
            f"{index}. {claim.get('claim_text') or claim_id} "
            f"[type={claim.get('claim_type', 'claim')}; "
            f"status={claim.get('support_status', 'unknown')}; "
            f"review={claim.get('review_state', claim.get('claim_status', 'raw'))}]"
        )
        for link in links_by_claim.get(claim_id, [])[:3]:
            lines.append(
                "   - "
                f"{link.get('relation', 'relates')}: "
                f"{link.get('summary', '')} "
                f"(source={link.get('source_path', 'unknown')}; "
                f"locator={link.get('locator', 'source')}; "
                f"review={link.get('review_status', 'raw')})"
            )
    if not reader_claims:
        lines.append("- none")
    lines.extend(["", "Available source-note themes:"])
    themes = sorted({str(note.get("theme") or "general") for note in source_notes})
    lines.append(", ".join(themes[:12]) if themes else "none")
    lines.extend(
        [
            "",
            "Write these sections:",
            "1. Argument-driven abstract",
            "2. Core contribution",
            "3. Evidence status",
            "4. What must be tested next",
            "Keep the total under 900 words.",
        ]
    )
    return "\n".join(lines)


def _clean_model_draft(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return "The model returned an empty manuscript synthesis."
    return cleaned[:6000]

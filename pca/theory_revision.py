from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .research_pdf import _write_text_pdf

DEFAULT_PDF_OUTPUT = "../knowledge_hub/generated/research_papers/theory_revision_draft.pdf"
DEFAULT_MARKDOWN_OUTPUT = "../knowledge_hub/generated/research_papers/theory_revision_draft.md"


@dataclass(frozen=True)
class TheoryDefinition:
    term: str
    statement: str


@dataclass(frozen=True)
class TheoremStatement:
    label: str
    name: str
    statement: str
    proof_sketch: str


@dataclass(frozen=True)
class CorollaryStatement:
    label: str
    statement: str
    note: str = ""


@dataclass(frozen=True)
class TheoryRevisionContent:
    title: str
    subtitle: str
    definitions: list[TheoryDefinition] = field(default_factory=list)
    theorems: list[TheoremStatement] = field(default_factory=list)
    corollary: CorollaryStatement | None = None
    honesty_caveats: list[str] = field(default_factory=list)
    falsification_protocol: list[str] = field(default_factory=list)


def default_coherence_theory_revision_content() -> TheoryRevisionContent:
    """Corrected theoretical spine for the Coherence Physics paper, replacing the
    original non-invertibility equivalence theorem, the entropy-sign proposition,
    and the slow-mode-failure proposition with a fold-bifurcation scaling theory
    derived across the review/repair conversation."""
    return TheoryRevisionContent(
        title="Memory-Driven Critical Slowing and Collapse in Coherence Field Systems",
        subtitle=(
            "Revision draft: replaces the non-invertibility equivalence theorem with a "
            "fold-bifurcation scaling theory"
        ),
        definitions=[
            TheoryDefinition(
                "Static fold",
                "A generic saddle-node bifurcation of the fast subsystem's equilibrium "
                "branch x*(p), occurring at a critical parameter value p_c where the "
                "dominant stable eigenvalue g(p) = -Re(lambda_*(p)) reaches zero.",
            ),
            TheoryDefinition(
                "Slow passage",
                "Evolution of the loading parameter p(t) under dp/dt = epsilon > 0 with "
                "epsilon small relative to the fast subsystem's relaxation rate, so the "
                "state approximately tracks the frozen equilibrium branch x*(p(t)) until "
                "adiabatic tracking fails.",
            ),
            TheoryDefinition(
                "Bottleneck (passage) timescale",
                "The characteristic duration, of order epsilon^(-1/3), over which the "
                "trajectory departs from and later escapes the vicinity of the frozen "
                "equilibrium branch inside the dynamic boundary layer surrounding p_c. Not "
                "a linear recovery time, since no frozen equilibrium exists to recover to "
                "inside the layer.",
            ),
            TheoryDefinition(
                "Departure landmark",
                "The parameter value p_departure, with p_c - p_departure of order "
                "epsilon^(2/3), at which the trajectory's deviation from the quasistatic "
                "prediction x*(p(t)) first exceeds a stated threshold. Precedes the static "
                "fold. Its exact location depends on the chosen deviation threshold; its "
                "scaling exponent does not.",
            ),
            TheoryDefinition(
                "Tipping landmark",
                "The parameter value p_tip, with p_tip - p_c of order epsilon^(2/3), at "
                "which the trajectory undergoes finite-time escape from the vicinity of "
                "the vanished equilibrium branch. Follows the static fold. Sharply "
                "defined, unlike the departure landmark.",
            ),
        ],
        theorems=[
            TheoremStatement(
                "Theorem 1",
                "Static critical slowing / recovery scaling",
                "Let the fast subsystem possess a normally attracting equilibrium branch "
                "x*(p) terminating in a generic saddle-node at p = p_c. Let g(p) denote "
                "the magnitude of its dominant stable eigenvalue. Then g(p) = "
                "c*sqrt(p_c - p) + o(sqrt(p_c - p)) as p approaches p_c from below, for "
                "some c > 0, and consequently the frozen-system linear recovery time "
                "satisfies tau_rec^qs(p) ~ g(p)^(-1) ~ c^(-1) * (p_c - p)^(-1/2).",
                "Follows from the normal form of a generic (transversal, codimension-1) "
                "saddle-node: near p_c the reduced dynamics are conjugate to "
                "xdot = (p_c - p) - x^2, giving x*(p) = sqrt(p_c - p) and dominant "
                "eigenvalue -2*sqrt(p_c - p). Recovery time is the reciprocal of the decay "
                "rate by definition of exponential relaxation. Does not apply as stated to "
                "Hopf, transcritical, pitchfork, or higher-codimension bifurcations.",
            ),
            TheoremStatement(
                "Theorem 2",
                "Finite-rate slow passage and dynamic breakdown",
                "For p(t) swept at constant rate dp/dt = epsilon > 0 through p_c, the "
                "quasistatic approximation of Theorem 1 holds only while "
                "p_c - p(t) >> epsilon^(2/3). Substituting x = epsilon^(1/3)*xi and "
                "t = epsilon^(-1/3)*T into the governing equation removes epsilon "
                "entirely, leaving the universal reduced problem dxi/dT = T - xi^2. "
                "Consequently the quasistatic approximation breaks down in a parameter "
                "layer of width O(epsilon^(2/3)) around p_c, and the associated dynamic "
                "bottleneck has characteristic passage timescale O(epsilon^(-1/3)).",
                "Direct consequence of the epsilon-free rescaled equation: since no free "
                "parameter remains, every qualitatively distinguished event of the reduced "
                "solution (departure from tracking, finite-time escape) occurs at a fixed "
                "O(1) value of the rescaled variable T, which maps back to "
                "p_c - p = epsilon^(2/3)*T and t = epsilon^(-1/3)*T in the original "
                "variables. Independently confirmed by the heuristic adiabaticity "
                "condition tau_rec(p) << (p_c - p)/epsilon, which yields the same "
                "epsilon^(2/3) threshold by a separate route.",
            ),
        ],
        corollary=CorollaryStatement(
            "Corollary",
            "The departure landmark p_departure and the tipping landmark p_tip both "
            "scale as p_c - O(epsilon^(2/3)) and p_c + O(epsilon^(2/3)) respectively, "
            "sharing the same universal exponent but generally different prefactors, "
            "because both are O(1) events of the same parameter-free reduced equation "
            "dxi/dT = T - xi^2 evaluated at different fixed values of T. They are not "
            "the same event described twice: departure is generically located before "
            "the static fold (T_departure < 0) and tipping after it (T_tip > 0), "
            "reflecting the documented delayed loss of stability under slow passage.",
            note=(
                "Both landmarks are forced to share an exponent by the rescaling; "
                "neither their differing location nor the fact that they differ is an "
                "independent assumption."
            ),
        ),
        honesty_caveats=[
            "T_tip is sharply defined: it is the finite-time blow-up of the rescaled "
            "solution, an unambiguous mathematical event.",
            "T_departure is convention-dependent: it requires a stated deviation "
            "threshold (e.g. 10% deviation from the quasistatic prediction x*(p(t))) "
            "before it is a well-defined number. Its epsilon^(2/3) scaling is robust to "
            "the threshold choice; its prefactor is not.",
            "Theorem 1 assumes a generic, non-degenerate (transversal) saddle-node. It "
            "does not apply as stated to Hopf, transcritical, pitchfork, or "
            "higher-codimension bifurcations, nor to cases where the eigenvalue "
            "crossing is not simple.",
            "Theorem 2's epsilon^(2/3) / epsilon^(-1/3) scaling is a leading-order "
            "asymptotic result as epsilon -> 0. It is not claimed to hold at O(1) sweep "
            "rates.",
            "This draft supersedes the original non-invertibility equivalence theorem, "
            "the entropy-sign proposition, and the slow-mode-failure proposition from "
            "the prior version of the paper. It does not certify that the surrounding "
            "sections (thermodynamic connection, temporal mode decomposition, "
            "comparative framework) have been independently re-derived; those remain "
            "open revision items.",
        ],
        falsification_protocol=[
            "Test 1 (frozen recovery scaling): for a grid of fixed p < p_c, locate the "
            "stable equilibrium, apply a small standardized perturbation, measure the "
            "recovery time, and fit log(tau_rec) = alpha + beta*log(p_c - p). "
            "Prediction: beta = 1/2.",
            "Test 2 (departure scaling): repeat the ramp experiment for several values "
            "of epsilon; record the parameter value at which measured recovery departs "
            "from the Test-1 fit by more than a pre-registered threshold. Prediction: "
            "p_c - p_departure is proportional to epsilon^(2/3).",
            "Test 3 (tipping delay): for the same epsilon sweep, record the parameter "
            "value at actual escape/tipping. Prediction: p_tip - p_c is proportional "
            "to epsilon^(2/3).",
            "Controls required before any deviation counts as falsifying: "
            "perturbations must stay small (linear regime), p_c must be estimated "
            "independently of the fitted data, measurements must be restricted to the "
            "region where a single real eigenvalue dominates and the equilibrium "
            "branch remains normally attracting, and the observed variable must be "
            "coupled to the critical eigenvector.",
            "Falsification rule: sustained deviation from beta = 1/2 (Test 1) or from "
            "the epsilon^(2/3) / epsilon^(-1/3) exponents (Tests 2-3), under the "
            "controls above and across a range of epsilon spanning at least one order "
            "of magnitude, counts as evidence against the generic-saddle-node "
            "interpretation of collapse in this system.",
        ],
    )


def _definitions_lines(definitions: list[TheoryDefinition]) -> list[str]:
    lines = ["Definitions", ""]
    for item in definitions:
        lines.append(f"{item.term}.")
        lines.append(item.statement)
        lines.append("")
    return lines


def _theorem_lines(theorem: TheoremStatement) -> list[str]:
    return [
        f"{theorem.label}: {theorem.name}",
        "",
        "Statement.",
        theorem.statement,
        "",
        "Proof sketch.",
        theorem.proof_sketch,
        "",
    ]


def _corollary_lines(corollary: CorollaryStatement | None) -> list[str]:
    if corollary is None:
        return []
    lines = [corollary.label, "", corollary.statement, ""]
    if corollary.note:
        lines.extend(["Note.", corollary.note, ""])
    return lines


def _caveats_lines(caveats: list[str]) -> list[str]:
    lines = ["Honesty Caveats", ""]
    for caveat in caveats:
        lines.append(f"- {caveat}")
    lines.append("")
    return lines


def _falsification_protocol_lines(steps: list[str]) -> list[str]:
    lines = ["Falsification Protocol", ""]
    for index, step in enumerate(steps, start=1):
        lines.append(f"{index}. {step}")
    lines.append("")
    return lines


def build_theory_revision_draft_lines(content: TheoryRevisionContent) -> list[str]:
    lines: list[str] = [content.title, content.subtitle, ""]
    lines.extend(_definitions_lines(content.definitions))
    for theorem in content.theorems:
        lines.extend(_theorem_lines(theorem))
    lines.extend(_corollary_lines(content.corollary))
    lines.extend(_caveats_lines(content.honesty_caveats))
    lines.extend(_falsification_protocol_lines(content.falsification_protocol))
    return lines


def _render_markdown(content: TheoryRevisionContent) -> str:
    parts: list[str] = [f"# {content.title}", "", f"*{content.subtitle}*", "", "## Definitions", ""]
    for item in content.definitions:
        parts.append(f"**{item.term}.** {item.statement}")
        parts.append("")
    for theorem in content.theorems:
        parts.append(f"## {theorem.label}: {theorem.name}")
        parts.append("")
        parts.append(f"**Statement.** {theorem.statement}")
        parts.append("")
        parts.append(f"**Proof sketch.** {theorem.proof_sketch}")
        parts.append("")
    if content.corollary is not None:
        parts.append(f"## {content.corollary.label}")
        parts.append("")
        parts.append(content.corollary.statement)
        parts.append("")
        if content.corollary.note:
            parts.append(f"*Note.* {content.corollary.note}")
            parts.append("")
    parts.append("## Honesty Caveats")
    parts.append("")
    for caveat in content.honesty_caveats:
        parts.append(f"- {caveat}")
    parts.append("")
    parts.append("## Falsification Protocol")
    parts.append("")
    for index, step in enumerate(content.falsification_protocol, start=1):
        parts.append(f"{index}. {step}")
    parts.append("")
    return "\n".join(parts)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_theory_revision_draft(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    *,
    mission_id: str | None = None,
    content: TheoryRevisionContent | None = None,
    output_path: str | Path = DEFAULT_PDF_OUTPUT,
    markdown_output_path: str | Path | None = DEFAULT_MARKDOWN_OUTPUT,
    reason: str = "",
) -> dict[str, Any]:
    """Assemble a governed theory-revision draft (Definitions, numbered theorems,
    a Corollary, Honesty Caveats, and a Falsification Protocol) from a corrected
    theoretical spine, write it to PDF (and optionally Markdown), and record the
    build as a ledger event. This produces a revision draft, not a certified
    proof: the generated document and the returned record both carry an explicit
    governance disclosure rather than gating on an external authorization check,
    matching the disclosure-in-artifact convention used by the rest of the
    research/paper subsystem (see coherence_paper_pipeline.py, research_pdf.py).
    """
    draft_content = content or default_coherence_theory_revision_content()
    lines = build_theory_revision_draft_lines(draft_content)

    pdf_path = Path(output_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_pdf(pdf_path, lines, draft_content.title)

    markdown_path: Path | None = None
    if markdown_output_path:
        markdown_path = Path(markdown_output_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(_render_markdown(draft_content), encoding="utf-8")

    section_labels = ["Definitions"]
    section_labels.extend(theorem.label for theorem in draft_content.theorems)
    if draft_content.corollary is not None:
        section_labels.append(draft_content.corollary.label)
    section_labels.extend(["Honesty Caveats", "Falsification Protocol"])

    record: dict[str, Any] = {
        "draft_id": f"theory_revision_draft_{uuid.uuid4()}",
        "identity_id": manifest.system_id,
        "mission_id": mission_id,
        "title": draft_content.title,
        "subtitle": draft_content.subtitle,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sections": section_labels,
        "definition_count": len(draft_content.definitions),
        "theorem_count": len(draft_content.theorems),
        "caveat_count": len(draft_content.honesty_caveats),
        "falsification_step_count": len(draft_content.falsification_protocol),
        "content_hash": _text_hash("\n".join(lines)),
        "pdf_path": str(pdf_path),
        "markdown_path": str(markdown_path) if markdown_path else None,
        "governance": (
            "revision draft only; not a certified proof and not a substitute for "
            "external peer review"
        ),
        "will_not": [
            "certify the theorems as correct or peer-reviewed",
            "modify or overwrite the original source paper",
            "mark the underlying mission or claims as resolved",
        ],
        "reason": reason or "manual CLI theory revision draft build",
    }
    ledger.append("theory_revision_draft.created", manifest.system_id, record)

    return {
        "record": record,
        "pdf_path": str(pdf_path),
        "markdown_path": str(markdown_path) if markdown_path else None,
    }


def render_theory_revision_draft_text(result: dict[str, Any]) -> str:
    record = result["record"]
    lines = [
        "Theory Revision Draft",
        f"title: {record.get('title')}",
        f"sections: {', '.join(record.get('sections') or [])}",
        f"pdf: {result.get('pdf_path') or 'none'}",
        f"markdown: {result.get('markdown_path') or 'none'}",
        "guardrail:",
        "- This is a revision draft, not a certified proof; steward review required "
        "before treating it as accepted.",
    ]
    return "\n".join(lines)


def theory_revision_draft_records_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[dict[str, Any]]:
    records = [
        event.payload
        for event in events
        if event.event_type == "theory_revision_draft.created"
    ]
    if mission_id is not None:
        records = [record for record in records if record.get("mission_id") == mission_id]
    return records

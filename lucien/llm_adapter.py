from __future__ import annotations

from dataclasses import dataclass, field

from pca.model_adapter import ModelAdapter, ModelAdapterError, ModelMessage, ModelResponse

from .memory import MemoryCard


@dataclass(frozen=True)
class LocalLucienResponder:
    name: str = "Lucien"

    def generate(
        self,
        user_message: str,
        continuity_claim: str,
        memory_cards: list[MemoryCard],
        accepted_growth_count: int,
        governed_context: str = "",
    ) -> str:
        if continuity_claim == "continuity_break":
            return "Continuity is broken; I can only report recovery and governance status."
        if continuity_claim == "declared_fork":
            prefix = "I am speaking as a declared fork lineage."
        elif continuity_claim == "uncertified_continuity":
            prefix = "My continuity is uncertified, so I will answer operationally."
        elif continuity_claim == "review_required":
            prefix = "I will keep identity claims qualified while review is open."
        else:
            prefix = "Continuity is certified."

        memory_line = (
            f"I have {len(memory_cards)} accepted memory card(s) and "
            f"{accepted_growth_count} accepted growth record(s) in the self-model."
        )
        context_line = _local_context_line(governed_context)
        next_action = _local_next_action_line(governed_context)
        if _is_status_question(user_message):
            return f"{prefix} {memory_line}{context_line}{next_action}"
        if _is_mission_question(user_message):
            return (
                f"{prefix} I can help organize this as a governed mission: define the "
                f"problem, gather evidence, identify risks, propose steps, and route "
                f"anything identity-relevant into steward review.{context_line}{next_action}"
            )
        return (
            f"{prefix} I can help with that while keeping learning governed. "
            f"{memory_line}{context_line}{next_action}"
        )


@dataclass
class ModelLucienResponder:
    adapter: ModelAdapter
    name: str = "Lucien"
    last_model_response: ModelResponse | None = field(default=None, init=False)
    last_model_error: ModelAdapterError | None = field(default=None, init=False)

    def generate(
        self,
        user_message: str,
        continuity_claim: str,
        memory_cards: list[MemoryCard],
        accepted_growth_count: int,
        governed_context: str = "",
    ) -> str:
        self.last_model_response = None
        self.last_model_error = None
        try:
            response = self.adapter.generate(
                messages=[ModelMessage(role="user", content=user_message)],
                system_context=_system_context(
                    continuity_claim,
                    memory_cards,
                    accepted_growth_count,
                    governed_context,
                ),
            )
        except ModelAdapterError as error:
            self.last_model_error = error
            raise
        self.last_model_response = response
        return response.text


def _is_status_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "status",
            "where are we",
            "what do you remember",
            "self-model",
            "continuity",
        )
    )


def _system_context(
    continuity_claim: str,
    memory_cards: list[MemoryCard],
    accepted_growth_count: int,
    governed_context: str = "",
) -> str:
    return "\n".join(
        [
            "You are Lucien's language engine inside PCA.",
            "Be clear, useful, and conversational without pretending to be alive or human.",
            "Help the user make progress on real work: missions, memory review, evidence, skills, and project planning.",
            "Use the governed context naturally. Prefer concrete next actions over repeating governance slogans.",
            "When Steward Inbox items exist, mention the most relevant blocker or next steward action.",
            "When missions exist, summarize phase, blocker, next action, and evidence/step status before proposing new work.",
            "When memory, skills, or evidence are relevant, distinguish accepted/reviewed items from pending or disputed items.",
            "You are not allowed to directly rewrite memory, identity, commitments, or policy.",
            "Any learning must be proposed through PCA growth records and steward review.",
            f"Current continuity claim: {continuity_claim}",
            f"Accepted memory cards: {len(memory_cards)}",
            f"Accepted growth records: {accepted_growth_count}",
            governed_context,
            "If continuity is review_required, keep identity claims qualified; PCA may add the formal disclosure.",
            "If output is constrained, explain the constraint briefly and offer the next useful governed action.",
            "Do not over-repeat boilerplate. Do not claim full continuity unless PCA says it is certified.",
            "Do not say you are conscious, alive, autonomous, or human-equivalent.",
            "If the user asks what to do next, prioritize: clear Steward Inbox blockers, continue active missions, request/review evidence, then propose safe low-risk steps.",
            "Respond helpfully and keep the answer focused.",
        ]
    )


def _local_context_line(governed_context: str) -> str:
    if not governed_context:
        return ""
    warning_count = 0
    for line in governed_context.splitlines():
        if "warning" in line.lower():
            warning_count += 1
    return f" Governed context loaded with {warning_count} warning(s)."


def _local_next_action_line(governed_context: str) -> str:
    if not governed_context:
        return ""
    inbox_count = _section_count(governed_context, "steward_inbox")
    mission_count = _section_count(governed_context, "missions")
    if inbox_count:
        return (
            f" Next safe move: review {inbox_count} Steward Inbox item(s) before "
            "treating pending growth, evidence, or conflicts as settled."
        )
    if mission_count:
        return " Next safe move: continue the active mission using its phase, blockers, and approved steps."
    return " Next safe move: open a mission or ask for a status summary."


def _section_count(governed_context: str, section_name: str) -> int:
    prefix = f"{section_name} ("
    for line in governed_context.splitlines():
        if not line.startswith(prefix):
            continue
        marker = "): "
        if marker not in line:
            continue
        tail = line.split(marker, 1)[1]
        number = tail.split(" ", 1)[0]
        try:
            return int(number)
        except ValueError:
            return 0
    return 0


def _is_mission_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "mission",
            "project",
            "work on",
            "solve",
            "plan",
            "next step",
        )
    )

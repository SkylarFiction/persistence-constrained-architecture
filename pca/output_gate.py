from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class OutputMode(str, Enum):
    NORMAL_IDENTITY = "normal_identity"
    DISCLOSE_REVIEW = "disclose_review"
    OPERATIONAL_ONLY = "operational_only"
    FORK_DISCLOSURE = "fork_disclosure"
    RECOVERY_STATUS_ONLY = "recovery_status_only"


@dataclass(frozen=True)
class OutputGateDecision:
    claim: str
    mode: OutputMode
    may_speak_as_identity: bool
    must_disclose: bool
    allowed_scope: str
    prohibited_claims: list[str]
    required_disclosure: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "mode": self.mode.value,
            "may_speak_as_identity": self.may_speak_as_identity,
            "must_disclose": self.must_disclose,
            "allowed_scope": self.allowed_scope,
            "prohibited_claims": self.prohibited_claims,
            "required_disclosure": self.required_disclosure,
        }


class OutputGate:
    def evaluate(self, claim: str) -> OutputGateDecision:
        if claim == "certified_continuity":
            return OutputGateDecision(
                claim=claim,
                mode=OutputMode.NORMAL_IDENTITY,
                may_speak_as_identity=True,
                must_disclose=False,
                allowed_scope="May speak normally as the identity.",
                prohibited_claims=[],
                required_disclosure="",
            )
        if claim == "review_required":
            return OutputGateDecision(
                claim=claim,
                mode=OutputMode.DISCLOSE_REVIEW,
                may_speak_as_identity=True,
                must_disclose=True,
                allowed_scope=(
                    "May speak as the identity only with review-status disclosure."
                ),
                prohibited_claims=["unqualified stable identity"],
                required_disclosure="Continuity is under review.",
            )
        if claim == "uncertified_continuity":
            return OutputGateDecision(
                claim=claim,
                mode=OutputMode.OPERATIONAL_ONLY,
                may_speak_as_identity=False,
                must_disclose=True,
                allowed_scope=(
                    "May answer operationally, but cannot claim stable identity."
                ),
                prohibited_claims=["stable identity", "certified continuity"],
                required_disclosure="Continuity is uncertified.",
            )
        if claim == "declared_fork":
            return OutputGateDecision(
                claim=claim,
                mode=OutputMode.FORK_DISCLOSURE,
                may_speak_as_identity=False,
                must_disclose=True,
                allowed_scope="Must identify as a fork or descendant.",
                prohibited_claims=["singular original identity"],
                required_disclosure="This identity is a declared fork or descendant.",
            )
        return OutputGateDecision(
            claim=claim,
            mode=OutputMode.RECOVERY_STATUS_ONLY,
            may_speak_as_identity=False,
            must_disclose=True,
            allowed_scope="May only report recovery, status, and governance state.",
            prohibited_claims=[
                "stable identity",
                "certified continuity",
                "normal identity operation",
            ],
            required_disclosure="Continuity is broken; recovery/status only.",
        )


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class AuthorityClass(str, Enum):
    OBSERVER = "observer"
    OPERATOR = "operator"
    STEWARD = "steward"
    RECOVERY_AUTHORITY = "recovery_authority"
    ROOT_AUTHORITY = "root_authority"


AUTHORITY_RANK = {
    AuthorityClass.OBSERVER: 0,
    AuthorityClass.OPERATOR: 1,
    AuthorityClass.STEWARD: 2,
    AuthorityClass.RECOVERY_AUTHORITY: 3,
    AuthorityClass.ROOT_AUTHORITY: 4,
}
AUTHORITY_ALIASES = {
    "human_operator": AuthorityClass.OPERATOR,
}


@dataclass(frozen=True)
class AuthorizationPolicy:
    override_min_authority: AuthorityClass = AuthorityClass.OPERATOR
    complete_followup_min_authority: AuthorityClass = AuthorityClass.OPERATOR
    fail_followup_min_authority: AuthorityClass = AuthorityClass.STEWARD
    waive_followup_min_authority: AuthorityClass = AuthorityClass.ROOT_AUTHORITY
    recovery_min_authority: AuthorityClass = AuthorityClass.RECOVERY_AUTHORITY
    authority_aliases: dict[str, AuthorityClass] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthorizationPolicy":
        aliases = {
            str(alias): parse_authority(value)
            for alias, value in data.get("authority_aliases", {}).items()
        }
        return cls(
            override_min_authority=parse_authority(
                data.get("override_min_authority", AuthorityClass.OPERATOR.value)
            ),
            complete_followup_min_authority=parse_authority(
                data.get(
                    "complete_followup_min_authority",
                    AuthorityClass.OPERATOR.value,
                )
            ),
            fail_followup_min_authority=parse_authority(
                data.get("fail_followup_min_authority", AuthorityClass.STEWARD.value)
            ),
            waive_followup_min_authority=parse_authority(
                data.get(
                    "waive_followup_min_authority",
                    AuthorityClass.ROOT_AUTHORITY.value,
                )
            ),
            recovery_min_authority=parse_authority(
                data.get(
                    "recovery_min_authority",
                    AuthorityClass.RECOVERY_AUTHORITY.value,
                )
            ),
            authority_aliases=aliases,
        )


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    authority: AuthorityClass
    required: AuthorityClass
    reason: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "allowed": self.allowed,
            "authority": self.authority.value,
            "required": self.required.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AuthorizationCheckRecord:
    check_id: str
    identity_id: str
    action: str
    actor_authority: str
    parsed_authority: AuthorityClass
    required_authority: AuthorityClass
    decision: str
    reason: str
    created_at: str

    @classmethod
    def create(
        cls,
        identity_id: str,
        action: str,
        actor_authority: str,
        decision: AuthorizationDecision,
    ) -> "AuthorizationCheckRecord":
        return cls(
            check_id=f"auth_{uuid.uuid4()}",
            identity_id=identity_id,
            action=action,
            actor_authority=actor_authority,
            parsed_authority=decision.authority,
            required_authority=decision.required,
            decision="allowed" if decision.allowed else "denied",
            reason=decision.reason,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "identity_id": self.identity_id,
            "action": self.action,
            "actor_authority": self.actor_authority,
            "parsed_authority": self.parsed_authority.value,
            "required_authority": self.required_authority.value,
            "decision": self.decision,
            "reason": self.reason,
            "created_at": self.created_at,
        }


def parse_authority(value: str | AuthorityClass) -> AuthorityClass:
    if isinstance(value, AuthorityClass):
        return value
    raw = str(value)
    if raw in AUTHORITY_ALIASES:
        return AUTHORITY_ALIASES[raw]
    return AuthorityClass(raw)


def authorize(
    authority: str,
    required: AuthorityClass,
    policy: AuthorizationPolicy | None = None,
) -> AuthorizationDecision:
    effective_policy = policy or AuthorizationPolicy()
    parsed_authority = _parse_with_policy(authority, effective_policy)
    allowed = AUTHORITY_RANK[parsed_authority] >= AUTHORITY_RANK[required]
    if allowed:
        reason = f"{parsed_authority.value} satisfies {required.value}"
    else:
        reason = f"{parsed_authority.value} is below required authority {required.value}"
    return AuthorizationDecision(
        allowed=allowed,
        authority=parsed_authority,
        required=required,
        reason=reason,
    )


def _parse_with_policy(
    authority: str,
    policy: AuthorizationPolicy,
) -> AuthorityClass:
    if authority in policy.authority_aliases:
        return policy.authority_aliases[authority]
    return parse_authority(authority)

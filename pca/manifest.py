from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PersistenceConstraint:
    name: str
    kind: str
    required: bool = True
    threshold: float | None = None
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersistenceConstraint":
        return cls(
            name=str(data["name"]),
            kind=str(data.get("kind", "invariant")),
            required=bool(data.get("required", True)),
            threshold=data.get("threshold"),
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "threshold": self.threshold,
            "description": self.description,
        }


@dataclass(frozen=True)
class IdentityManifest:
    system_id: str
    name: str
    version: str
    origin: dict[str, Any]
    invariants: list[str]
    constraints: list[PersistenceConstraint] = field(default_factory=list)
    allowed_transforms: list[str] = field(default_factory=list)
    transform_policies: list[Any] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IdentityManifest":
        return cls(
            system_id=str(data["system_id"]),
            name=str(data["name"]),
            version=str(data.get("version", "0.1.0")),
            origin=dict(data.get("origin", {})),
            invariants=[str(item) for item in data.get("invariants", [])],
            constraints=[
                PersistenceConstraint.from_dict(item)
                for item in data.get("constraints", [])
            ],
            allowed_transforms=[
                str(item) for item in data.get("allowed_transforms", [])
            ],
            transform_policies=data.get("transform_policies", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_id": self.system_id,
            "name": self.name,
            "version": self.version,
            "origin": self.origin,
            "invariants": self.invariants,
            "constraints": [item.to_dict() for item in self.constraints],
            "allowed_transforms": self.allowed_transforms,
            "transform_policies": [
                item.to_dict() if hasattr(item, "to_dict") else item
                for item in self.transform_policies
            ],
        }

    def transform_policy(self, name: str) -> Any | None:
        from .policy import TransformPolicy

        raw_policies = self.transform_policies
        policies = [
            item if isinstance(item, TransformPolicy) else TransformPolicy.from_dict(item)
            for item in raw_policies
        ]
        for policy in policies:
            if policy.name == name:
                return policy
        if name in self.allowed_transforms:
            from .policy import IdentityRisk, PolicyDecision

            return TransformPolicy(
                name=name,
                decision=PolicyDecision.ALLOW,
                identity_risk=IdentityRisk.MEDIUM,
            )
        return None

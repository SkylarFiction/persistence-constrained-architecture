from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib import request


@dataclass(frozen=True)
class ModelMessage:
    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True)
class ModelResponse:
    text: str
    provider: str
    model: str
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "raw": self.raw or {},
        }


class ModelAdapter:
    def generate(
        self,
        messages: list[ModelMessage],
        system_context: str,
    ) -> ModelResponse:
        raise NotImplementedError


class EchoAdapter(ModelAdapter):
    def generate(
        self,
        messages: list[ModelMessage],
        system_context: str,
    ) -> ModelResponse:
        user_message = _latest_user_message(messages)
        return ModelResponse(
            text=(
                "Continuity is being governed. "
                f"I received: {user_message} "
                "I will answer through PCA rather than changing identity directly."
            ),
            provider="echo",
            model="echo-local",
            raw={"system_context_length": len(system_context)},
        )


class OpenAICompatibleAdapter(ModelAdapter):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: int = 30,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        messages: list[ModelMessage],
        system_context: str,
    ) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_context},
                *[message.to_dict() for message in messages],
            ],
            "temperature": 0.4,
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return ModelResponse(
            text=text or "The model returned an empty response.",
            provider="openai_compatible",
            model=self.model,
            raw=_compact_raw(data),
        )


def adapter_from_environment() -> ModelAdapter:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return EchoAdapter()
    return OpenAICompatibleAdapter(
        api_key=api_key,
        model=os.environ.get("LUCIEN_MODEL", "gpt-4o-mini"),
        base_url=os.environ.get("LUCIEN_MODEL_BASE_URL", "https://api.openai.com/v1"),
    )


def _latest_user_message(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _compact_raw(data: dict[str, Any]) -> dict[str, Any]:
    usage = data.get("usage", {})
    return {
        "id": data.get("id"),
        "object": data.get("object"),
        "usage": usage,
    }

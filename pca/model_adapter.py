from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request


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


class ModelAdapterError(RuntimeError):
    def __init__(
        self,
        message: str,
        provider: str,
        model: str,
        error_type: str = "model_adapter_error",
    ):
        super().__init__(message)
        self.provider = provider
        self.model = model
        self.error_type = error_type

    def to_dict(self) -> dict[str, str]:
        return {
            "message": str(self),
            "provider": self.provider,
            "model": self.model,
            "error_type": self.error_type,
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
        model: str = "gpt-4.1-mini",
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
            "input": [
                {
                    "role": "developer",
                    "content": system_context,
                },
                *[
                    {
                        "role": message.role,
                        "content": message.content,
                    }
                    for message in messages
                ],
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/responses",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ModelAdapterError(
                f"OpenAI API request failed with HTTP {exc.code}: {detail}",
                provider="openai",
                model=self.model,
                error_type="http_error",
            ) from exc
        except OSError as exc:
            raise ModelAdapterError(
                f"OpenAI API request failed: {exc}",
                provider="openai",
                model=self.model,
                error_type=exc.__class__.__name__,
            ) from exc
        text = _extract_responses_text(data).strip()
        return ModelResponse(
            text=text or "The model returned an empty response.",
            provider="openai",
            model=self.model,
            raw=_compact_raw(data),
        )


def adapter_from_environment(env_path: str = ".env") -> ModelAdapter:
    _load_dotenv(env_path)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return EchoAdapter()
    return OpenAICompatibleAdapter(
        api_key=api_key,
        model=os.environ.get("LUCIEN_MODEL", "gpt-4.1-mini"),
        base_url=os.environ.get("LUCIEN_MODEL_BASE_URL", "https://api.openai.com/v1"),
    )


def model_environment_diagnostic(env_path: str = ".env") -> dict[str, Any]:
    _load_dotenv(env_path)
    env_file = Path(env_path)
    raw = b""
    env_file_exists = env_file.exists()
    if env_file_exists:
        try:
            raw = env_file.read_bytes()
        except OSError:
            raw = b""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("LUCIEN_MODEL", "gpt-4.1-mini")
    key_present = bool(api_key.strip())
    return {
        "env_path": str(env_file),
        "env_file_exists": env_file_exists,
        "env_file_plain_text": not raw.startswith(b"{\\rtf"),
        "openai_key_present": key_present,
        "openai_key_prefix_ok": (
            api_key.startswith("sk-") or api_key.startswith("sk-proj-")
            if key_present
            else False
        ),
        "configured_model": model,
        "configured_provider": "openai" if key_present else "echo",
    }


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
        "status": data.get("status"),
        "usage": usage,
    }


def _extract_responses_text(data: dict[str, Any]) -> str:
    output_text = data.get("output_text")
    if isinstance(output_text, str):
        return output_text
    chunks = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks)


def _load_dotenv(path: str) -> None:
    if not path:
        return
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _strip_env_value(value.strip())


def _strip_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value

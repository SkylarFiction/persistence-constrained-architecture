from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

MODEL_MODE_ECHO = "echo"
MODEL_MODE_OPENAI = "openai"
MODEL_MODE_LOCAL_OLLAMA = "local_ollama"
MODEL_MODE_LOCAL_FIRST = "local_first"
MODEL_MODE_SERIOUS_ONLY = "serious_only"
MODEL_MODES = {
    MODEL_MODE_ECHO,
    MODEL_MODE_OPENAI,
    MODEL_MODE_LOCAL_OLLAMA,
    MODEL_MODE_LOCAL_FIRST,
    MODEL_MODE_SERIOUS_ONLY,
}
DEFAULT_MODEL_MODE = MODEL_MODE_SERIOUS_ONLY
DEFAULT_INPUT_COST_PER_M_TOKEN = 0.40
DEFAULT_OUTPUT_COST_PER_M_TOKEN = 1.60


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
        claim = _context_value(system_context, "Current continuity claim") or _context_value(
            system_context,
            "Continuity claim",
        )
        claim = claim or "unknown"
        memory_count = _context_value(system_context, "Accepted memory cards") or "0"
        growth_count = _context_value(system_context, "Accepted growth records") or "0"
        inbox_count = _section_count(system_context, "steward_inbox")
        mission_count = _section_count(system_context, "missions")
        if claim == "continuity_break":
            text = "Continuity is broken; I can only report recovery and governance status."
        else:
            prefix = _continuity_prefix(claim)
            text = (
                f"{prefix} I received: {user_message}. "
                f"I have {memory_count} accepted memory card(s) and "
                f"{growth_count} accepted growth record(s). "
                f"{_next_action_sentence(inbox_count, mission_count)} "
                "I will keep working through PCA rather than changing identity directly."
            )
        return ModelResponse(
            text=text,
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


class OllamaAdapter(ModelAdapter):
    def __init__(
        self,
        model: str = "llama3.1:8b",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 60,
    ):
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
            "stream": False,
            "messages": [
                {"role": "system", "content": system_context},
                *[message.to_dict() for message in messages],
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ModelAdapterError(
                f"Ollama request failed with HTTP {exc.code}: {detail}",
                provider="ollama",
                model=self.model,
                error_type="http_error",
            ) from exc
        except OSError as exc:
            raise ModelAdapterError(
                f"Ollama request failed: {exc}",
                provider="ollama",
                model=self.model,
                error_type=exc.__class__.__name__,
            ) from exc
        text = _extract_ollama_text(data).strip()
        return ModelResponse(
            text=text or "The local model returned an empty response.",
            provider="ollama",
            model=self.model,
            raw=_compact_ollama_raw(data),
        )


class FallbackAdapter(ModelAdapter):
    def __init__(self, primary: ModelAdapter, fallback: ModelAdapter):
        self.primary = primary
        self.fallback = fallback

    def generate(
        self,
        messages: list[ModelMessage],
        system_context: str,
    ) -> ModelResponse:
        try:
            return self.primary.generate(messages, system_context)
        except ModelAdapterError as primary_error:
            try:
                response = self.fallback.generate(messages, system_context)
            except ModelAdapterError:
                raise primary_error
            return ModelResponse(
                text=response.text,
                provider=response.provider,
                model=response.model,
                raw={
                    **(response.raw or {}),
                    "fallback_from": primary_error.to_dict(),
                },
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


def local_adapter_from_environment(env_path: str = ".env") -> ModelAdapter:
    _load_dotenv(env_path)
    provider = os.environ.get("LUCIEN_LOCAL_PROVIDER", "ollama").strip().lower()
    if provider not in {"ollama", "local_ollama"}:
        return EchoAdapter()
    return OllamaAdapter(
        model=os.environ.get("LUCIEN_OLLAMA_MODEL", "llama3.1:8b"),
        base_url=os.environ.get("LUCIEN_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )


def adapter_for_model_mode(
    mode: str | None,
    use_openai: bool = False,
    env_path: str = ".env",
) -> ModelAdapter:
    normalized = normalize_model_mode(mode)
    if normalized == MODEL_MODE_ECHO:
        return EchoAdapter()
    if normalized == MODEL_MODE_LOCAL_OLLAMA:
        return local_adapter_from_environment(env_path)
    if normalized == MODEL_MODE_LOCAL_FIRST:
        local = local_adapter_from_environment(env_path)
        if use_openai:
            return FallbackAdapter(local, adapter_from_environment(env_path))
        return FallbackAdapter(local, EchoAdapter())
    if normalized == MODEL_MODE_SERIOUS_ONLY and not use_openai:
        return EchoAdapter()
    return adapter_from_environment(env_path)


def normalize_model_mode(mode: str | None) -> str:
    normalized = (mode or os.environ.get("LUCIEN_MODEL_MODE") or DEFAULT_MODEL_MODE).strip()
    normalized = normalized.lower().replace("-", "_")
    if normalized in {"serious", "serious_replies", "openai_serious"}:
        normalized = MODEL_MODE_SERIOUS_ONLY
    if normalized in {"ollama", "local", "local_model"}:
        normalized = MODEL_MODE_LOCAL_OLLAMA
    if normalized in {"local_first", "local_openai_fallback", "local_with_openai_fallback"}:
        normalized = MODEL_MODE_LOCAL_FIRST
    if normalized not in MODEL_MODES:
        return DEFAULT_MODEL_MODE
    return normalized


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
    local_provider = os.environ.get("LUCIEN_LOCAL_PROVIDER", "ollama")
    ollama_url = os.environ.get("LUCIEN_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model = os.environ.get("LUCIEN_OLLAMA_MODEL", "llama3.1:8b")
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
        "local_provider": local_provider,
        "local_model": ollama_model,
        "local_base_url": ollama_url,
        "local_model_configured": bool(ollama_model.strip()),
        "default_model_mode": normalize_model_mode(None),
    }


def estimate_model_usage(
    context_length: int,
    response_length: int,
    raw_usage: dict[str, Any] | None = None,
    model: str = "gpt-4.1-mini",
) -> dict[str, Any]:
    usage = raw_usage or {}
    input_tokens = _usage_int(usage, "input_tokens")
    output_tokens = _usage_int(usage, "output_tokens")
    used_api_usage = input_tokens is not None or output_tokens is not None
    if input_tokens is None:
        input_tokens = _estimate_tokens_from_chars(context_length)
    if output_tokens is None:
        output_tokens = _estimate_tokens_from_chars(response_length)
    input_rate, output_rate = _pricing_rates()
    estimated_cost = (
        (input_tokens / 1_000_000) * input_rate
        + (output_tokens / 1_000_000) * output_rate
    )
    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": round(estimated_cost, 6),
        "input_cost_per_m_token": input_rate,
        "output_cost_per_m_token": output_rate,
        "source": "api_usage" if used_api_usage else "char_estimate",
    }


def _latest_user_message(messages: list[ModelMessage]) -> str:
    for message in reversed(messages):
        if message.role == "user":
            return message.content
    return ""


def _continuity_prefix(claim: str) -> str:
    if claim == "certified_continuity":
        return "Continuity is certified."
    if claim == "review_required":
        return "I will keep identity claims qualified while review is open."
    if claim == "uncertified_continuity":
        return "Continuity is uncertified, so I will answer operationally."
    if claim == "declared_fork":
        return "I am speaking as a declared fork lineage."
    return "Continuity is being governed."


def _next_action_sentence(inbox_count: int, mission_count: int) -> str:
    if inbox_count:
        return (
            f"Next safe move: review {inbox_count} Steward Inbox item(s) "
            "before treating pending growth, evidence, or conflicts as settled."
        )
    if mission_count:
        return "Next safe move: continue the active mission through its governed phase."
    return "Next safe move: open a mission or ask for a governed status summary."


def _context_value(context: str, label: str) -> str:
    prefix = f"{label}:"
    for line in context.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def _section_count(context: str, section_name: str) -> int:
    prefix = f"{section_name} ("
    for line in context.splitlines():
        if not line.startswith(prefix):
            continue
        marker = "): "
        if marker not in line:
            continue
        number = line.split(marker, 1)[1].split(" ", 1)[0]
        try:
            return int(number)
        except ValueError:
            return 0
    return 0


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


def _extract_ollama_text(data: dict[str, Any]) -> str:
    message = data.get("message", {})
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"]
    response = data.get("response")
    if isinstance(response, str):
        return response
    return ""


def _compact_ollama_raw(data: dict[str, Any]) -> dict[str, Any]:
    usage = {}
    if isinstance(data.get("prompt_eval_count"), int):
        usage["input_tokens"] = data["prompt_eval_count"]
    if isinstance(data.get("eval_count"), int):
        usage["output_tokens"] = data["eval_count"]
    return {
        "model": data.get("model"),
        "created_at": data.get("created_at"),
        "done": data.get("done"),
        "usage": usage,
    }


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


def _estimate_tokens_from_chars(length: int) -> int:
    return max(1, int((max(0, length) + 3) / 4))


def _usage_int(usage: dict[str, Any], key: str) -> int | None:
    value = usage.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _pricing_rates() -> tuple[float, float]:
    input_rate = _env_float(
        "LUCIEN_INPUT_COST_PER_M_TOKEN",
        DEFAULT_INPUT_COST_PER_M_TOKEN,
    )
    output_rate = _env_float(
        "LUCIEN_OUTPUT_COST_PER_M_TOKEN",
        DEFAULT_OUTPUT_COST_PER_M_TOKEN,
    )
    return input_rate, output_rate


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

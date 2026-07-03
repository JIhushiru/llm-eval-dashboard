"""Adapter registry: provider lookup, model-id parsing, backend listing."""

from app.adapters.anthropic_adapter import AnthropicAdapter
from app.adapters.base import AdapterError, GenerationResult, LLMAdapter
from app.adapters.ollama_adapter import OllamaAdapter
from app.adapters.openai_adapter import OpenAIAdapter

__all__ = [
    "AdapterError",
    "GenerationResult",
    "LLMAdapter",
    "PROVIDERS",
    "get_adapter",
    "list_backends",
    "parse_model_id",
    "provider_availability",
]

PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "ollama")

_ADAPTERS: dict[str, LLMAdapter] = {
    "anthropic": AnthropicAdapter(),
    "openai": OpenAIAdapter(),
    "ollama": OllamaAdapter(),
}


def get_adapter(provider: str) -> LLMAdapter:
    try:
        return _ADAPTERS[provider]
    except KeyError:
        raise ValueError(f"unknown provider: {provider!r}") from None


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Split "provider:model" on the FIRST colon only."""
    provider, sep, model = model_id.partition(":")
    if not sep or not provider or not model:
        raise ValueError(f"invalid model id {model_id!r}: expected 'provider:model'")
    return provider, model


async def provider_availability(provider: str) -> tuple[bool, str]:
    adapter = get_adapter(provider)
    return await adapter.availability()


async def list_backends() -> list[dict[str, object]]:
    infos: list[dict[str, object]] = []
    for provider in PROVIDERS:
        available, reason, models = await _ADAPTERS[provider].describe()
        infos.append(
            {"provider": provider, "available": available, "reason": reason, "models": models}
        )
    return infos

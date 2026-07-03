"""Anthropic adapter (anthropic.AsyncAnthropic)."""

import anthropic

from app.adapters.base import AdapterError, GenerationResult, LLMAdapter
from app.config import get_settings

SUGGESTED_MODELS = ["claude-opus-4-8", "claude-sonnet-5", "claude-haiku-4-5"]


class AnthropicAdapter(LLMAdapter):
    provider = "anthropic"

    def is_configured(self) -> tuple[bool, str]:
        if get_settings().anthropic_api_key:
            return True, "ANTHROPIC_API_KEY is set"
        return False, "ANTHROPIC_API_KEY is not set"

    async def generate(self, model: str, prompt: str, max_tokens: int) -> GenerationResult:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise AdapterError("ANTHROPIC_API_KEY is not set")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            # temperature intentionally omitted: rejected by current Anthropic models
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise AdapterError(f"anthropic generation failed: {exc}") from exc
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return GenerationResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    async def list_models(self) -> list[str]:
        return list(SUGGESTED_MODELS)

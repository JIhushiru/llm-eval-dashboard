"""OpenAI adapter (openai.AsyncOpenAI)."""

import openai

from app.adapters.base import AdapterError, GenerationResult, LLMAdapter
from app.config import get_settings

SUGGESTED_MODELS = ["gpt-4o", "gpt-4o-mini"]


class OpenAIAdapter(LLMAdapter):
    provider = "openai"

    def is_configured(self) -> tuple[bool, str]:
        if get_settings().openai_api_key:
            return True, "OPENAI_API_KEY is set"
        return False, "OPENAI_API_KEY is not set"

    async def generate(self, model: str, prompt: str, max_tokens: int) -> GenerationResult:
        settings = get_settings()
        if not settings.openai_api_key:
            raise AdapterError("OPENAI_API_KEY is not set")
        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        try:
            # No token-cap parameter: keeps compatibility across chat model families.
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise AdapterError(f"openai generation failed: {exc}") from exc
        choice = response.choices[0] if response.choices else None
        text = (choice.message.content if choice is not None else None) or ""
        usage = response.usage
        return GenerationResult(
            text=text,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )

    async def list_models(self) -> list[str]:
        return list(SUGGESTED_MODELS)

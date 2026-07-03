"""Adapter abstractions shared by all LLM providers."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class GenerationResult(BaseModel):
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class AdapterError(Exception):
    """Retryable provider/network failure; all adapters wrap errors in this."""


class LLMAdapter(ABC):
    provider: str

    @abstractmethod
    def is_configured(self) -> tuple[bool, str]:
        """(available, reason) from static configuration only — no network."""

    @abstractmethod
    async def generate(self, model: str, prompt: str, max_tokens: int) -> GenerationResult:
        ...

    @abstractmethod
    async def list_models(self) -> list[str]:
        """Suggested model names for the UI."""

    async def availability(self) -> tuple[bool, str]:
        """(available, reason); ollama overrides this with a network probe."""
        return self.is_configured()

    async def describe(self) -> tuple[bool, str, list[str]]:
        """(available, reason, models) for GET /api/backends."""
        available, reason = await self.availability()
        return available, reason, await self.list_models()

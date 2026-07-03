"""Ollama adapter (raw httpx against the local Ollama HTTP API)."""

import httpx

from app.adapters.base import AdapterError, GenerationResult, LLMAdapter
from app.config import get_settings

PROBE_TIMEOUT_S = 2.0
GENERATE_TIMEOUT_S = 120.0


class OllamaAdapter(LLMAdapter):
    provider = "ollama"

    def is_configured(self) -> tuple[bool, str]:
        # No API key exists for ollama; real availability comes from the probe.
        return True, f"no API key required (server: {get_settings().ollama_base_url})"

    async def _probe(self) -> tuple[bool, str, list[str]]:
        base = get_settings().ollama_base_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
                response = await client.get(f"{base}/api/tags")
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            return False, f"ollama unreachable at {base}: {exc}", []
        models = [m["name"] for m in data.get("models", []) if m.get("name")]
        return True, f"ollama reachable at {base}", models

    async def availability(self) -> tuple[bool, str]:
        available, reason, _ = await self._probe()
        return available, reason

    async def describe(self) -> tuple[bool, str, list[str]]:
        return await self._probe()

    async def list_models(self) -> list[str]:
        _, _, models = await self._probe()
        return models

    async def generate(self, model: str, prompt: str, max_tokens: int) -> GenerationResult:
        # max_tokens is accepted for interface parity; /api/generate has no cap param here.
        base = get_settings().ollama_base_url.rstrip("/")
        payload = {"model": model, "prompt": prompt, "stream": False}
        try:
            async with httpx.AsyncClient(timeout=GENERATE_TIMEOUT_S) as client:
                response = await client.post(f"{base}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            raise AdapterError(f"ollama generation failed: {exc}") from exc
        return GenerationResult(
            text=str(data.get("response", "")),
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
        )

"""Fake LLM adapter for tests: zero network, configurable failures/latency/responses."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from app.adapters.base import AdapterError, GenerationResult, LLMAdapter

# First line of the rubric template; lets a single fake adapter tell judge calls
# apart from generation calls without any extra plumbing.
JUDGE_PROMPT_MARKER = "You are an expert evaluator of LLM outputs."

DEFAULT_JUDGE_JSON = (
    '{"correctness": 4, "relevance": 5, "instruction_following": 4, '
    '"rationale": "Fake judge rationale for tests."}'
)


def split_responder(
    generation_text: str, judge_text: str = DEFAULT_JUDGE_JSON
) -> Callable[[str, str], str]:
    """Responder answering judge prompts with judge_text and all others with generation_text."""

    def _respond(_model: str, prompt: str) -> str:
        return judge_text if JUDGE_PROMPT_MARKER in prompt else generation_text

    return _respond


class FakeAdapter(LLMAdapter):
    provider = "fake"

    def __init__(
        self,
        respond: Callable[[str, str], str] | None = None,
        fail_first: int = 0,
        fail_always: bool = False,
        delay_s: float = 0.0,
    ) -> None:
        self.respond = respond
        self.fail_first = fail_first
        self.fail_always = fail_always
        self.delay_s = delay_s
        self.calls: int = 0
        self.prompts: list[str] = []
        self._active: int = 0
        self.max_active: int = 0

    def is_configured(self) -> tuple[bool, str]:
        return True, "fake adapter is always configured"

    async def list_models(self) -> list[str]:
        return ["fake-model"]

    async def generate(self, model: str, prompt: str, max_tokens: int) -> GenerationResult:
        self.calls += 1
        self.prompts.append(prompt)
        if self.fail_always:
            raise AdapterError("permanent fake failure")
        if self.calls <= self.fail_first:
            raise AdapterError(f"transient fake failure #{self.calls}")
        self._active += 1
        self.max_active = max(self.max_active, self._active)
        try:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
        finally:
            self._active -= 1
        text = self.respond(model, prompt) if self.respond else DEFAULT_JUDGE_JSON
        return GenerationResult(text=text, input_tokens=17, output_tokens=len(text) // 4)

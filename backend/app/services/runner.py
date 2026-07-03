"""Async run executor: generation, checks, and judging with bounded concurrency."""

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from app import adapters, database
from app.adapters.base import AdapterError, GenerationResult
from app.config import Settings, get_settings
from app.models import CaseResult, Run, TestCase, utcnow
from app.services import checks as checks_service
from app.services import judge as judge_service

T = TypeVar("T")

MAX_CONCURRENCY = 5
DEFAULT_ATTEMPTS = 3


async def with_retries(
    coro_factory: Callable[[], Awaitable[T]],
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = 1.0,
) -> tuple[T, int]:
    """Retry on AdapterError with exponential backoff + jitter.

    Returns (result, retries) where retries == 0 means the first try succeeded.
    """
    last_exc: AdapterError | None = None
    for attempt in range(attempts):
        try:
            return await coro_factory(), attempt
        except AdapterError as exc:
            last_exc = exc
            if attempt < attempts - 1:
                await asyncio.sleep(base_delay * (2**attempt) + random.uniform(0, 0.5))
    assert last_exc is not None
    raise last_exc


@dataclass(frozen=True)
class _CaseSnapshot:
    id: int
    prompt: str
    expected_behavior: str
    reference_answer: str | None
    assertions: list[dict[str, Any]]


async def execute_run(run_id: int) -> None:
    session = database.SessionLocal()
    try:
        run = session.get(Run, run_id)
        if run is None:
            return
        run.status = "running"
        session.commit()
        models = list(run.models)
        template = run.prompt_template
        judge_model_id = run.judge_model
        suite_cases = (
            session.query(TestCase)
            .filter(TestCase.suite_id == run.suite_id)
            .order_by(TestCase.id)
            .all()
        )
        cases = [
            _CaseSnapshot(
                id=case.id,
                prompt=case.prompt,
                expected_behavior=case.expected_behavior,
                reference_answer=case.reference_answer,
                assertions=list(case.assertions or []),
            )
            for case in suite_cases
        ]
    finally:
        session.close()

    settings = get_settings()
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    try:
        tasks = [
            asyncio.create_task(
                _run_case(run_id, case, model_id, template, judge_model_id, settings, semaphore)
            )
            for case in cases
            for model_id in models
        ]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        failures = [o for o in outcomes if isinstance(o, BaseException)]
        if failures:
            raise failures[0]
    except Exception as exc:
        _finish(run_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        return
    _finish(run_id, status="completed", error=None)


async def _run_case(
    run_id: int,
    case: _CaseSnapshot,
    model_id: str,
    template: str | None,
    judge_model_id: str,
    settings: Settings,
    semaphore: asyncio.Semaphore,
) -> None:
    # One semaphore slot covers the whole task: generation + checks + judge call.
    async with semaphore:
        provider, model_name = adapters.parse_model_id(model_id)
        adapter = adapters.get_adapter(provider)
        prompt = template.replace("{prompt}", case.prompt) if template else case.prompt

        result = CaseResult(run_id=run_id, case_id=case.id, model=model_id)

        async def _generate() -> tuple[GenerationResult, float]:
            start = time.perf_counter()
            generation = await adapter.generate(
                model_name, prompt, settings.generation_max_tokens
            )
            return generation, (time.perf_counter() - start) * 1000.0

        try:
            (generation, latency_ms), retries = await with_retries(_generate)
        except AdapterError as exc:
            result.error = str(exc)
            result.retries = DEFAULT_ATTEMPTS - 1
            _persist(result)
            return

        result.retries = retries
        result.response_text = generation.text
        result.latency_ms = latency_ms
        result.input_tokens = generation.input_tokens
        result.output_tokens = generation.output_tokens

        check_results = checks_service.run_checks(generation.text, case.assertions)
        result.checks = [check.model_dump() for check in check_results]
        result.checks_passed = checks_service.checks_passed(check_results)

        judge_prompt = judge_service.build_judge_prompt(
            prompt=prompt,
            expected_behavior=case.expected_behavior,
            response=generation.text,
            reference_answer=case.reference_answer,
        )
        judge_provider, judge_name = adapters.parse_model_id(judge_model_id)
        judge_adapter = adapters.get_adapter(judge_provider)
        try:
            judge_generation, _ = await with_retries(
                lambda: judge_adapter.generate(judge_name, judge_prompt, settings.judge_max_tokens)
            )
            parsed = judge_service.parse_judge_response(judge_generation.text)
            result.judge_scores = {
                "correctness": parsed.correctness,
                "relevance": parsed.relevance,
                "instruction_following": parsed.instruction_following,
            }
            result.judge_rationale = parsed.rationale
        except AdapterError as exc:
            result.judge_error = f"judge call failed: {exc}"
        except judge_service.JudgeParseError as exc:
            result.judge_error = f"judge response unparseable: {exc}"

        _persist(result)


def _persist(result: CaseResult) -> None:
    session = database.SessionLocal()
    try:
        session.add(result)
        session.commit()
    finally:
        session.close()


def _finish(run_id: int, status: str, error: str | None) -> None:
    session = database.SessionLocal()
    try:
        run = session.get(Run, run_id)
        if run is None:
            return
        run.status = status
        run.error = error
        run.completed_at = utcnow()
        session.commit()
    finally:
        session.close()

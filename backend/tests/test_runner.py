"""Runner tests: concurrency cap, retries, failure handling (SPEC section 8)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import AdapterError
# Aliased so pytest does not try to collect the ORM class as a test class.
from app.models import CaseResult, Run, Suite
from app.models import TestCase as DBTestCase
from app.services.runner import (
    DEFAULT_ATTEMPTS,
    MAX_CONCURRENCY,
    execute_run,
    with_retries,
)
from tests.fakes import DEFAULT_JUDGE_JSON, JUDGE_PROMPT_MARKER, FakeAdapter, split_responder

# ------------------------------------------------------------- with_retries


async def test_with_retries_zero_retries_on_first_success() -> None:
    async def ok() -> str:
        return "hi"

    result, retries = await with_retries(ok)
    assert result == "hi"
    assert retries == 0


async def test_with_retries_counts_transient_failures(no_retry_sleep: None) -> None:
    calls = 0

    async def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise AdapterError("transient")
        return "recovered"

    result, retries = await with_retries(flaky)
    assert result == "recovered"
    assert retries == 2
    assert calls == 3


async def test_with_retries_raises_after_all_attempts(no_retry_sleep: None) -> None:
    calls = 0

    async def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise AdapterError("permanent")

    with pytest.raises(AdapterError):
        await with_retries(always_fails)
    assert calls == DEFAULT_ATTEMPTS


async def test_with_retries_does_not_retry_unexpected_errors() -> None:
    calls = 0

    async def buggy() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("bug, not an AdapterError")

    with pytest.raises(RuntimeError):
        await with_retries(buggy)
    assert calls == 1


# -------------------------------------------------------------- execute_run


async def test_semaphore_caps_concurrency_at_five(
    register_adapter: Callable[..., FakeAdapter],
    seed_suite: Callable[..., Suite],
    make_run: Callable[..., Run],
    db_session: Session,
) -> None:
    adapter = register_adapter(FakeAdapter(delay_s=0.05))
    suite = seed_suite(n_cases=10)
    run = make_run(suite, models=["fake:m1", "fake:m2"])  # 20 tasks

    await execute_run(run.id)

    db_session.expire_all()
    refreshed = db_session.get(Run, run.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.completed_at is not None
    results = db_session.scalars(select(CaseResult).where(CaseResult.run_id == run.id)).all()
    assert len(results) == 20
    assert adapter.calls == 40  # one generation + one judge call per task
    assert adapter.max_active <= MAX_CONCURRENCY
    assert adapter.max_active >= 2  # sanity: tasks really did overlap


async def test_flaky_adapter_retries_twice_then_succeeds(
    register_adapter: Callable[..., FakeAdapter],
    seed_suite: Callable[..., Suite],
    make_run: Callable[..., Run],
    db_session: Session,
    no_retry_sleep: None,
) -> None:
    register_adapter(FakeAdapter(fail_first=2))
    suite = seed_suite(n_cases=1)
    run = make_run(suite, models=["fake:m"])

    await execute_run(run.id)

    db_session.expire_all()
    result = db_session.scalars(select(CaseResult).where(CaseResult.run_id == run.id)).one()
    assert result.retries == 2
    assert result.error is None
    assert result.response_text == DEFAULT_JUDGE_JSON
    assert result.judge_scores == {
        "correctness": 4,
        "relevance": 5,
        "instruction_following": 4,
    }
    assert db_session.get(Run, run.id).status == "completed"


async def test_permanent_generation_failure_records_error_and_run_completes(
    register_adapter: Callable[..., FakeAdapter],
    seed_suite: Callable[..., Suite],
    make_run: Callable[..., Run],
    db_session: Session,
    no_retry_sleep: None,
) -> None:
    adapter = register_adapter(FakeAdapter(fail_always=True))
    suite = seed_suite(n_cases=1, assertions=[{"type": "contains", "value": "x"}])
    run = make_run(suite, models=["fake:m"])

    await execute_run(run.id)

    db_session.expire_all()
    result = db_session.scalars(select(CaseResult).where(CaseResult.run_id == run.id)).one()
    assert result.error is not None and "permanent fake failure" in result.error
    assert result.retries == DEFAULT_ATTEMPTS - 1
    assert result.response_text is None
    assert result.checks_passed is None  # checks skipped on generation failure
    assert result.judge_scores is None
    assert result.judge_error is None  # judge never ran
    assert adapter.calls == DEFAULT_ATTEMPTS  # generation attempts only, no judge call
    refreshed = db_session.get(Run, run.id)
    assert refreshed.status == "completed"  # run finishes even with errored cases
    assert refreshed.completed_at is not None


async def test_judge_parse_failure_sets_judge_error(
    register_adapter: Callable[..., FakeAdapter],
    seed_suite: Callable[..., Suite],
    make_run: Callable[..., Run],
    db_session: Session,
) -> None:
    register_adapter(
        FakeAdapter(respond=split_responder("model answer", judge_text="certainly not json"))
    )
    suite = seed_suite(n_cases=1, assertions=[{"type": "contains", "value": "answer"}])
    run = make_run(suite, models=["fake:m"])

    await execute_run(run.id)

    db_session.expire_all()
    result = db_session.scalars(select(CaseResult).where(CaseResult.run_id == run.id)).one()
    assert result.response_text == "model answer"
    assert result.checks_passed is True  # checks still ran before judging
    assert result.judge_scores is None
    assert result.judge_error is not None and "unparseable" in result.judge_error
    assert db_session.get(Run, run.id).status == "completed"


async def test_checks_recorded_and_empty_assertions_yield_null(
    register_adapter: Callable[..., FakeAdapter],
    seed_suite: Callable[..., Suite],
    make_run: Callable[..., Run],
    db_session: Session,
) -> None:
    register_adapter(FakeAdapter(respond=split_responder("The answer is 42.")))
    suite = seed_suite(n_cases=2, assertions=[{"type": "contains", "value": "42"}])
    cases = db_session.scalars(
        select(DBTestCase).where(DBTestCase.suite_id == suite.id).order_by(DBTestCase.id)
    ).all()
    cases[1].assertions = []
    db_session.commit()
    run = make_run(suite, models=["fake:m"])

    await execute_run(run.id)

    db_session.expire_all()
    results = {
        r.case_id: r
        for r in db_session.scalars(select(CaseResult).where(CaseResult.run_id == run.id))
    }
    with_checks = results[cases[0].id]
    assert with_checks.checks_passed is True
    assert len(with_checks.checks) == 1
    assert with_checks.checks[0]["type"] == "contains"
    assert with_checks.checks[0]["passed"] is True
    without_checks = results[cases[1].id]
    assert without_checks.checks == []
    assert without_checks.checks_passed is None


async def test_prompt_template_is_applied_to_generation_and_judge(
    register_adapter: Callable[..., FakeAdapter],
    seed_suite: Callable[..., Suite],
    make_run: Callable[..., Run],
    db_session: Session,
) -> None:
    adapter = register_adapter(FakeAdapter())
    suite = seed_suite(n_cases=1)
    run = make_run(suite, models=["fake:m"], prompt_template="Answer briefly: {prompt}")

    await execute_run(run.id)

    generation_prompts = [p for p in adapter.prompts if JUDGE_PROMPT_MARKER not in p]
    assert generation_prompts == ["Answer briefly: Prompt number 0"]
    judge_prompts = [p for p in adapter.prompts if JUDGE_PROMPT_MARKER in p]
    assert len(judge_prompts) == 1
    assert "Answer briefly: Prompt number 0" in judge_prompts[0]


async def test_execute_run_with_unknown_run_id_is_a_noop(db_session: Session) -> None:
    await execute_run(99999)
    assert db_session.scalars(select(CaseResult)).all() == []

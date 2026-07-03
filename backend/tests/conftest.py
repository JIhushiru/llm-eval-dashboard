"""Shared fixtures: fresh temp-file SQLite per test, TestClient, fake-adapter helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import adapters, database
from app.config import get_settings
from app.models import CaseResult, Run, Suite, TestCase, utcnow
from tests.fakes import FakeAdapter


@pytest.fixture(autouse=True)
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the whole app (env + engine + session factory) at a fresh temp DB.

    API keys are forced to "" so provider availability is deterministic even if the
    developer has a real .env / environment keys.
    """
    monkeypatch.setenv("EVALFORGE_DB_PATH", str(tmp_path / "evalforge_test.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    engine = database._make_engine()
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(
        database,
        "SessionLocal",
        sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
    )
    database.init_db()
    yield
    engine.dispose()  # release the SQLite file handle so tmp_path can be cleaned on Windows
    get_settings.cache_clear()


@pytest.fixture
def db_session(temp_db: None) -> Iterator[Session]:
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(temp_db: None) -> Iterator[TestClient]:
    from app.database import get_db
    from app.main import app

    def _get_db() -> Iterator[Session]:
        db = database.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def register_adapter(monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeAdapter]:
    """Install a FakeAdapter under a provider name (default "fake") for this test."""

    def _register(adapter: FakeAdapter, provider: str = "fake") -> FakeAdapter:
        monkeypatch.setitem(adapters._ADAPTERS, provider, adapter)
        if provider not in adapters.PROVIDERS:
            monkeypatch.setattr(adapters, "PROVIDERS", (*adapters.PROVIDERS, provider))
        return adapter

    return _register


@pytest.fixture
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the runner's exponential-backoff sleeps instantaneous."""

    async def _instant(_delay: float) -> None:
        return None

    monkeypatch.setattr("app.services.runner.asyncio.sleep", _instant)


@pytest.fixture
def seed_suite(db_session: Session) -> Callable[..., Suite]:
    def _make(
        n_cases: int = 1,
        assertions: list[dict[str, object]] | None = None,
        reference_answer: str | None = None,
    ) -> Suite:
        suite = Suite(name=f"suite-{uuid4().hex[:8]}", description="test suite")
        db_session.add(suite)
        db_session.flush()
        for i in range(n_cases):
            db_session.add(
                TestCase(
                    suite_id=suite.id,
                    prompt=f"Prompt number {i}",
                    expected_behavior=f"Expected behavior {i}",
                    reference_answer=reference_answer,
                    tags=["test"],
                    assertions=list(assertions) if assertions else [],
                )
            )
        db_session.commit()
        return suite

    return _make


@pytest.fixture
def make_run(db_session: Session) -> Callable[..., Run]:
    """A pending run row, ready to hand to execute_run()."""

    def _make(
        suite: Suite,
        models: list[str],
        judge_model: str = "fake:judge",
        prompt_version: str = "v1",
        prompt_template: str | None = None,
    ) -> Run:
        run = Run(
            suite_id=suite.id,
            prompt_version=prompt_version,
            prompt_template=prompt_template,
            models=list(models),
            judge_model=judge_model,
            status="pending",
        )
        db_session.add(run)
        db_session.commit()
        return run

    return _make


@pytest.fixture
def make_completed_run(db_session: Session) -> Callable[..., Run]:
    """A synthetic completed run with judge-scored results (for compare/history tests)."""

    def _make(
        suite: Suite,
        model: str,
        score_triples: list[tuple[int, int, int]],
        prompt_version: str = "v1",
        days_ago: float = 0.0,
    ) -> Run:
        cases = db_session.scalars(
            select(TestCase).where(TestCase.suite_id == suite.id).order_by(TestCase.id)
        ).all()
        created = utcnow() - timedelta(days=days_ago)
        run = Run(
            suite_id=suite.id,
            prompt_version=prompt_version,
            models=[model],
            judge_model="fake:judge",
            status="completed",
            created_at=created,
            completed_at=created + timedelta(minutes=5),
        )
        db_session.add(run)
        db_session.flush()
        for case, (correctness, relevance, instruction) in zip(cases, score_triples):
            db_session.add(
                CaseResult(
                    run_id=run.id,
                    case_id=case.id,
                    model=model,
                    response_text=f"[synthetic] response for case {case.id}",
                    latency_ms=800.0,
                    input_tokens=50,
                    output_tokens=30,
                    retries=0,
                    checks=[],
                    checks_passed=None,
                    judge_scores={
                        "correctness": correctness,
                        "relevance": relevance,
                        "instruction_following": instruction,
                    },
                    judge_rationale="synthetic rationale",
                )
            )
        db_session.commit()
        return run

    return _make

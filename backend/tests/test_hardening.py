"""Tests for the opt-in hardening layer: auth gate, rate limiting, pagination,
and Alembic migrations (SPEC section 14)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.config import get_settings
from app.ratelimit import reset_rate_limit_state


def _enable(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


# ---------------- Auth gate ----------------


def test_api_open_when_token_unset(client: TestClient) -> None:
    # Default (conftest forces the token to ""): the gate is a no-op.
    assert client.get("/api/suites").status_code == 200


def test_token_required_when_set(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch, EVALFORGE_API_TOKEN="s3cret")

    assert client.get("/api/suites").status_code == 401
    assert client.get(
        "/api/suites", headers={"Authorization": "Bearer wrong"}
    ).status_code == 401
    assert client.get(
        "/api/suites", headers={"Authorization": "Bearer s3cret"}
    ).status_code == 200


def test_non_ascii_token_is_rejected_not_500(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A non-ASCII candidate token (only transmittable via the URL-encoded
    # ?token= query param — HTTP headers are latin-1) must fall through to 401,
    # never crash to 500. secrets.compare_digest raises TypeError on non-ASCII
    # str, so the compare is done on bytes.
    _enable(monkeypatch, EVALFORGE_API_TOKEN="s3cret")
    assert client.get("/api/suites?token=café").status_code == 401
    # And a matching non-ASCII token still authenticates (bytes compare).
    _enable(monkeypatch, EVALFORGE_API_TOKEN="café")
    assert client.get("/api/suites?token=café").status_code == 200


def test_health_stays_open_under_auth(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable(monkeypatch, EVALFORGE_API_TOKEN="s3cret")
    assert client.get("/api/health").status_code == 200


def test_export_link_accepts_token_query_param(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, register_adapter
) -> None:
    # A run to export, created before enabling auth (uses the fake adapter path).
    from tests.fakes import FakeAdapter, split_responder

    register_adapter(FakeAdapter(respond=split_responder("hi")))
    suite_id = client.post("/api/suites", json={"name": f"S-{uuid4().hex[:6]}"}).json()["id"]
    client.post(
        f"/api/suites/{suite_id}/cases",
        json={"prompt": "p", "expected_behavior": "e"},
    )
    run = client.post(
        "/api/runs",
        json={"suite_id": suite_id, "models": ["fake:m"], "prompt_version": "v1", "judge_model": "fake:j"},
    ).json()

    _enable(monkeypatch, EVALFORGE_API_TOKEN="s3cret")
    run_id = run["id"]
    # No credentials at all -> rejected.
    assert client.get(f"/api/runs/{run_id}/export.csv").status_code == 401
    # Token as a query param (how the <a href> download links pass it) -> ok.
    assert client.get(f"/api/runs/{run_id}/export.csv?token=s3cret").status_code == 200


# ---------------- Rate limiting ----------------


def test_rate_limit_returns_429_over_the_cap(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_rate_limit_state()
    _enable(monkeypatch, EVALFORGE_RATE_LIMIT_PER_MINUTE="3")

    codes = [client.get("/api/backends").status_code for _ in range(3)]
    assert codes == [200, 200, 200]
    blocked = client.get("/api/backends")
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}


def test_health_is_exempt_from_rate_limit(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_rate_limit_state()
    _enable(monkeypatch, EVALFORGE_RATE_LIMIT_PER_MINUTE="2")
    # Well over the cap, but health is exempt.
    for _ in range(6):
        assert client.get("/api/health").status_code == 200


# ---------------- Pagination ----------------


def test_suites_pagination_and_total_header(client: TestClient) -> None:
    for i in range(5):
        assert client.post("/api/suites", json={"name": f"suite-{i}-{uuid4().hex[:4]}"}).status_code == 201

    first = client.get("/api/suites?limit=2&offset=0")
    assert first.status_code == 200
    assert first.headers["X-Total-Count"] == "5"
    assert len(first.json()) == 2

    third = client.get("/api/suites?limit=2&offset=4")
    assert len(third.json()) == 1  # 5 total, last page has the remainder

    # No params -> full list preserved (backward compatible).
    assert len(client.get("/api/suites").json()) == 5


def test_runs_pagination(
    client: TestClient, seed_suite, make_completed_run
) -> None:
    suite = seed_suite(n_cases=2)
    for v in ("v1", "v2", "v3"):
        make_completed_run(suite, "fake:m", [(4, 4, 4), (5, 5, 5)], prompt_version=v)

    page = client.get(f"/api/runs?suite_id={suite.id}&limit=2&offset=0")
    assert page.status_code == 200
    assert page.headers["X-Total-Count"] == "3"
    assert len(page.json()) == 2
    # Newest-first ordering preserved under pagination.
    assert page.json()[0]["prompt_version"] == "v3"


# ---------------- Migrations ----------------


def test_alembic_upgrade_builds_full_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.database import run_migrations

    fresh = tmp_path / "migrated.db"
    monkeypatch.setenv("EVALFORGE_DB_PATH", str(fresh))
    get_settings.cache_clear()

    run_migrations()

    engine = create_engine(f"sqlite:///{fresh.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {"suites", "test_cases", "runs", "case_results"} <= tables
    assert "alembic_version" in tables

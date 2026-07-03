"""API-level tests through the FastAPI TestClient (SPEC sections 9 & 12)."""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.ollama_adapter import OllamaAdapter
from app.config import get_settings
# Aliased so pytest does not try to collect the ORM class as a test class.
from app.models import CaseResult, Run, Suite
from app.models import TestCase as DBTestCase
from tests.fakes import FakeAdapter, split_responder

HIGH_TRIPLES: list[tuple[int, int, int]] = [(5, 5, 5), (4, 5, 5), (5, 4, 5), (5, 5, 4), (4, 5, 4)]
LOW_TRIPLES: list[tuple[int, int, int]] = [(1, 1, 1), (1, 2, 1), (2, 1, 1), (1, 1, 2), (2, 2, 1)]


def _poll_run(client: TestClient, run_id: int, timeout_s: float = 5.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        body: dict[str, Any] = response.json()
        if body["status"] in ("completed", "failed") or time.monotonic() > deadline:
            return body
        time.sleep(0.05)


def _launch_completed_run(
    client: TestClient, register_adapter: Callable[..., FakeAdapter]
) -> int:
    """Two-case suite run against a fake model; returns the completed run id."""
    register_adapter(FakeAdapter(respond=split_responder("The answer is 42.")))
    suite_id = client.post(
        "/api/suites", json={"name": f"E2E-{uuid4().hex[:6]}"}
    ).json()["id"]
    assert (
        client.post(
            f"/api/suites/{suite_id}/cases",
            json={
                "prompt": "What is 6 times 7?",
                "expected_behavior": "States that the answer is 42.",
                "assertions": [{"type": "contains", "value": "42"}],
            },
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/suites/{suite_id}/cases",
            json={"prompt": "Say hello.", "expected_behavior": "A greeting."},
        ).status_code
        == 201
    )
    created = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["fake:model-a"],
            "prompt_version": "v1",
            "judge_model": "fake:judge",
        },
    )
    assert created.status_code == 201
    run_id: int = created.json()["id"]
    detail = _poll_run(client, run_id)
    assert detail["status"] == "completed"
    return run_id


# -------------------------------------------------------------------- basics


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_backends_reports_availability(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def probe_down(self: OllamaAdapter) -> tuple[bool, str, list[str]]:
        return False, "ollama unreachable (test stub)", []

    monkeypatch.setattr(OllamaAdapter, "_probe", probe_down)
    body = client.get("/api/backends").json()
    by_provider = {b["provider"]: b for b in body}
    assert set(by_provider) == {"anthropic", "openai", "ollama"}
    assert by_provider["anthropic"]["available"] is False
    assert by_provider["anthropic"]["reason"]
    assert by_provider["anthropic"]["models"] == [
        "claude-opus-4-8",
        "claude-sonnet-5",
        "claude-haiku-4-5",
    ]
    assert by_provider["openai"]["available"] is False
    assert by_provider["openai"]["models"] == ["gpt-4o", "gpt-4o-mini"]
    assert by_provider["ollama"]["available"] is False
    assert by_provider["ollama"]["models"] == []

    async def probe_up(self: OllamaAdapter) -> tuple[bool, str, list[str]]:
        return True, "ollama reachable (test stub)", ["llama3.1:latest"]

    monkeypatch.setattr(OllamaAdapter, "_probe", probe_up)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    body = client.get("/api/backends").json()
    by_provider = {b["provider"]: b for b in body}
    assert by_provider["anthropic"]["available"] is True
    assert by_provider["ollama"]["available"] is True
    assert by_provider["ollama"]["models"] == ["llama3.1:latest"]


# ---------------------------------------------------------------- suite CRUD


def test_suite_crud_flow(client: TestClient) -> None:
    created = client.post("/api/suites", json={"name": "Suite One", "description": "first"})
    assert created.status_code == 201
    suite = created.json()
    assert suite["name"] == "Suite One"
    assert suite["description"] == "first"
    assert "created_at" in suite

    listed = client.get("/api/suites").json()
    assert [s["name"] for s in listed] == ["Suite One"]
    assert listed[0]["case_count"] == 0
    assert listed[0]["run_count"] == 0

    detail = client.get(f"/api/suites/{suite['id']}").json()
    assert detail["cases"] == []

    updated = client.put(f"/api/suites/{suite['id']}", json={"description": "second"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "second"
    assert updated.json()["name"] == "Suite One"  # partial update leaves name intact

    assert client.get("/api/suites/9999").status_code == 404
    assert client.put("/api/suites/9999", json={"name": "x"}).status_code == 404

    assert client.delete(f"/api/suites/{suite['id']}").status_code == 204
    assert client.get(f"/api/suites/{suite['id']}").status_code == 404
    assert client.delete(f"/api/suites/{suite['id']}").status_code == 404


def test_duplicate_suite_name_is_409(client: TestClient) -> None:
    assert client.post("/api/suites", json={"name": "Dup"}).status_code == 201
    duplicate = client.post("/api/suites", json={"name": "Dup"})
    assert duplicate.status_code == 409
    assert "Dup" in duplicate.json()["detail"]

    other_id = client.post("/api/suites", json={"name": "Other"}).json()["id"]
    rename = client.put(f"/api/suites/{other_id}", json={"name": "Dup"})
    assert rename.status_code == 409


def test_suite_delete_cascades_to_cases_runs_results(
    client: TestClient,
    seed_suite: Callable[..., Suite],
    make_completed_run: Callable[..., Run],
    db_session: Session,
) -> None:
    suite = seed_suite(n_cases=2)
    make_completed_run(suite, "fake:m", [(4, 4, 4), (5, 5, 5)])
    assert client.delete(f"/api/suites/{suite.id}").status_code == 204
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(DBTestCase)) == 0
    assert db_session.scalar(select(func.count()).select_from(Run)) == 0
    assert db_session.scalar(select(func.count()).select_from(CaseResult)) == 0


# ----------------------------------------------------------------- case CRUD


def test_case_crud_flow(client: TestClient) -> None:
    suite_id = client.post("/api/suites", json={"name": "Cases"}).json()["id"]
    payload = {
        "prompt": "Return the answer as JSON.",
        "expected_behavior": "Valid JSON with key 'answer'.",
        "reference_answer": '{"answer": 42}',
        "tags": ["json", "extraction"],
        "assertions": [
            {"type": "json_valid"},
            {"type": "contains", "value": "answer", "case_sensitive": True},
        ],
    }
    created = client.post(f"/api/suites/{suite_id}/cases", json=payload)
    assert created.status_code == 201
    case = created.json()
    assert case["suite_id"] == suite_id
    assert case["tags"] == ["json", "extraction"]
    assert [a["type"] for a in case["assertions"]] == ["json_valid", "contains"]
    assert case["assertions"][1]["case_sensitive"] is True

    assert client.post("/api/suites/9999/cases", json=payload).status_code == 404

    updated = client.put(f"/api/cases/{case['id']}", json={"tags": ["only-tags"]})
    assert updated.status_code == 200
    body = updated.json()
    assert body["tags"] == ["only-tags"]
    assert body["prompt"] == payload["prompt"]  # untouched fields survive partial update
    assert len(body["assertions"]) == 2

    assert client.get("/api/suites").json()[0]["case_count"] == 1

    assert client.delete(f"/api/cases/{case['id']}").status_code == 204
    assert client.delete(f"/api/cases/{case['id']}").status_code == 404
    assert client.put(f"/api/cases/{case['id']}", json={"tags": []}).status_code == 404


# -------------------------------------------------------------- run creation


def test_run_creation_validations(
    client: TestClient, register_adapter: Callable[..., FakeAdapter]
) -> None:
    register_adapter(FakeAdapter())
    suite_id = client.post("/api/suites", json={"name": "Runs"}).json()["id"]

    missing_suite = client.post(
        "/api/runs", json={"suite_id": 9999, "models": ["fake:m"], "prompt_version": "v1"}
    )
    assert missing_suite.status_code == 400

    no_cases = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["fake:m"],
            "prompt_version": "v1",
            "judge_model": "fake:judge",
        },
    )
    assert no_cases.status_code == 400
    assert "no test cases" in no_cases.json()["detail"]

    client.post(
        f"/api/suites/{suite_id}/cases",
        json={"prompt": "Hi", "expected_behavior": "Greets"},
    )

    bad_template = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["fake:m"],
            "prompt_version": "v1",
            "prompt_template": "missing the placeholder",
            "judge_model": "fake:judge",
        },
    )
    assert bad_template.status_code == 400
    assert "{prompt}" in bad_template.json()["detail"]

    malformed = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["not-a-model-id"],
            "prompt_version": "v1",
            "judge_model": "fake:judge",
        },
    )
    assert malformed.status_code == 400

    unknown_provider = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["mystery:m"],
            "prompt_version": "v1",
            "judge_model": "fake:judge",
        },
    )
    assert unknown_provider.status_code == 400
    assert "mystery" in unknown_provider.json()["detail"]

    # provider exists but has no API key configured in tests
    unavailable = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["anthropic:claude-opus-4-8"],
            "prompt_version": "v1",
            "judge_model": "fake:judge",
        },
    )
    assert unavailable.status_code == 400
    assert "not available" in unavailable.json()["detail"]

    # default judge model is anthropic:... which is also unavailable here
    judge_unavailable = client.post(
        "/api/runs",
        json={"suite_id": suite_id, "models": ["fake:m"], "prompt_version": "v1"},
    )
    assert judge_unavailable.status_code == 400

    empty_models = client.post(
        "/api/runs", json={"suite_id": suite_id, "models": [], "prompt_version": "v1"}
    )
    assert empty_models.status_code == 422  # schema-level min_length=1


# ------------------------------------------------------------ run happy path


def test_run_happy_path_end_to_end(
    client: TestClient, register_adapter: Callable[..., FakeAdapter]
) -> None:
    adapter = register_adapter(FakeAdapter(respond=split_responder("The answer is 42.")))
    suite_id = client.post("/api/suites", json={"name": "Happy"}).json()["id"]
    client.post(
        f"/api/suites/{suite_id}/cases",
        json={
            "prompt": "What is 6 times 7?",
            "expected_behavior": "States that the answer is 42.",
            "assertions": [{"type": "contains", "value": "42"}],
        },
    )
    client.post(
        f"/api/suites/{suite_id}/cases",
        json={"prompt": "Say hello.", "expected_behavior": "A greeting."},
    )

    created = client.post(
        "/api/runs",
        json={
            "suite_id": suite_id,
            "models": ["fake:model-a"],
            "prompt_version": "v1",
            "judge_model": "fake:judge",
        },
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "pending"
    assert run["progress"] == {"total": 2, "done": 0}
    assert run["judge_model"] == "fake:judge"

    detail = _poll_run(client, run["id"])
    assert detail["status"] == "completed"
    assert detail["completed_at"] is not None
    assert detail["error"] is None
    assert detail["progress"] == {"total": 2, "done": 2}

    results = detail["results"]
    assert len(results) == 2
    by_prompt = {r["prompt"]: r for r in results}
    checked = by_prompt["What is 6 times 7?"]
    assert checked["response_text"] == "The answer is 42."
    assert checked["checks_passed"] is True
    assert checked["checks"][0]["type"] == "contains"
    assert checked["checks"][0]["passed"] is True
    assert checked["judge_scores"] == {
        "correctness": 4,
        "relevance": 5,
        "instruction_following": 4,
    }
    assert checked["overall"] == pytest.approx(13 / 3)
    assert checked["retries"] == 0
    assert checked["latency_ms"] is not None
    unchecked = by_prompt["Say hello."]
    assert unchecked["checks"] == []
    assert unchecked["checks_passed"] is None

    stats_entries = detail["stats"]
    assert len(stats_entries) == 1
    entry = stats_entries[0]
    assert entry["model"] == "fake:model-a"
    assert entry["n_scored"] == 2
    assert entry["mean"] == pytest.approx(13 / 3)
    assert entry["std"] == pytest.approx(0.0)
    assert entry["ci_low"] == pytest.approx(13 / 3)  # identical scores -> degenerate CI
    assert entry["ci_high"] == pytest.approx(13 / 3)
    assert entry["checks_pass_rate"] == pytest.approx(1.0)
    assert entry["avg_latency_ms"] is not None and entry["avg_latency_ms"] >= 0
    assert entry["dimensions"] == {
        "correctness": 4.0,
        "relevance": 5.0,
        "instruction_following": 4.0,
    }

    listed = client.get("/api/runs", params={"suite_id": suite_id}).json()
    assert [r["id"] for r in listed] == [run["id"]]
    assert listed[0]["progress"] == {"total": 2, "done": 2}

    assert adapter.calls == 4  # 2 generations + 2 judge calls
    assert client.get("/api/runs/9999").status_code == 404


def test_runs_list_newest_first_and_suite_filter(
    client: TestClient,
    seed_suite: Callable[..., Suite],
    make_completed_run: Callable[..., Run],
) -> None:
    suite = seed_suite(n_cases=2)
    older = make_completed_run(suite, "fake:m", [(4, 4, 4), (4, 4, 4)], "v1", days_ago=2)
    newer = make_completed_run(suite, "fake:m", [(5, 5, 5), (5, 5, 5)], "v2", days_ago=1)
    other = seed_suite(n_cases=1)
    make_completed_run(other, "fake:m", [(3, 3, 3)], "x1")

    assert len(client.get("/api/runs").json()) == 3
    filtered = client.get("/api/runs", params={"suite_id": suite.id}).json()
    assert [r["id"] for r in filtered] == [newer.id, older.id]
    assert filtered[0]["suite_name"] == suite.name
    assert client.get("/api/runs", params={"suite_id": 9999}).json() == []


# ------------------------------------------------------------------- exports


def test_export_csv(client: TestClient, register_adapter: Callable[..., FakeAdapter]) -> None:
    run_id = _launch_completed_run(client, register_adapter)
    response = client.get(f"/api/runs/{run_id}/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == [
        "run_id",
        "prompt_version",
        "case_id",
        "model",
        "prompt",
        "expected_behavior",
        "response_text",
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "retries",
        "checks_passed",
        "correctness",
        "relevance",
        "instruction_following",
        "overall",
        "judge_rationale",
        "error",
    ]
    data = rows[1:]
    assert len(data) == 2  # one row per case_result
    first = dict(zip(rows[0], data[0]))
    assert first["run_id"] == str(run_id)
    assert first["prompt_version"] == "v1"
    assert first["model"] == "fake:model-a"
    assert first["prompt"] == "What is 6 times 7?"
    assert first["response_text"] == "The answer is 42."
    assert first["checks_passed"] == "True"
    assert first["correctness"] == "4"
    assert first["relevance"] == "5"
    assert first["instruction_following"] == "4"
    assert first["overall"] == "4.3333"
    assert first["error"] == ""
    second = dict(zip(rows[0], data[1]))
    assert second["checks_passed"] == ""  # no assertions -> null -> empty cell

    assert client.get("/api/runs/9999/export.csv").status_code == 404


def test_export_json(client: TestClient, register_adapter: Callable[..., FakeAdapter]) -> None:
    run_id = _launch_completed_run(client, register_adapter)
    response = client.get(f"/api/runs/{run_id}/export.json")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    body = response.json()
    assert body["id"] == run_id
    assert body["status"] == "completed"
    assert len(body["results"]) == 2
    assert body["stats"][0]["n_scored"] == 2
    assert body["results"][0]["judge_scores"]["relevance"] == 5

    assert client.get("/api/runs/9999/export.json").status_code == 404


# ------------------------------------------------------------------- compare


def test_compare_endpoint_returns_tests_and_cases(
    client: TestClient,
    seed_suite: Callable[..., Suite],
    make_completed_run: Callable[..., Run],
) -> None:
    suite = seed_suite(n_cases=5)
    run_a = make_completed_run(suite, "fake:m", HIGH_TRIPLES, "v1", days_ago=3)
    run_b = make_completed_run(suite, "fake:m", LOW_TRIPLES, "v2", days_ago=1)

    response = client.get("/api/compare", params={"run_a": run_a.id, "run_b": run_b.id})
    assert response.status_code == 200
    body = response.json()
    assert body["run_a"]["id"] == run_a.id
    assert body["run_b"]["id"] == run_b.id
    assert body["shared_models"] == ["fake:m"]

    assert len(body["tests"]) == 1
    test = body["tests"][0]
    assert test["model"] == "fake:m"
    assert test["n_a"] == 5
    assert test["n_b"] == 5
    assert test["mean_a"] > 4.0
    assert test["mean_b"] < 2.0
    assert test["u_statistic"] == 0.0  # completely disjoint overall scores
    assert test["p_value"] < 0.05
    assert "difference" in test["interpretation"]

    assert len(body["cases"]) == 5
    for case in body["cases"]:
        side = case["results"]["fake:m"]
        assert side["a"] is not None
        assert side["b"] is not None
        assert side["a"]["overall"] > side["b"]["overall"]
        assert case["prompt"]
        assert case["expected_behavior"]


def test_compare_validation_errors(
    client: TestClient,
    seed_suite: Callable[..., Suite],
    make_completed_run: Callable[..., Run],
    make_run: Callable[..., Run],
) -> None:
    suite = seed_suite(n_cases=2)
    other = seed_suite(n_cases=2)
    completed = make_completed_run(suite, "fake:m", [(4, 4, 4), (5, 5, 5)])
    foreign = make_completed_run(other, "fake:m", [(3, 3, 3), (2, 2, 2)])
    pending = make_run(suite, models=["fake:m"])  # never executed

    different_suites = client.get(
        "/api/compare", params={"run_a": completed.id, "run_b": foreign.id}
    )
    assert different_suites.status_code == 400
    not_completed = client.get(
        "/api/compare", params={"run_a": completed.id, "run_b": pending.id}
    )
    assert not_completed.status_code == 400
    missing = client.get("/api/compare", params={"run_a": completed.id, "run_b": 9999})
    assert missing.status_code == 404


# ------------------------------------------------------------------- history


def test_history_flags_constructed_regression(
    client: TestClient,
    seed_suite: Callable[..., Suite],
    make_completed_run: Callable[..., Run],
) -> None:
    suite = seed_suite(n_cases=5)
    make_completed_run(suite, "fake:m", HIGH_TRIPLES, "v1", days_ago=7)
    make_completed_run(suite, "fake:m", LOW_TRIPLES, "v2", days_ago=3)
    make_completed_run(suite, "fake:m", HIGH_TRIPLES, "v3", days_ago=1)
    # only one scored result -> below the 2-result minimum -> no history point
    make_completed_run(suite, "fake:m", HIGH_TRIPLES[:1], "v4", days_ago=0)

    body = client.get(f"/api/suites/{suite.id}/history").json()
    assert len(body["series"]) == 1
    series = body["series"][0]
    assert series["model"] == "fake:m"
    points = series["points"]
    assert [p["prompt_version"] for p in points] == ["v1", "v2", "v3"]
    assert [p["flag"] for p in points] == ["first", "regression", "improvement"]
    assert all(p["n_scored"] == 5 for p in points)
    for point in points:
        assert point["ci_low"] <= point["mean"] <= point["ci_high"]
    assert points[1]["mean"] < points[0]["mean"]

    filtered = client.get(
        f"/api/suites/{suite.id}/history", params={"model": "fake:m"}
    ).json()
    assert len(filtered["series"]) == 1
    no_match = client.get(
        f"/api/suites/{suite.id}/history", params={"model": "other:none"}
    ).json()
    assert no_match["series"] == []
    assert client.get("/api/suites/9999/history").status_code == 404

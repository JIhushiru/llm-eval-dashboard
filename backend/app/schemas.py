"""Pydantic v2 models for every API request/response body."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AssertionType = Literal[
    "contains", "not_contains", "regex", "not_regex", "json_valid", "max_length"
]

RunStatus = Literal["pending", "running", "completed", "failed"]

HistoryFlag = Literal["first", "stable", "regression", "improvement"]


# ---------------------------------------------------------------- assertions

class Assertion(BaseModel):
    type: AssertionType
    value: str | None = None
    case_sensitive: bool = False  # contains / not_contains only
    max_chars: int | None = None  # max_length only


class CheckResult(BaseModel):
    type: str
    passed: bool
    detail: str


class JudgeScores(BaseModel):
    correctness: int
    relevance: int
    instruction_following: int


# -------------------------------------------------------------------- suites

class SuiteCreate(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class SuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class SuiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    created_at: datetime


class SuiteListItem(SuiteOut):
    case_count: int
    run_count: int


# --------------------------------------------------------------------- cases

class CaseCreate(BaseModel):
    prompt: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    reference_answer: str | None = None
    tags: list[str] = Field(default_factory=list)
    assertions: list[Assertion] = Field(default_factory=list)


class CaseUpdate(BaseModel):
    prompt: str | None = Field(default=None, min_length=1)
    expected_behavior: str | None = Field(default=None, min_length=1)
    reference_answer: str | None = None
    tags: list[str] | None = None
    assertions: list[Assertion] | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    suite_id: int
    prompt: str
    expected_behavior: str
    reference_answer: str | None
    tags: list[str]
    assertions: list[Assertion]
    created_at: datetime


class SuiteDetail(SuiteOut):
    cases: list[CaseOut]


# ---------------------------------------------------------------------- runs

class RunCreate(BaseModel):
    suite_id: int
    models: list[str] = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    prompt_template: str | None = None
    judge_model: str | None = None


class Progress(BaseModel):
    total: int
    done: int


class RunListItem(BaseModel):
    id: int
    suite_id: int
    suite_name: str
    prompt_version: str
    models: list[str]
    judge_model: str
    status: RunStatus
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    progress: Progress


class CaseResultOut(BaseModel):
    id: int
    run_id: int
    case_id: int
    model: str
    prompt: str
    expected_behavior: str
    response_text: str | None
    error: str | None
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    retries: int
    checks: list[CheckResult]
    checks_passed: bool | None
    judge_scores: JudgeScores | None
    judge_rationale: str | None
    judge_error: str | None
    overall: float | None  # derived: mean of the three judge dimensions
    created_at: datetime


class DimensionMeans(BaseModel):
    correctness: float
    relevance: float
    instruction_following: float


class ModelStats(BaseModel):
    model: str
    n_scored: int
    mean: float
    std: float
    ci_low: float
    ci_high: float
    checks_pass_rate: float | None
    avg_latency_ms: float | None
    dimensions: DimensionMeans


class RunDetail(RunListItem):
    prompt_template: str | None
    results: list[CaseResultOut]
    stats: list[ModelStats]


# ------------------------------------------------------------------- compare

class CompareTest(BaseModel):
    model: str
    n_a: int
    n_b: int
    mean_a: float
    mean_b: float
    u_statistic: float
    p_value: float
    interpretation: str


class CompareCaseSide(BaseModel):
    a: CaseResultOut | None
    b: CaseResultOut | None


class CompareCase(BaseModel):
    case_id: int
    prompt: str
    expected_behavior: str
    results: dict[str, CompareCaseSide]


class CompareOut(BaseModel):
    run_a: RunListItem
    run_b: RunListItem
    shared_models: list[str]
    tests: list[CompareTest]
    cases: list[CompareCase]


# ------------------------------------------------------------------- history

class HistoryPoint(BaseModel):
    run_id: int
    prompt_version: str
    created_at: datetime
    mean: float
    ci_low: float
    ci_high: float
    n_scored: int
    flag: HistoryFlag


class HistorySeries(BaseModel):
    model: str
    points: list[HistoryPoint]


class HistoryOut(BaseModel):
    series: list[HistorySeries]


# ------------------------------------------------------------------ backends

class BackendInfo(BaseModel):
    provider: str
    available: bool
    reason: str
    models: list[str]


class HealthOut(BaseModel):
    status: str

"""Run-detail assembly plus CSV/JSON export builders."""

import csv
import io
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CaseResult, Run, TestCase
from app.schemas import (
    CaseResultOut,
    DimensionMeans,
    ModelStats,
    Progress,
    RunDetail,
    RunListItem,
)
from app.services import stats

# Fixed seed so CI numbers are stable across page refreshes.
BOOTSTRAP_SEED = 42

CSV_COLUMNS = [
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


def overall_score(judge_scores: dict[str, int] | None) -> float | None:
    if not judge_scores:
        return None
    return (
        judge_scores["correctness"]
        + judge_scores["relevance"]
        + judge_scores["instruction_following"]
    ) / 3.0


def case_result_out(result: CaseResult) -> CaseResultOut:
    return CaseResultOut(
        id=result.id,
        run_id=result.run_id,
        case_id=result.case_id,
        model=result.model,
        prompt=result.case.prompt,
        expected_behavior=result.case.expected_behavior,
        response_text=result.response_text,
        error=result.error,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        retries=result.retries,
        checks=result.checks or [],
        checks_passed=result.checks_passed,
        judge_scores=result.judge_scores,
        judge_rationale=result.judge_rationale,
        judge_error=result.judge_error,
        overall=overall_score(result.judge_scores),
        created_at=result.created_at,
    )


def run_progress(db: Session, run: Run) -> Progress:
    case_count = (
        db.scalar(
            select(func.count()).select_from(TestCase).where(TestCase.suite_id == run.suite_id)
        )
        or 0
    )
    done = (
        db.scalar(
            select(func.count()).select_from(CaseResult).where(CaseResult.run_id == run.id)
        )
        or 0
    )
    return Progress(total=case_count * len(run.models), done=done)


def run_list_item(db: Session, run: Run) -> RunListItem:
    return RunListItem(
        id=run.id,
        suite_id=run.suite_id,
        suite_name=run.suite.name,
        prompt_version=run.prompt_version,
        models=list(run.models),
        judge_model=run.judge_model,
        status=run.status,
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at,
        progress=run_progress(db, run),
    )


def compute_model_stats(
    results: Sequence[CaseResult], models_order: Sequence[str]
) -> list[ModelStats]:
    by_model: dict[str, list[CaseResult]] = {}
    for result in results:
        by_model.setdefault(result.model, []).append(result)
    ordered = [m for m in models_order if m in by_model] + [
        m for m in by_model if m not in models_order
    ]

    out: list[ModelStats] = []
    for model_id in ordered:
        rows = by_model[model_id]
        scored = [r for r in rows if r.judge_scores is not None]
        if not scored:
            continue
        overalls = [
            (
                r.judge_scores["correctness"]
                + r.judge_scores["relevance"]
                + r.judge_scores["instruction_following"]
            )
            / 3.0
            for r in scored
        ]
        mean, std = stats.mean_std(overalls)
        ci_low, ci_high = stats.bootstrap_ci(overalls, seed=BOOTSTRAP_SEED)
        checked = [r for r in rows if r.checks_passed is not None]
        checks_pass_rate = (
            sum(1 for r in checked if r.checks_passed) / len(checked) if checked else None
        )
        latencies = [r.latency_ms for r in rows if r.latency_ms is not None]
        avg_latency_ms = sum(latencies) / len(latencies) if latencies else None
        dimensions = DimensionMeans(
            correctness=sum(r.judge_scores["correctness"] for r in scored) / len(scored),
            relevance=sum(r.judge_scores["relevance"] for r in scored) / len(scored),
            instruction_following=sum(
                r.judge_scores["instruction_following"] for r in scored
            )
            / len(scored),
        )
        out.append(
            ModelStats(
                model=model_id,
                n_scored=len(scored),
                mean=mean,
                std=std,
                ci_low=ci_low,
                ci_high=ci_high,
                checks_pass_rate=checks_pass_rate,
                avg_latency_ms=avg_latency_ms,
                dimensions=dimensions,
            )
        )
    return out


def build_run_detail(db: Session, run: Run) -> RunDetail:
    results = sorted(run.results, key=lambda r: (r.case_id, r.model))
    base = run_list_item(db, run)
    return RunDetail(
        **base.model_dump(),
        prompt_template=run.prompt_template,
        results=[case_result_out(r) for r in results],
        stats=compute_model_stats(run.results, run.models),
    )


def build_export_json(db: Session, run: Run) -> dict[str, Any]:
    return build_run_detail(db, run).model_dump(mode="json")


def build_export_csv(run: Run) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for result in sorted(run.results, key=lambda r: (r.case_id, r.model)):
        scores = result.judge_scores or {}
        overall = overall_score(result.judge_scores)
        writer.writerow(
            [
                run.id,
                run.prompt_version,
                result.case_id,
                result.model,
                result.case.prompt,
                result.case.expected_behavior,
                _cell(result.response_text),
                _cell(result.latency_ms),
                _cell(result.input_tokens),
                _cell(result.output_tokens),
                result.retries,
                _cell(result.checks_passed),
                _cell(scores.get("correctness")),
                _cell(scores.get("relevance")),
                _cell(scores.get("instruction_following")),
                _cell(round(overall, 4) if overall is not None else None),
                _cell(result.judge_rationale),
                _cell(result.error),
            ]
        )
    return buffer.getvalue()


def _cell(value: object) -> object:
    return "" if value is None else value

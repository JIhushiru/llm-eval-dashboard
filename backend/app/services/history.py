"""Score-over-time series per (suite, model) with regression flags."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Run
from app.schemas import HistoryOut, HistoryPoint, HistorySeries
from app.services import stats

# Fixed seed so CI numbers are stable across page refreshes.
BOOTSTRAP_SEED = 42


def _overall(judge_scores: dict[str, int]) -> float:
    return (
        judge_scores["correctness"]
        + judge_scores["relevance"]
        + judge_scores["instruction_following"]
    ) / 3.0


def suite_history(db: Session, suite_id: int, model: str | None = None) -> HistoryOut:
    runs = (
        db.scalars(
            select(Run)
            .where(Run.suite_id == suite_id, Run.status == "completed")
            .order_by(Run.created_at, Run.id)
        )
        .all()
    )

    series_models: list[str] = []
    for run in runs:
        for model_id in run.models:
            if model is not None and model_id != model:
                continue
            if model_id not in series_models:
                series_models.append(model_id)

    series: list[HistorySeries] = []
    for model_id in series_models:
        points: list[HistoryPoint] = []
        previous: HistoryPoint | None = None
        for run in runs:
            if model_id not in run.models:
                continue
            overalls = [
                _overall(result.judge_scores)
                for result in run.results
                if result.model == model_id and result.judge_scores is not None
            ]
            if len(overalls) < 2:
                continue
            mean, _ = stats.mean_std(overalls)
            ci_low, ci_high = stats.bootstrap_ci(overalls, seed=BOOTSTRAP_SEED)
            flag = "first" if previous is None else _flag(previous, mean, (ci_low, ci_high))
            point = HistoryPoint(
                run_id=run.id,
                prompt_version=run.prompt_version,
                created_at=run.created_at,
                mean=mean,
                ci_low=ci_low,
                ci_high=ci_high,
                n_scored=len(overalls),
                flag=flag,
            )
            points.append(point)
            previous = point
        if points:
            series.append(HistorySeries(model=model_id, points=points))
    return HistoryOut(series=series)


def _flag(previous: HistoryPoint, mean: float, ci: tuple[float, float]) -> str:
    if not stats.ci_overlap((previous.ci_low, previous.ci_high), ci):
        if mean < previous.mean:
            return "regression"
        if mean > previous.mean:
            return "improvement"
    return "stable"

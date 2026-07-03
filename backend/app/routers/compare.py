"""Side-by-side comparison of two completed runs of the same suite."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CaseResult, Run, TestCase
from app.schemas import CompareCase, CompareCaseSide, CompareOut, CompareTest
from app.services import export, stats

router = APIRouter(prefix="/api", tags=["compare"])


@router.get("/compare", response_model=CompareOut)
def compare_runs(run_a: int, run_b: int, db: Session = Depends(get_db)) -> CompareOut:
    a = db.get(Run, run_a)
    if a is None:
        raise HTTPException(status_code=404, detail=f"run {run_a} not found")
    b = db.get(Run, run_b)
    if b is None:
        raise HTTPException(status_code=404, detail=f"run {run_b} not found")
    if a.status != "completed" or b.status != "completed":
        raise HTTPException(status_code=400, detail="both runs must be completed")
    if a.suite_id != b.suite_id:
        raise HTTPException(status_code=400, detail="runs must belong to the same suite")

    shared_models = [m for m in a.models if m in b.models]

    tests: list[CompareTest] = []
    for model_id in shared_models:
        scores_a = _overall_scores(a.results, model_id)
        scores_b = _overall_scores(b.results, model_id)
        if not scores_a or not scores_b:
            continue
        mw = stats.mann_whitney_u(scores_a, scores_b)
        tests.append(
            CompareTest(
                model=model_id,
                n_a=len(scores_a),
                n_b=len(scores_b),
                mean_a=stats.mean_std(scores_a)[0],
                mean_b=stats.mean_std(scores_b)[0],
                u_statistic=mw.u_statistic,
                p_value=mw.p_value,
                interpretation=stats.interpret_p_value(mw.p_value),
            )
        )

    results_a = {(r.case_id, r.model): r for r in a.results}
    results_b = {(r.case_id, r.model): r for r in b.results}
    case_ids = sorted({r.case_id for r in a.results} | {r.case_id for r in b.results})

    cases: list[CompareCase] = []
    for case_id in case_ids:
        case = db.get(TestCase, case_id)
        if case is None:
            continue
        per_model: dict[str, CompareCaseSide] = {}
        for model_id in shared_models:
            result_a = results_a.get((case_id, model_id))
            result_b = results_b.get((case_id, model_id))
            per_model[model_id] = CompareCaseSide(
                a=export.case_result_out(result_a) if result_a is not None else None,
                b=export.case_result_out(result_b) if result_b is not None else None,
            )
        cases.append(
            CompareCase(
                case_id=case_id,
                prompt=case.prompt,
                expected_behavior=case.expected_behavior,
                results=per_model,
            )
        )

    return CompareOut(
        run_a=export.run_list_item(db, a),
        run_b=export.run_list_item(db, b),
        shared_models=shared_models,
        tests=tests,
        cases=cases,
    )


def _overall_scores(results: list[CaseResult], model_id: str) -> list[float]:
    scores: list[float] = []
    for result in results:
        if result.model != model_id:
            continue
        overall = export.overall_score(result.judge_scores)
        if overall is not None:
            scores.append(overall)
    return scores

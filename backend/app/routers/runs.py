"""Run creation, listing, detail, and CSV/JSON export."""

import json

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import adapters
from app.config import get_settings
from app.database import get_db
from app.models import Run, Suite, TestCase
from app.schemas import RunCreate, RunDetail, RunListItem
from app.services import export
from app.services.runner import execute_run

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _get_run_or_404(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return run


@router.post("", response_model=RunListItem, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> RunListItem:
    suite = db.get(Suite, payload.suite_id)
    if suite is None:
        raise HTTPException(status_code=400, detail=f"suite {payload.suite_id} does not exist")
    case_count = db.scalar(
        select(func.count()).select_from(TestCase).where(TestCase.suite_id == suite.id)
    )
    if not case_count:
        raise HTTPException(
            status_code=400, detail=f"suite {suite.id} has no test cases; add at least one"
        )
    if payload.prompt_template is not None and "{prompt}" not in payload.prompt_template:
        raise HTTPException(
            status_code=400,
            detail="prompt_template must contain the literal placeholder '{prompt}'",
        )

    judge_model = payload.judge_model or get_settings().default_judge_model
    availability_cache: dict[str, tuple[bool, str]] = {}
    for model_id in [*payload.models, judge_model]:
        try:
            provider, _ = adapters.parse_model_id(model_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if provider not in adapters.PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown provider {provider!r} in model {model_id!r}; "
                f"expected one of {', '.join(adapters.PROVIDERS)}",
            )
        if provider not in availability_cache:
            availability_cache[provider] = await adapters.provider_availability(provider)
        available, reason = availability_cache[provider]
        if not available:
            raise HTTPException(
                status_code=400,
                detail=f"provider {provider!r} is not available for model {model_id!r}: {reason}",
            )

    run = Run(
        suite_id=suite.id,
        prompt_version=payload.prompt_version,
        prompt_template=payload.prompt_template,
        models=payload.models,
        judge_model=judge_model,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(execute_run, run.id)
    return export.run_list_item(db, run)


@router.get("", response_model=list[RunListItem])
def list_runs(
    response: Response,
    suite_id: int | None = None,
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RunListItem]:
    count_query = select(func.count()).select_from(Run)
    query = select(Run).order_by(Run.created_at.desc(), Run.id.desc())
    if suite_id is not None:
        count_query = count_query.where(Run.suite_id == suite_id)
        query = query.where(Run.suite_id == suite_id)
    response.headers["X-Total-Count"] = str(db.scalar(count_query) or 0)
    query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    runs = db.scalars(query).all()
    return [export.run_list_item(db, run) for run in runs]


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: int, db: Session = Depends(get_db)) -> RunDetail:
    run = _get_run_or_404(db, run_id)
    return export.build_run_detail(db, run)


@router.get("/{run_id}/export.json")
def export_run_json(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = _get_run_or_404(db, run_id)
    payload = export.build_export_json(db, run)
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="run_{run_id}_export.json"'
        },
    )


@router.get("/{run_id}/export.csv")
def export_run_csv(run_id: int, db: Session = Depends(get_db)) -> Response:
    run = _get_run_or_404(db, run_id)
    csv_text = export.build_export_csv(run)
    return Response(
        content=csv_text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="run_{run_id}_export.csv"'
        },
    )

"""Suite CRUD and per-suite score history."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Run, Suite, TestCase
from app.schemas import (
    HistoryOut,
    SuiteCreate,
    SuiteDetail,
    SuiteListItem,
    SuiteOut,
    SuiteUpdate,
)
from app.services import history

router = APIRouter(prefix="/api/suites", tags=["suites"])


def _get_suite_or_404(db: Session, suite_id: int) -> Suite:
    suite = db.get(Suite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail=f"suite {suite_id} not found")
    return suite


@router.get("", response_model=list[SuiteListItem])
def list_suites(db: Session = Depends(get_db)) -> list[SuiteListItem]:
    suites = db.scalars(select(Suite).order_by(Suite.created_at, Suite.id)).all()
    items: list[SuiteListItem] = []
    for suite in suites:
        case_count = db.scalar(
            select(func.count()).select_from(TestCase).where(TestCase.suite_id == suite.id)
        )
        run_count = db.scalar(
            select(func.count()).select_from(Run).where(Run.suite_id == suite.id)
        )
        items.append(
            SuiteListItem(
                id=suite.id,
                name=suite.name,
                description=suite.description,
                created_at=suite.created_at,
                case_count=case_count or 0,
                run_count=run_count or 0,
            )
        )
    return items


@router.post("", response_model=SuiteOut, status_code=status.HTTP_201_CREATED)
def create_suite(payload: SuiteCreate, db: Session = Depends(get_db)) -> Suite:
    existing = db.scalar(select(Suite).where(Suite.name == payload.name))
    if existing is not None:
        raise HTTPException(
            status_code=409, detail=f"suite name {payload.name!r} already exists"
        )
    suite = Suite(name=payload.name, description=payload.description)
    db.add(suite)
    db.commit()
    db.refresh(suite)
    return suite


@router.get("/{suite_id}", response_model=SuiteDetail)
def get_suite(suite_id: int, db: Session = Depends(get_db)) -> SuiteDetail:
    suite = _get_suite_or_404(db, suite_id)
    cases = db.scalars(
        select(TestCase).where(TestCase.suite_id == suite_id).order_by(TestCase.id)
    ).all()
    return SuiteDetail(
        id=suite.id,
        name=suite.name,
        description=suite.description,
        created_at=suite.created_at,
        cases=cases,  # type: ignore[arg-type]  (validated via from_attributes)
    )


@router.put("/{suite_id}", response_model=SuiteOut)
def update_suite(
    suite_id: int, payload: SuiteUpdate, db: Session = Depends(get_db)
) -> Suite:
    suite = _get_suite_or_404(db, suite_id)
    updates = payload.model_dump(exclude_unset=True)
    new_name = updates.get("name")
    if new_name is not None and new_name != suite.name:
        existing = db.scalar(select(Suite).where(Suite.name == new_name))
        if existing is not None:
            raise HTTPException(
                status_code=409, detail=f"suite name {new_name!r} already exists"
            )
    for field, value in updates.items():
        setattr(suite, field, value)
    db.commit()
    db.refresh(suite)
    return suite


@router.delete("/{suite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_suite(suite_id: int, db: Session = Depends(get_db)) -> Response:
    suite = _get_suite_or_404(db, suite_id)
    db.delete(suite)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{suite_id}/history", response_model=HistoryOut)
def get_suite_history(
    suite_id: int, model: str | None = None, db: Session = Depends(get_db)
) -> HistoryOut:
    _get_suite_or_404(db, suite_id)
    return history.suite_history(db, suite_id, model)

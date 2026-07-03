"""Test-case create/update/delete."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Suite, TestCase
from app.schemas import CaseCreate, CaseOut, CaseUpdate

router = APIRouter(prefix="/api", tags=["cases"])


@router.post(
    "/suites/{suite_id}/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED
)
def create_case(
    suite_id: int, payload: CaseCreate, db: Session = Depends(get_db)
) -> TestCase:
    suite = db.get(Suite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail=f"suite {suite_id} not found")
    case = TestCase(
        suite_id=suite_id,
        prompt=payload.prompt,
        expected_behavior=payload.expected_behavior,
        reference_answer=payload.reference_answer,
        tags=payload.tags,
        assertions=[assertion.model_dump() for assertion in payload.assertions],
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return case


@router.put("/cases/{case_id}", response_model=CaseOut)
def update_case(
    case_id: int, payload: CaseUpdate, db: Session = Depends(get_db)
) -> TestCase:
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    updates = payload.model_dump(exclude_unset=True)
    if "assertions" in updates and payload.assertions is not None:
        updates["assertions"] = [assertion.model_dump() for assertion in payload.assertions]
    for field, value in updates.items():
        setattr(case, field, value)
    db.commit()
    db.refresh(case)
    return case


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: int, db: Session = Depends(get_db)) -> Response:
    case = db.get(TestCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    db.delete(case)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

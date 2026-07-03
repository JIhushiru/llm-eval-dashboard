"""ORM models (SQLAlchemy 2.0 Mapped[] style)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    # Stored naive-UTC so values loaded from SQLite compare cleanly with fresh ones.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Suite(Base):
    __tablename__ = "suites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    cases: Mapped[list[TestCase]] = relationship(
        back_populates="suite", cascade="all, delete-orphan", passive_deletes=True
    )
    runs: Mapped[list[Run]] = relationship(
        back_populates="suite", cascade="all, delete-orphan", passive_deletes=True
    )


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id", ondelete="CASCADE"))
    prompt: Mapped[str] = mapped_column(Text)
    expected_behavior: Mapped[str] = mapped_column(Text)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    assertions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    suite: Mapped[Suite] = relationship(back_populates="cases")
    results: Mapped[list[CaseResult]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id", ondelete="CASCADE"))
    prompt_version: Mapped[str] = mapped_column(String(255))
    prompt_template: Mapped[str | None] = mapped_column(Text)
    models: Mapped[list[str]] = mapped_column(JSON)
    judge_model: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    suite: Mapped[Suite] = relationship(back_populates="runs")
    results: Mapped[list[CaseResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class CaseResult(Base):
    __tablename__ = "case_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"))
    case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"))
    model: Mapped[str] = mapped_column(String(255))
    response_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    retries: Mapped[int] = mapped_column(default=0)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    checks_passed: Mapped[bool | None]
    judge_scores: Mapped[dict[str, int] | None] = mapped_column(JSON)
    judge_rationale: Mapped[str | None] = mapped_column(Text)
    judge_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    run: Mapped[Run] = relationship(back_populates="results")
    case: Mapped[TestCase] = relationship(back_populates="results")

"""SQLAlchemy engine, session factory, and declarative base."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine() -> Engine:
    db_path = Path(get_settings().evalforge_db_path)
    if str(db_path.parent) not in ("", "."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        # SQLite does not enforce ON DELETE CASCADE unless this pragma is set.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine: Engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from app import models  # noqa: F401  (register tables on the metadata)

    Base.metadata.create_all(bind=engine)


def run_migrations() -> None:
    """Bring the database to the latest Alembic revision (`upgrade head`).

    Used by the managed-deployment startup path (EVALFORGE_USE_MIGRATIONS=true).
    Script location and DB URL are set programmatically so this works regardless
    of the process working directory (e.g. inside the container).
    """
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config()
    cfg.set_main_option("script_location", str(backend_root / "migrations"))
    cfg.set_main_option(
        "sqlalchemy.url", f"sqlite:///{Path(get_settings().evalforge_db_path).as_posix()}"
    )
    command.upgrade(cfg, "head")


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

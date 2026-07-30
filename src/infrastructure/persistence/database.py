"""SQLAlchemy engine, session factory, and declarative base.

Only infrastructure/persistence modules should ever import from here.
Use cases and the domain never see a Session or an Engine.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.infrastructure.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope: commit on success, rollback on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables via create_all() — dev/test convenience only.

    As of the Alembic baseline (alembic/versions/0001_baseline.py), this
    is no longer the source of truth for schema changes. Any new column,
    table, or constraint should be added via `alembic revision` and
    applied with `alembic upgrade head`. This function remains only so
    `pytest` and fresh local setups don't require running migrations
    just to get a working dev database.
    """
    from src.infrastructure.persistence import models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)

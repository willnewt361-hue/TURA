"""Database session and engine."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

_settings = get_settings()

# Ensure data directory exists for SQLite
if _settings.database_url.startswith("sqlite"):
    db_path = _settings.database_url.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)) or "data", exist_ok=True)

connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}
engine = create_engine(
    _settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_connection, connection_record):  # noqa: ARG001
    if _settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

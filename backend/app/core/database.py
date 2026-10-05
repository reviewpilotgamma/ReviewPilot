"""SQLite engine (WAL mode), session factory and declarative base."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import DateTime, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.core.config import BACKEND_DIR, get_settings


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Stores naive UTC in SQLite, always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        return value.replace(tzinfo=UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


def _set_sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.execute("PRAGMA busy_timeout=5000;")
    cur.close()


def build_engine(url: str) -> Engine:
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
    eng = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith("sqlite"):
        event.listen(eng, "connect", _set_sqlite_pragmas)
    return eng


engine: Engine = build_engine(get_settings().DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def configure_engine(url: str) -> None:
    """Rebind the global engine (used by tests)."""
    global engine
    engine.dispose()
    engine = build_engine(url)
    SessionLocal.configure(bind=engine)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations(url: str | None = None) -> None:
    """Upgrade the database to the latest Alembic revision."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(BACKEND_DIR / "alembic")))
    # Passed via attributes (not ini options) to avoid configparser '%' interpolation issues.
    cfg.attributes["url"] = url or engine.url.render_as_string(hide_password=False)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")

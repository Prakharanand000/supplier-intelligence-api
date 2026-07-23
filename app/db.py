"""Async SQLAlchemy engine/session setup with a SQLite safety net.

PostgreSQL is the intended datastore. If it is unreachable at startup and
ALLOW_SQLITE_FALLBACK is on, we swap to a local SQLite file so a demo can run
on a laptop with nothing installed. The schema is identical either way.
"""

from __future__ import annotations

import logging

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.models import Base

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
ACTIVE_BACKEND = "uninitialized"


def _backend_label(url: str) -> str:
    """Report the driver actually in use, not the one we hoped for."""
    scheme = url.split(":", 1)[0].split("+", 1)[0]
    return {"postgresql": "postgresql", "sqlite": "sqlite"}.get(scheme, scheme)


async def _try_engine(url: str) -> AsyncEngine | None:
    engine = create_async_engine(url, pool_pre_ping=True, future=True)

    if url.startswith("sqlite"):
        # SQLite locks the whole file on write. The OFAC bulk load and the
        # concurrent HTTP-cache writes collide without these: WAL lets readers
        # run during a write, and busy_timeout makes writers queue instead of
        # failing instantly with "database is locked".
        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=15000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return engine
    except Exception as exc:  # noqa: BLE001 - any driver/connection error
        log.warning("Could not connect to %s: %s", url.split("@")[-1], exc)
        await engine.dispose()
        return None


async def init_db() -> None:
    """Connect (with fallback) and create tables."""
    global _engine, _sessionmaker, ACTIVE_BACKEND

    engine = await _try_engine(settings.database_url)
    if engine is not None:
        ACTIVE_BACKEND = _backend_label(settings.database_url)
    elif settings.allow_sqlite_fallback:
        log.warning(
            "PostgreSQL unavailable - falling back to SQLite at %s. "
            "Start Postgres with `docker compose up -d` for the intended setup.",
            settings.sqlite_url,
        )
        engine = await _try_engine(settings.sqlite_url)
        ACTIVE_BACKEND = _backend_label(settings.sqlite_url) + " (fallback)"

    if engine is None:
        raise RuntimeError(
            "No database available. Set DATABASE_URL to a reachable PostgreSQL "
            "instance, or set ALLOW_SQLITE_FALLBACK=true."
        )

    _engine = engine
    _sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    log.info("Database ready (%s)", ACTIVE_BACKEND)


async def close_db() -> None:
    if _engine is not None:
        await _engine.dispose()


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_db() has not been called")
    return _sessionmaker

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings
from app.performance_audit import install_sqlalchemy_instrumentation


if sys.platform == "win32":
    current_policy = asyncio.get_event_loop_policy()
    if not isinstance(current_policy, asyncio.WindowsSelectorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


engine: Engine | None = None
async_engine: AsyncEngine | None = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False, expire_on_commit=False)
async_session_maker = async_sessionmaker(autoflush=False, expire_on_commit=False)


def _database_url_with_driver(drivername: str) -> str:
    url = make_url(settings.database_url)
    if url.drivername != drivername:
        url = url.set(drivername=drivername)
    return url.render_as_string(hide_password=False)


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = create_engine(
            _database_url_with_driver("postgresql+psycopg"),
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_recycle=settings.db_pool_recycle_seconds,
        )
        SessionLocal.configure(bind=engine)
        install_sqlalchemy_instrumentation(engine)
    return engine


def get_async_engine() -> AsyncEngine:
    global async_engine
    if async_engine is None:
        async_engine_kwargs = {
            "pool_pre_ping": True,
            "pool_recycle": settings.db_pool_recycle_seconds,
        }
        if sys.platform == "win32":
            async_engine_kwargs["poolclass"] = NullPool
        else:
            async_engine_kwargs["pool_size"] = settings.db_pool_size
            async_engine_kwargs["max_overflow"] = settings.db_max_overflow
            async_engine_kwargs["pool_timeout"] = settings.db_pool_timeout_seconds

        async_engine = create_async_engine(
            _database_url_with_driver("postgresql+asyncpg"),
            **async_engine_kwargs,
        )
        async_session_maker.configure(bind=async_engine)
        install_sqlalchemy_instrumentation(async_engine.sync_engine)
    return async_engine


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    get_async_engine()
    async with async_session_maker() as session:
        yield session

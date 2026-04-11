from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import logging
import sys
from threading import Lock
from time import perf_counter
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool, QueuePool

from app.config import settings
from app.observability import emit_structured_log
from app.performance_audit import install_sqlalchemy_instrumentation


if sys.platform == "win32" and sys.version_info < (3, 14):
    current_policy = asyncio.get_event_loop_policy()
    if not isinstance(current_policy, asyncio.WindowsSelectorEventLoopPolicy):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


logger = logging.getLogger(__name__)


engine: Engine | None = None
async_engine: AsyncEngine | None = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False, expire_on_commit=False)
async_session_maker = async_sessionmaker(autoflush=False, expire_on_commit=False)
_BOUND_SYNC_SESSION: ContextVar[Session | None] = ContextVar("db_bound_sync_session", default=None)
_POOL_INSTRUMENTATION_LOCK = Lock()
_POOL_STATES: dict[int, "_PoolTelemetryState"] = {}
_INSTRUMENTED_POOLS: set[int] = set()


@dataclass(slots=True)
class _PoolTelemetryState:
    label: str
    last_queue_wait_ms: float = 0.0
    average_queue_wait_ms: float = 0.0
    max_queue_wait_ms: float = 0.0
    queue_wait_samples: int = 0
    last_warning_signature: tuple[str, int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class PoolStatusSnapshot:
    label: str
    pool_class: str
    pool_size: int
    max_overflow: int
    checked_out: int
    overflow: int
    current_capacity: int
    total_capacity: int | None
    utilization_ratio: float
    queue_wait_time_ms: float
    average_queue_wait_time_ms: float
    max_queue_wait_time_ms: float
    queue_wait_samples: int
    pool_timeout_seconds: int


class _ObservedPoolMixin:
    def _do_get(self):  # type: ignore[override]
        started_at = perf_counter()
        entry = super()._do_get()
        wait_ms = (perf_counter() - started_at) * 1000.0
        entry.info["ft_pool_wait_ms"] = wait_ms
        _record_queue_wait_sample(self, wait_ms)
        return entry

    def _inc_overflow(self) -> bool:  # type: ignore[override]
        increased = super()._inc_overflow()
        if increased:
            _record_pool_activity(self, "overflow")
        return increased


class ObservedQueuePool(_ObservedPoolMixin, QueuePool):
    pass


class ObservedAsyncAdaptedQueuePool(_ObservedPoolMixin, AsyncAdaptedQueuePool):
    pass


def _database_url_with_driver(drivername: str) -> str:
    url = make_url(settings.database_url)
    if url.drivername != drivername:
        url = url.set(drivername=drivername)
    return url.render_as_string(hide_password=False)


@contextmanager
def bind_request_sync_session(session: Session):
    token = _BOUND_SYNC_SESSION.set(session)
    try:
        yield
    finally:
        _BOUND_SYNC_SESSION.reset(token)


def get_bound_request_sync_session() -> Session | None:
    return _BOUND_SYNC_SESSION.get()


def _pool_state_for(pool: QueuePool | AsyncAdaptedQueuePool) -> _PoolTelemetryState | None:
    with _POOL_INSTRUMENTATION_LOCK:
        return _POOL_STATES.get(id(pool))


def _normalized_overflow(pool: QueuePool | AsyncAdaptedQueuePool) -> int:
    return max(int(pool.overflow()), 0)


def _configured_total_capacity(pool: QueuePool | AsyncAdaptedQueuePool) -> int | None:
    max_overflow = int(getattr(pool, "_max_overflow", 0))
    if max_overflow < 0:
        return None
    return int(pool.size()) + max_overflow


def _build_pool_status_snapshot(pool: QueuePool | AsyncAdaptedQueuePool, state: _PoolTelemetryState) -> PoolStatusSnapshot:
    pool_size = int(pool.size())
    checked_out = int(pool.checkedout())
    overflow = _normalized_overflow(pool)
    current_capacity = pool_size + overflow
    total_capacity = _configured_total_capacity(pool)
    utilization_denominator = total_capacity if total_capacity is not None else max(current_capacity, 1)
    utilization_ratio = checked_out / max(utilization_denominator, 1)
    max_overflow = int(getattr(pool, "_max_overflow", 0))
    return PoolStatusSnapshot(
        label=state.label,
        pool_class=type(pool).__name__,
        pool_size=pool_size,
        max_overflow=max_overflow,
        checked_out=checked_out,
        overflow=overflow,
        current_capacity=current_capacity,
        total_capacity=total_capacity,
        utilization_ratio=utilization_ratio,
        queue_wait_time_ms=round(state.last_queue_wait_ms, 3),
        average_queue_wait_time_ms=round(state.average_queue_wait_ms, 3),
        max_queue_wait_time_ms=round(state.max_queue_wait_ms, 3),
        queue_wait_samples=state.queue_wait_samples,
        pool_timeout_seconds=settings.db_pool_timeout_seconds,
    )


def _record_queue_wait_sample(pool: QueuePool | AsyncAdaptedQueuePool, wait_ms: float) -> None:
    state = _pool_state_for(pool)
    if state is None:
        return
    with _POOL_INSTRUMENTATION_LOCK:
        state = _POOL_STATES.get(id(pool))
        if state is None:
            return
        state.last_queue_wait_ms = wait_ms
        state.queue_wait_samples += 1
        if state.queue_wait_samples == 1:
            state.average_queue_wait_ms = wait_ms
        else:
            state.average_queue_wait_ms += (wait_ms - state.average_queue_wait_ms) / state.queue_wait_samples
        state.max_queue_wait_ms = max(state.max_queue_wait_ms, wait_ms)


def _record_pool_activity(pool: QueuePool | AsyncAdaptedQueuePool, pool_event: str, *, wait_ms: float | None = None) -> None:
    state = _pool_state_for(pool)
    if state is None:
        return
    snapshot = _build_pool_status_snapshot(pool, state)
    utilization_pct = int(round(snapshot.utilization_ratio * 100))
    signature = (pool_event, snapshot.checked_out, snapshot.overflow, utilization_pct)
    should_warn = snapshot.utilization_ratio >= 0.8
    with _POOL_INSTRUMENTATION_LOCK:
        state = _POOL_STATES.get(id(pool))
        if state is None:
            return
        if not should_warn:
            state.last_warning_signature = None
            return
        if state.last_warning_signature == signature:
            return
        state.last_warning_signature = signature

    emit_structured_log(
        logger,
        "db_pool.high_utilization",
        level=logging.WARNING,
        pool_label=snapshot.label,
        pool_event=pool_event,
        pool_class=snapshot.pool_class,
        pool_size=snapshot.pool_size,
        max_overflow=snapshot.max_overflow,
        checked_out=snapshot.checked_out,
        overflow=snapshot.overflow,
        current_capacity=snapshot.current_capacity,
        total_capacity=snapshot.total_capacity,
        utilization_ratio=round(snapshot.utilization_ratio, 4),
        queue_wait_time_ms=round(wait_ms if wait_ms is not None else snapshot.queue_wait_time_ms, 3),
        average_queue_wait_time_ms=snapshot.average_queue_wait_time_ms,
        max_queue_wait_time_ms=snapshot.max_queue_wait_time_ms,
    )


def _install_pool_instrumentation(engine: Engine, *, label: str) -> None:
    pool = engine.pool
    if not isinstance(pool, (QueuePool, AsyncAdaptedQueuePool)):
        return

    pool_id = id(pool)
    with _POOL_INSTRUMENTATION_LOCK:
        if pool_id in _INSTRUMENTED_POOLS:
            return
        _POOL_STATES[pool_id] = _PoolTelemetryState(label=label)
        _INSTRUMENTED_POOLS.add(pool_id)

    @event.listens_for(pool, "checkout")
    def _on_checkout(_dbapi_connection, connection_record, _connection_proxy) -> None:
        wait_ms = float(connection_record.info.pop("ft_pool_wait_ms", 0.0) or 0.0)
        _record_pool_activity(pool, "checkout", wait_ms=wait_ms)

    @event.listens_for(pool, "checkin")
    def _on_checkin(_dbapi_connection, _connection_record) -> None:
        _record_pool_activity(pool, "checkin")


def get_async_pool_status() -> PoolStatusSnapshot:
    pool = get_async_engine().sync_engine.pool
    if not isinstance(pool, (QueuePool, AsyncAdaptedQueuePool)):
        raise RuntimeError("Async engine is not using a queue-backed pool")
    state = _pool_state_for(pool)
    if state is None:
        _install_pool_instrumentation(get_async_engine().sync_engine, label="api_async")
        state = _pool_state_for(pool)
    if state is None:
        raise RuntimeError("Async pool instrumentation is unavailable")
    return _build_pool_status_snapshot(pool, state)


def get_engine() -> Engine:
    global engine
    if engine is None:
        engine = create_engine(
            _database_url_with_driver("postgresql+psycopg"),
            poolclass=ObservedQueuePool,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_recycle=settings.db_pool_recycle_seconds,
        )
        SessionLocal.configure(bind=engine)
        _install_pool_instrumentation(engine, label="worker_sync")
        install_sqlalchemy_instrumentation(engine)
    return engine


def get_async_engine() -> AsyncEngine:
    global async_engine
    if async_engine is None:
        async_engine = create_async_engine(
            _database_url_with_driver("postgresql+asyncpg"),
            poolclass=ObservedAsyncAdaptedQueuePool,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_recycle=settings.db_pool_recycle_seconds,
        )
        async_session_maker.configure(bind=async_engine)
        _install_pool_instrumentation(async_engine.sync_engine, label="api_async")
        install_sqlalchemy_instrumentation(async_engine.sync_engine)
    return async_engine


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    get_async_engine()
    async with async_session_maker() as session:
        yield session

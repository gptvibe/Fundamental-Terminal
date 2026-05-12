from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.status_stream as status_stream
from app.db.base import Base
from app.models import Company, RefreshJob, RefreshJobEvent


def _configure_sqlite_store(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[Company.__table__, RefreshJob.__table__, RefreshJobEvent.__table__])
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX IF EXISTS uq_refresh_jobs_active_ticker_dataset")
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr(status_stream, "get_engine", lambda: engine)
    monkeypatch.setattr(status_stream, "SessionLocal", session_factory)
    return session_factory


def _insert_company(session_factory, *, ticker: str, cik: str = "0000320193", company_id: int | None = None) -> int:
    with session_factory() as session:
        company = Company(
            id=company_id,
            ticker=ticker,
            cik=cik,
            name=f"{ticker} Corp",
        )
        session.add(company)
        session.commit()
        return int(company.id)


class _FakeRedisLockClient:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, float | None]] = {}
        self._now = time.monotonic

    def set_now_provider(self, provider) -> None:
        self._now = provider

    def ping(self) -> bool:
        return True

    def _purge_if_expired(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None:
            return
        _, expires_at = entry
        if expires_at is not None and expires_at <= self._now():
            self._entries.pop(key, None)

    def set(self, key: str, value: str, *, nx: bool = False, xx: bool = False, ex: int | None = None):
        self._purge_if_expired(key)
        exists = key in self._entries
        if nx and exists:
            return False
        if xx and not exists:
            return False
        expires_at = None if ex is None else (self._now() + float(ex))
        self._entries[key] = (value, expires_at)
        return True

    def get(self, key: str):
        self._purge_if_expired(key)
        entry = self._entries.get(key)
        if entry is None:
            return None
        return entry[0]

    def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            self._purge_if_expired(key)
            if key in self._entries:
                self._entries.pop(key, None)
                deleted += 1
        return deleted

    def rpush(self, *_args, **_kwargs) -> int:
        return 1

    def publish(self, *_args, **_kwargs) -> int:
        return 1


class _FakeMonotonicClock:
    def __init__(self) -> None:
        self._value = 0.0

    def now(self) -> float:
        return self._value

    def advance(self, seconds: float) -> None:
        self._value += float(seconds)


def test_shared_status_broker_persists_jobs_and_prevents_duplicates(monkeypatch) -> None:
    session_factory = _configure_sqlite_store(monkeypatch)
    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)

    job_id = broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False)
    duplicate_job_id = broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=True)

    assert duplicate_job_id == job_id

    claimed = broker.claim_next_job(worker_id="worker-1")

    assert claimed is not None
    assert claimed.job_id == job_id
    assert broker.claim_next_job(worker_id="worker-2") is None

    broker.publish(
        job_id,
        stage="normalize",
        message="Normalizing SEC payloads",
        status="running",
        expected_claim_token=claimed.claim_token,
    )
    broker.complete(job_id, message="Refresh complete", expected_claim_token=claimed.claim_token)

    restarted_broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)
    assert restarted_broker.has_job(job_id) is True

    with session_factory() as session:
        job = session.execute(select(RefreshJob).where(RefreshJob.job_id == job_id)).scalar_one()
        events = session.execute(
            select(RefreshJobEvent)
            .join(RefreshJob, RefreshJob.id == RefreshJobEvent.refresh_job_id)
            .where(RefreshJob.job_id == job_id)
            .order_by(RefreshJobEvent.sequence)
        ).scalars().all()
        job.updated_at = datetime.now(timezone.utc) - timedelta(seconds=180)
        job.completed_at = datetime.now(timezone.utc) - timedelta(seconds=180)
        session.commit()

    assert job.status == "completed"
    assert [event.stage for event in events] == ["queued", "started", "normalize", "complete"]

    next_job_id = restarted_broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False)
    assert next_job_id != job_id


def test_shared_status_broker_claims_oldest_job_first(monkeypatch) -> None:
    _configure_sqlite_store(monkeypatch)
    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)

    older_job_id = broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False)
    newer_job_id = broker.create_job(ticker="MSFT", kind="refresh", dataset="company_refresh", force=False)

    claimed = broker.claim_next_job(worker_id="worker-1")

    assert claimed is not None
    assert claimed.job_id == older_job_id
    assert claimed.ticker == "AAPL"
    assert claimed.job_id != newer_job_id


def test_shared_status_broker_formats_jobs_ahead_for_queued_job_events(monkeypatch) -> None:
    _configure_sqlite_store(monkeypatch)
    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)

    first_job_id = broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False)
    broker.create_job(ticker="MSFT", kind="refresh", dataset="company_refresh", force=False)
    queued_job_id = broker.create_job(ticker="NET", kind="refresh", dataset="company_refresh", force=False)

    queued_event = broker.list_events(queued_job_id)[0]
    initial_payload = json.loads(broker.format_sse(queued_job_id, queued_event).split("data: ", 1)[1])

    assert initial_payload["queue_position"] == 3
    assert initial_payload["jobs_ahead"] == 2

    claimed = broker.claim_next_job(worker_id="worker-1")

    assert claimed is not None
    assert claimed.job_id == first_job_id

    running_ahead_payload = json.loads(broker.format_sse(queued_job_id, queued_event).split("data: ", 1)[1])

    assert running_ahead_payload["queue_position"] == 3
    assert running_ahead_payload["jobs_ahead"] == 2

    broker.complete(first_job_id, expected_claim_token=claimed.claim_token)

    updated_payload = json.loads(broker.format_sse(queued_job_id, queued_event).split("data: ", 1)[1])

    assert updated_payload["queue_position"] == 2
    assert updated_payload["jobs_ahead"] == 1


def test_shared_status_broker_returns_existing_job_for_running_equivalent(monkeypatch) -> None:
    _configure_sqlite_store(monkeypatch)
    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)

    job_id = broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")
    claimed = broker.claim_next_job(worker_id="worker-1")

    assert claimed is not None
    assert claimed.job_id == job_id

    duplicate_job_id = broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")

    assert duplicate_job_id == job_id


def test_shared_status_broker_dedupe_ttl_expiry_allows_new_job(monkeypatch) -> None:
    session_factory = _configure_sqlite_store(monkeypatch)
    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)
    broker._dedupe_ttl = timedelta(seconds=60)

    first_job_id = broker.create_job(ticker="MSFT", kind="refresh", dataset="company_refresh", force=False, reason="manual")
    claimed = broker.claim_next_job(worker_id="worker-1")

    assert claimed is not None
    assert claimed.job_id == first_job_id

    broker.complete(first_job_id, expected_claim_token=claimed.claim_token)

    immediate_duplicate_job_id = broker.create_job(
        ticker="MSFT",
        kind="refresh",
        dataset="company_refresh",
        force=False,
        reason="manual",
    )
    assert immediate_duplicate_job_id == first_job_id

    stale_timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)
    with session_factory() as session:
        job = session.execute(select(RefreshJob).where(RefreshJob.job_id == first_job_id)).scalar_one()
        job.updated_at = stale_timestamp
        job.completed_at = stale_timestamp
        session.commit()

    new_job_id = broker.create_job(ticker="MSFT", kind="refresh", dataset="company_refresh", force=False, reason="manual")
    assert new_job_id != first_job_id


def test_single_flight_refresh_first_stale_request_enqueues(monkeypatch) -> None:
    _configure_sqlite_store(monkeypatch)
    monkeypatch.setattr(status_stream, "ensure_company", lambda _session, _ticker: type("_Company", (), {"id": 7})())
    monkeypatch.setattr(status_stream, "set_active_refresh_job", lambda *_args, **_kwargs: None)
    fake_redis = _FakeRedisLockClient()
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_sync_redis_client", lambda self: fake_redis)
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_async_redis_client", lambda self: None)

    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)
    result = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")

    assert result.status == "enqueued"
    assert result.job_id is not None


def test_single_flight_refresh_second_stale_request_skips_duplicate(monkeypatch) -> None:
    _configure_sqlite_store(monkeypatch)
    company_id = 7
    monkeypatch.setattr(status_stream, "ensure_company", lambda _session, _ticker: type("_Company", (), {"id": company_id})())
    monkeypatch.setattr(status_stream, "set_active_refresh_job", lambda *_args, **_kwargs: None)
    fake_redis = _FakeRedisLockClient()
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_sync_redis_client", lambda self: fake_redis)
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_async_redis_client", lambda self: None)

    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)
    broker._dedupe_ttl = timedelta(0)
    first = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")
    second = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")

    assert first.status == "enqueued"
    assert second.status == "skipped_due_to_existing_lock"
    assert second.job_id == first.job_id
    assert fake_redis.get(f"refresh-lock:{company_id}:company_refresh") == first.job_id


def test_single_flight_refresh_lock_expires_safely(monkeypatch) -> None:
    _configure_sqlite_store(monkeypatch)
    company_id = 7
    monkeypatch.setattr(status_stream, "ensure_company", lambda _session, _ticker: type("_Company", (), {"id": company_id})())
    monkeypatch.setattr(status_stream, "set_active_refresh_job", lambda *_args, **_kwargs: None)
    fake_redis = _FakeRedisLockClient()
    clock = _FakeMonotonicClock()
    fake_redis.set_now_provider(clock.now)
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_sync_redis_client", lambda self: fake_redis)
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_async_redis_client", lambda self: None)

    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)
    broker._refresh_enqueue_lock_ttl_seconds = 2
    stale_lock_key = f"refresh-lock:{company_id}:company_refresh"
    fake_redis.set(stale_lock_key, "stale-job", nx=True, ex=2)

    skipped = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")
    assert skipped.status == "skipped_due_to_existing_lock"

    clock.advance(3)
    enqueued = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")

    assert enqueued.status == "enqueued"
    assert enqueued.job_id is not None


def test_single_flight_refresh_failed_jobs_do_not_permanently_block(monkeypatch) -> None:
    session_factory = _configure_sqlite_store(monkeypatch)
    company_id = 7
    monkeypatch.setattr(status_stream, "ensure_company", lambda _session, _ticker: type("_Company", (), {"id": company_id})())
    monkeypatch.setattr(status_stream, "set_active_refresh_job", lambda *_args, **_kwargs: None)
    fake_redis = _FakeRedisLockClient()
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_sync_redis_client", lambda self: fake_redis)
    monkeypatch.setattr(status_stream.SharedStatusBroker, "_build_async_redis_client", lambda self: None)

    broker = status_stream.SharedStatusBroker(poll_interval_seconds=0.01)
    broker._dedupe_ttl = timedelta(0)
    first = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")
    assert first.status == "enqueued"
    assert first.job_id is not None

    claimed = broker.claim_next_job(worker_id="worker-1")
    assert claimed is not None
    broker.fail(first.job_id, message="refresh failed")

    with session_factory() as session:
        failed_job = session.execute(select(RefreshJob).where(RefreshJob.job_id == first.job_id)).scalar_one()
        assert failed_job.status == "failed"

    assert fake_redis.get(f"refresh-lock:{company_id}:company_refresh") is None

    retry = broker.create_job_result(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False, reason="stale")
    assert retry.status == "enqueued"
    assert retry.job_id is not None
    assert retry.job_id != first.job_id
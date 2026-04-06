from __future__ import annotations

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

    assert job.status == "completed"
    assert [event.stage for event in events] == ["queued", "started", "normalize", "complete"]

    next_job_id = restarted_broker.create_job(ticker="AAPL", kind="refresh", dataset="company_refresh", force=False)
    assert next_job_id != job_id
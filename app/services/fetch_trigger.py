from __future__ import annotations

from datetime import datetime, timezone

from fastapi import BackgroundTasks

from app.db.session import SessionLocal, get_engine
from app.services.refresh_state import acquire_refresh_lock, ensure_company

from app.services.sec_edgar import run_refresh_job
from app.services.status_stream import status_broker


def queue_company_refresh(
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    force: bool = False,
) -> str:
    normalized_ticker = ticker.strip().upper()
    get_engine()

    active_job_id = status_broker.get_active_job_id(ticker=normalized_ticker, kind="refresh")
    if active_job_id is not None:
        return active_job_id

    job_id = status_broker.create_job(ticker=normalized_ticker, kind="refresh")

    with SessionLocal() as session:
        company = ensure_company(session, normalized_ticker)
        if company is not None:
            duplicate_job_id = acquire_refresh_lock(
                session,
                company_id=company.id,
                dataset="company_refresh",
                job_id=job_id,
                now=datetime.now(timezone.utc),
            )
            if duplicate_job_id is not None:
                session.rollback()
                return duplicate_job_id
            session.commit()

    background_tasks.add_task(run_refresh_job, normalized_ticker, force, job_id)
    return job_id

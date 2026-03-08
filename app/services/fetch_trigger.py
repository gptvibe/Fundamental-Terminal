from __future__ import annotations

from fastapi import BackgroundTasks

from app.services.sec_edgar import run_refresh_job
from app.services.status_stream import status_broker


def queue_company_refresh(
    background_tasks: BackgroundTasks,
    ticker: str,
    *,
    force: bool = False,
) -> str:
    normalized_ticker = ticker.strip().upper()
    job_id = status_broker.create_job(ticker=normalized_ticker, kind="refresh")
    background_tasks.add_task(run_refresh_job, normalized_ticker, force, job_id)
    return job_id

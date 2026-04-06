from __future__ import annotations

from fastapi import BackgroundTasks

from app.services.status_stream import status_broker


def queue_company_refresh(
    background_tasks: BackgroundTasks | None,
    ticker: str,
    *,
    force: bool = False,
) -> str:
    normalized_ticker = ticker.strip().upper()
    _ = background_tasks
    return status_broker.create_job(
        ticker=normalized_ticker,
        kind="refresh",
        dataset="company_refresh",
        force=force,
    )

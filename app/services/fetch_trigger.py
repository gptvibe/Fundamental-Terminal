from __future__ import annotations

from app.services.status_stream import status_broker


def queue_company_refresh(
    ticker: str,
    *,
    force: bool = False,
) -> str:
    normalized_ticker = ticker.strip().upper()
    return status_broker.create_job(
        ticker=normalized_ticker,
        kind="refresh",
        dataset="company_refresh",
        force=force,
    )

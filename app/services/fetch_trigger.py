from __future__ import annotations

from app.services.status_stream import RefreshEnqueueResult, status_broker


def queue_company_refresh(
    ticker: str,
    *,
    force: bool = False,
    reason: str = "manual",
    as_of: str | None = None,
) -> RefreshEnqueueResult:
    normalized_ticker = ticker.strip().upper()
    if hasattr(status_broker, "create_job_result"):
        return status_broker.create_job_result(
            ticker=normalized_ticker,
            kind="refresh",
            dataset="company_refresh",
            force=force,
            reason=reason,
            as_of=as_of,
        )

    job_id = status_broker.create_job(
        ticker=normalized_ticker,
        kind="refresh",
        dataset="company_refresh",
        force=force,
        reason=reason,
        as_of=as_of,
    )
    return RefreshEnqueueResult(
        status="enqueued",
        job_id=job_id,
        ticker=normalized_ticker,
        dataset="company_refresh",
    )

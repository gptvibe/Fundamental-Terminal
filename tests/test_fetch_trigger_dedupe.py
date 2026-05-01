from __future__ import annotations

from types import SimpleNamespace

from fastapi import BackgroundTasks

import app.api.handlers.jobs as job_handlers
import app.services.fetch_trigger as fetch_trigger


def test_queue_company_refresh_returns_existing_job_id(monkeypatch):
    monkeypatch.setattr(
        fetch_trigger.status_broker,
        "create_job",
        lambda **_kwargs: "job-existing",
    )

    job_id = fetch_trigger.queue_company_refresh("AAPL", force=False)

    assert job_id == "job-existing"


def test_queue_company_refresh_normalizes_and_enqueues(monkeypatch):
    captured: dict[str, object] = {}

    def _create_job(**kwargs):
        captured.update(kwargs)
        return "job-new"

    monkeypatch.setattr(fetch_trigger.status_broker, "create_job", _create_job)

    job_id = fetch_trigger.queue_company_refresh(" msft ", force=True)

    assert job_id == "job-new"
    assert captured == {
        "ticker": "MSFT",
        "kind": "refresh",
        "dataset": "company_refresh",
        "force": True,
    }


def test_refresh_company_handler_queues_normalized_ticker_without_background_tasks_argument(monkeypatch):
    captured: dict[str, object] = {}

    monkeypatch.setattr(job_handlers, "_normalize_ticker", lambda ticker: ticker.strip().upper(), raising=False)
    monkeypatch.setattr(
        job_handlers,
        "_resolve_cached_company_snapshot",
        lambda session, ticker: SimpleNamespace(company=SimpleNamespace(ticker=ticker)),
        raising=False,
    )

    def _queue_company_refresh(ticker: str, *, force: bool = False) -> str:
        captured["ticker"] = ticker
        captured["force"] = force
        return "job-manual"

    monkeypatch.setattr(job_handlers, "queue_company_refresh", _queue_company_refresh)

    response = job_handlers.refresh_company.__wrapped__(
        " aapl ",
        BackgroundTasks(),
        force=True,
        session=object(),
    )

    assert response.status == "queued"
    assert response.ticker == "AAPL"
    assert response.refresh.job_id == "job-manual"
    assert captured == {"ticker": "AAPL", "force": True}

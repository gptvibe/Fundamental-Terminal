from __future__ import annotations

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

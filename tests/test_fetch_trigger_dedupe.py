from __future__ import annotations

from fastapi import BackgroundTasks

import app.services.fetch_trigger as fetch_trigger


def test_queue_company_refresh_returns_existing_job_id(monkeypatch):
    background_tasks = BackgroundTasks()

    monkeypatch.setattr(
        fetch_trigger.status_broker,
        "create_job",
        lambda **_kwargs: "job-existing",
    )

    job_id = fetch_trigger.queue_company_refresh(background_tasks, "AAPL", force=False)

    assert job_id == "job-existing"
    assert len(background_tasks.tasks) == 0


def test_queue_company_refresh_normalizes_and_enqueues(monkeypatch):
    background_tasks = BackgroundTasks()
    captured: dict[str, object] = {}

    def _create_job(**kwargs):
        captured.update(kwargs)
        return "job-new"

    monkeypatch.setattr(fetch_trigger.status_broker, "create_job", _create_job)

    job_id = fetch_trigger.queue_company_refresh(background_tasks, " msft ", force=True)

    assert job_id == "job-new"
    assert len(background_tasks.tasks) == 0
    assert captured == {
        "ticker": "MSFT",
        "kind": "refresh",
        "dataset": "company_refresh",
        "force": True,
    }

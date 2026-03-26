from __future__ import annotations

from types import SimpleNamespace

from fastapi import BackgroundTasks

import app.services.fetch_trigger as fetch_trigger


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class _SessionFactory:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self

    def __enter__(self) -> _FakeSession:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_queue_company_refresh_uses_db_lock_to_dedupe(monkeypatch):
    fake_session = _FakeSession()
    background_tasks = BackgroundTasks()

    monkeypatch.setattr(fetch_trigger, "get_engine", lambda: None)
    monkeypatch.setattr(fetch_trigger, "SessionLocal", _SessionFactory(fake_session))
    monkeypatch.setattr(fetch_trigger, "ensure_company", lambda *_args, **_kwargs: SimpleNamespace(id=42))
    monkeypatch.setattr(fetch_trigger, "acquire_refresh_lock", lambda *_args, **_kwargs: "job-existing")
    monkeypatch.setattr(fetch_trigger.status_broker, "get_active_job_id", lambda **_kwargs: None)
    monkeypatch.setattr(fetch_trigger.status_broker, "create_job", lambda **_kwargs: "job-new")

    job_id = fetch_trigger.queue_company_refresh(background_tasks, "AAPL", force=False)

    assert job_id == "job-existing"
    assert fake_session.rolled_back is True
    assert len(background_tasks.tasks) == 0


def test_queue_company_refresh_schedules_task_when_lock_acquired(monkeypatch):
    fake_session = _FakeSession()
    background_tasks = BackgroundTasks()

    monkeypatch.setattr(fetch_trigger, "get_engine", lambda: None)
    monkeypatch.setattr(fetch_trigger, "SessionLocal", _SessionFactory(fake_session))
    monkeypatch.setattr(fetch_trigger, "ensure_company", lambda *_args, **_kwargs: SimpleNamespace(id=42))
    monkeypatch.setattr(fetch_trigger, "acquire_refresh_lock", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(fetch_trigger.status_broker, "get_active_job_id", lambda **_kwargs: None)
    monkeypatch.setattr(fetch_trigger.status_broker, "create_job", lambda **_kwargs: "job-new")

    job_id = fetch_trigger.queue_company_refresh(background_tasks, "MSFT", force=True)

    assert job_id == "job-new"
    assert fake_session.committed is True
    assert len(background_tasks.tasks) == 1

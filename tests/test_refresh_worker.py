from __future__ import annotations

from types import SimpleNamespace

import app.worker as worker_module


class _FakeBroker:
    def __init__(self, jobs: list[object | None]) -> None:
        self._jobs = list(jobs)
        self.has_blocking_queue = True
        self.requeue_limits: list[int] = []

    def requeue_expired_jobs(self, *, limit: int) -> None:
        self.requeue_limits.append(limit)

    def claim_next_job_blocking(self, *, worker_id: str, timeout_seconds: float):
        assert worker_id
        assert timeout_seconds >= 0
        if self._jobs:
            return self._jobs.pop(0)
        return None


class _FakeThread:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None

    def join(self, timeout: float | None = None) -> None:
        return None


class _FakeService:
    def __init__(self, name: str) -> None:
        self.name = name
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def _job(job_id: str, ticker: str = "MSFT") -> SimpleNamespace:
    return SimpleNamespace(job_id=job_id, claim_token=f"claim-{job_id}", ticker=ticker, force=False)


def test_queue_worker_reuses_service_across_back_to_back_jobs(monkeypatch) -> None:
    created_services: list[_FakeService] = []
    seen_service_names: list[str] = []

    monkeypatch.setattr(worker_module, "status_broker", _FakeBroker([_job("job-1"), _job("job-2"), None]))
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        worker_module,
        "EdgarIngestionService",
        lambda: created_services.append(_FakeService(f"service-{len(created_services) + 1}")) or created_services[-1],
    )
    monkeypatch.setattr(
        worker_module,
        "run_refresh_job",
        lambda identifier, **kwargs: seen_service_names.append(kwargs["service"].name) or {"identifier": identifier},
    )

    result = worker_module.run_refresh_queue_worker(poll_interval_seconds=0.01, once=True)

    assert result == 0
    assert seen_service_names == ["service-1", "service-1"]
    assert len(created_services) == 1
    assert created_services[0].close_calls == 1


def test_queue_worker_recreates_service_after_job_failure(monkeypatch) -> None:
    created_services: list[_FakeService] = []
    seen_service_names: list[str] = []

    monkeypatch.setattr(worker_module, "status_broker", _FakeBroker([_job("job-1"), _job("job-2"), None]))
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        worker_module,
        "EdgarIngestionService",
        lambda: created_services.append(_FakeService(f"service-{len(created_services) + 1}")) or created_services[-1],
    )

    def _run_refresh_job(_identifier: str, **kwargs):
        service = kwargs["service"]
        seen_service_names.append(service.name)
        if kwargs["job_id"] == "job-1":
            raise RuntimeError("boom")
        return {"ok": True}

    monkeypatch.setattr(worker_module, "run_refresh_job", _run_refresh_job)

    result = worker_module.run_refresh_queue_worker(poll_interval_seconds=0.01, once=True)

    assert result == 0
    assert seen_service_names == ["service-1", "service-2"]
    assert len(created_services) == 2
    assert created_services[0].close_calls == 1
    assert created_services[1].close_calls == 1

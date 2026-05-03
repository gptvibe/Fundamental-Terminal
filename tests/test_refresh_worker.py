from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from app.observability import reset_worker_observations, snapshot_worker_observations
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

    def heartbeat_worker(self, worker_id: str, *, state: str, current_job_id: str | None = None, ticker: str | None = None) -> None:
        assert worker_id
        assert state

    def clear_worker_heartbeat(self, worker_id: str) -> None:
        assert worker_id


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


def test_queue_worker_emits_failed_refresh_metric(monkeypatch) -> None:
    reset_worker_observations()
    created_services: list[_FakeService] = []

    monkeypatch.setattr(worker_module, "status_broker", _FakeBroker([_job("job-1", ticker="AAPL"), None]))
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        worker_module,
        "EdgarIngestionService",
        lambda: created_services.append(_FakeService(f"service-{len(created_services) + 1}")) or created_services[-1],
    )

    def _run_refresh_job(_identifier: str, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "run_refresh_job", _run_refresh_job)

    result = worker_module.run_refresh_queue_worker(poll_interval_seconds=0.01, once=True)

    assert result == 0
    snapshot = snapshot_worker_observations()
    assert snapshot["totals"]["failed_refresh_count"] == 1
    assert snapshot["records"][0]["status"] == "failed"
    assert snapshot["records"][0]["ticker"] == "AAPL"


def test_queue_worker_logs_warning_for_unresolved_ticker(monkeypatch) -> None:
    created_services: list[_FakeService] = []
    warning_messages: list[str] = []
    exception_messages: list[str] = []

    monkeypatch.setattr(worker_module, "status_broker", _FakeBroker([_job("job-1", ticker="ZZZZ"), None]))
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        worker_module,
        "EdgarIngestionService",
        lambda: created_services.append(_FakeService(f"service-{len(created_services) + 1}")) or created_services[-1],
    )
    monkeypatch.setattr(
        worker_module,
        "run_refresh_job",
        lambda _identifier, **_kwargs: (_ for _ in ()).throw(ValueError("Unable to resolve SEC company for 'ZZZZ'")),
    )
    monkeypatch.setattr(worker_module.logger, "warning", lambda message, *_args: warning_messages.append(message))
    monkeypatch.setattr(worker_module.logger, "exception", lambda message, *_args: exception_messages.append(message))

    result = worker_module.run_refresh_queue_worker(poll_interval_seconds=0.01, once=True)

    assert result == 0
    assert warning_messages == ["Refresh worker skipped unresolved ticker for job %s (%s): %s"]
    assert exception_messages == []
    assert len(created_services) == 1
    assert created_services[0].close_calls == 1


def test_expected_refresh_failure_classifier() -> None:
    assert worker_module._is_expected_refresh_failure(ValueError("Unable to resolve SEC company for 'ZZZZ'")) is True
    assert worker_module._is_expected_refresh_failure(ValueError("Company identifier is required")) is False
    assert worker_module._is_expected_refresh_failure(RuntimeError("boom")) is False


def test_queue_worker_uses_sleep_for_non_blocking_idle_poll(monkeypatch) -> None:
    class _StopLoop(RuntimeError):
        pass

    real_event_type = threading.Event

    class _CountingEvent:
        allocations = 0

        def __init__(self) -> None:
            type(self).allocations += 1
            self._event = real_event_type()

        def wait(self, timeout: float | None = None) -> bool:
            return self._event.wait(timeout)

        def set(self) -> None:
            self._event.set()

    broker = _FakeBroker([None])
    broker.has_blocking_queue = False
    sleep_calls: list[float] = []

    def _sleep(interval: float) -> None:
        sleep_calls.append(interval)
        raise _StopLoop()

    monkeypatch.setattr(worker_module, "status_broker", broker)
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)
    monkeypatch.setattr(worker_module.threading, "Event", _CountingEvent)
    monkeypatch.setattr(worker_module.time, "sleep", _sleep)

    with pytest.raises(_StopLoop):
        worker_module.run_refresh_queue_worker(poll_interval_seconds=0.25, once=False)

    assert sleep_calls == [0.25]
    assert _CountingEvent.allocations == 1


def test_worker_lifecycle_heartbeat_writes_health_file(monkeypatch, tmp_path) -> None:
    health_file = tmp_path / "worker-heartbeat.txt"
    seen_heartbeats: list[tuple[str, str]] = []

    class _Broker:
        def heartbeat_worker(
            self,
            worker_id: str,
            *,
            state: str,
            current_job_id: str | None = None,
            ticker: str | None = None,
        ) -> None:
            seen_heartbeats.append((worker_id, state))

    stop_event = threading.Event()
    stop_event.set()

    monkeypatch.setattr(worker_module, "status_broker", _Broker())
    monkeypatch.setenv("DATA_FETCHER_HEALTH_HEARTBEAT_FILE", str(health_file))

    worker_module._worker_lifecycle_heartbeat_loop(
        "worker-test-1",
        {"state": "idle", "current_job_id": None, "ticker": None},
        threading.Lock(),
        stop_event,
    )

    assert seen_heartbeats == [("worker-test-1", "idle")]
    assert health_file.exists()
    assert int(health_file.read_text(encoding="utf-8").strip()) > 0


def test_queue_worker_propagates_claim_errors_and_clears_heartbeat(monkeypatch) -> None:
    clear_calls: list[str] = []

    class _ClaimFailureBroker:
        has_blocking_queue = True

        def requeue_expired_jobs(self, *, limit: int) -> None:
            assert limit == 10

        def claim_next_job_blocking(self, *, worker_id: str, timeout_seconds: float):
            assert worker_id
            assert timeout_seconds == 0.5
            raise RuntimeError("claim failed")

        def heartbeat_worker(
            self,
            worker_id: str,
            *,
            state: str,
            current_job_id: str | None = None,
            ticker: str | None = None,
        ) -> None:
            assert worker_id
            assert state

        def clear_worker_heartbeat(self, worker_id: str) -> None:
            clear_calls.append(worker_id)

    monkeypatch.setattr(worker_module, "status_broker", _ClaimFailureBroker())
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)

    with pytest.raises(RuntimeError, match="claim failed"):
        worker_module.run_refresh_queue_worker(poll_interval_seconds=0.5, once=False)

    assert len(clear_calls) == 1


def test_queue_worker_propagates_recovery_errors_and_clears_heartbeat(monkeypatch) -> None:
    clear_calls: list[str] = []

    class _RecoveryFailureBroker:
        has_blocking_queue = True

        def requeue_expired_jobs(self, *, limit: int) -> None:
            assert limit == 10
            raise RuntimeError("recovery failed")

        def claim_next_job_blocking(self, *, worker_id: str, timeout_seconds: float):
            raise AssertionError("claim_next_job_blocking should not be called after recovery failure")

        def heartbeat_worker(
            self,
            worker_id: str,
            *,
            state: str,
            current_job_id: str | None = None,
            ticker: str | None = None,
        ) -> None:
            assert worker_id
            assert state

        def clear_worker_heartbeat(self, worker_id: str) -> None:
            clear_calls.append(worker_id)

    monkeypatch.setattr(worker_module, "status_broker", _RecoveryFailureBroker())
    monkeypatch.setattr(worker_module.threading, "Thread", _FakeThread)

    with pytest.raises(RuntimeError, match="recovery failed"):
        worker_module.run_refresh_queue_worker(poll_interval_seconds=0.25, once=False)

    assert len(clear_calls) == 1

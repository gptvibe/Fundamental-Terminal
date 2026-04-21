from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.services.status_stream import JobEvent, SharedStatusBroker


def _pubsub_message(*, sequence: int, status: str, stage: str = "sync") -> dict[str, str]:
    payload = {
        "job_id": "job-1",
        "trace_id": "job-1",
        "sequence": sequence,
        "timestamp": datetime(2026, 4, 21, tzinfo=timezone.utc).isoformat(),
        "ticker": "AAPL",
        "kind": "refresh",
        "stage": stage,
        "message": f"event-{sequence}",
        "status": status,
        "level": "info",
    }
    return {"type": "message", "data": json.dumps(payload)}


class _FakePubSub:
    def __init__(self, responder: Callable[[float], Awaitable[object | None]]) -> None:
        self._responder = responder
        self.subscribed_channels: list[str] = []
        self.unsubscribed_channels: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)

    async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float) -> object | None:
        assert ignore_subscribe_messages is True
        return await self._responder(timeout)

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_channels.append(channel)

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedisAsync:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> _FakePubSub:
        return self._pubsub


def _build_broker(pubsub: _FakePubSub, *, poll_interval_seconds: float, recovery_interval_seconds: float) -> SharedStatusBroker:
    broker = SharedStatusBroker.__new__(SharedStatusBroker)
    broker._subscriber_queue_size = 50
    broker._poll_interval_seconds = poll_interval_seconds
    broker._recovery_interval_seconds = recovery_interval_seconds
    broker._recovery_batch_size = 10
    broker._lease_duration = None
    broker._redis = None
    broker._redis_async = _FakeRedisAsync(pubsub)
    broker._queue_key = "queue"
    broker._event_channel_prefix = "events:"
    return broker


def _drain_sequences(queue: asyncio.Queue[JobEvent]) -> list[int]:
    drained: list[int] = []
    while not queue.empty():
        drained.append(queue.get_nowait().sequence)
    return drained


def test_async_subscribe_recovers_skipped_pubsub_sequences(monkeypatch) -> None:
    messages = iter(
        [
            _pubsub_message(sequence=3, status="running", stage="stage-3"),
            _pubsub_message(sequence=4, status="completed", stage="stage-4"),
        ]
    )

    async def responder(_timeout: float) -> object | None:
        return next(messages, None)

    pubsub = _FakePubSub(responder)
    broker = _build_broker(pubsub, poll_interval_seconds=0.001, recovery_interval_seconds=0.05)

    recovered_events = {
        1: [
            JobEvent(
                sequence=2,
                timestamp=datetime(2026, 4, 21, tzinfo=timezone.utc),
                ticker="AAPL",
                kind="refresh",
                stage="stage-2",
                message="event-2",
                status="running",
            ),
            JobEvent(
                sequence=3,
                timestamp=datetime(2026, 4, 21, tzinfo=timezone.utc),
                ticker="AAPL",
                kind="refresh",
                stage="stage-3",
                message="event-3",
                status="running",
            ),
        ]
    }

    async def fake_async_list_events(job_id: str, *, after_sequence: int = 0) -> list[JobEvent]:
        assert job_id == "job-1"
        return recovered_events.get(after_sequence, [])

    async def fail_snapshot(_job_id: str) -> tuple[str, int] | None:
        raise AssertionError("idle snapshot recovery should not run when pubsub delivers the terminal event")

    monkeypatch.setattr(broker, "async_list_events", fake_async_list_events)
    monkeypatch.setattr(broker, "_async_job_snapshot", fail_snapshot)

    async def exercise() -> list[int]:
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        stop_event = asyncio.Event()
        await broker._subscribe_job_events_async("job-1", queue, stop_event, last_sequence=1)
        return _drain_sequences(queue)

    assert asyncio.run(exercise()) == [2, 3, 4]


def test_async_subscribe_throttles_idle_snapshot_recovery(monkeypatch) -> None:
    poll_interval_seconds = 0.01
    recovery_interval_seconds = 0.05
    idle_cycles = 6

    async def exercise() -> int:
        loop_count = 0
        stop_event = asyncio.Event()

        async def responder(timeout: float) -> object | None:
            nonlocal loop_count
            loop_count += 1
            await asyncio.sleep(timeout)
            if loop_count >= idle_cycles:
                stop_event.set()
            return None

        pubsub = _FakePubSub(responder)
        broker = _build_broker(
            pubsub,
            poll_interval_seconds=poll_interval_seconds,
            recovery_interval_seconds=recovery_interval_seconds,
        )

        snapshot_calls = 0

        async def fake_async_job_snapshot(job_id: str) -> tuple[str, int] | None:
            nonlocal snapshot_calls
            assert job_id == "job-1"
            snapshot_calls += 1
            return ("running", 0)

        async def fake_async_list_events(_job_id: str, *, after_sequence: int = 0) -> list[JobEvent]:
            assert after_sequence == 0
            return []

        monkeypatch.setattr(broker, "_async_job_snapshot", fake_async_job_snapshot)
        monkeypatch.setattr(broker, "async_list_events", fake_async_list_events)

        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        await broker._subscribe_job_events_async("job-1", queue, stop_event, last_sequence=0)
        assert queue.empty()
        return snapshot_calls

    assert asyncio.run(exercise()) == 1
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal


JobState = Literal["queued", "running", "completed", "failed"]
JobLevel = Literal["info", "success", "error"]


@dataclass(slots=True)
class JobEvent:
    sequence: int
    timestamp: datetime
    stage: str
    message: str
    status: JobState
    level: JobLevel = "info"

    def to_payload(self, job_id: str) -> dict[str, str | int]:
        return {
            "job_id": job_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "stage": self.stage,
            "message": self.message,
            "status": self.status,
            "level": self.level,
        }


@dataclass(slots=True)
class JobRecord:
    job_id: str
    ticker: str
    kind: str
    status: JobState = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    sequence: int = 0
    events: list[JobEvent] = field(default_factory=list)
    subscribers: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue[JobEvent]]] = field(default_factory=dict)


class StatusBroker:
    def __init__(self, *, max_jobs: int = 250, retention_minutes: int = 120) -> None:
        self._lock = threading.Lock()
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._max_jobs = max_jobs
        self._retention = timedelta(minutes=retention_minutes)

    def create_job(self, *, ticker: str, kind: str) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord(job_id=job_id, ticker=ticker, kind=kind)
        with self._lock:
            self._jobs[job_id] = record
            self._prune_locked()

        self.publish(job_id, stage="queued", message=f"{kind.title()} job queued for {ticker}", status="queued")
        return job_id

    def publish(
        self,
        job_id: str,
        *,
        stage: str,
        message: str,
        status: JobState | None = None,
        level: JobLevel = "info",
    ) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return

            if status is not None:
                record.status = status
            record.sequence += 1
            event = JobEvent(
                sequence=record.sequence,
                timestamp=datetime.now(timezone.utc),
                stage=stage,
                message=message,
                status=record.status,
                level=level,
            )
            record.events.append(event)
            subscribers = list(record.subscribers.values())

        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                continue

    def complete(self, job_id: str, *, message: str = "Refresh complete") -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            record.completed_at = datetime.now(timezone.utc)
        self.publish(job_id, stage="complete", message=message, status="completed", level="success")

    def fail(self, job_id: str, *, message: str) -> None:
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                return
            record.completed_at = datetime.now(timezone.utc)
        self.publish(job_id, stage="error", message=message, status="failed", level="error")

    def subscribe(
        self,
        job_id: str,
    ) -> tuple[list[JobEvent], asyncio.Queue[JobEvent], Callable[[], None]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[JobEvent] = asyncio.Queue()
        token = uuid.uuid4().hex
        with self._lock:
            record = self._jobs.get(job_id)
            if record is None:
                raise KeyError(job_id)
            backlog = list(record.events)
            record.subscribers[token] = (loop, queue)

        def unsubscribe() -> None:
            with self._lock:
                active_record = self._jobs.get(job_id)
                if active_record is not None:
                    active_record.subscribers.pop(token, None)

        return backlog, queue, unsubscribe

    def format_sse(self, job_id: str, event: JobEvent) -> str:
        payload = json.dumps(event.to_payload(job_id))
        return f"event: status\ndata: {payload}\n\n"

    def has_job(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs

    def _prune_locked(self) -> None:
        cutoff = datetime.now(timezone.utc) - self._retention
        stale_job_ids = [job_id for job_id, record in self._jobs.items() if record.completed_at and record.completed_at < cutoff]
        for job_id in stale_job_ids:
            self._jobs.pop(job_id, None)

        while len(self._jobs) > self._max_jobs:
            self._jobs.popitem(last=False)


class JobReporter:
    def __init__(self, job_id: str | None = None) -> None:
        self.job_id = job_id

    @property
    def enabled(self) -> bool:
        return self.job_id is not None

    def step(self, stage: str, message: str) -> None:
        if self.job_id is not None:
            status_broker.publish(self.job_id, stage=stage, message=message, status="running")

    def complete(self, message: str) -> None:
        if self.job_id is not None:
            status_broker.complete(self.job_id, message=message)

    def fail(self, message: str) -> None:
        if self.job_id is not None:
            status_broker.fail(self.job_id, message=message)


status_broker = StatusBroker()

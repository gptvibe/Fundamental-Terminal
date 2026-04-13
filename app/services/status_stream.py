from __future__ import annotations

import asyncio
from contextlib import contextmanager
import json
import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import settings
from app.db.session import SessionLocal, async_session_maker, get_async_engine, get_bound_request_sync_session, get_engine
from app.models import RefreshJob, RefreshJobEvent
from app.observability import emit_structured_log
from app.services.refresh_state import ensure_company, set_active_refresh_job

try:
    import redis
    import redis.asyncio as redis_async
    from redis.exceptions import RedisError
except Exception:  # pragma: no cover - optional dependency at runtime
    redis = None
    redis_async = None

    class RedisError(Exception):
        pass


JobState = Literal["queued", "running", "completed", "failed"]
JobLevel = Literal["info", "success", "error"]

ACTIVE_JOB_STATES = frozenset({"queued", "running"})
TERMINAL_JOB_STATES = frozenset({"completed", "failed"})

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class JobEvent:
    sequence: int
    timestamp: datetime
    ticker: str
    kind: str
    stage: str
    message: str
    status: JobState
    level: JobLevel = "info"

    def to_payload(self, job_id: str) -> dict[str, str | int | None]:
        return {
            "job_id": job_id,
            "trace_id": job_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "ticker": self.ticker,
            "kind": self.kind,
            "stage": self.stage,
            "message": self.message,
            "status": self.status,
            "level": self.level,
        }


@dataclass(frozen=True, slots=True)
class ClaimedJob:
    job_id: str
    ticker: str
    kind: str
    dataset: str
    force: bool
    company_id: int | None
    worker_id: str
    claim_token: str


def _safe_put_nowait(queue: asyncio.Queue[JobEvent], event: JobEvent) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        pass


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
    def __init__(
        self,
        *,
        max_jobs: int = 250,
        retention_minutes: int = 120,
        max_events_per_job: int = 200,
        subscriber_queue_size: int = 200,
    ) -> None:
        self._lock = threading.Lock()
        self._jobs: OrderedDict[str, JobRecord] = OrderedDict()
        self._max_jobs = max_jobs
        self._retention = timedelta(minutes=retention_minutes)
        self._max_events_per_job = max_events_per_job
        self._subscriber_queue_size = subscriber_queue_size

    def create_job(self, *, ticker: str, kind: str) -> str:
        job_id = uuid.uuid4().hex
        record = JobRecord(job_id=job_id, ticker=ticker, kind=kind)
        with self._lock:
            self._jobs[job_id] = record
            self._prune_locked()

        self.publish(job_id, stage="queued", message=f"{kind.title()} job queued for {ticker}", status="queued")
        return job_id

    def get_active_job_id(self, *, ticker: str, kind: str) -> str | None:
        with self._lock:
            for record in reversed(tuple(self._jobs.values())):
                if record.ticker != ticker or record.kind != kind:
                    continue
                if record.status in ACTIVE_JOB_STATES:
                    return record.job_id

        return None

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
                ticker=record.ticker,
                kind=record.kind,
                stage=stage,
                message=message,
                status=record.status,
                level=level,
            )
            record.events.append(event)
            if len(record.events) > self._max_events_per_job:
                record.events = record.events[-self._max_events_per_job :]
            subscribers = list(record.subscribers.values())

        _emit_event_log(job_id, event)

        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(_safe_put_nowait, queue, event)
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
        queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
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
            oldest_job_id, oldest_record = next(iter(self._jobs.items()))
            if oldest_record.status in ACTIVE_JOB_STATES:
                break
            self._jobs.pop(oldest_job_id, None)


class SharedStatusBroker:
    def __init__(
        self,
        *,
        subscriber_queue_size: int = 200,
        poll_interval_seconds: float = settings.refresh_status_poll_seconds,
        recovery_batch_size: int = 10,
    ) -> None:
        self._subscriber_queue_size = subscriber_queue_size
        self._poll_interval_seconds = poll_interval_seconds
        self._recovery_batch_size = recovery_batch_size
        self._lease_duration = timedelta(seconds=settings.refresh_lock_timeout_seconds)
        self._redis = self._build_sync_redis_client()
        self._redis_async = self._build_async_redis_client()
        self._queue_key = f"{settings.hot_response_cache_namespace}:refresh-jobs:queue"
        self._event_channel_prefix = f"{settings.hot_response_cache_namespace}:refresh-jobs:events:"

    @property
    def has_blocking_queue(self) -> bool:
        return self._redis is not None

    def create_job(
        self,
        *,
        ticker: str,
        kind: str,
        dataset: str = "company_refresh",
        force: bool = False,
        company_id: int | None = None,
    ) -> str:
        normalized_ticker = ticker.strip().upper()
        now = datetime.now(timezone.utc)

        with self._sync_session_scope() as session:
            existing_job = self._get_active_job(session, ticker=normalized_ticker, kind=kind, dataset=dataset)
            if existing_job is not None:
                return existing_job.job_id

            resolved_company_id = company_id
            if resolved_company_id is None:
                company = ensure_company(session, normalized_ticker)
                resolved_company_id = company.id if company is not None else None

            job = RefreshJob(
                job_id=uuid.uuid4().hex,
                company_id=resolved_company_id,
                ticker=normalized_ticker,
                dataset=dataset,
                kind=kind,
                force=force,
                status="queued",
                requested_at=now,
                updated_at=now,
            )
            try:
                session.add(job)
                session.flush()
                event = self._append_event(
                    session,
                    job,
                    timestamp=now,
                    stage="queued",
                    message=f"{kind.title()} job queued for {normalized_ticker}",
                    status="queued",
                )
                if resolved_company_id is not None:
                    set_active_refresh_job(
                        session,
                        company_id=resolved_company_id,
                        dataset=dataset,
                        job_id=job.job_id,
                        updated_at=now,
                    )
                session.commit()
            except IntegrityError:
                session.rollback()
                existing_job = self._get_active_job(session, ticker=normalized_ticker, kind=kind, dataset=dataset)
                if existing_job is not None:
                    return existing_job.job_id
                raise

        _emit_event_log(job.job_id, event)
        self._publish_realtime_event(job.job_id, event)
        self._enqueue_job_signal(job.job_id)
        return job.job_id

    def get_active_job_id(self, *, ticker: str, kind: str, dataset: str = "company_refresh") -> str | None:
        normalized_ticker = ticker.strip().upper()
        with self._sync_session_scope() as session:
            job = self._get_active_job(session, ticker=normalized_ticker, kind=kind, dataset=dataset)
            return job.job_id if job is not None else None

    def publish(
        self,
        job_id: str,
        *,
        stage: str,
        message: str,
        status: JobState | None = None,
        level: JobLevel = "info",
        expected_claim_token: str | None = None,
    ) -> None:
        event = self._record_event(
            job_id,
            stage=stage,
            message=message,
            status=status,
            level=level,
            expected_claim_token=expected_claim_token,
        )
        if event is not None:
            _emit_event_log(job_id, event)
            self._publish_realtime_event(job_id, event)

    def complete(
        self,
        job_id: str,
        *,
        message: str = "Refresh complete",
        expected_claim_token: str | None = None,
    ) -> None:
        self.publish(
            job_id,
            stage="complete",
            message=message,
            status="completed",
            level="success",
            expected_claim_token=expected_claim_token,
        )

    def fail(self, job_id: str, *, message: str, expected_claim_token: str | None = None) -> None:
        self.publish(
            job_id,
            stage="error",
            message=message,
            status="failed",
            level="error",
            expected_claim_token=expected_claim_token,
        )

    def touch(self, job_id: str, *, expected_claim_token: str | None = None) -> None:
        now = datetime.now(timezone.utc)
        try:
            with self._sync_session_scope() as session:
                job = self._get_job(session, job_id, for_update=True)
                if job is None or job.status != "running":
                    return
                if expected_claim_token is not None and job.claim_token != expected_claim_token:
                    return
                job.last_heartbeat_at = now
                job.lease_expires_at = now + self._lease_duration
                job.updated_at = now
                session.commit()
        except SQLAlchemyError:
            return

    def claim_next_job(self, *, worker_id: str) -> ClaimedJob | None:
        now = datetime.now(timezone.utc)

        with self._sync_session_scope() as session:
            statement: Select[tuple[RefreshJob]] = (
                select(RefreshJob)
                .where(RefreshJob.status == "queued")
                .order_by(RefreshJob.requested_at.asc(), RefreshJob.id.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            job = session.execute(statement).scalar_one_or_none()
            if job is None:
                return None

            claim_token = uuid.uuid4().hex
            job.status = "running"
            job.started_at = job.started_at or now
            job.claimed_at = now
            job.last_heartbeat_at = now
            job.lease_expires_at = now + self._lease_duration
            job.worker_id = worker_id
            job.claim_token = claim_token
            job.attempt_count += 1
            job.last_error = None
            job.updated_at = now
            event = self._append_event(
                session,
                job,
                timestamp=now,
                stage="started",
                message=f"{job.kind.title()} job started for {job.ticker}",
                status="running",
            )
            session.commit()

        _emit_event_log(job.job_id, event)
        self._publish_realtime_event(job.job_id, event)
        return ClaimedJob(
            job_id=job.job_id,
            ticker=job.ticker,
            kind=job.kind,
            dataset=job.dataset,
            force=job.force,
            company_id=job.company_id,
            worker_id=worker_id,
            claim_token=claim_token,
        )

    def claim_next_job_blocking(self, *, worker_id: str, timeout_seconds: float | None = None) -> ClaimedJob | None:
        if self._redis is None:
            return self.claim_next_job(worker_id=worker_id)

        timeout = max(1, int(timeout_seconds or settings.refresh_queue_block_seconds))
        try:
            self._redis.blpop(self._queue_key, timeout=timeout)
        except RedisError:
            return self.claim_next_job(worker_id=worker_id)
        return self.claim_next_job(worker_id=worker_id)

    def requeue_expired_jobs(self, *, limit: int = 10) -> int:
        now = datetime.now(timezone.utc)
        emitted: list[tuple[str, JobEvent]] = []
        with self._sync_session_scope() as session:
            statement: Select[tuple[RefreshJob]] = (
                select(RefreshJob)
                .where(
                    RefreshJob.status == "running",
                    RefreshJob.lease_expires_at.is_not(None),
                    RefreshJob.lease_expires_at < now,
                )
                .order_by(RefreshJob.lease_expires_at, RefreshJob.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            jobs = list(session.execute(statement).scalars())
            for job in jobs:
                job.status = "queued"
                job.claimed_at = None
                job.last_heartbeat_at = None
                job.lease_expires_at = None
                job.worker_id = None
                job.claim_token = None
                job.last_error = "worker_lease_expired"
                job.updated_at = now
                event = self._append_event(
                    session,
                    job,
                    timestamp=now,
                    stage="requeued",
                    message="Worker lease expired; refresh job returned to the queue",
                    status="queued",
                    level="error",
                )
                emitted.append((job.job_id, event))
            session.commit()

        for public_job_id, event in emitted:
            _emit_event_log(public_job_id, event)
            self._publish_realtime_event(public_job_id, event)
            self._enqueue_job_signal(public_job_id)
        return len(emitted)

    def subscribe(
        self,
        job_id: str,
    ) -> tuple[list[JobEvent], asyncio.Queue[JobEvent], Callable[[], None]]:
        if not self.has_job(job_id):
            raise KeyError(job_id)

        backlog = self.list_events(job_id)
        queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        stop_event = asyncio.Event()
        task = asyncio.create_task(
            self._poll_job_events(
                job_id,
                queue,
                stop_event,
                last_sequence=backlog[-1].sequence if backlog else 0,
            )
        )

        def unsubscribe() -> None:
            stop_event.set()
            task.cancel()

        return backlog, queue, unsubscribe

    async def async_subscribe(
        self,
        job_id: str,
    ) -> tuple[list[JobEvent], asyncio.Queue[JobEvent], Callable[[], None]]:
        if not await self.async_has_job(job_id):
            raise KeyError(job_id)

        backlog = await self.async_list_events(job_id)
        queue: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=self._subscriber_queue_size)
        stop_event = asyncio.Event()
        last_sequence = backlog[-1].sequence if backlog else 0
        task = asyncio.create_task(
            self._subscribe_job_events_async(
                job_id,
                queue,
                stop_event,
                last_sequence=last_sequence,
            )
        )

        def unsubscribe() -> None:
            stop_event.set()
            task.cancel()

        return backlog, queue, unsubscribe

    def list_events(self, job_id: str, *, after_sequence: int = 0) -> list[JobEvent]:
        with self._sync_session_scope() as session:
            return self._list_events_in_session(session, job_id, after_sequence=after_sequence)

    async def async_list_events(self, job_id: str, *, after_sequence: int = 0) -> list[JobEvent]:
        return await self._run_async(lambda session: self._list_events_in_session(session, job_id, after_sequence=after_sequence))

    def format_sse(self, job_id: str, event: JobEvent) -> str:
        payload_data = event.to_payload(job_id)
        payload_data.update(self._build_queue_payload(job_id, event))
        payload = json.dumps(payload_data)
        return f"event: status\ndata: {payload}\n\n"

    def has_job(self, job_id: str) -> bool:
        return self._job_snapshot(job_id) is not None

    async def async_has_job(self, job_id: str) -> bool:
        return await self._async_job_snapshot(job_id) is not None

    async def _poll_job_events(
        self,
        job_id: str,
        queue: asyncio.Queue[JobEvent],
        stop_event: asyncio.Event,
        *,
        last_sequence: int,
    ) -> None:
        try:
            while not stop_event.is_set():
                snapshot = self._job_snapshot(job_id)
                if snapshot is None:
                    return

                status, event_sequence = snapshot
                if event_sequence > last_sequence:
                    for event in self.list_events(job_id, after_sequence=last_sequence):
                        last_sequence = event.sequence
                        _safe_put_nowait(queue, event)

                if status in TERMINAL_JOB_STATES and last_sequence >= event_sequence:
                    return

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _poll_job_events_async(
        self,
        job_id: str,
        queue: asyncio.Queue[JobEvent],
        stop_event: asyncio.Event,
        *,
        last_sequence: int,
    ) -> None:
        try:
            while not stop_event.is_set():
                snapshot = await self._async_job_snapshot(job_id)
                if snapshot is None:
                    return

                status, event_sequence = snapshot
                if event_sequence > last_sequence:
                    for event in await self.async_list_events(job_id, after_sequence=last_sequence):
                        last_sequence = event.sequence
                        _safe_put_nowait(queue, event)

                if status in TERMINAL_JOB_STATES and last_sequence >= event_sequence:
                    return

                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=self._poll_interval_seconds)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            return

    async def _subscribe_job_events_async(
        self,
        job_id: str,
        queue: asyncio.Queue[JobEvent],
        stop_event: asyncio.Event,
        *,
        last_sequence: int,
    ) -> None:
        if self._redis_async is None:
            await self._poll_job_events_async(job_id, queue, stop_event, last_sequence=last_sequence)
            return

        pubsub = self._redis_async.pubsub()
        channel = self._event_channel(job_id)
        try:
            await pubsub.subscribe(channel)
            while not stop_event.is_set():
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=self._poll_interval_seconds)
                except RedisError:
                    await self._poll_job_events_async(job_id, queue, stop_event, last_sequence=last_sequence)
                    return

                event = _job_event_from_pubsub(message)
                if event is not None and event.sequence > last_sequence:
                    last_sequence = event.sequence
                    _safe_put_nowait(queue, event)
                    if event.status in TERMINAL_JOB_STATES:
                        return
                    continue

                snapshot = await self._async_job_snapshot(job_id)
                if snapshot is None:
                    return

                status, event_sequence = snapshot
                if event_sequence > last_sequence:
                    for missed_event in await self.async_list_events(job_id, after_sequence=last_sequence):
                        last_sequence = missed_event.sequence
                        _safe_put_nowait(queue, missed_event)
                if status in TERMINAL_JOB_STATES and last_sequence >= event_sequence:
                    return
        except asyncio.CancelledError:
            return
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:
                pass
            try:
                await pubsub.aclose()
            except Exception:
                pass

    def _build_queue_payload(self, job_id: str, event: JobEvent) -> dict[str, int]:
        if event.status != "queued":
            return {}

        try:
            with self._sync_session_scope() as session:
                queued_snapshot = self._queued_job_snapshot_in_session(session, job_id)
                if queued_snapshot is None:
                    return {}

                requested_at, job_pk = queued_snapshot
                jobs_ahead = self._count_jobs_ahead_in_session(session, requested_at=requested_at, job_pk=job_pk)
        except SQLAlchemyError:
            return {}

        return {
            "queue_position": jobs_ahead + 1,
            "jobs_ahead": jobs_ahead,
        }

    def _job_snapshot(self, job_id: str) -> tuple[str, int] | None:
        try:
            with self._sync_session_scope() as session:
                return self._job_snapshot_in_session(session, job_id)
        except SQLAlchemyError:
            return None

    async def _async_job_snapshot(self, job_id: str) -> tuple[str, int] | None:
        try:
            return await self._run_async(lambda session: self._job_snapshot_in_session(session, job_id))
        except SQLAlchemyError:
            return None

    def _record_event(
        self,
        job_id: str,
        *,
        stage: str,
        message: str,
        status: JobState | None,
        level: JobLevel,
        expected_claim_token: str | None,
    ) -> JobEvent | None:
        now = datetime.now(timezone.utc)
        try:
            with self._sync_session_scope() as session:
                job = self._get_job(session, job_id, for_update=True)
                if job is None:
                    return None
                if expected_claim_token is not None and job.claim_token != expected_claim_token:
                    return None

                next_status = status or job.status
                if next_status == "queued":
                    job.claimed_at = None
                    job.last_heartbeat_at = None
                    job.lease_expires_at = None
                    job.worker_id = None
                    job.claim_token = None
                elif next_status == "running":
                    job.last_heartbeat_at = now
                    job.lease_expires_at = now + self._lease_duration
                else:
                    job.completed_at = now
                    job.last_heartbeat_at = now
                    job.lease_expires_at = None
                    job.claim_token = None

                job.status = next_status
                if next_status == "failed":
                    job.last_error = message
                job.updated_at = now
                event = self._append_event(
                    session,
                    job,
                    timestamp=now,
                    stage=stage,
                    message=message,
                    status=next_status,
                    level=level,
                )
                session.commit()
                return event
        except SQLAlchemyError:
            return None

    def _append_event(
        self,
        session,
        job: RefreshJob,
        *,
        timestamp: datetime,
        stage: str,
        message: str,
        status: JobState,
        level: JobLevel = "info",
    ) -> JobEvent:
        job.event_sequence += 1
        event = RefreshJobEvent(
            refresh_job_id=job.id,
            sequence=job.event_sequence,
            timestamp=timestamp,
            ticker=job.ticker,
            kind=job.kind,
            stage=stage,
            message=message,
            status=status,
            level=level,
        )
        session.add(event)
        return JobEvent(
            sequence=event.sequence,
            timestamp=event.timestamp,
            ticker=event.ticker,
            kind=event.kind,
            stage=event.stage,
            message=event.message,
            status=event.status,
            level=event.level,
        )

    @contextmanager
    def _sync_session_scope(self):
        bound_session = get_bound_request_sync_session()
        if bound_session is not None:
            yield bound_session
            return

        get_engine()
        with SessionLocal() as session:
            yield session

    async def _run_async(self, callback: Callable[[object], object]):
        get_async_engine()
        async with async_session_maker() as session:
            return await session.run_sync(callback)

    def _list_events_in_session(self, session, job_id: str, *, after_sequence: int = 0) -> list[JobEvent]:
        job = self._get_job(session, job_id)
        if job is None:
            return []
        statement: Select[tuple[RefreshJobEvent]] = (
            select(RefreshJobEvent)
            .where(RefreshJobEvent.refresh_job_id == job.id, RefreshJobEvent.sequence > after_sequence)
            .order_by(RefreshJobEvent.sequence)
        )
        return [
            JobEvent(
                sequence=event.sequence,
                timestamp=event.timestamp,
                ticker=event.ticker,
                kind=event.kind,
                stage=event.stage,
                message=event.message,
                status=event.status,
                level=event.level,
            )
            for event in session.execute(statement).scalars()
        ]

    def _job_snapshot_in_session(self, session, job_id: str) -> tuple[str, int] | None:
        statement = select(RefreshJob.status, RefreshJob.event_sequence).where(RefreshJob.job_id == job_id)
        row = session.execute(statement).one_or_none()
        if row is None:
            return None
        return str(row[0]), int(row[1])

    def _queued_job_snapshot_in_session(self, session, job_id: str) -> tuple[datetime, int] | None:
        statement = select(RefreshJob.requested_at, RefreshJob.id, RefreshJob.status).where(RefreshJob.job_id == job_id)
        row = session.execute(statement).one_or_none()
        if row is None or row[2] != "queued":
            return None
        return row[0], int(row[1])

    def _count_jobs_ahead_in_session(self, session, *, requested_at: datetime, job_pk: int) -> int:
        statement = select(func.count()).select_from(RefreshJob).where(
            RefreshJob.status.in_(tuple(ACTIVE_JOB_STATES)),
            (RefreshJob.requested_at < requested_at)
            | ((RefreshJob.requested_at == requested_at) & (RefreshJob.id < job_pk)),
        )
        return int(session.execute(statement).scalar_one())

    def _get_active_job(self, session, *, ticker: str, kind: str, dataset: str) -> RefreshJob | None:
        statement: Select[tuple[RefreshJob]] = (
            select(RefreshJob)
            .where(
                RefreshJob.ticker == ticker,
                RefreshJob.kind == kind,
                RefreshJob.dataset == dataset,
                RefreshJob.status.in_(tuple(ACTIVE_JOB_STATES)),
            )
            .order_by(RefreshJob.requested_at.desc(), RefreshJob.id.desc())
            .limit(1)
        )
        return session.execute(statement).scalar_one_or_none()

    def _get_job(self, session, job_id: str, *, for_update: bool = False) -> RefreshJob | None:
        statement: Select[tuple[RefreshJob]] = select(RefreshJob).where(RefreshJob.job_id == job_id)
        if for_update:
            statement = statement.with_for_update()
        return session.execute(statement).scalar_one_or_none()

    def _build_sync_redis_client(self):
        if redis is None:
            return None
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=max(settings.refresh_queue_block_seconds + 1.0, 5.0),
                socket_connect_timeout=1.0,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _build_async_redis_client(self):
        if redis_async is None:
            return None
        try:
            return redis_async.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=max(settings.refresh_status_poll_seconds + 1.0, 5.0),
                socket_connect_timeout=1.0,
            )
        except Exception:
            return None

    def _enqueue_job_signal(self, job_id: str) -> None:
        if self._redis is None:
            return
        try:
            self._redis.rpush(self._queue_key, job_id)
        except RedisError:
            return

    def _publish_realtime_event(self, job_id: str, event: JobEvent) -> None:
        if self._redis is None:
            return
        try:
            self._redis.publish(self._event_channel(job_id), json.dumps(event.to_payload(job_id), separators=(",", ":")))
        except RedisError:
            return

    def _event_channel(self, job_id: str) -> str:
        return f"{self._event_channel_prefix}{job_id}"


class JobReporter:
    def __init__(self, job_id: str | None = None, *, claim_token: str | None = None) -> None:
        self.job_id = job_id
        self.claim_token = claim_token

    @property
    def enabled(self) -> bool:
        return self.job_id is not None

    def step(self, stage: str, message: str) -> None:
        if self.job_id is not None:
            status_broker.publish(
                self.job_id,
                stage=stage,
                message=message,
                status="running",
                expected_claim_token=self.claim_token,
            )

    def complete(self, message: str) -> None:
        if self.job_id is not None:
            status_broker.complete(self.job_id, message=message, expected_claim_token=self.claim_token)

    def fail(self, message: str) -> None:
        if self.job_id is not None:
            status_broker.fail(self.job_id, message=message, expected_claim_token=self.claim_token)


def _emit_event_log(job_id: str, event: JobEvent) -> None:
    emit_structured_log(
        logger,
        "job.event",
        job_id=job_id,
        trace_id=job_id,
        ticker=event.ticker,
        job_kind=event.kind,
        stage=event.stage,
        message=event.message,
        status=event.status,
        level_name=event.level,
        sequence=event.sequence,
    )


def _job_event_from_pubsub(message: object) -> JobEvent | None:
    if not isinstance(message, dict) or message.get("type") != "message":
        return None

    payload = message.get("data")
    if payload is None:
        return None

    try:
        parsed = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    timestamp = parsed.get("timestamp")
    if not isinstance(timestamp, str):
        return None
    if timestamp.endswith("Z"):
        timestamp = f"{timestamp[:-1]}+00:00"

    try:
        parsed_timestamp = datetime.fromisoformat(timestamp)
    except ValueError:
        return None

    if parsed_timestamp.tzinfo is None:
        parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
    else:
        parsed_timestamp = parsed_timestamp.astimezone(timezone.utc)

    try:
        sequence = int(parsed.get("sequence"))
    except (TypeError, ValueError):
        return None

    return JobEvent(
        sequence=sequence,
        timestamp=parsed_timestamp,
        ticker=str(parsed.get("ticker") or ""),
        kind=str(parsed.get("kind") or ""),
        stage=str(parsed.get("stage") or ""),
        message=str(parsed.get("message") or ""),
        status=str(parsed.get("status") or "queued"),
        level=str(parsed.get("level") or "info"),
    )


status_broker = SharedStatusBroker()

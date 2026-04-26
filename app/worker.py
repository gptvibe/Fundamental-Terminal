from __future__ import annotations

import argparse
import logging
import threading
import time
import uuid

from app.config import settings
from app.observability import observe_worker_job
from app.services.fetch_trigger import queue_company_refresh
from app.services.sec_edgar import EdgarIngestionService, run_refresh_job
from app.services.status_stream import ClaimedJob, status_broker


logger = logging.getLogger(__name__)


def _heartbeat_loop(job: ClaimedJob, stop_event: threading.Event) -> None:
    interval = max(5.0, settings.refresh_lock_timeout_seconds / 3)
    while not stop_event.wait(interval):
        status_broker.touch(job.job_id, expected_claim_token=job.claim_token)


def _worker_lifecycle_heartbeat_loop(
    worker_id: str,
    state_ref: dict[str, str | None],
    state_lock: threading.Lock,
    stop_event: threading.Event,
) -> None:
    interval = max(2.0, settings.worker_heartbeat_interval_seconds)
    while True:
        with state_lock:
            state = str(state_ref.get("state") or "idle")
            current_job_id = state_ref.get("current_job_id")
            ticker = state_ref.get("ticker")
        status_broker.heartbeat_worker(
            worker_id,
            state=state,
            current_job_id=current_job_id,
            ticker=ticker,
        )
        if stop_event.wait(interval):
            return


def run_refresh_queue_worker(*, poll_interval_seconds: float | None = None, once: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    effective_poll_interval = poll_interval_seconds or settings.refresh_queue_poll_seconds
    worker_id = f"{threading.current_thread().name}-{uuid.uuid4().hex[:8]}"
    next_recovery_at = 0.0
    service: EdgarIngestionService | None = None
    worker_state_lock = threading.Lock()
    worker_state: dict[str, str | None] = {"state": "starting", "current_job_id": None, "ticker": None}
    lifecycle_stop_event = threading.Event()
    lifecycle_thread = threading.Thread(
        target=_worker_lifecycle_heartbeat_loop,
        args=(worker_id, worker_state, worker_state_lock, lifecycle_stop_event),
        name=f"worker-heartbeat-{worker_id[-8:]}",
        daemon=True,
    )

    def _update_worker_state(*, state: str, current_job_id: str | None = None, ticker: str | None = None) -> None:
        with worker_state_lock:
            worker_state["state"] = state
            worker_state["current_job_id"] = current_job_id
            worker_state["ticker"] = ticker.strip().upper() if ticker else None

    try:
        lifecycle_thread.start()
        _update_worker_state(state="idle")
        while True:
            now = time.monotonic()
            if now >= next_recovery_at:
                status_broker.requeue_expired_jobs(limit=10)
                next_recovery_at = now + settings.refresh_recovery_interval_seconds

            job = status_broker.claim_next_job_blocking(worker_id=worker_id, timeout_seconds=effective_poll_interval)
            if job is None:
                _close_refresh_service(service)
                service = None
                _update_worker_state(state="idle")
                if once:
                    return 0
                if not status_broker.has_blocking_queue:
                    threading.Event().wait(effective_poll_interval)
                continue

            if service is None:
                service = EdgarIngestionService()

            logger.info("Processing refresh job %s for %s", job.job_id, job.ticker)
            _update_worker_state(state="busy", current_job_id=job.job_id, ticker=job.ticker)
            stop_event = threading.Event()
            heartbeat_thread = threading.Thread(
                target=_heartbeat_loop,
                args=(job, stop_event),
                name=f"refresh-heartbeat-{job.job_id[:8]}",
                daemon=True,
            )
            heartbeat_thread.start()
            try:
                with observe_worker_job(
                    worker_kind="refresh_queue",
                    job_name="refresh_job",
                    trace_id=job.job_id,
                    ticker=job.ticker,
                    count_refresh_failure=True,
                ):
                    run_refresh_job(
                        job.ticker,
                        force=job.force,
                        job_id=job.job_id,
                        claim_token=job.claim_token,
                        service=service,
                    )
            except Exception:
                logger.exception("Refresh worker failed for job %s (%s)", job.job_id, job.ticker)
                _close_refresh_service(service)
                service = None
            finally:
                stop_event.set()
                heartbeat_thread.join(timeout=1.0)
                _update_worker_state(state="idle")
    finally:
        _update_worker_state(state="stopping")
        lifecycle_stop_event.set()
        lifecycle_thread.join(timeout=1.0)
        status_broker.clear_worker_heartbeat(worker_id)
        _close_refresh_service(service)


def enqueue_refresh_jobs(identifiers: list[str], *, force: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for identifier in identifiers:
        job_id = queue_company_refresh(None, identifier, force=force)
        logger.info("Queued refresh job %s for %s", job_id, identifier.strip().upper())
    return 0


def _close_refresh_service(service: EdgarIngestionService | None) -> None:
    if service is None:
        return
    try:
        service.close()
    except Exception:
        logger.exception("Failed to close refresh worker service")


def worker_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or feed the durable company refresh queue")
    parser.add_argument("identifiers", nargs="*", help="Ticker symbols to enqueue onto the refresh queue")
    parser.add_argument("--enqueue", action="store_true", help="Enqueue the supplied identifiers onto the refresh queue")
    parser.add_argument("--queue-worker", action="store_true", help="Run the queue consumer loop")
    parser.add_argument("--once", action="store_true", help="Exit after a single claim attempt when running the queue consumer")
    parser.add_argument("--poll-interval", type=float, default=settings.refresh_queue_poll_seconds, help="Seconds between queue polls when idle")
    parser.add_argument("--force", action="store_true", help="Bypass the freshness window for enqueued refresh jobs")
    args = parser.parse_args(argv)

    if args.queue_worker or not args.identifiers:
        return run_refresh_queue_worker(poll_interval_seconds=args.poll_interval, once=args.once)
    return enqueue_refresh_jobs(list(args.identifiers), force=args.force)


if __name__ == "__main__":
    raise SystemExit(worker_main())

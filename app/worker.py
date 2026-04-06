from __future__ import annotations

import argparse
import logging
import threading
import uuid

from app.config import settings
from app.services.fetch_trigger import queue_company_refresh
from app.services.sec_edgar import run_refresh_job
from app.services.status_stream import ClaimedJob, status_broker


logger = logging.getLogger(__name__)


def _heartbeat_loop(job: ClaimedJob, stop_event: threading.Event) -> None:
    interval = max(5.0, settings.refresh_lock_timeout_seconds / 3)
    while not stop_event.wait(interval):
        status_broker.touch(job.job_id, expected_claim_token=job.claim_token)


def run_refresh_queue_worker(*, poll_interval_seconds: float | None = None, once: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    effective_poll_interval = poll_interval_seconds or settings.refresh_queue_poll_seconds
    worker_id = f"{threading.current_thread().name}-{uuid.uuid4().hex[:8]}"

    while True:
        job = status_broker.claim_next_job(worker_id=worker_id)
        if job is None:
            if once:
                return 0
            threading.Event().wait(effective_poll_interval)
            continue

        logger.info("Processing refresh job %s for %s", job.job_id, job.ticker)
        stop_event = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            args=(job, stop_event),
            name=f"refresh-heartbeat-{job.job_id[:8]}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            run_refresh_job(job.ticker, force=job.force, job_id=job.job_id, claim_token=job.claim_token)
        except Exception:
            logger.exception("Refresh worker failed for job %s (%s)", job.job_id, job.ticker)
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=1.0)


def enqueue_refresh_jobs(identifiers: list[str], *, force: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for identifier in identifiers:
        job_id = queue_company_refresh(None, identifier, force=force)
        logger.info("Queued refresh job %s for %s", job_id, identifier.strip().upper())
    return 0


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

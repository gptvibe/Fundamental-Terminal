from __future__ import annotations

import logging

from app.observability import observe_worker_job
from app.services.market_context import run_market_context_refresh_job


def macro_worker_main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        with observe_worker_job(
            worker_kind="macro",
            job_name="market_context_refresh",
            trace_id="macro-market-context-refresh",
        ):
            run_market_context_refresh_job()
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(macro_worker_main())

# Incremental Price Refresh No-Op Benchmark

This repo now has a no-op fast path for incremental Yahoo price refreshes when the fetched overlap window exactly matches the stored overlap window.

## What was measured

Command:

```powershell
.\.venv\Scripts\python.exe -m scripts.benchmark_incremental_price_refresh --rounds 2000 --bar-count 8
```

This is an in-process micro-benchmark. It measures Python and SQLAlchemy statement-building overhead with a fake session, not end-to-end PostgreSQL latency.

## Result snapshot

Measured on April 21, 2026 in this workspace:

- `always_write_unchanged_tail`: avg `1.1714 ms`, `4` session executes
- `no_op_unchanged_tail`: avg `0.1625 ms`, `1` session execute
- `changed_tail_write`: avg `0.6510 ms`, `4` session executes

## Takeaway

The no-op path is about 7.2x cheaper than the old always-write path in this micro-benchmark and cuts statement executions from 4 to 1 for unchanged tails.

That said, the configured overlap window is small, so this is a modest repo-level optimization. The main win is not raw refresh throughput by itself; it is avoiding unnecessary row rewrites, hot-cache invalidation, and downstream fingerprint churn when prices did not actually change.

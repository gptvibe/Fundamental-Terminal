# Development Notes

## Do Not Commit Local Runtime Artifacts

Keep generated local artifacts out of source control. Do not commit:

- local caches under `data/market_cache/` and `data/sec_cache/`
- TypeScript build metadata such as `*.tsbuildinfo`
- logs, temporary screenshots, and test-output folders
- ad hoc performance run outputs under `artifacts/performance/`

Curated benchmark baselines that are intentionally retained belong in `artifacts/performance/baselines/`.

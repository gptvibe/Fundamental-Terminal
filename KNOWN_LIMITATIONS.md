# Known Limitations

This document tracks current product and operational constraints for the `v0.1.x` line.

## Product

- Coverage prioritizes U.S. public equities and official/public-source availability; some sectors or edge tickers may have partial data.
- Strict official mode can intentionally remove non-core fallback-backed market context panels.
- Historical point-in-time (`as_of`) coverage exists on major company endpoints, but not every route has the same historical depth.
- Some analytics and modeling outputs are derived computations and should be interpreted as decision support, not investment advice.

## Operations

- Small-host deployments may require lite or small-host compose overrides for stable responsiveness under constrained RAM/CPU.
- Background refresh completeness depends on worker health and queue throughput; transient lag can occur during heavy upstream activity.
- Upstream source throttling or temporary outages can degrade freshness for selected datasets.

## Release And Quality

- Frontend typechecking currently runs via `npm run build` (no dedicated `typecheck` script yet).
- Smoke checks validate key routes but are not a substitute for full exploratory UI testing across all company surfaces.
- Performance regression gate is benchmark-based and sensitive to environment noise; run it on a stable machine for release decisions.

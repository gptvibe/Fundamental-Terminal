# Lazy-load heavy visual components to reduce first-load JS

## What changed

### New files
| File | Purpose |
|---|---|
| `frontend/components/ui/skeletons.tsx` | `ChartSkeleton`, `TableSkeleton`, `GridSkeleton` — lightweight shimmer placeholders |
| `frontend/components/charts/stake-change-trend-charts.tsx` | Extracted inline Recharts JSX from `ownership-changes/page.tsx` into a lazy-loadable component |
| `frontend/app/globals.css` | Added `.skeleton-block` / `.skeleton-table` utility classes with shimmer animation |
| `docs/lazy-loading-bundle-reduction.md` | Before/after bundle notes |

### Pages updated — eager → `next/dynamic`

| Page | Components converted |
|---|---|
| `ownership-changes/page.tsx` | `StakeChangeTrendCharts` (newly extracted from inline JSX) |
| `insiders/page.tsx` | `InsiderActivityTrendChart`, `InsiderRoleActivityChart` |
| `earnings/page.tsx` | `EarningsTrendChart` |
| `financials/financials-client-page.tsx` | `BusinessSegmentBreakdown`, `CashFlowWaterfallChart`, `CapitalStructureIntelligencePanel`, `FinancialComparisonPanel` |

All conversions use `ssr: false` + `ChartSkeleton` loading fallback.

### Bundle analysis tooling
- Installed `@next/bundle-analyzer` + `cross-env` as devDependencies
- `next.config.mjs` wrapped with `withBundleAnalyzer` (no-op unless `ANALYZE=true`)
- New script: `npm run analyze` → opens interactive treemap at `.next/analyze/client.html`

## Why

Recharts (~130 KB gzip) was previously included in the initial bundle of every page that rendered a chart. These pages now ship a smaller initial payload and fetch chart code in parallel post-hydration, showing a shimmer skeleton in the meantime.

**Estimated first-load JS reduction per affected route: ~130–150 KB gzip.**

## Build output (first-load JS after this change)

```
Route                                    First Load JS
/company/[ticker]/earnings               140 kB  ← was ~270 kB
/company/[ticker]/insiders               142 kB  ← was ~272 kB
/company/[ticker]/financials             258 kB  (4 more components deferred)
/company/[ticker]/ownership-changes      245 kB  (inline Recharts extracted)
```

## Verification
- ✅ `npm test` — 457/457 tests pass
- ✅ Docker build succeeds (`docker compose -f docker-compose.yml -f docker-compose.build.yml up --build -d`)
- ✅ Visually confirmed AAPL/earnings, AAPL/insiders render correctly after build

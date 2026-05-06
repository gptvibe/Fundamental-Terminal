# Lazy-Loading: Bundle Reduction Notes

## Overview

Heavy visual libraries (Recharts, AG Grid) were previously imported eagerly at the page level, bloating the initial JavaScript bundle sent to the browser. This change moves all chart and grid components to `next/dynamic` with `ssr: false`, splitting them into separate async chunks loaded only when rendered.

## Changes Made

### New Files
- `frontend/components/ui/skeletons.tsx` — `ChartSkeleton`, `TableSkeleton`, `GridSkeleton` loading placeholders
- `frontend/components/charts/stake-change-trend-charts.tsx` — Extracted inline Recharts JSX from `ownership-changes` page into a lazy-loadable component
- `frontend/app/globals.css` — Added `.skeleton-block` / `.skeleton-table` utility classes with shimmer animation

### Pages Updated

| Page | Components Converted | Library |
|---|---|---|
| `ownership-changes/page.tsx` | `StakeChangeTrendCharts` (new extraction) | Recharts |
| `insiders/page.tsx` | `InsiderActivityTrendChart`, `InsiderRoleActivityChart` | Recharts |
| `earnings/page.tsx` | `EarningsTrendChart` | Recharts |
| `financials/financials-client-page.tsx` | `BusinessSegmentBreakdown`, `CashFlowWaterfallChart`, `CapitalStructureIntelligencePanel`, `FinancialComparisonPanel` | Recharts |

### Pages Already Using Dynamic Imports (No Change Needed)
- `governance/page.tsx` — `GovernanceFilingChart`, `GovernancePayTrendChart`
- `peers/page.tsx` — `PeerComparisonDashboard`
- `models/page.tsx` — `DenseGrid` (AG Grid)
- `company/page.tsx` — multiple deferred sections
- `financials/financials-client-page.tsx` — had many dynamic imports; 4 more added

### Bundle Analyzer Added
- `@next/bundle-analyzer` + `cross-env` installed as devDependencies
- `next.config.mjs` updated to wrap with `withBundleAnalyzer` (only active when `ANALYZE=true`)
- New script: `npm run analyze` → `cross-env ANALYZE=true next build`

## Estimated Impact

### Before
The `recharts` module (~500 KB minified, ~130 KB gzip) was included in the main JS bundle for any page that directly imported it at the module level. Pages like `/insiders`, `/earnings`, `/ownership-changes`, and `/financials` all paid this cost on first load regardless of whether charts were visible.

### After
Each chart component is now a separate dynamic chunk. The initial page bundle for these routes no longer includes Recharts or AG Grid. The library code is fetched in parallel after hydration, while a `ChartSkeleton` shimmer placeholder renders immediately.

**Estimated first-load JS reduction per affected route: ~130–150 KB gzip** (Recharts + transitive deps removed from critical path).

## How to Run Bundle Analysis

```bash
cd frontend
npm run analyze
```

This generates interactive treemap reports at `frontend/.next/analyze/client.html` and `server.html`.

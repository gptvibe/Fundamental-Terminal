# Chart Expansion Rollout

## Goal

Standardize expandable chart behavior across the frontend by reusing the shared inspector stack:

- `frontend/components/charts/interactive-chart-frame.tsx`
- `frontend/components/charts/chart-inspector.tsx`
- `frontend/components/charts/chart-framework.tsx`

Inline cards should stay visually stable. Expanded mode should add controls, richer annotations, export/reset actions, and state handling without introducing invalid chart or timeframe choices.

## Status Key

- `already migrated`: already on the shared frame/inspector path
- `partial`: uses shared chart framework pieces but not the shared expansion flow end to end
- `migrated in rollout`: migrated as part of this rollout
- `non-expandable`: utility/support surface, not an inspector candidate
- `design follow-up`: chart-like surface intentionally skipped for now because it needs a broader async or orchestration treatment

## Checklist

| File | Current status | Dataset kind | Expand? | Allowed chart types | Timeframe controls | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `balance-sheet-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `bar` inline, inspector-ready time-series surface | none | Financial stock metrics. Preserve selected/comparison markers from shared financial state. |
| `beneficial-ownership-form-chart.tsx` | migrated in rollout | `categorical_snapshot` | yes | `bar` | none | Snapshot of 13D/13G form mix; no date window switching. |
| `business-segment-breakdown.tsx` | already migrated | `segment_mix` | yes | `donut`, `pie`, `stacked_bar` | snapshot only | Already uses shared frame and inspector controls. Keep as the reference for composition charts. |
| `capital-markets-signal-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `composed` | none | Annual financing-event plus debt-change overlay. Inspector does not expose pie/donut options. |
| `cash-flow-waterfall-chart.tsx` | migrated in rollout | `waterfall` | yes | `bar` | snapshot only | Selected-period bridge with optional compare/trend context. Cadence remains annual/quarterly only when standalone. |
| `chart-framework.tsx` | non-expandable | utility | no | n/a | n/a | Shared control, badge, and CSV helpers. |
| `chart-inspector.tsx` | non-expandable | utility | no | n/a | n/a | Shared modal/expanded inspector. |
| `company-visualization-lab.tsx` | partial | mixed orchestration surface | design follow-up | mixed | custom | Multi-chart lab/orchestration surface. Not a single expandable card. |
| `derived-metrics-panel.tsx` | design follow-up | async time series panel | no for this rollout | tbd | tbd | Separate async/freshness panel with polling and source freshness UI. Needs a dedicated async inspector contract. |
| `earnings-trend-chart.tsx` | migrated in rollout | `time_series` | yes | `composed` | none | Release-driven trend; no synthetic timeframe switching unless the source series becomes windowable later. |
| `filing-event-category-chart.tsx` | migrated in rollout | `categorical_snapshot` | yes | `bar` | none | Event/category distribution. Keep categorical-only rendering. |
| `financial-chart-state-bar.tsx` | non-expandable | utility | no | n/a | n/a | Shared selected/compare/cadence state summary. |
| `financial-history-line-chart.tsx` | already migrated | `time_series` | yes | `line` | `1y`, `3y`, `5y`, `10y`, `max` | Already uses shared frame and window controls. |
| `financial-trend-chart.tsx` | already migrated | `time_series` | yes | `line`, `area`, `bar`, `composed` | `1y`, `3y`, `5y`, `10y`, `max` | Already uses shared frame, preferences, exports, and stage states. |
| `governance-filing-chart.tsx` | migrated in rollout | `categorical_snapshot` | yes | `bar` | none | Snapshot counts by proxy form. |
| `growth-waterfall-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `composed` | none | Annual value-plus-growth view. Metric toggle remains the primary control. |
| `insider-activity-trend-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `composed` | none | Fixed 12-month rolling trend; preserve buy/sell/net semantics. |
| `insider-role-activity-chart.tsx` | migrated in rollout | `categorical_snapshot` | yes | fixed categorical composed view | none | Role buckets are categorical; inspector avoids exposing line-only variants. |
| `institutional-ownership-trend-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `line` | none | Quarterly ownership series; keep brush in expanded mode. |
| `interactive-chart-frame.tsx` | non-expandable | utility | no | n/a | n/a | Shared expandable frame wrapper. |
| `liquidity-capital-chart.tsx` | migrated in rollout | specialized multi-panel time series | yes | fixed multi-panel layout | none | Two linked visuals in one card. Inspector expands both panels without forcing a fake chart-type switch. |
| `margin-trend-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `line` | none | Preserve annual/quarterly/TTM semantics from the existing inline view. |
| `operating-cost-structure-chart.tsx` | migrated in rollout | `stacked_time_series` | yes | fixed multi-series line view | none | Cost component mix stays stack-friendly at the capability level while preserving the established inline line treatment. |
| `price-fundamentals-module.tsx` | already migrated | `time_series` | yes | `line`, `area`, `composed` | `1y`, `3y`, `5y`, `10y`, `max` | Already uses shared frame for both subcharts. |
| `share-dilution-tracker-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `composed` | none | Share-count plus dilution-rate dual-axis chart. |
| `smart-money-flow-chart.tsx` | migrated in rollout | `time_series` | yes | fixed `composed` | none | Supports loading/error/refresh-aware expanded states; keep brush in expanded mode. |

## Migration Groups

1. Time-series financial charts
   - `balance-sheet-chart.tsx`
   - `financial-trend-chart.tsx`
   - `financial-history-line-chart.tsx`
   - `margin-trend-chart.tsx`
   - `operating-cost-structure-chart.tsx`
   - `liquidity-capital-chart.tsx`
   - `share-dilution-tracker-chart.tsx`
   - `growth-waterfall-chart.tsx`
   - `cash-flow-waterfall-chart.tsx`

2. Ownership / insider charts
   - `beneficial-ownership-form-chart.tsx`
   - `institutional-ownership-trend-chart.tsx`
   - `insider-activity-trend-chart.tsx`
   - `insider-role-activity-chart.tsx`

3. Capital markets / dilution charts
   - `capital-markets-signal-chart.tsx`
   - `share-dilution-tracker-chart.tsx`
   - `smart-money-flow-chart.tsx`

4. Composition / categorical charts
   - `business-segment-breakdown.tsx`
   - `filing-event-category-chart.tsx`
   - `governance-filing-chart.tsx`
   - `beneficial-ownership-form-chart.tsx`

5. Specialized charts
   - `price-fundamentals-module.tsx`
   - `earnings-trend-chart.tsx`
   - `liquidity-capital-chart.tsx`

## Follow-up Candidates

- `company-visualization-lab.tsx`: multi-chart orchestration surface; needs a lab-specific expansion model rather than wrapping the whole page fragment in a single inspector.
- `derived-metrics-panel.tsx`: async polling, freshness UI, and metric selector make it a good future candidate, but it should move only after a dedicated async inspector contract is defined.
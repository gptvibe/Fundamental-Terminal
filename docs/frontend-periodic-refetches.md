# Frontend Periodic Refetch Inventory

Updated: 2026-04-06

## Removed From This Refactor

The following surfaces no longer use timer-based polling for refresh completion. They now reload on durable job-stream terminal events or on explicit state changes:

- `/company/[ticker]`
- `/company/[ticker]/models`
- `/company/[ticker]/financials`
- `/watchlist`
- `ResearchBriefPlainEnglishPanel`
- `MetricsExplorerPanel`
- `CapitalStructureIntelligencePanel`
- `DerivedMetricsPanel`

## Remaining Periodic Refetches

### Homepage top rail

- File: `frontend/app/page.tsx`
- Trigger: 5 minute interval, plus `focus` and `visibilitychange`
- Why it remains: macro context and source-registry health are global surfaces that should recover after idle time without requiring a full navigation.
- Scope: refreshes the homepage top-rail market context and data-health panels only.

### Earnings workspace active refresh

- File: `frontend/app/company/[ticker]/earnings/page.tsx`
- Trigger: 3 second interval only while `trackedJobId` is active
- Why it remains: this page still reloads a single workspace payload keyed to a live refresh job and has not yet been migrated to the shared job-stream completion path.
- Scope: refreshes the earnings workspace until the backend clears `refresh.job_id`.

### Ownership workspace active refresh

- File: `frontend/app/company/[ticker]/ownership/page.tsx`
- Trigger: 3 second interval only while institutional ownership refresh is active
- Why it remains: this page still coordinates two ownership endpoints during warmup and has not yet been converted to multi-endpoint SSE completion handling.
- Scope: refreshes holdings and ownership summary until data is present or both refresh job ids clear.

## Non-Refetch Timers

These timers remain in the frontend, but they are UI delays rather than network refetch loops:

- `frontend/components/layout/app-chrome.tsx`
- `frontend/components/personal/company-device-panel.tsx`

# Company Research Workspace UI

This update keeps the existing company routes intact while making the workspace feel like one coherent research surface.

## What changed

- Added a shared sticky company header across overview, financials, models, peers, and earnings.
- Added a source and freshness ribbon that keeps SEC-first provenance visible alongside cached market-profile inputs.
- Expanded the Financials data-quality panel so it now renders persisted companyfacts-vs-parser reconciliation status, confidence penalties, disagreement counts, exact SEC tags, and the exact periods used for each compared metric.
- Expanded the shared segment view on overview and financials so business and geography disclosures now lead with investor-facing summaries of mix shifts, margin contribution, concentration, and unusual disclosure changes before the charts.
- Added a capital structure intelligence panel on the financials and models routes with persisted debt maturity ladders, lease schedules, debt roll-forwards, interest burden, payout mix, SBC, and net dilution bridges.
- Grouped company navigation into core views and research feeds, with keyboard arrow navigation between sections.
- Standardized summary strips, utility-rail actions, and empty or loading states.
- Converted the peer selection area into a compare tray that works better on mobile and remains keyboard accessible.

## Data trust model

- Financial statements and research metrics remain SEC EDGAR/XBRL first.
- Reconciliation between normalized companyfacts values and filing-parser values is persisted on the financial statement rows rather than recomputed ad hoc in the browser.
- The Financials route exposes the parser-backed reconciliation as a structured payload with statement-level `as_of`, refresh time, provenance sources, confidence score, and per-metric lineage.
- The Financials route now also exposes additive `segment_analysis` payloads for business and geographic disclosures, each carrying `as_of`, `last_refreshed_at`, provenance sources, confidence flags, concentration, top mix movers, margin contributors, and unusual disclosure summaries.
- Capital structure intelligence is derived only from persisted SEC companyfacts and surfaces provenance, as-of dates, refresh timestamps, and confidence flags for each section.
- Market profile and price context continue to rely on cached Yahoo Finance data only where already allowed.
- Refresh actions remain background-queued so the UI can serve cached data immediately.

## UX notes

- Export uses the browser print flow so users can save the current research view as PDF.
- Sticky elements drop back to static positioning on narrower layouts to avoid crowding smaller screens.
- Shared state styling is intended for reuse by future company-route tabs without changing the backend contract.
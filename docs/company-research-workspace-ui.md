# Company Research Workspace UI

This update keeps the existing company routes intact while making the workspace feel like one coherent research surface.

## What changed

- Added a shared sticky company header across overview, financials, models, peers, and earnings.
- Added a source and freshness ribbon that keeps SEC-first provenance visible alongside cached market-profile inputs.
- Grouped company navigation into core views and research feeds, with keyboard arrow navigation between sections.
- Standardized summary strips, utility-rail actions, and empty or loading states.
- Converted the peer selection area into a compare tray that works better on mobile and remains keyboard accessible.

## Data trust model

- Financial statements and research metrics remain SEC EDGAR/XBRL first.
- Market profile and price context continue to rely on cached Yahoo Finance data only where already allowed.
- Refresh actions remain background-queued so the UI can serve cached data immediately.

## UX notes

- Export uses the browser print flow so users can save the current research view as PDF.
- Sticky elements drop back to static positioning on narrower layouts to avoid crowding smaller screens.
- Shared state styling is intended for reuse by future company-route tabs without changing the backend contract.
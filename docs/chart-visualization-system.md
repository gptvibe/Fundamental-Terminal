# Company Visualization System

## Scope

This update introduces a reusable chart framework and a new company visualization module focused on cached SEC-first data.

- Fundamental source priority: SEC EDGAR/XBRL
- Market profile source: Yahoo Finance (price context only)
- No paid/auth-gated vendors
- Cache-first route behavior is unchanged

## What Was Added

### Reusable chart framework

Shared chart primitives live in the frontend chart components layer:

- control groups for cadence, value mode, and date range
- compare mode picker (up to 5 metrics)
- standardized source/freshness/provenance badge row
- unified chart state blocks (loading, empty, error)
- CSV export helper for plotted rows

### New visualization module

`CompanyVisualizationLab` adds higher-signal visuals with consistent controls:

- multi-metric explorer with quarterly/annual/TTM toggle
- absolute/margin/growth/per-share mode toggle
- date range toggle
- compare mode (2 to 5 metrics)
- event annotations from:
  - earnings releases
  - 8-K filing events
  - capital markets filings
  - insider trades
  - beneficial ownership filings

### High-value chart set

- margin stack over time
- cash conversion and accrual quality chart
- dilution and SBC timeline
- capital allocation and shareholder yield timeline
- segment mix evolution chart
- geography concentration evolution chart
- filing cadence and filing lag heatmap

### Provenance and exports

Every chart card now includes:

- source badge
- freshness badge
- provenance badge
- CSV export for the plotted series

## Notes

- The refresh queue and existing status/SSE flow are reused as-is.
- The backend contract remains cache-first; this module reads existing persisted endpoints.
- The new controls are designed for desktop readability and tablet usability.

import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ChartShareCard } from "@/components/company/chart-share-card";
import { buildOutlookChartShareSnapshot, buildStudioChartShareSnapshot } from "@/lib/chart-share";
import type { CompanyChartsDashboardResponse } from "@/lib/types";

function makePayload(): CompanyChartsDashboardResponse {
  return {
    company: {
      ticker: "ACME",
      cik: "0000001",
      name: "Acme Corp",
      sector: "Technology",
      market_sector: "Technology",
      market_industry: "Software",
      oil_exposure_type: "non_oil",
      oil_support_status: "unsupported",
      oil_support_reasons: [],
      strict_official_mode: true,
      last_checked: "2026-04-23T00:00:00Z",
      last_checked_financials: "2026-04-23T00:00:00Z",
      last_checked_prices: null,
      last_checked_insiders: null,
      last_checked_institutional: null,
      last_checked_filings: null,
      cache_state: "fresh",
    },
    title: "Growth Outlook",
    build_state: "ready",
    build_status: "Charts ready.",
    summary: {
      headline: "Growth Outlook",
      primary_score: { key: "growth", label: "Growth", score: 88, tone: "positive", detail: "Strong" },
      secondary_badges: [{ key: "quality", label: "Quality", score: 84, tone: "positive", detail: "Healthy" }],
      thesis: "Projected and reported values remain explicit.",
      unavailable_notes: [],
      freshness_badges: [],
      source_badges: ["SEC Company Facts"],
    },
    factors: { primary: null, supporting: [] },
    legend: {
      title: "Actual vs Forecast",
      items: [
        { key: "actual", label: "Reported", style: "solid", tone: "actual", description: "Historical filings." },
        { key: "forecast", label: "Forecast", style: "dashed", tone: "forecast", description: "Projected path." },
      ],
    },
    cards: {
      revenue: {
        key: "revenue",
        title: "Revenue",
        subtitle: null,
        metric_label: null,
        unit_label: null,
        empty_state: null,
        highlights: [],
        series: [
          { key: "revenue_actual", label: "Reported", unit: "usd", chart_type: "line", series_kind: "actual", stroke_style: "solid", points: [{ period_label: "FY2025", fiscal_year: 2025, period_end: null, value: 100, series_kind: "actual", annotation: null }] },
          { key: "revenue_forecast", label: "Forecast", unit: "usd", chart_type: "line", series_kind: "forecast", stroke_style: "dashed", points: [{ period_label: "FY2026E", fiscal_year: 2026, period_end: null, value: 120, series_kind: "forecast", annotation: "Projection" }] },
        ],
      },
      revenue_growth: { key: "revenue_growth", title: "Revenue Growth", subtitle: null, metric_label: null, unit_label: null, empty_state: null, highlights: [], series: [] },
      profit_metric: { key: "profit_metric", title: "Profit", subtitle: null, metric_label: null, unit_label: null, empty_state: null, highlights: [], series: [] },
      cash_flow_metric: { key: "cash_flow_metric", title: "Cash", subtitle: null, metric_label: null, unit_label: null, empty_state: null, highlights: [], series: [] },
      eps: { key: "eps", title: "EPS", subtitle: null, metric_label: null, unit_label: null, empty_state: null, highlights: [], series: [] },
      growth_summary: {
        key: "growth_summary",
        title: "Growth Summary",
        subtitle: null,
        comparisons: [{ key: "hist_3y", label: "Hist 3Y", company_value: 0.24, benchmark_value: null, benchmark_label: null, unit: "percent", company_label: "ACME", benchmark_available: false }],
        empty_state: null,
      },
      forecast_assumptions: null,
    },
    forecast_methodology: {
      version: "company_charts_dashboard_v9",
      label: "Driver-based integrated forecast",
      summary: "Forecast summary",
      disclaimer: "Forecast disclaimer",
      forecast_horizon_years: 3,
      confidence_label: "Forecast stability: Moderate stability",
    },
    forecast_diagnostics: {
      score_key: "forecast_stability",
      score_name: "Forecast Stability",
      heuristic: true,
      final_score: 72,
      summary: "Moderate stability.",
      history_depth_years: 4,
      thin_history: false,
      growth_volatility: 0.1,
      growth_volatility_band: "moderate",
      missing_data_penalty: 0,
      quality_score: 0.9,
      missing_inputs: [],
      sample_size: 3,
      scenario_dispersion: 0.1,
      sector_template: "Technology",
      guidance_usage: "management_guidance_applied",
      historical_backtest_error_band: "moderate",
      backtest_weighted_error: 0.1,
      backtest_horizon_errors: {},
      backtest_metric_weights: {},
      backtest_metric_errors: {},
      backtest_metric_horizon_errors: {},
      backtest_metric_sample_sizes: {},
      components: [],
    },
    event_overlay: {
      title: "Event overlays",
      available_event_types: [],
      default_enabled_event_types: [],
      events: [],
      sparse_data_note: null,
    },
    quarter_change: {
      title: "What changed since last quarter?",
      latest_period_label: null,
      prior_period_label: null,
      summary: "",
      items: [],
      empty_state: "No quarter-over-quarter changes are available.",
    },
    projection_studio: {
      methodology: null,
      drivers_used: [],
      scenarios_comparison: [
        { key: "revenue_growth", label: "Revenue Growth", unit: "percent", reported_values: {}, projected_values: {}, formula_traces: {}, scenario_values: { base: 0.12, bull: 0.18, bear: 0.05 }, detail: null },
      ],
      sensitivity_matrix: [],
      schedule_sections: [
        {
          key: "income_statement",
          title: "Income Statement",
          rows: [{ key: "revenue", label: "Revenue", unit: "usd", reported_values: { 2025: 100 }, projected_values: { 2026: 120 }, formula_traces: {}, scenario_values: {}, detail: null }],
        },
      ],
    },
    what_if: {
      impact_summary: { forecast_year: 2026, metrics: [] },
      overrides_applied: [{ key: "price_growth", label: "Price Growth", unit: "percent", requested_value: 0.02, applied_value: 0.02, baseline_value: 0.01, min_value: -0.1, max_value: 0.2, clipped: false, source_detail: "SEC", source_kind: "sec" }],
      overrides_clipped: [],
      driver_control_metadata: [],
    },
    chart_spec: null,
    payload_version: "company_charts_dashboard_v9",
    refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: 0.9,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: [],
    as_of: "2026-04-23",
    last_refreshed_at: "2026-04-23T00:00:00Z",
    source_mix: {
      source_ids: [],
      source_tiers: [],
      primary_source_ids: [],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
  };
}

describe("ChartShareCard", () => {
  it("renders the outlook share card snapshot", () => {
    const markup = renderToStaticMarkup(<ChartShareCard snapshot={buildOutlookChartShareSnapshot(makePayload())} layout="landscape" />);
    expect(markup).toMatchSnapshot();
  });

  it("renders the studio share card snapshot", () => {
    const markup = renderToStaticMarkup(<ChartShareCard snapshot={buildStudioChartShareSnapshot(makePayload(), { scenarioName: "Bull Case", overrideCount: 1 })} layout="portrait" />);
    expect(markup).toMatchSnapshot();
  });
});

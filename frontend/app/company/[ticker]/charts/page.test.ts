// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompanyChartsPage from "@/app/company/[ticker]/charts/page";

const headersMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href?: string; children: React.ReactNode }) =>
    React.createElement("a", { href: href ?? "#" }, children),
}));

vi.mock("./charts-retry-button", () => ({
  ChartsRetryButton: () => React.createElement("button", { type: "button" }, "Try again"),
}));

vi.mock("./projection-studio-hydration", () => ({
  ProjectionStudioHydration: () => React.createElement("div", { "data-testid": "projection-studio" }, "Projection Studio"),
}));

function buildPayload(overrides: Record<string, unknown> = {}) {
  return {
    company: {
      ticker: "NVDA",
      cik: "0001045810",
      name: "NVIDIA Corp",
      sector: "Technology",
      market_sector: "Technology",
      market_industry: "Semiconductors",
      oil_exposure_type: "non_oil",
      oil_support_status: "unsupported",
      oil_support_reasons: [],
      strict_official_mode: true,
      last_checked: "2026-04-13T00:00:00Z",
      last_checked_financials: "2026-04-13T00:00:00Z",
      last_checked_prices: null,
      last_checked_insiders: null,
      last_checked_institutional: null,
      last_checked_filings: null,
      earnings_last_checked: null,
      cache_state: "fresh",
    },
    title: "Growth Outlook",
    build_state: "ready",
    build_status: "Charts dashboard is ready.",
    summary: {
      headline: "Growth Outlook",
      primary_score: { key: "growth", label: "Growth", score: 96, tone: "positive", detail: "Strong trend persistence." },
      secondary_badges: [],
      thesis: "Reported growth remains strong, while forecast values stay clearly labeled as projections.",
      unavailable_notes: [],
      freshness_badges: ["Refreshed Apr 13, 2026", "Annual history"],
      source_badges: ["SEC Company Facts", "Internal deterministic forecast"],
    },
    factors: { primary: null, supporting: [] },
    legend: {
      title: "Actual vs Forecast",
      items: [
        { key: "actual", label: "Actual", style: "solid", tone: "actual", description: "Reported official history." },
        { key: "forecast", label: "Forecast", style: "dashed", tone: "forecast", description: "Projected internal scenario." },
      ],
    },
    cards: {
      revenue: {
        key: "revenue",
        title: "Revenue",
        subtitle: "Reported history and 3-year projection",
        metric_label: "Revenue",
        unit_label: "USD",
        empty_state: null,
        highlights: ["Reported through FY2025", "Forecast horizon 2Y"],
        series: [
          {
            key: "revenue_actual",
            label: "Actual",
            unit: "usd",
            chart_type: "line",
            series_kind: "actual",
            stroke_style: "solid",
            points: [
              { period_label: "FY2024", fiscal_year: 2024, period_end: "2024-01-28", value: 60922000000, series_kind: "actual", annotation: null },
              { period_label: "FY2025", fiscal_year: 2025, period_end: "2025-01-26", value: 130497000000, series_kind: "actual", annotation: null },
            ],
          },
          {
            key: "revenue_forecast",
            label: "Forecast",
            unit: "usd",
            chart_type: "line",
            series_kind: "forecast",
            stroke_style: "dashed",
            points: [
              { period_label: "FY2026E", fiscal_year: 2026, period_end: "2026-01-25", value: 181000000000, series_kind: "forecast", annotation: "Projection" },
              { period_label: "FY2027E", fiscal_year: 2027, period_end: "2027-01-31", value: 223000000000, series_kind: "forecast", annotation: "Projection" },
            ],
          },
        ],
      },
      revenue_growth: {
        key: "revenue_growth",
        title: "Revenue Growth",
        subtitle: "Actual vs projected growth rates",
        metric_label: "Revenue Growth",
        unit_label: "%",
        empty_state: null,
        highlights: ["Forecast shown with muted bars"],
        series: [
          { key: "revenue_growth_actual", label: "Actual", unit: "percent", chart_type: "bar", series_kind: "actual", stroke_style: "solid", points: [{ period_label: "FY2025", fiscal_year: 2025, period_end: "2025-01-26", value: 1.14, series_kind: "actual", annotation: null }] },
          { key: "revenue_growth_forecast", label: "Forecast", unit: "percent", chart_type: "bar", series_kind: "forecast", stroke_style: "muted", points: [{ period_label: "FY2026E", fiscal_year: 2026, period_end: "2026-01-25", value: 0.39, series_kind: "forecast", annotation: "Projection" }] },
        ],
      },
      profit_metric: { key: "profit_metric", title: "Profit Metrics", subtitle: "EBIT and net income", metric_label: "Profit", unit_label: "USD", empty_state: null, highlights: [], series: [] },
      cash_flow_metric: { key: "cash_flow_metric", title: "Cash Flow Metrics", subtitle: "Operating cash flow and free cash flow", metric_label: "Cash Flow", unit_label: "USD", empty_state: null, highlights: [], series: [] },
      eps: { key: "eps", title: "EPS", subtitle: "Diluted EPS actual vs projection", metric_label: "EPS", unit_label: "USD/share", empty_state: null, highlights: [], series: [] },
      growth_summary: { key: "growth_summary", title: "Growth Summary", subtitle: "Company growth only until benchmark support is trustworthy", empty_state: null, comparisons: [] },
      forecast_assumptions: { key: "forecast_assumptions", title: "Forecast Assumptions", empty_state: null, items: [{ key: "revenue_guardrail", label: "Revenue guardrail", value: "Clipped to sane annual growth bands", detail: "Recent YoY blended with trailing CAGR." }] },
      forecast_calculations: null,
      revenue_outlook_bridge: null,
      margin_path: null,
      fcf_outlook: null,
    },
    event_overlay: {
      title: "Event overlays",
      available_event_types: ["earnings", "guidance", "buyback", "major_m_and_a", "restatement"],
      default_enabled_event_types: ["earnings", "guidance", "restatement"],
      events: [],
      sparse_data_note: null,
    },
    quarter_change: {
      title: "What changed since last quarter?",
      latest_period_label: "FY2025",
      prior_period_label: "FY2024",
      summary: "Reported deltas and event context.",
      items: [],
      empty_state: null,
    },
    forecast_methodology: {
      version: "company_charts_dashboard_v9",
      label: "Deterministic projection with empirical stability overlay",
      summary: "Forecasts are generated from persisted historical official inputs with guarded trend and margin rules.",
      disclaimer: "Forecast values remain projections rather than reported results.",
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
      growth_volatility: 0.12,
      growth_volatility_band: "moderate",
      missing_data_penalty: 0,
      quality_score: 0.95,
      missing_inputs: [],
      sample_size: 3,
      scenario_dispersion: 0.18,
      sector_template: "Technology",
      guidance_usage: "management_guidance_applied",
      historical_backtest_error_band: "moderate",
      backtest_weighted_error: 0.11,
      backtest_horizon_errors: { "1": 0.08 },
      backtest_metric_weights: { revenue: 0.5 },
      backtest_metric_errors: { revenue: 0.08 },
      backtest_metric_horizon_errors: { revenue: { "1": 0.08 } },
      backtest_metric_sample_sizes: { revenue: 3 },
      components: [],
    },
    projection_studio: null,
    what_if: null,
    chart_spec: null,
    payload_version: "company_charts_dashboard_v9",
    provenance: [],
    as_of: "2026-04-13",
    last_refreshed_at: "2026-04-13T00:00:00Z",
    source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
    confidence_flags: [],
    refresh: { triggered: false, reason: "fresh", ticker: "NVDA", job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: 0.95,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    ...overrides,
  };
}

describe("CompanyChartsPage server route", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    headersMock.mockReset();
    headersMock.mockReturnValue(
      new Headers([
        ["host", "localhost:3000"],
        ["x-forwarded-proto", "http"],
      ])
    );
    vi.stubGlobal("fetch", fetchMock);
  });

  it("passes an explicit as_of query through to charts loading", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => buildPayload(),
    });

    const jsx = await CompanyChartsPage({
      params: { ticker: "nvda" },
      searchParams: { as_of: "2025-12-27" },
    });
    render(jsx);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/companies/NVDA/charts?as_of=2025-12-27",
      expect.objectContaining({ next: expect.objectContaining({ revalidate: 20 }) })
    );
  });

  it("renders the charts dashboard with explicit actual-vs-forecast separation", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => buildPayload(),
    });

    const jsx = await CompanyChartsPage({
      params: { ticker: "nvda" },
      searchParams: {},
    });
    render(jsx);

    expect(screen.getByText("NVIDIA Corp")).toBeTruthy();
    expect(screen.getByText("Projected periods begin at the divider and use a soft shaded region inside each chart.")).toBeTruthy();
    expect(screen.getAllByText("Actual").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Forecast").length).toBeGreaterThan(0);
  });
});
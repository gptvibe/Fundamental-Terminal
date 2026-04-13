// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyChartsPage from "@/app/company/[ticker]/charts/page";
import { getCompanyCharts } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "nvda" }),
}));

vi.mock("@/lib/api", () => ({
  getCompanyCharts: vi.fn(),
}));

describe("CompanyChartsPage", () => {
  it("renders the charts dashboard with explicit actual-vs-forecast separation", async () => {
    vi.mocked(getCompanyCharts).mockResolvedValue({
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
        cache_state: "fresh",
      },
      title: "Growth Outlook",
      build_state: "ready",
      build_status: "Charts dashboard is ready.",
      summary: {
        headline: "Growth Outlook",
        primary_score: { key: "growth", label: "Growth", score: 96, tone: "positive", detail: "Strong trend persistence." },
        secondary_badges: [
          { key: "quality", label: "Quality", score: 91, tone: "positive", detail: "Healthy reported margins." },
          { key: "momentum", label: "Momentum", score: 88, tone: "positive", detail: "Recent growth still strong." },
          { key: "forecast_confidence", label: "Forecast Confidence", score: 78, tone: "neutral", detail: "Three annual reported periods available." },
        ],
        thesis: "Reported growth remains strong, while forecast values stay clearly labeled as projections.",
        unavailable_notes: ["Value is hidden until a trustworthy valuation comparator is available."],
        freshness_badges: ["Refreshed Apr 13, 2026", "Annual history"],
        source_badges: ["SEC Company Facts", "Internal deterministic forecast"],
      },
      factors: {
        primary: { key: "growth", label: "Growth", score: 96, normalized_score: 0.96, tone: "positive", detail: "3Y revenue CAGR and 1Y forward growth." },
        supporting: [
          { key: "quality", label: "Quality", score: 91, normalized_score: 0.91, tone: "positive", detail: "Margins and cash conversion." },
          { key: "momentum", label: "Momentum", score: 88, normalized_score: 0.88, tone: "positive", detail: "Recent drift remains strong." },
          { key: "value", label: "Value", score: null, normalized_score: null, tone: "unavailable", detail: null, unavailable_reason: "Waiting for trustworthy benchmark support." },
          { key: "forecast_confidence", label: "Forecast Confidence", score: 78, normalized_score: 0.78, tone: "neutral", detail: "Guardrailed deterministic projection." },
        ],
      },
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
          highlights: ["Reported through FY2026", "Forecast horizon 3Y"],
          series: [
            {
              key: "revenue_actual",
              label: "Actual",
              unit: "usd",
              chart_type: "line",
              series_kind: "actual",
              stroke_style: "solid",
              points: [
                { period_label: "FY2024", fiscal_year: 2024, period_end: "2024-01-28", value: 60_922_000_000, series_kind: "actual", annotation: null },
                { period_label: "FY2025", fiscal_year: 2025, period_end: "2025-01-26", value: 130_497_000_000, series_kind: "actual", annotation: null },
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
                { period_label: "FY2026E", fiscal_year: 2026, period_end: "2026-01-25", value: 181_000_000_000, series_kind: "forecast", annotation: "Projection" },
                { period_label: "FY2027E", fiscal_year: 2027, period_end: "2027-01-31", value: 223_000_000_000, series_kind: "forecast", annotation: "Projection" },
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
            {
              key: "revenue_growth_actual",
              label: "Actual",
              unit: "percent",
              chart_type: "bar",
              series_kind: "actual",
              stroke_style: "solid",
              points: [{ period_label: "FY2025", fiscal_year: 2025, period_end: "2025-01-26", value: 1.14, series_kind: "actual", annotation: null }],
            },
            {
              key: "revenue_growth_forecast",
              label: "Forecast",
              unit: "percent",
              chart_type: "bar",
              series_kind: "forecast",
              stroke_style: "muted",
              points: [{ period_label: "FY2026E", fiscal_year: 2026, period_end: "2026-01-25", value: 0.39, series_kind: "forecast", annotation: "Projection" }],
            },
          ],
        },
        profit_metric: { key: "profit_metric", title: "Profit Metrics", subtitle: "EBIT and net income", metric_label: "Profit", unit_label: "USD", empty_state: null, highlights: [], series: [] },
        cash_flow_metric: { key: "cash_flow_metric", title: "Cash Flow Metrics", subtitle: "Operating cash flow and free cash flow", metric_label: "Cash Flow", unit_label: "USD", empty_state: null, highlights: [], series: [] },
        eps: { key: "eps", title: "EPS", subtitle: "Diluted EPS actual vs projection", metric_label: "EPS", unit_label: "USD/share", empty_state: null, highlights: [], series: [] },
        growth_summary: {
          key: "growth_summary",
          title: "Growth Summary",
          subtitle: "Company growth only until benchmark support is trustworthy",
          empty_state: null,
          comparisons: [
            { key: "hist_3y", label: "Hist 3Y", company_value: 0.47, benchmark_value: null, benchmark_label: null, unit: "percent", company_label: "NVDA", benchmark_available: false },
          ],
        },
        forecast_assumptions: {
          key: "forecast_assumptions",
          title: "Forecast Assumptions",
          empty_state: null,
          items: [
            { key: "revenue_guardrail", label: "Revenue guardrail", value: "Clipped to sane annual growth bands", detail: "Recent YoY blended with trailing CAGR." },
          ],
        },
      },
      forecast_methodology: {
        version: "company_charts_dashboard_v1",
        label: "Deterministic internal projection",
        summary: "Forecasts are generated from persisted historical official inputs with guarded trend and margin rules.",
        disclaimer: "Forecast values are projections derived in-house from historical official data and are not reported results or analyst consensus.",
        forecast_horizon_years: 3,
        confidence_label: "Medium confidence",
      },
      payload_version: "company_charts_dashboard_v1",
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
    });

    render(React.createElement(CompanyChartsPage));

    await waitFor(() => {
      expect(getCompanyCharts).toHaveBeenCalledWith("NVDA");
    });

    expect(screen.getAllByText("Growth Outlook").length).toBeGreaterThan(0);
    expect(screen.getByText("Actual vs Forecast")).toBeTruthy();
    expect(screen.getByText("Revenue Growth")).toBeTruthy();
    expect(screen.getByText("Forecast Assumptions")).toBeTruthy();
    expect(screen.getByText(/Forecast values are projections derived in-house/i)).toBeTruthy();
    expect(screen.getByText("NVIDIA Corp")).toBeTruthy();
  });
});

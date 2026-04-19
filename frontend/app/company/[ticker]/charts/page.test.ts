// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyChartsPage from "@/app/company/[ticker]/charts/page";
import { getCompanyCharts } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "nvda" }),
  useSearchParams: () => ({ get: () => null }),
  usePathname: () => "/company/NVDA/charts",
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
          { key: "forecast_stability", label: "Forecast Stability", score: 72, tone: "neutral", detail: "Forecast stability uses the Technology sector template and 4 annual periods; historical backtests show 11.0% composite weighted APE (moderate) across 3 point-in-time walk-forward snapshots with REVENUE 50%, EBIT 20%, EPS 15%, and FCF 15%; guidance status management_guidance_applied; scenario dispersion 18.0% bull/bear spread. This is a conservative stability signal, not statistical confidence." },
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
          { key: "forecast_stability", label: "Forecast Stability", score: 72, normalized_score: 0.72, tone: "neutral", detail: "Forecast stability uses the Technology sector template and 4 annual periods; historical backtests show 11.0% composite weighted APE (moderate) across 3 point-in-time walk-forward snapshots with REVENUE 50%, EBIT 20%, EPS 15%, and FCF 15%; guidance status management_guidance_applied; scenario dispersion 18.0% bull/bear spread. This is a conservative stability signal, not statistical confidence." },
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
        version: "company_charts_dashboard_v7",
        label: "Deterministic projection with empirical stability overlay",
        summary: "Forecasts are generated from persisted historical official inputs with guarded trend and margin rules.",
        disclaimer: "Forecast stability is a conservative communication aid grounded in historical multi-metric walk-forward error, not a probability, prediction interval, or statistical confidence measure. Forecast values remain projections rather than reported results or analyst consensus.",
        forecast_horizon_years: 3,
        score_name: "Forecast Stability",
        heuristic: true,
        score_components: ["Historical backtests", "History depth", "Cyclicality", "Scenario dispersion"],
        confidence_label: "Forecast stability: Moderate stability",
      },
      forecast_diagnostics: {
        score_key: "forecast_stability",
        score_name: "Forecast Stability",
        heuristic: true,
        final_score: 72,
        summary: "Forecast stability uses the Technology sector template and 4 annual periods; historical backtests show 11.0% composite weighted APE (moderate) across 3 point-in-time walk-forward snapshots with REVENUE 50%, EBIT 20%, EPS 15%, and FCF 15%; guidance status management_guidance_applied; scenario dispersion 18.0% bull/bear spread. This is a conservative stability signal, not statistical confidence.",
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
        backtest_horizon_errors: { "1": 0.08, "2": 0.12, "3": 0.14 },
        backtest_metric_weights: { revenue: 0.5, operating_income: 0.2, eps: 0.15, free_cash_flow: 0.15 },
        backtest_metric_errors: { revenue: 0.08, operating_income: 0.12, eps: 0.11, free_cash_flow: 0.14 },
        backtest_metric_horizon_errors: {
          revenue: { "1": 0.08, "2": 0.11, "3": 0.13 },
          operating_income: { "1": 0.09, "2": 0.12, "3": 0.15 },
          eps: { "1": 0.08, "2": 0.11, "3": 0.14 },
          free_cash_flow: { "1": 0.1, "2": 0.14, "3": 0.16 },
        },
        backtest_metric_sample_sizes: { revenue: 3, operating_income: 3, eps: 3, free_cash_flow: 3 },
        components: [],
      },
      payload_version: "company_charts_dashboard_v7",
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
    expect(screen.getByText("SEC-Derived Outlook")).toBeTruthy();
    expect(screen.getByText("SEC EDGAR filings only")).toBeTruthy();
    expect(screen.getByText("No third-party consensus or price prediction content")).toBeTruthy();
    expect(screen.getByText("Point-in-time inputs only")).toBeTruthy();
    expect(screen.getByText("Guarded fallback when disclosures are thin")).toBeTruthy();
    expect(screen.getByText("Deterministic projection with empirical stability overlay")).toBeTruthy();
    expect(screen.getByText(/Forecasts are generated from persisted historical official inputs/i)).toBeTruthy();
    expect(screen.getByText("NVIDIA Corp")).toBeTruthy();
  });
});

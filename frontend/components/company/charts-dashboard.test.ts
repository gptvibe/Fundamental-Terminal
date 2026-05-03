// @vitest-environment jsdom

import fs from "node:fs";
import path from "node:path";

import * as React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyChartsDashboard, MetricChartTooltipContent } from "@/components/company/charts-dashboard";
import type { CompanyChartsDashboardResponse } from "@/lib/types";

const mockUseForecastAccuracy = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/company/ACME/charts",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) =>
    React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/hooks/use-forecast-accuracy", () => ({
  useForecastAccuracy: (...args: unknown[]) => mockUseForecastAccuracy(...args),
}));

vi.mock("recharts", () => {
  function Wrapper({ children }: { children?: React.ReactNode }) {
    return React.createElement("div", null, children);
  }

  return {
    Area: Wrapper,
    Bar: Wrapper,
    CartesianGrid: Wrapper,
    ComposedChart: Wrapper,
    LabelList: Wrapper,
    Line: Wrapper,
    ReferenceArea: Wrapper,
    ReferenceLine: Wrapper,
    ResponsiveContainer: Wrapper,
    Tooltip: Wrapper,
    XAxis: Wrapper,
    YAxis: Wrapper,
  };
});

function makePayload(overrides?: Partial<CompanyChartsDashboardResponse>): CompanyChartsDashboardResponse {
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
    build_status: "Charts dashboard ready.",
    summary: {
      headline: "Growth Outlook",
      primary_score: { key: "growth", label: "Growth", score: 88, tone: "positive", detail: "Strong trend persistence.", unavailable_reason: null },
      secondary_badges: [],
      thesis: "Reported and projected values stay distinct.",
      unavailable_notes: [],
      freshness_badges: ["Updated 2026-04-13"],
      source_badges: ["Official filings"],
    },
    factors: {
      primary: { key: "growth", label: "Growth", score: 88, normalized_score: 0.88, tone: "positive", detail: "Strong trend.", unavailable_reason: null },
      supporting: [],
    },
    legend: {
      title: "Actual vs Forecast",
      items: [
        { key: "actual", label: "Reported", style: "solid", tone: "actual", description: "Historical filings." },
        { key: "forecast", label: "Forecast", style: "dashed", tone: "forecast", description: "Projected path." },
      ],
    },
    cards: {
      revenue: makeMetricCard("revenue", "Revenue"),
      revenue_outlook_bridge: makeMetricCard("revenue_outlook_bridge", "Revenue Outlook Bridge"),
      revenue_growth: makeMetricCard("revenue_growth", "Revenue Growth", "percent", "bar"),
      profit_metric: makeMetricCard("profit_metric", "Profit Metrics"),
      margin_path: makeMetricCard("margin_path", "Margin Path", "percent"),
      cash_flow_metric: makeMetricCard("cash_flow_metric", "Cash Flow Metrics"),
      fcf_outlook: makeMetricCard("fcf_outlook", "FCF Outlook"),
      eps: makeMetricCard("eps", "EPS", "usd_per_share", "bar"),
      growth_summary: {
        key: "growth_summary",
        title: "Growth Summary",
        subtitle: "Company growth only",
        comparisons: [
          { key: "hist_3y", label: "Hist 3Y", company_value: 0.25, benchmark_value: null, benchmark_label: null, unit: "percent", company_label: "Company", benchmark_available: false },
        ],
        empty_state: null,
      },
      forecast_assumptions: {
        key: "forecast_assumptions",
        title: "Forecast Assumptions",
        items: [
          { key: "revenue_method", label: "Revenue Method", value: "Driver", detail: null },
          { key: "growth_guardrail", label: "Growth Guardrail", value: "Default clip", detail: "Fallback default clip remains active." },
          { key: "history_depth", label: "History Depth", value: "5 annual periods", detail: null },
          { key: "cash_support", label: "Cash + Debt Support", value: "$90M cash", detail: null },
          { key: "dilution", label: "Dilution Bridge", value: "Proxy fallback", detail: "Proxy fallback from historical share drift." },
        ],
        empty_state: null,
      },
      forecast_calculations: {
        key: "forecast_calculations",
        title: "Forecast Calculations",
        items: [{ key: "formula_revenue", label: "Revenue Formula", value: "Prior revenue x (1 + growth)", detail: "Year-one bridge." }],
        empty_state: null,
      },
    },
    forecast_methodology: {
      version: "company_charts_dashboard_v8",
      label: "Driver-based integrated forecast",
      summary: "Forecasts are generated from official inputs.",
      disclaimer: "Forecast values are projections.",
      forecast_horizon_years: 3,
      score_name: "Forecast Stability",
      heuristic: false,
      score_components: ["History depth"],
      confidence_label: "Forecast stability: Moderate stability",
    },
    forecast_diagnostics: {
      score_key: "forecast_stability",
      score_name: "Forecast Stability",
      heuristic: false,
      final_score: 72,
      summary: "Moderate stability.",
      history_depth_years: 5,
      thin_history: false,
      growth_volatility: 0.12,
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
      available_event_types: ["earnings", "guidance", "buyback", "major_m_and_a", "restatement"],
      default_enabled_event_types: ["earnings", "guidance", "restatement"],
      events: [
        {
          key: "earnings-fy2025",
          event_type: "earnings",
          label: "Earnings release",
          event_date: "2026-01-20",
          period_label: "FY2025",
          detail: "Filed 2026-01-20",
          source_label: "SEC earnings release",
          source_url: null,
        },
      ],
      sparse_data_note: null,
    },
    quarter_change: {
      title: "What changed since last quarter?",
      latest_period_label: "FY2025",
      prior_period_label: "FY2024",
      summary: "Reported deltas and event context.",
      items: [
        {
          key: "revenue_delta",
          label: "Revenue",
          value: "+$20.0M (+20.00%)",
          detail: "FY2025 vs FY2024",
          metric_diff: {
            metric_key: "revenue",
            metric_label: "Revenue",
            previous_value: 100,
            current_value: 120,
            absolute_change: 20,
            percentage_change: 0.2,
            previous_value_missing: false,
            stale_cache: false,
            changed_input_fields: ["revenue"],
            source: {
              source_id: "sec_companyfacts",
              source_label: "Official filing snapshot",
              filing_type: "10-K",
              filing_date: "2025-12-31",
              detail: "10-K for FY2025 versus FY2024.",
            },
          },
        },
      ],
      empty_state: null,
    },
    payload_version: "company_charts_dashboard_v8",
    provenance: [],
    as_of: "2026-04-13",
    last_refreshed_at: "2026-04-13T00:00:00Z",
    source_mix: {
      source_ids: [],
      source_tiers: [],
      primary_source_ids: [],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
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
    ...overrides,
  };
}

function makeMetricCard(
  key: string,
  title: string,
  unit: "usd" | "usd_per_share" | "percent" = "usd",
  chartType: "line" | "bar" = "line"
) {
  return {
    key,
    title,
    subtitle: `${title} subtitle`,
    metric_label: title,
    unit_label: unit,
    empty_state: null,
    highlights: [],
    series: [
      {
        key: `${key}_actual`,
        label: "Reported",
        unit,
        chart_type: chartType,
        series_kind: "actual" as const,
        stroke_style: "solid" as const,
        points: [{ period_label: "FY2025", fiscal_year: 2025, period_end: "2025-12-31", value: unit === "percent" ? 0.25 : 100, series_kind: "actual" as const, annotation: null }],
      },
      {
        key: `${key}_forecast`,
        label: "Forecast",
        unit,
        chart_type: chartType,
        series_kind: "forecast" as const,
        stroke_style: "dashed" as const,
        points: [{ period_label: "FY2026E", fiscal_year: 2026, period_end: null, value: unit === "percent" ? 0.28 : 120, series_kind: "forecast" as const, annotation: "Projection" }],
      },
    ],
  };
}

describe("CompanyChartsDashboard", () => {
  beforeEach(() => {
    mockUseForecastAccuracy.mockReturnValue({ data: null, loading: false, error: null });
  });

  it("renders the requested dashboard matrix and forecast detail rows", () => {
    mockUseForecastAccuracy.mockReturnValue({
      data: {
        status: "ok",
        aggregate: { mean_absolute_percentage_error: 0.12, directional_accuracy: 0.75 },
      },
      loading: false,
      error: null,
    });
    render(React.createElement(CompanyChartsDashboard, { payload: makePayload() }));

    const assumptionsStrip = screen.getByText("Key Assumptions").closest("section");
    const detailsGrid = screen.getByLabelText("Forecast details");
    const dashboard = screen.getByLabelText("Growth outlook dashboard");
    const summary = screen.getByLabelText("Growth outlook summary");
    const detailCards = screen.getByLabelText("Growth outlook details");
    expect(assumptionsStrip).toBeTruthy();
    if (!assumptionsStrip) {
      throw new Error("Expected key assumptions strip.");
    }
    expect(detailsGrid).toBeTruthy();
    expect(dashboard).toBeTruthy();
    expect(summary).toBeTruthy();
    expect(detailCards).toBeTruthy();

    expect(screen.getByText("Revenue Outlook Bridge")).toBeTruthy();
    expect(screen.getByText("Margin Path")).toBeTruthy();
    expect(screen.getByText("FCF Outlook")).toBeTruthy();
    expect(within(detailsGrid).getByText("Forecast Calculations")).toBeTruthy();
    expect(within(detailsGrid).getByText("Forecast Assumptions")).toBeTruthy();
    expect(screen.getByText("Key Assumptions")).toBeTruthy();
    expect(screen.getByText("SEC-Derived Outlook")).toBeTruthy();
    expect(screen.getByTestId("forecast-trust-cue")).toBeTruthy();
    expect(screen.getByText("SEC Default")).toBeTruthy();
    expect(screen.getByText("MAPE 12.00%")).toBeTruthy();
    expect(screen.getByText("SEC EDGAR filings only")).toBeTruthy();
    expect(screen.getByText("No third-party consensus or price prediction content")).toBeTruthy();
    expect(screen.getByText("Projected periods begin at the divider and use a soft shaded region inside each chart.")).toBeTruthy();
    expect(screen.getAllByText("Reported").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Projected").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Copy Image" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download PNG" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy Link" })).toBeTruthy();
    expect(screen.getAllByText("FY2025").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/FY2026E/i).length).toBeGreaterThan(0);
    expect(within(assumptionsStrip).getByText("Revenue Method")).toBeTruthy();
    expect(within(assumptionsStrip).getAllByText("Fallback").length).toBeGreaterThan(0);
    expect(screen.getByText("Event overlays")).toBeTruthy();
    expect(screen.getByText("What changed since last quarter?")).toBeTruthy();
    expect(screen.getByText("Earnings release")).toBeTruthy();
    expect(screen.getAllByText("Revenue").length).toBeGreaterThan(0);

    const matrixTitles = within(dashboard)
      .getAllByRole("heading", { level: 2 })
      .map((heading) => heading.textContent);
    expect(matrixTitles).toEqual(["Revenue", "Growth Summary"]);

    const extendedMetrics = screen.getByLabelText("Growth outlook extended metrics");
    expect(within(extendedMetrics).getByText("Revenue Growth")).toBeTruthy();
    expect(within(extendedMetrics).getByText("Profit Metrics")).toBeTruthy();
    expect(within(extendedMetrics).getByText("Cash Flow Metrics")).toBeTruthy();
    expect(within(extendedMetrics).getByText("EPS")).toBeTruthy();

    expect(within(summary).queryByText("Revenue")).toBeNull();
    expect(within(detailCards).getByText("Revenue Outlook Bridge")).toBeTruthy();
  });

  it("prefers the versioned chart spec when it is present", () => {
    const baseline = makePayload();
    const payload = makePayload({
      title: "Legacy Outlook",
      summary: {
        headline: "Legacy Headline",
        primary_score: { key: "growth", label: "Growth", score: 88, tone: "positive", detail: "Legacy detail", unavailable_reason: null },
        secondary_badges: [],
        thesis: "Legacy thesis",
        unavailable_notes: [],
        freshness_badges: ["Legacy freshness"],
        source_badges: ["Legacy source"],
      },
      chart_spec: {
        schema_version: "company_chart_spec_v1",
        payload_version: "company_charts_dashboard_v8",
        company: null,
        build_state: "ready",
        build_status: "Charts dashboard ready.",
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
        as_of: "2026-04-13",
        last_refreshed_at: "2026-04-13T00:00:00Z",
        source_mix: {
          source_ids: [],
          source_tiers: [],
          primary_source_ids: [],
          fallback_source_ids: [],
          official_only: true,
        },
        confidence_flags: [],
        available_modes: ["outlook"],
        default_mode: "outlook",
        outlook: {
          title: "Spec Outlook",
          summary: {
            headline: "Spec Headline",
            primary_score: { key: "growth", label: "Growth", score: 91, tone: "positive", detail: "Spec detail", unavailable_reason: null },
            secondary_badges: [],
            thesis: "Spec thesis",
            unavailable_notes: [],
            freshness_badges: ["Spec freshness"],
            source_badges: ["Spec source"],
          },
          legend: baseline.legend,
          cards: baseline.cards,
          primary_card_order: ["revenue", "revenue_growth", "profit_metric", "cash_flow_metric", "eps"],
          secondary_card_order: ["revenue_outlook_bridge", "margin_path", "fcf_outlook"],
          comparison_card_order: ["growth_summary"],
          detail_card_order: ["forecast_assumptions", "forecast_calculations"],
          methodology: baseline.forecast_methodology,
          forecast_diagnostics: baseline.forecast_diagnostics!,
          event_overlay: baseline.event_overlay,
          quarter_change: baseline.quarter_change,
        },
        studio: null,
      },
    });

    render(React.createElement(CompanyChartsDashboard, { payload }));

    expect(screen.getByText("Spec Outlook")).toBeTruthy();
    expect(screen.getByText("Spec Headline")).toBeTruthy();
    expect(screen.queryByText("Legacy Headline")).toBeNull();
  });

  it("labels tooltip rows as reported or projected", () => {
    const payload = makePayload();

    render(
      React.createElement(MetricChartTooltipContent, {
        active: true,
        label: "FY2026E",
        seriesList: payload.cards.revenue.series,
        payload: [
          {
            dataKey: "revenue_forecast",
            name: "Forecast",
            color: "#7be0a7",
            value: 120,
            payload: {
              periodLabel: "FY2026E",
              forecastZone: true,
              events: [],
              values: { revenue_forecast: 120 },
              pointMeta: {
                revenue_forecast: {
                  annotation: "Projection",
                  seriesKind: "forecast",
                },
              },
            },
          },
        ] as never,
      })
    );

    expect(screen.getByText("Projected period")).toBeTruthy();
    expect(screen.getByText("Projected")).toBeTruthy();
    expect(screen.getByText("Projection")).toBeTruthy();
    expect(screen.getByText("$120")).toBeTruthy();
  });

  it("renders event context inside tooltip when event overlays are present", () => {
    const payload = makePayload();

    render(
      React.createElement(MetricChartTooltipContent, {
        active: true,
        label: "FY2025",
        seriesList: payload.cards.revenue.series,
        payload: [
          {
            dataKey: "revenue_actual",
            name: "Reported",
            color: "#f2efe6",
            value: 100,
            payload: {
              periodLabel: "FY2025",
              forecastZone: false,
              events: payload.event_overlay.events,
              values: { revenue_actual: 100 },
              pointMeta: {
                revenue_actual: {
                  annotation: null,
                  seriesKind: "actual",
                },
              },
            },
          },
        ] as never,
      })
    );

    expect(screen.getByText("Earnings release")).toBeTruthy();
    expect(screen.getByText(/SEC earnings release/i)).toBeTruthy();
  });

  it("shows event overlay toggles and quarter-change panel", () => {
    render(React.createElement(CompanyChartsDashboard, { payload: makePayload() }));

    expect(screen.getByRole("group", { name: "Event overlay toggles" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "earnings" })).toBeTruthy();
    expect(screen.getByText("What changed since last quarter?")).toBeTruthy();
    expect(screen.getAllByText("FY2025 vs FY2024").length).toBeGreaterThan(0);
  });

  it("opens a why-changed dialog from metric cards", () => {
    render(React.createElement(CompanyChartsDashboard, { payload: makePayload() }));

    fireEvent.click(screen.getByRole("button", { name: "Why changed Revenue" }));

    expect(screen.getByText("Why Revenue changed")).toBeTruthy();
    expect(screen.getByText("Old value")).toBeTruthy();
    expect(screen.getByText("New value")).toBeTruthy();
    expect(screen.getByText("Absolute change")).toBeTruthy();
    expect(screen.getByText("Percentage change")).toBeTruthy();
    expect(screen.getByText("Official filing snapshot")).toBeTruthy();
    expect(screen.getAllByText("revenue").length).toBeGreaterThan(0);
  });

  it("omits optional forecast cards and keeps the strip graceful when fields are missing", () => {
    const baseline = makePayload();
    const payload = makePayload({
      cards: {
        ...baseline.cards,
        revenue_outlook_bridge: null,
        margin_path: null,
        fcf_outlook: null,
        forecast_calculations: null,
        forecast_assumptions: {
          key: "forecast_assumptions",
          title: "Forecast Assumptions",
          items: [
            { key: "blank", label: "", value: "", detail: null },
            { key: "history_depth", label: "History Depth", value: "4 annual periods", detail: null },
          ],
          empty_state: null,
        },
      },
    });

    render(React.createElement(CompanyChartsDashboard, { payload }));

    const assumptionsStrip = screen.getByText("Key Assumptions").closest("section");
    const detailsGrid = screen.getByLabelText("Forecast details");
    expect(assumptionsStrip).toBeTruthy();
    if (!assumptionsStrip) {
      throw new Error("Expected key assumptions strip.");
    }

    expect(screen.queryByText("Revenue Outlook Bridge")).toBeNull();
    expect(screen.queryByText("Margin Path")).toBeNull();
    expect(screen.queryByText("FCF Outlook")).toBeNull();
    expect(within(detailsGrid).getByText("Forecast Assumptions")).toBeTruthy();
    expect(screen.getByText("Key Assumptions")).toBeTruthy();
    expect(within(assumptionsStrip).getByText("History Depth")).toBeTruthy();
    expect(screen.getAllByText("Revenue").length).toBeGreaterThan(0);
    expect(screen.getByText("Forecast Assumptions")).toBeTruthy();
  });

  it("defines a consistent minimum height for metric chart cards", () => {
    const css = fs.readFileSync(path.resolve(process.cwd(), "app/globals.css"), "utf8");

    expect(css).toContain(".charts-page-shell {");
    expect(css).toContain("width: 100%;");
    expect(css).toContain(".charts-card-matrix {");
    expect(css).toContain("min-height: 316px;");
    expect(css).toContain(".charts-dashboard-matrix {");
  });
});

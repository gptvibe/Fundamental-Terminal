import { describe, expect, it } from "vitest";

import {
  buildCompanyChartsSpecFromPayload,
  deserializeCompanyChartsSpec,
  getOrderedOutlookDetailCards,
  getOrderedOutlookMetricCards,
  serializeCompanyChartsSpec,
} from "@/lib/chart-spec";
import type { CompanyChartsDashboardResponse } from "@/lib/types";

function buildPayload(): CompanyChartsDashboardResponse {
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
      earnings_last_checked: null,
      cache_state: "fresh",
    },
    title: "Growth Outlook",
    build_state: "ready",
    build_status: "Charts dashboard ready.",
    summary: {
      headline: "Growth Outlook",
      primary_score: { key: "growth", label: "Growth", score: 88, tone: "positive", detail: "Strong trend.", unavailable_reason: null },
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
      revenue_outlook_bridge: makeMetricCard("revenue_outlook_bridge", "Revenue Bridge"),
      revenue_growth: makeMetricCard("revenue_growth", "Revenue Growth", "percent", "bar"),
      profit_metric: makeMetricCard("profit_metric", "Profit Metrics"),
      margin_path: makeMetricCard("margin_path", "Margin Path", "percent"),
      cash_flow_metric: makeMetricCard("cash_flow_metric", "Cash Flow Metrics"),
      fcf_outlook: makeMetricCard("fcf_outlook", "FCF Outlook"),
      eps: makeMetricCard("eps", "EPS", "usd_per_share", "bar"),
      growth_summary: {
        key: "growth_summary",
        title: "Growth Summary",
        subtitle: null,
        comparisons: [],
        empty_state: null,
      },
      forecast_assumptions: {
        key: "forecast_assumptions",
        title: "Forecast Assumptions",
        items: [{ key: "method", label: "Method", value: "Driver-based", detail: null }],
        empty_state: null,
      },
      forecast_calculations: {
        key: "forecast_calculations",
        title: "Forecast Calculations",
        items: [{ key: "formula", label: "Formula", value: "Prior x (1 + growth)", detail: null }],
        empty_state: null,
      },
    },
    forecast_methodology: {
      version: "company_charts_dashboard_v9",
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
    projection_studio: {
      methodology: null,
      schedule_sections: [],
      drivers_used: [],
      scenarios_comparison: [],
      sensitivity_matrix: [],
    },
    what_if: {
      impact_summary: null,
      overrides_applied: [],
      overrides_clipped: [],
      driver_control_metadata: [],
    },
    payload_version: "company_charts_dashboard_v9",
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

describe("chart-spec", () => {
  it("builds a versioned spec from the legacy charts payload", () => {
    const spec = buildCompanyChartsSpecFromPayload(buildPayload());

    expect(spec.schema_version).toBe("company_chart_spec_v1");
    expect(spec.available_modes).toEqual(["outlook", "studio"]);
    expect(getOrderedOutlookMetricCards(spec.outlook, "primary").map((card) => card.key)).toEqual([
      "revenue",
      "revenue_growth",
      "profit_metric",
      "cash_flow_metric",
      "eps",
    ]);
    expect(getOrderedOutlookMetricCards(spec.outlook, "secondary").map((card) => card.key)).toEqual([
      "revenue_outlook_bridge",
      "margin_path",
      "fcf_outlook",
    ]);
    expect(getOrderedOutlookDetailCards(spec.outlook).map((card) => card.key)).toEqual([
      "forecast_assumptions",
      "forecast_calculations",
    ]);
    expect(spec.studio?.title).toBe("Projection Studio");
  });

  it("serializes and deserializes a chart spec artifact", () => {
    const spec = buildCompanyChartsSpecFromPayload(buildPayload());
    const serialized = serializeCompanyChartsSpec(spec);
    const roundTrip = deserializeCompanyChartsSpec(serialized);

    expect(roundTrip).toEqual(spec);
  });

  it("returns null for malformed serialized chart spec payloads", () => {
    expect(deserializeCompanyChartsSpec("{\"schema_version\":\"company_chart_spec_v1\"}")).toBeNull();
    expect(deserializeCompanyChartsSpec("not-json")).toBeNull();
  });

  it("rebuilds from legacy payload when chart_spec is malformed", () => {
    const payload = buildPayload();
    const malformed = {
      ...payload,
      chart_spec: {
        schema_version: "company_chart_spec_v1",
      } as unknown as CompanyChartsDashboardResponse["chart_spec"],
    };

    const spec = buildCompanyChartsSpecFromPayload(malformed);
    expect(spec.payload_version).toBe(payload.payload_version);
    expect(spec.outlook.title).toBe(payload.title);
    expect(spec.studio?.title).toBe("Projection Studio");
  });
});

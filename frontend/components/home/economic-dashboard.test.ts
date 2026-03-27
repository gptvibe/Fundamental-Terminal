import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { EconomicDashboard } from "@/components/home/economic-dashboard";
import type { CompanyMarketContextResponse } from "@/lib/types";

vi.mock("recharts", () => {
  const MockWithChildren = ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children);
  const MockLeaf = () => React.createElement("div");

  return {
    Bar: MockLeaf,
    BarChart: MockWithChildren,
    CartesianGrid: MockLeaf,
    Cell: MockLeaf,
    Line: MockLeaf,
    LineChart: MockWithChildren,
    ReferenceLine: MockLeaf,
    ResponsiveContainer: MockWithChildren,
    Tooltip: MockLeaf,
    XAxis: MockLeaf,
    YAxis: MockLeaf,
  };
});

function makeContext(): CompanyMarketContextResponse {
  return {
    company: null,
    status: "ok",
    curve_points: [
      { tenor: "rrp", rate: 0.048, observation_date: "2026-03-21" },
      { tenor: "1m", rate: 0.0455, observation_date: "2026-03-21" },
      { tenor: "2m", rate: 0.0452, observation_date: "2026-03-21" },
      { tenor: "3m", rate: 0.043, observation_date: "2026-03-21" },
      { tenor: "4m", rate: 0.0427, observation_date: "2026-03-21" },
      { tenor: "6m", rate: 0.0422, observation_date: "2026-03-21" },
      { tenor: "1y", rate: 0.0417, observation_date: "2026-03-21" },
      { tenor: "2y", rate: 0.04, observation_date: "2026-03-21" },
      { tenor: "3y", rate: 0.0403, observation_date: "2026-03-21" },
      { tenor: "5y", rate: 0.0406, observation_date: "2026-03-21" },
      { tenor: "7y", rate: 0.0414, observation_date: "2026-03-21" },
      { tenor: "10y", rate: 0.0425, observation_date: "2026-03-21" },
      { tenor: "20y", rate: 0.0449, observation_date: "2026-03-21" },
      { tenor: "30y", rate: 0.046, observation_date: "2026-03-21" },
    ],
    slope_2s10s: { label: "2s10s", value: 0.0025, short_tenor: "2y", long_tenor: "10y", observation_date: "2026-03-21" },
    slope_3m10y: { label: "3m10y", value: -0.0005, short_tenor: "3m", long_tenor: "10y", observation_date: "2026-03-21" },
    fred_series: [
      { series_id: "BAA10Y", label: "Credit Spread", category: "credit_spread", units: "percent", value: 0.0175, observation_date: "2026-03-01", state: "ok" },
      { series_id: "T10YIE", label: "10Y Breakeven Inflation", category: "inflation", units: "percent", value: 0.024, observation_date: "2026-03-01", state: "ok" },
      { series_id: "CPIAUCSL", label: "Headline CPI (YoY)", category: "inflation", units: "percent", value: 0.029, observation_date: "2026-03-01", state: "ok" },
      { series_id: "CPILFESL", label: "Core CPI (YoY)", category: "inflation_core", units: "percent", value: 0.031, observation_date: "2026-03-01", state: "ok" },
      { series_id: "PCEPI", label: "PCE Price Index (YoY)", category: "inflation_pce", units: "percent", value: 0.027, observation_date: "2026-03-01", state: "ok" },
      { series_id: "PCEPILFE", label: "Core PCE (YoY)", category: "inflation_core_pce", units: "percent", value: 0.028, observation_date: "2026-03-01", state: "ok" },
      { series_id: "UNRATE", label: "Unemployment Rate", category: "labor", units: "percent", value: 0.041, observation_date: "2026-03-01", state: "ok" },
      { series_id: "USREC", label: "Recession Indicator", category: "regime", units: "index", value: 0, observation_date: "2026-03-01", state: "ok" },
    ],
    provenance: [
      {
        source_id: "us_treasury_daily_par_yield_curve",
        source_tier: "official_treasury_or_fed",
        display_label: "U.S. Treasury Daily Par Yield Curve",
        url: "https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
        default_freshness_ttl_seconds: 86400,
        disclosure_note: "Official Treasury yield curve used for risk-free rates and macro term-structure context.",
        role: "primary",
        as_of: "2026-03-21",
        last_refreshed_at: "2026-03-22T00:00:00Z",
      },
      {
        source_id: "fred",
        source_tier: "official_treasury_or_fed",
        display_label: "Federal Reserve Economic Data (FRED)",
        url: "https://fred.stlouisfed.org/",
        default_freshness_ttl_seconds: 86400,
        disclosure_note: "Federal Reserve public macro series used for supplemental rates, inflation, labor, and credit context.",
        role: "supplemental",
        as_of: "2026-03-01",
        last_refreshed_at: "2026-03-22T00:00:00Z",
      },
    ],
    as_of: "2026-03-21",
    last_refreshed_at: "2026-03-22T00:00:00Z",
    source_mix: {
      source_ids: ["us_treasury_daily_par_yield_curve", "fred"],
      source_tiers: ["official_treasury_or_fed"],
      primary_source_ids: ["us_treasury_daily_par_yield_curve"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    provenance_details: {
      treasury: { status: "ok" },
      fred: { enabled: true, status: "ok" },
    },
    fetched_at: "2026-03-22T00:00:00Z",
    refresh: { triggered: false, reason: "fresh", ticker: null, job_id: null },
  };
}

describe("EconomicDashboard", () => {
  it("renders professional macro sections and current indicators", () => {
    const html = renderToStaticMarkup(React.createElement(EconomicDashboard, { context: makeContext() }));

    expect(html).toContain("Yield-curve inversion is still a live risk signal.");
    expect(html).toContain("Current term structure");
    expect(html).toContain("Cross-market scorecard");
    expect(html).toContain("10Y Treasury");
    expect(html).toContain("BAA Credit Spread");
    expect(html).toContain("RRP award rate");
    expect(html).toContain("3M Treasury bill");
    expect(html).toContain("Headline CPI (YoY)");
    expect(html).toContain("Core CPI (YoY)");
    expect(html).toContain("PCE price index (YoY)");
    expect(html).toContain("Core PCE (YoY)");
    expect(html).toContain("Show core factors");
    expect(html).toContain("Front-end avg");
    expect(html).toContain("10Y minus RRP");
    expect(html).toContain("Expansion regime");
    expect(html).toContain("U.S. Treasury Daily Par Yield Curve");
  });
});

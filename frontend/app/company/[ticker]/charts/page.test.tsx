// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompanyChartsPage from "./page";

const getCompanyCharts = vi.fn();
const useParams = vi.fn();
const useSearchParams = vi.fn();
const usePathname = vi.fn();

vi.mock("@/lib/api", () => ({
  getCompanyCharts: (...args: unknown[]) => getCompanyCharts(...args),
}));

vi.mock("@/components/company/charts-dashboard", () => ({
  CompanyChartsDashboard: ({ activeMode, studioEnabled }: { activeMode?: string; studioEnabled?: boolean }) => (
    <div data-testid="charts-dashboard">
      dashboard:{activeMode}:{studioEnabled ? "enabled" : "disabled"}
    </div>
  ),
}));

vi.mock("@/components/company/projection-studio", () => ({
  ProjectionStudio: () => <div data-testid="projection-studio">Projection Studio</div>,
}));

vi.mock("next/navigation", () => ({
  useParams: () => useParams(),
  useSearchParams: () => useSearchParams(),
  usePathname: () => usePathname(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

function buildPayload(overrides: Record<string, unknown> = {}) {
  return {
    company: {
      ticker: "ACME",
      cik: "0000000001",
      name: "Acme Corporation",
      sector: "Technology",
      market_sector: "Technology",
      market_industry: "Application Software",
      oil_exposure_type: "non_oil",
      oil_support_status: "supported",
      oil_support_reasons: [],
      strict_official_mode: true,
      last_checked: null,
      last_checked_financials: null,
      last_checked_prices: null,
      last_checked_insiders: null,
      last_checked_institutional: null,
      last_checked_filings: null,
      earnings_last_checked: null,
      cache_state: "fresh",
    },
    title: "Growth Outlook",
    build_state: "ready",
    build_status: "Snapshot ready",
    summary: {
      headline: "Headline",
      primary_score: { key: "stability", label: "Forecast Stability", score: 81, tone: "positive" },
      secondary_badges: [],
      source_badges: ["SEC XBRL"],
      freshness_badges: ["Fresh"],
      thesis: "Growth outlook thesis",
      unavailable_notes: [],
    },
    factors: { items: [] },
    legend: {
      title: "Legend",
      items: [
        { key: "reported", label: "Reported", tone: "neutral", style: "solid" },
        { key: "forecast", label: "Projected", tone: "positive", style: "dashed" },
      ],
    },
    cards: {
      revenue: { key: "revenue", title: "Revenue", series: [] },
      revenue_growth: { key: "revenue_growth", title: "Revenue Growth", series: [] },
      profit_metric: { key: "profit_metric", title: "Profit Metrics", series: [] },
      cash_flow_metric: { key: "cash_flow_metric", title: "Cash Flow Metrics", series: [] },
      eps: { key: "eps", title: "EPS", series: [] },
      growth_summary: { key: "growth_summary", title: "Growth Summary", comparisons: [] },
      forecast_assumptions: null,
      forecast_calculations: null,
      revenue_outlook_bridge: null,
      margin_path: null,
      fcf_outlook: null,
    },
    forecast_methodology: {
      version: "company_charts_dashboard_v9",
      label: "Driver-based integrated forecast",
      summary: "Methodology summary",
      disclaimer: "Methodology disclaimer",
      forecast_horizon_years: 3,
      confidence_label: "High confidence",
    },
    projection_studio: null,
    payload_version: "company_charts_dashboard_v9",
    provenance: [],
    as_of: "2026-04-17",
    last_refreshed_at: null,
    source_mix: {
      source_ids: ["sec_companyfacts"],
      source_tiers: ["official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
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

describe("CompanyChartsPage", () => {
  beforeEach(() => {
    getCompanyCharts.mockReset();
    useParams.mockReturnValue({ ticker: "acme" });
    usePathname.mockReturnValue("/company/acme/charts");
    useSearchParams.mockReturnValue({ get: () => null });
  });

  it("renders Growth Outlook by default", async () => {
    getCompanyCharts.mockResolvedValue(buildPayload());

    render(React.createElement(CompanyChartsPage));

    await waitFor(() => {
      expect(getCompanyCharts).toHaveBeenCalledWith("ACME", undefined);
    });
    expect(screen.getByTestId("charts-dashboard").textContent).toBe("dashboard:outlook:disabled");
  });

  it("renders Projection Studio when URL mode is studio and payload exists", async () => {
    useSearchParams.mockReturnValue({ get: (key: string) => (key === "mode" ? "studio" : null) });
    getCompanyCharts.mockResolvedValue(
      buildPayload({
        projection_studio: {
          methodology: null,
          schedule_sections: [],
          drivers_used: [],
          scenarios_comparison: [],
          sensitivity_matrix: [],
        },
      })
    );

    render(React.createElement(CompanyChartsPage));

    expect(await screen.findByTestId("projection-studio")).toBeTruthy();
  });

  it("falls back to Growth Outlook when studio mode is requested without payload", async () => {
    useSearchParams.mockReturnValue({ get: (key: string) => (key === "mode" ? "studio" : null) });
    getCompanyCharts.mockResolvedValue(buildPayload());

    render(React.createElement(CompanyChartsPage));

    expect(await screen.findByTestId("charts-dashboard")).toBeTruthy();
    expect(screen.getByTestId("charts-dashboard").textContent).toBe("dashboard:outlook:disabled");
  });
});
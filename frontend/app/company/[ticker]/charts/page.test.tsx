// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompanyChartsPage, { generateMetadata } from "./page";

const headersMock = vi.fn();
const fetchMock = vi.fn();

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
}));

vi.mock("./charts-retry-button", () => ({
  ChartsRetryButton: () => <button type="button">Try again</button>,
}));

vi.mock("@/components/company/charts-dashboard", () => ({
  CompanyChartsDashboard: ({ activeMode, studioEnabled }: { activeMode?: string; studioEnabled?: boolean }) => (
    <div data-testid="charts-dashboard">
      dashboard:{activeMode}:{studioEnabled ? "enabled" : "disabled"}
    </div>
  ),
}));

vi.mock("./projection-studio-hydration", () => ({
  ProjectionStudioHydration: () => <div data-testid="projection-studio">Projection Studio</div>,
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

  it("renders Growth Outlook by default from server data", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => buildPayload(),
    });

    const jsx = await CompanyChartsPage({
      params: { ticker: "acme" },
      searchParams: { as_of: "2026-04-17" },
    });
    render(jsx);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/companies/ACME/charts?as_of=2026-04-17",
      expect.objectContaining({ next: expect.objectContaining({ revalidate: 20 }) })
    );
    expect(screen.getByTestId("charts-dashboard").textContent).toBe("dashboard:outlook:disabled");
  });

  it("builds route metadata from the cached charts payload", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => buildPayload(),
    });

    const metadata = await generateMetadata({
      params: { ticker: "acme" },
      searchParams: { as_of: "2026-04-17" },
    });

    expect(metadata.title).toBe("Acme Corporation Growth Outlook");
    expect(metadata.description).toContain("Growth outlook thesis");
    expect(metadata.description).toContain("SEC XBRL");
    expect(metadata.alternates?.canonical).toBe("http://localhost:3000/company/ACME/charts?as_of=2026-04-17");
    expect(metadata.openGraph?.images?.[0]).toBe("http://localhost:3000/company/ACME/charts/opengraph-image?as_of=2026-04-17");
  });

  it("renders Projection Studio when mode is studio and payload includes studio", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () =>
        buildPayload({
          projection_studio: {
            methodology: null,
            schedule_sections: [],
            drivers_used: [],
            scenarios_comparison: [],
            sensitivity_matrix: [],
          },
        }),
    });

    const jsx = await CompanyChartsPage({
      params: { ticker: "acme" },
      searchParams: { mode: "studio" },
    });
    render(jsx);

    expect(screen.getByTestId("projection-studio")).toBeTruthy();
  });

  it("falls back to Growth Outlook when studio mode is requested without studio payload", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => buildPayload(),
    });

    const jsx = await CompanyChartsPage({
      params: { ticker: "acme" },
      searchParams: { mode: "studio" },
    });
    render(jsx);

    expect(screen.getByTestId("charts-dashboard").textContent).toBe("dashboard:outlook:disabled");
  });

  it("maps 404 failures to product copy and never renders raw transport text", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({}),
    });

    const jsx = await CompanyChartsPage({
      params: { ticker: "acme" },
      searchParams: {},
    });
    render(jsx);

    expect(screen.getByText("Charts for this company are unavailable or not yet prepared.")).toBeTruthy();
    expect(screen.queryByText(/API request failed:/i)).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});

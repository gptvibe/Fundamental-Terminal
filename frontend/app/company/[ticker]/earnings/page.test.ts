// @vitest-environment jsdom

import * as React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CompanyEarningsPage from "@/app/company/[ticker]/earnings/page";
import { getCompanyEarningsWorkspace } from "@/lib/api";

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal("ResizeObserver", ResizeObserverMock);

afterEach(() => {
  cleanup();
});

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: "2026-03-21", earnings_last_checked: "2026-03-22" },
    loading: false,
    error: null,
    refreshing: false,
    refreshState: null,
    consoleEntries: [],
    connectionState: "connected",
    queueRefresh: vi.fn(),
    reloadKey: 0,
  }),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) =>
    React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, children }: { title: string; children?: React.ReactNode }) =>
    React.createElement("section", null, React.createElement("h2", null, title), children),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/charts/earnings-trend-chart", () => ({
  EarningsTrendChart: () => React.createElement("div", null, "earnings-chart"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyEarningsWorkspace: vi.fn(async () => ({
    company: {
      ticker: "ACME",
      cik: "0000000001",
      name: "Acme Corp",
      sector: "Tech",
      market_sector: "Technology",
      market_industry: "Software",
      last_checked: "2026-05-08T00:00:00Z",
      last_checked_financials: "2026-05-08T00:00:00Z",
      last_checked_prices: "2026-05-08T00:00:00Z",
      last_checked_insiders: null,
      last_checked_institutional: null,
      last_checked_filings: null,
      earnings_last_checked: "2026-05-08T00:00:00Z",
      cache_state: "fresh",
    },
    earnings_releases: [
      {
        accession_number: "0000001-26-000010",
        form: "8-K",
        filing_date: "2026-05-07",
        report_date: "2026-05-07",
        primary_document: "acme-q2-earnings.htm",
        exhibit_document: "ex99-1.htm",
        exhibit_type: "99.1",
        source_url: "https://www.sec.gov/acme/earnings/q2",
        parse_state: "parsed",
        reported_period_label: "Q2 2026",
        reported_period_end: "2026-04-30",
        revenue: 120,
        operating_income: 35,
        net_income: 28,
        diluted_eps: 1.18,
        revenue_guidance_low: 125,
        revenue_guidance_high: 130,
        eps_guidance_low: 1.2,
        eps_guidance_high: 1.3,
        share_repurchase_amount: 500,
        dividend_per_share: 0.24,
        highlights: ["Revenue grew 18%", "Free cash flow stayed positive"],
      },
      {
        accession_number: "0000001-26-000004",
        form: "8-K",
        filing_date: "2026-02-06",
        report_date: "2026-02-06",
        primary_document: "acme-q1-earnings.htm",
        exhibit_document: "ex99-1.htm",
        exhibit_type: "99.1",
        source_url: "https://www.sec.gov/acme/earnings/q1",
        parse_state: "metadata_only",
        reported_period_label: "Q1 2026",
        reported_period_end: "2026-01-31",
        revenue: 95,
        operating_income: 21,
        net_income: 18,
        diluted_eps: 0.91,
        revenue_guidance_low: null,
        revenue_guidance_high: null,
        eps_guidance_low: null,
        eps_guidance_high: null,
        share_repurchase_amount: null,
        dividend_per_share: null,
        highlights: [],
      },
    ],
    summary: {
      total_releases: 2,
      parsed_releases: 1,
      metadata_only_releases: 1,
      releases_with_guidance: 1,
      releases_with_buybacks: 1,
      releases_with_dividends: 1,
      latest_filing_date: "2026-05-07",
      latest_report_date: "2026-05-07",
      latest_reported_period_end: "2026-04-30",
      latest_revenue: 120,
      latest_operating_income: 35,
      latest_net_income: 28,
      latest_diluted_eps: 1.18,
    },
    model_points: [
      {
        period_start: "2026-01-01",
        period_end: "2026-04-30",
        filing_type: "10-Q",
        quality_score: 72,
        quality_score_delta: 6,
        eps_drift: 0.27,
        earnings_momentum_drift: 0.08,
        segment_contribution_delta: 0.1,
        release_statement_coverage_ratio: 0.8,
        fallback_ratio: 0.25,
        stale_period_warning: false,
        quality_flags: [],
        source_statement_ids: [101, 102],
        source_release_ids: [10],
        explainability: {
          formula_version: "sec_earnings_intel_v1",
          period_end: "2026-04-30",
          filing_type: "10-Q",
          inputs: [
            {
              field: "revenue",
              value: 120,
              period_end: "2026-04-30",
              sec_tags: ["us-gaap:Revenues"],
            },
          ],
          component_values: {},
          proxy_usage: {},
          segment_deltas: [
            {
              segment_id: "core",
              segment_name: "Core",
              current_share: 0.65,
              previous_share: 0.55,
              delta: 0.1,
            },
          ],
          release_statement_coverage: {},
          quality_formula: "quality-f",
          eps_drift_formula: "eps-f",
          momentum_formula: "mom-f",
        },
      },
    ],
    backtests: {
      window_sessions: 3,
      quality_directional_consistency: 0.75,
      quality_total_windows: 4,
      quality_consistent_windows: 3,
      eps_directional_consistency: 0.5,
      eps_total_windows: 2,
      eps_consistent_windows: 1,
      windows: [],
    },
    peer_context: {
      peer_group_basis: "market_sector",
      peer_group_size: 8,
      quality_percentile: 0.88,
      eps_drift_percentile: 0.67,
      sector_group_size: 12,
      sector_quality_percentile: 0.84,
      sector_eps_drift_percentile: 0.63,
    },
    alerts: [
      {
        id: "quality-regime:2026-04-30",
        type: "quality_regime_shift",
        level: "high",
        title: "Quality score regime shift",
        detail: "Quality regime moved from mid to high.",
        period_end: "2026-04-30",
      },
    ],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyEarningsPage", () => {
  it("renders earnings summary, trend, and release detail panels", async () => {
    render(React.createElement(CompanyEarningsPage));

    await waitFor(() => {
      expect(getCompanyEarningsWorkspace).toHaveBeenCalledTimes(1);
      expect(screen.getAllByText("Revenue grew 18%").length).toBeGreaterThan(0);
      expect(screen.getByText(/Revenue 125-130/)).toBeTruthy();
    });

    expect(getCompanyEarningsWorkspace).toHaveBeenCalledWith("ACME");
    expect(screen.getByText("Earnings")).toBeTruthy();
    expect(screen.getByText("earnings-chart")).toBeTruthy();
    expect(screen.getByText(/Buyback authorization 500/)).toBeTruthy();
    expect(screen.getByText("Peer-Relative Context")).toBeTruthy();
    expect(screen.getByText("Directional Backtests")).toBeTruthy();
    expect(screen.getByText("Model Alerts")).toBeTruthy();
    expect(screen.getByText("Explainability")).toBeTruthy();
    expect(screen.getByText("Quality score regime shift")).toBeTruthy();
    expect(screen.getByText(/Formulas:/)).toBeTruthy();

    fireEvent.click(screen.getByText("Q1 2026"));

    expect(screen.getByText("Metadata only capture; open the SEC filing to inspect the full release narrative.")).toBeTruthy();
    expect(screen.getByText("No guidance disclosed")).toBeTruthy();
  });

  it("supports workspace panel interactions and metadata toggle", async () => {
    render(React.createElement(CompanyEarningsPage));

    await waitFor(() => {
      expect(screen.getByText(/Coverage ratio/i)).toBeTruthy();
      expect(screen.getByText(/Fallback ratio/i)).toBeTruthy();
      expect(screen.getByText(/Stale warning/i)).toBeTruthy();
      expect(screen.getByText("Quality consistency")).toBeTruthy();
      expect(screen.getByText("EPS windows")).toBeTruthy();
    });

    const toggle = screen.getAllByRole("button", { name: "Show metadata-only releases" })[0];
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide metadata-only releases" })).toBeTruthy();

    expect(screen.getAllByText("Peer basis").length).toBeGreaterThan(0);
    expect(screen.getByText("market sector")).toBeTruthy();
    expect(screen.getByText("SEC tags")).toBeTruthy();
    expect(screen.getByText("us-gaap:Revenues")).toBeTruthy();
  });
});

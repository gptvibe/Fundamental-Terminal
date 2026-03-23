// @vitest-environment jsdom

import * as React from "react";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CompanyOwnershipPage from "@/app/company/[ticker]/ownership/page";
import { getCompanyInstitutionalHoldings, getCompanyInstitutionalHoldingsSummary } from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "msft" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "MSFT", name: "Microsoft", sector: "Tech", last_checked: "2026-03-21" },
    financials: [],
    institutionalData: null,
    institutionalHoldings: [],
    institutionalError: null,
    loading: false,
    refreshing: false,
    refreshState: { triggered: true, reason: "manual", ticker: "MSFT", job_id: "job-1" },
    activeJobId: "job-1",
    consoleEntries: [],
    connectionState: "open",
    queueRefresh: vi.fn(),
    reloadKey: "0",
  }),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ children }: { children?: React.ReactNode }) => React.createElement("section", null, children),
}));

vi.mock("@/components/ui/plain-english-scorecard", () => ({
  PlainEnglishScorecard: () => React.createElement("div", null, "scorecard"),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/charts/institutional-ownership-trend-chart", () => ({
  InstitutionalOwnershipTrendChart: () => React.createElement("div", null, "ownership-trend"),
}));

vi.mock("@/components/charts/smart-money-flow-chart", () => ({
  SmartMoneyFlowChart: () => React.createElement("div", null, "smart-money-flow"),
}));

vi.mock("@/components/institutional/new-vs-exited-positions", () => ({
  NewVsExitedPositions: () => React.createElement("div", null, "new-vs-exited"),
}));

vi.mock("@/components/institutional/conviction-heatmap", () => ({
  ConvictionHeatmap: () => React.createElement("div", null, "conviction-heatmap"),
}));

vi.mock("@/components/institutional/smart-money-summary", () => ({
  SmartMoneySummary: () => React.createElement("div", null, "smart-money-summary"),
}));

vi.mock("@/components/institutional/top-holder-trend", () => ({
  TopHolderTrend: () => React.createElement("div", null, "top-holder-trend"),
}));

vi.mock("@/components/tables/hedge-fund-activity-table", () => ({
  HedgeFundActivityTable: () => React.createElement("div", null, "hedge-fund-activity"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyInstitutionalHoldings: vi.fn(),
  getCompanyInstitutionalHoldingsSummary: vi.fn(),
}));

describe("CompanyOwnershipPage auto refresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("shows ownership data without a full page reload after the refresh job completes", async () => {
    const fetchHoldings = vi.mocked(getCompanyInstitutionalHoldings);
    const fetchSummary = vi.mocked(getCompanyInstitutionalHoldingsSummary);

    fetchSummary
      .mockResolvedValueOnce({
        company: null,
        summary: { total_rows: 0, unique_managers: 0, amended_rows: 0, latest_reporting_date: null },
        refresh: { triggered: true, reason: "manual", ticker: "MSFT", job_id: "job-1" },
      })
      .mockResolvedValueOnce({
        company: null,
        summary: { total_rows: 0, unique_managers: 0, amended_rows: 0, latest_reporting_date: null },
        refresh: { triggered: true, reason: "manual", ticker: "MSFT", job_id: "job-1" },
      })
      .mockResolvedValueOnce({
        company: null,
        summary: { total_rows: 1, unique_managers: 1, amended_rows: 0, latest_reporting_date: "2025-12-31" },
        refresh: { triggered: false, reason: "fresh", ticker: "MSFT", job_id: null },
      })
      .mockResolvedValue({
        company: null,
        summary: { total_rows: 1, unique_managers: 1, amended_rows: 0, latest_reporting_date: "2025-12-31" },
        refresh: { triggered: false, reason: "fresh", ticker: "MSFT", job_id: null },
      });

    fetchHoldings
      .mockResolvedValueOnce({
        company: null,
        institutional_holdings: [],
        refresh: { triggered: true, reason: "manual", ticker: "MSFT", job_id: "job-1" },
      })
      .mockResolvedValueOnce({
        company: null,
        institutional_holdings: [
          {
            fund_name: "Example Fund",
            fund_cik: null,
            fund_manager: null,
            manager_query: null,
            universe_source: null,
            fund_strategy: null,
            accession_number: null,
            filing_form: "13F-HR",
            base_form: "13F-HR",
            is_amendment: false,
            reporting_date: "2025-12-31",
            filing_date: "2026-02-14",
            shares_held: 100,
            market_value: 1000,
            change_in_shares: 100,
            percent_change: 1,
            portfolio_weight: 0.01,
            put_call: null,
            investment_discretion: null,
            voting_authority_sole: null,
            voting_authority_shared: null,
            voting_authority_none: null,
            source: "sec",
          },
        ],
        refresh: { triggered: false, reason: "fresh", ticker: "MSFT", job_id: null },
      })
      .mockResolvedValue({
        company: null,
        institutional_holdings: [
          {
            fund_name: "Example Fund",
            fund_cik: null,
            fund_manager: null,
            manager_query: null,
            universe_source: null,
            fund_strategy: null,
            accession_number: null,
            filing_form: "13F-HR",
            base_form: "13F-HR",
            is_amendment: false,
            reporting_date: "2025-12-31",
            filing_date: "2026-02-14",
            shares_held: 100,
            market_value: 1000,
            change_in_shares: 100,
            percent_change: 1,
            portfolio_weight: 0.01,
            put_call: null,
            investment_discretion: null,
            voting_authority_sole: null,
            voting_authority_shared: null,
            voting_authority_none: null,
            source: "sec",
          },
        ],
        refresh: { triggered: false, reason: "fresh", ticker: "MSFT", job_id: null },
      });

    render(React.createElement(CompanyOwnershipPage));

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchSummary.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(fetchHoldings.mock.calls.length).toBeGreaterThanOrEqual(1);

    expect(screen.getAllByText("0").length).toBeGreaterThan(0);

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(fetchSummary.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(fetchHoldings.mock.calls.length).toBeGreaterThanOrEqual(2);

    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
  });
});
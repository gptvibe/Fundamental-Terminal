// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyEarningsPage from "@/app/company/[ticker]/earnings/page";
import { getCompanyEarnings, getCompanyEarningsSummary } from "@/lib/api";

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
  getCompanyEarnings: vi.fn(async () => ({
    company: null,
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
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyEarningsSummary: vi.fn(async () => ({
    company: null,
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
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyEarningsPage", () => {
  it("renders earnings summary, trend, and release detail panels", async () => {
    render(React.createElement(CompanyEarningsPage));

    await waitFor(() => {
      expect(getCompanyEarnings).toHaveBeenCalledTimes(1);
      expect(getCompanyEarningsSummary).toHaveBeenCalledTimes(1);
      expect(screen.getAllByText("Revenue grew 18%").length).toBeGreaterThan(0);
      expect(screen.getByText(/Revenue 125-130/)).toBeTruthy();
    });

    expect(getCompanyEarnings).toHaveBeenCalledWith("ACME");
    expect(getCompanyEarningsSummary).toHaveBeenCalledWith("ACME");
    expect(screen.getByText("Earnings")).toBeTruthy();
    expect(screen.getByText("earnings-chart")).toBeTruthy();
    expect(screen.getByText(/Buyback authorization 500/)).toBeTruthy();

    fireEvent.click(screen.getByText("Q1 2026"));

    expect(screen.getByText("Metadata only capture; open the SEC filing to inspect the full release narrative.")).toBeTruthy();
    expect(screen.getByText("No guidance disclosed")).toBeTruthy();
  });
});

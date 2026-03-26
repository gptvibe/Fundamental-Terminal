import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import CompanyCapitalMarketsPage from "@/app/company/[ticker]/capital-markets/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: null },
    financials: [],
    loading: false,
    refreshing: false,
    refreshState: null,
    consoleEntries: [],
    connectionState: "connected",
    queueRefresh: vi.fn(),
    reloadKey: 0,
  }),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children),
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

vi.mock("@/components/charts/capital-markets-signal-chart", () => ({
  CapitalMarketsSignalChart: () => React.createElement("div", null, "capital-signal-chart"),
}));

vi.mock("@/components/charts/share-dilution-tracker-chart", () => ({
  ShareDilutionTrackerChart: () => React.createElement("div", null, "dilution-chart"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyCapitalMarkets: vi.fn(async () => ({
    company: null,
    filings: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyCapitalMarketsSummary: vi.fn(async () => ({
    company: null,
    summary: {
      total_filings: 0,
      late_filer_notices: 0,
      max_offering_amount: null,
    },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyFilingEvents: vi.fn(async () => ({
    company: null,
    events: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyCapitalMarketsPage", () => {
  it("renders the shared capital-markets workspace header and panels", () => {
    const html = renderToStaticMarkup(React.createElement(CompanyCapitalMarketsPage));

    expect(html).toContain("Capital Markets");
    expect(html).toContain("SEC-first financing workspace covering registration activity");
    expect(html).toContain("Financing Signal Tracker");
    expect(html).toContain("Capital Raise Filings");
    expect(html).toContain("Recent Financing Events");
    expect(html).toContain("capital-signal-chart");
    expect(html).toContain("dilution-chart");
  });
});

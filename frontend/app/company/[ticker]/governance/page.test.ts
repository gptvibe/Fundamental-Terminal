import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import CompanyGovernancePage from "@/app/company/[ticker]/governance/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: null },
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

vi.mock("@/components/charts/governance-filing-chart", () => ({
  GovernanceFilingChart: () => React.createElement("div", null, "governance-chart"),
}));

vi.mock("recharts", () => {
  function Wrapper({ children }: { children?: React.ReactNode }) {
    return React.createElement("div", null, children);
  }

  return {
    Bar: Wrapper,
    BarChart: Wrapper,
    CartesianGrid: Wrapper,
    ResponsiveContainer: Wrapper,
    Tooltip: Wrapper,
    XAxis: Wrapper,
    YAxis: Wrapper,
  };
});

vi.mock("@/lib/api", () => ({
  getCompanyGovernance: vi.fn(async () => ({
    company: null,
    filings: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyGovernanceSummary: vi.fn(async () => ({
    company: null,
    summary: {
      total_filings: 0,
      definitive_proxies: 0,
      supplemental_proxies: 0,
      filings_with_meeting_date: 0,
      filings_with_exec_comp: 0,
      filings_with_vote_items: 0,
      latest_meeting_date: null,
      max_vote_item_count: 0,
    },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyExecutiveCompensation: vi.fn(async () => ({
    company: null,
    rows: [],
    fiscal_years: [],
    source: "none",
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyGovernancePage", () => {
  it("renders the shared governance workspace header and panels", () => {
    const html = renderToStaticMarkup(React.createElement(CompanyGovernancePage));

    expect(html).toContain("Governance");
    expect(html).toContain("Proxy intelligence stays centered on SEC DEF 14A and DEFA14A filings");
    expect(html).toContain("Proxy Filing Mix");
    expect(html).toContain("Board &amp; Meeting History");
    expect(html).toContain("Executive Compensation");
    expect(html).toContain("governance-chart");
  });
});
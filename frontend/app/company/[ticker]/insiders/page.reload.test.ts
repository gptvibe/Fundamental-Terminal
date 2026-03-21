// @vitest-environment jsdom

import * as React from "react";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyInsidersPage from "@/app/company/[ticker]/insiders/page";
import { getCompanyForm144Filings } from "@/lib/api";

let reloadKey = 0;

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: "2026-03-21" },
    insiderData: null,
    insiderTrades: [],
    insiderError: null,
    loading: false,
    refreshing: false,
    refreshState: null,
    consoleEntries: [],
    connectionState: "connected",
    queueRefresh: vi.fn(),
    reloadKey,
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

vi.mock("@/components/insiders/insider-activity-summary", () => ({
  InsiderActivitySummary: () => React.createElement("div", null, "insider-summary"),
}));

vi.mock("@/components/charts/insider-activity-trend-chart", () => ({
  InsiderActivityTrendChart: () => React.createElement("div", null, "insider-trend"),
}));

vi.mock("@/components/insiders/insider-signal-breakdown", () => ({
  InsiderSignalBreakdown: () => React.createElement("div", null, "insider-signal"),
}));

vi.mock("@/components/charts/insider-role-activity-chart", () => ({
  InsiderRoleActivityChart: () => React.createElement("div", null, "insider-role"),
}));

vi.mock("@/components/tables/insider-transactions-table", () => ({
  InsiderTransactionsTable: () => React.createElement("div", null, "insider-table"),
}));

vi.mock("@/components/tables/form144-filings-table", () => ({
  Form144FilingsTable: () => React.createElement("div", null, "form144-table"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyForm144Filings: vi.fn(async () => ({
    company: null,
    filings: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
  })),
}));

describe("CompanyInsidersPage Form 144 refresh", () => {
  it("refetches Form 144 filings when workspace reloadKey changes", async () => {
    const fetchForm144 = vi.mocked(getCompanyForm144Filings);
    const { rerender } = render(React.createElement(CompanyInsidersPage));

    await waitFor(() => {
      expect(fetchForm144).toHaveBeenCalledTimes(1);
    });

    reloadKey = 1;
    rerender(React.createElement(CompanyInsidersPage));

    await waitFor(() => {
      expect(fetchForm144).toHaveBeenCalledTimes(2);
    });

    expect(fetchForm144).toHaveBeenNthCalledWith(1, "ACME");
    expect(fetchForm144).toHaveBeenNthCalledWith(2, "ACME");
  });
});

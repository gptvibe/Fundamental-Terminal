// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyOverviewPage from "@/app/company/[ticker]/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", cik: "0000001", sector: "Tech", last_checked: "2026-03-10" },
    financials: [],
    priceHistory: [],
    fundamentalsTrendData: [],
    latestFinancial: null,
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

vi.mock("@/components/alerts/risk-red-flag-panel", () => ({
  RiskRedFlagPanel: () => React.createElement("div", null, "risk-red-flags"),
}));

vi.mock("@/components/charts/business-segment-breakdown", () => ({
  BusinessSegmentBreakdown: () => React.createElement("div", null, "segment-breakdown"),
}));

vi.mock("@/components/charts/cash-flow-waterfall-chart", () => ({
  CashFlowWaterfallChart: () => React.createElement("div", null, "cashflow-waterfall"),
}));

vi.mock("@/components/charts/liquidity-capital-chart", () => ({
  LiquidityCapitalChart: () => React.createElement("div", null, "liquidity-capital"),
}));

vi.mock("@/components/charts/price-fundamentals-module", () => ({
  PriceFundamentalsModule: () => React.createElement("div", null, "price-fundamentals"),
}));

vi.mock("@/components/charts/share-dilution-tracker-chart", () => ({
  ShareDilutionTrackerChart: () => React.createElement("div", null, "dilution-tracker"),
}));

vi.mock("@/components/company/financial-history-section", () => ({
  FinancialHistorySection: () => React.createElement("div", null, "financial-history"),
}));

vi.mock("@/components/peers/peer-comparison-dashboard", () => ({
  PeerComparisonDashboard: () => React.createElement("div", null, "peer-dashboard"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyActivityFeed: vi.fn(async () => ({
    company: null,
    entries: [
      {
        id: "entry-144",
        date: "2026-03-10",
        type: "form144",
        badge: "144",
        title: "Jane Doe filed Form 144 planned sale",
        detail: "Planned sale 2026-03-18 | Jane Doe | 12,500 shares | $2,500,000",
        href: null,
      },
    ],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyAlerts: vi.fn(async () => ({
    company: null,
    alerts: [],
    summary: { total: 0, high: 0, medium: 0, low: 0 },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyOverviewPage activity feed", () => {
  it("renders Form 144 entries with planned-sale label", async () => {
    render(React.createElement(CompanyOverviewPage));

    await waitFor(() => {
      expect(screen.getByText("Jane Doe filed Form 144 planned sale")).toBeTruthy();
    });

    expect(screen.getByText("planned-sale")).toBeTruthy();
    expect(screen.getByText("144")).toBeTruthy();
  });
});

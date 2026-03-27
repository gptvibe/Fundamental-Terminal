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
    data: {
      provenance: [
        {
          source_id: "sec_companyfacts",
          source_tier: "official_regulator",
          display_label: "SEC Company Facts (XBRL)",
          url: "https://data.sec.gov/api/xbrl/companyfacts/",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
          role: "primary",
          as_of: "2025-12-31",
          last_refreshed_at: "2026-03-10T00:00:00Z",
        },
        {
          source_id: "yahoo_finance",
          source_tier: "commercial_fallback",
          display_label: "Yahoo Finance",
          url: "https://finance.yahoo.com/",
          default_freshness_ttl_seconds: 3600,
          disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
          role: "fallback",
          as_of: "2026-03-10",
          last_refreshed_at: "2026-03-10T00:00:00Z",
        },
      ],
      source_mix: {
        source_ids: ["sec_companyfacts", "yahoo_finance"],
        source_tiers: ["commercial_fallback", "official_regulator"],
        primary_source_ids: ["sec_companyfacts"],
        fallback_source_ids: ["yahoo_finance"],
        official_only: false,
      },
    },
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

vi.mock("@/components/charts/company-visualization-lab", () => ({
  CompanyVisualizationLab: () => React.createElement("div", null, "visualization-lab"),
}));

vi.mock("@/components/company/financial-history-section", () => ({
  FinancialHistorySection: () => React.createElement("div", null, "financial-history"),
}));

vi.mock("@/components/company/changes-since-last-filing-card", () => ({
  ChangesSinceLastFilingCard: () => React.createElement("div", null, "changes-since-last-filing"),
}));

vi.mock("@/components/peers/peer-comparison-dashboard", () => ({
  PeerComparisonDashboard: () => React.createElement("div", null, "peer-dashboard"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyActivityOverview: vi.fn(async () => ({
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
    alerts: [],
    summary: { total: 0, high: 0, medium: 0, low: 0 },
    provenance: [
      {
        source_id: "ft_activity_overview",
        source_tier: "derived_from_official",
        display_label: "Fundamental Terminal Activity Overview",
        url: "https://github.com/gptvibe/Fundamental-Terminal",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Unified activity feed assembled from official SEC disclosures and official macro status signals.",
        role: "derived",
        as_of: "2026-03-10",
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
      {
        source_id: "sec_edgar",
        source_tier: "official_regulator",
        display_label: "SEC EDGAR Filing Archive",
        url: "https://www.sec.gov/edgar/search/",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Official SEC filing archive used for filing metadata, ownership, governance, and event disclosures.",
        role: "primary",
        as_of: "2026-03-10",
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
    ],
    as_of: "2026-03-10",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: {
      source_ids: ["ft_activity_overview", "sec_edgar"],
      source_tiers: ["derived_from_official", "official_regulator"],
      primary_source_ids: ["sec_edgar"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    market_context_status: {
      state: "partial",
      label: "Macro partial",
      observation_date: "2026-03-10",
      source: "U.S. Treasury Daily Par Yield Curve",
    },
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
    expect(screen.getByText("commercial_fallback")).toBeTruthy();
    expect(screen.getByText(/Price history and market profile data on this overview surface includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();
    expect(screen.getByText("SEC EDGAR Filing Archive")).toBeTruthy();
  });
});

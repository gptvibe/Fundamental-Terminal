// @vitest-environment jsdom

import * as React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CompanyPeersPage from "@/app/company/[ticker]/peers/page";

const mockUseCompanyWorkspace = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: (...args: unknown[]) => mockUseCompanyWorkspace(...args),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) => React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, children }: { title: string; children?: React.ReactNode }) => React.createElement("section", null, React.createElement("h2", null, title), children),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/peers/peer-comparison-dashboard", () => ({
  PeerComparisonDashboard: ({ ticker }: { ticker: string }) => React.createElement("div", null, `peer-dashboard-${ticker}`),
}));

describe("CompanyPeersPage", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders loading state while company context loads", () => {
    mockUseCompanyWorkspace.mockReturnValue({
      company: null,
      financials: [],
      loading: true,
      refreshing: false,
      refreshState: null,
      consoleEntries: [],
      connectionState: "idle",
      queueRefresh: vi.fn(),
      reloadKey: "reload-1",
    });

    render(React.createElement(CompanyPeersPage));

    expect(screen.getByRole("heading", { name: "Peers" })).toBeTruthy();
    expect(screen.getByText("4 selected peers")).toBeTruthy();
    expect(screen.getByText("Loading peer comparison...")).toBeTruthy();
  });

  it("renders peer workspace metrics once company context is available", () => {
    mockUseCompanyWorkspace.mockReturnValue({
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
            last_refreshed_at: "2026-03-22T00:00:00Z",
          },
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            url: "https://finance.yahoo.com/",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
            role: "fallback",
            as_of: "2026-03-21",
            last_refreshed_at: "2026-03-21T00:00:00Z",
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
      company: { name: "Acme Corp", sector: "Technology", last_checked: "2026-03-22T00:00:00Z", strict_official_mode: false },
      financials: [{ id: 1 }],
      loading: false,
      refreshing: false,
      refreshState: null,
      consoleEntries: [],
      connectionState: "idle",
      queueRefresh: vi.fn(),
      reloadKey: "reload-2",
    });

    render(React.createElement(CompanyPeersPage));

    expect(screen.getByRole("heading", { name: "Peers" })).toBeTruthy();
    expect(screen.getByText("4 selected peers")).toBeTruthy();
    expect(screen.getByText(/Market profile and peer-comparison price inputs on this surface includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();
    expect(screen.getByText("peer-dashboard-ACME")).toBeTruthy();
  });

  it("explains strict official mode when peer charts are disabled", () => {
    mockUseCompanyWorkspace.mockReturnValue({
      company: { name: "Acme Corp", sector: "Technology", last_checked: "2026-03-22T00:00:00Z", strict_official_mode: true },
      financials: [{ id: 1 }],
      loading: false,
      refreshing: false,
      refreshState: null,
      consoleEntries: [],
      connectionState: "idle",
      queueRefresh: vi.fn(),
      reloadKey: "reload-3",
    });

    render(React.createElement(CompanyPeersPage));

    expect(screen.getByText(/Strict official mode disables peer valuation charts/i)).toBeTruthy();
    expect(screen.getByText("peer-dashboard-ACME")).toBeTruthy();
  });
});

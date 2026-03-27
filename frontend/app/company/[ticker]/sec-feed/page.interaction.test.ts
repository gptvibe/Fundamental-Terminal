// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CompanySecFeedPage from "@/app/company/[ticker]/sec-feed/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: "2026-03-10" },
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

vi.mock("@/lib/api", () => ({
  getCompanyActivityOverview: vi.fn(async () => ({
    company: { ticker: "ACME", cik: "0000001", name: "Acme Corp", sector: "Tech", market_sector: null, market_industry: null, last_checked: null, last_checked_financials: null, last_checked_prices: null, last_checked_insiders: null, last_checked_institutional: null, last_checked_filings: null, cache_state: "fresh" },
    entries: [
      {
        id: "entry-144",
        date: "2026-03-11",
        type: "form144",
        badge: "144",
        title: "Jane Doe filed Form 144 planned sale",
        detail: "Planned sale 2026-03-18 | Jane Doe | 12,500 shares | $2,500,000",
        href: null,
      },
      {
        id: "entry-new",
        date: "2026-03-10",
        type: "event",
        badge: "Earnings",
        title: "Newest Event",
        detail: "Most recent timeline entry",
        href: null,
      },
      {
        id: "entry-old",
        date: "2026-03-01",
        type: "filing",
        badge: "10-K",
        title: "Older Event",
        detail: "Older timeline entry",
        href: null,
      },
    ],
    alerts: [
      {
        id: "alert-high",
        level: "high",
        title: "High Priority Alert",
        detail: "High severity signal",
        source: "capital-markets",
        date: "2026-03-10",
        href: null,
      },
      {
        id: "alert-medium",
        level: "medium",
        title: "Medium Priority Alert",
        detail: "Medium severity signal",
        source: "insider-trades",
        date: "2026-03-09",
        href: null,
      },
      {
        id: "alert-low",
        level: "low",
        title: "Low Priority Alert",
        detail: "Low severity signal",
        source: "ownership",
        date: "2026-03-08",
        href: null,
      },
    ],
    summary: { total: 3, high: 1, medium: 1, low: 1 },
    provenance: [
      {
        source_id: "ft_activity_overview",
        source_tier: "derived_from_official",
        display_label: "Fundamental Terminal Activity Overview",
        url: "https://github.com/gptvibe/Fundamental-Terminal",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Unified activity feed assembled from official SEC disclosures and official macro status signals.",
        role: "derived",
        as_of: "2026-03-11",
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
        as_of: "2026-03-11",
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
    ],
    as_of: "2026-03-11",
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

describe("CompanySecFeedPage interactions", () => {
  it("filters alerts by severity and preserves feed entry order", async () => {
    const user = userEvent.setup();
    render(React.createElement(CompanySecFeedPage));

    await waitFor(() => {
      expect(screen.getByText("High Priority Alert")).toBeTruthy();
    });

    expect(screen.getByText("planned-sale")).toBeTruthy();
    expect(screen.getByText("Jane Doe filed Form 144 planned sale")).toBeTruthy();
    expect(screen.getByText("SEC EDGAR Filing Archive")).toBeTruthy();

    const newest = screen.getByText("Newest Event");
    const older = screen.getByText("Older Event");
    expect(Boolean(newest.compareDocumentPosition(older) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true);

    await user.click(screen.getByRole("button", { name: "High (1)" }));
    expect(screen.getByText("High Priority Alert")).toBeTruthy();
    expect(screen.queryByText("Medium Priority Alert")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Medium (1)" }));
    expect(screen.getByText("Medium Priority Alert")).toBeTruthy();
    expect(screen.queryByText("High Priority Alert")).toBeNull();
  });
});

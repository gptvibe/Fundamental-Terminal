// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PeerComparisonDashboard } from "@/components/peers/peer-comparison-dashboard";
import { getCompanyPeers } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCompanyPeers: vi.fn(),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ children }: { children?: React.ReactNode }) => React.createElement("section", null, children),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("recharts", () => {
  function Wrapper({ children }: { children?: React.ReactNode }) {
    return React.createElement("div", null, children);
  }

  return {
    Bar: Wrapper,
    BarChart: Wrapper,
    CartesianGrid: Wrapper,
    Cell: Wrapper,
    Legend: Wrapper,
    Line: Wrapper,
    LineChart: Wrapper,
    PolarAngleAxis: Wrapper,
    PolarGrid: Wrapper,
    PolarRadiusAxis: Wrapper,
    Radar: Wrapper,
    RadarChart: Wrapper,
    ResponsiveContainer: Wrapper,
    Tooltip: Wrapper,
    XAxis: Wrapper,
    YAxis: Wrapper,
  };
});

function buildResponse(selectedTickers: string[]) {
  return {
    company: {
      ticker: "AAPL",
      cik: "0000320193",
      name: "Apple Inc.",
      sector: "Technology",
      market_sector: "Technology",
      market_industry: "Consumer Electronics",
      last_checked: "2026-03-22T00:00:00Z",
      cache_state: "fresh",
    },
    peer_basis: "Cached peer universe",
    available_companies: [
      { ticker: "AAPL", name: "Apple Inc.", sector: "Technology", market_sector: "Technology", market_industry: "Consumer Electronics", last_checked: null, cache_state: "fresh", is_focus: true },
      { ticker: "MSFT", name: "Microsoft", sector: "Technology", market_sector: "Technology", market_industry: "Software", last_checked: null, cache_state: "fresh", is_focus: false },
      { ticker: "GOOG", name: "Alphabet", sector: "Technology", market_sector: "Technology", market_industry: "Internet", last_checked: null, cache_state: "fresh", is_focus: false },
    ],
    selected_tickers: selectedTickers,
    peers: [
      {
        ticker: "AAPL",
        name: "Apple Inc.",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Consumer Electronics",
        is_focus: true,
        cache_state: "fresh",
        last_checked: "2026-03-22T00:00:00Z",
        period_end: "2025-12-31",
        price_date: "2026-03-21",
        latest_price: 190,
        pe: 28,
        ev_to_ebit: 20,
        price_to_free_cash_flow: 30,
        roe: 0.24,
        revenue_growth: 0.08,
        piotroski_score: 8,
        altman_z_score: 4,
        revenue_history: [],
      },
      {
        ticker: "MSFT",
        name: "Microsoft",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        is_focus: false,
        cache_state: "fresh",
        last_checked: "2026-03-22T00:00:00Z",
        period_end: "2025-12-31",
        price_date: "2026-03-21",
        latest_price: 420,
        pe: 34,
        ev_to_ebit: 24,
        price_to_free_cash_flow: 38,
        roe: 0.31,
        revenue_growth: 0.12,
        piotroski_score: 8,
        altman_z_score: 5,
        revenue_history: [],
      },
      {
        ticker: "GOOG",
        name: "Alphabet",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Internet",
        is_focus: false,
        cache_state: "fresh",
        last_checked: "2026-03-22T00:00:00Z",
        period_end: "2025-12-31",
        price_date: "2026-03-21",
        latest_price: 160,
        pe: 25,
        ev_to_ebit: 18,
        price_to_free_cash_flow: 22,
        roe: 0.2,
        revenue_growth: 0.11,
        piotroski_score: 7,
        altman_z_score: 4,
        revenue_history: [],
      },
    ],
    notes: {
      ev_to_ebit: "Proxy metric",
      price_to_free_cash_flow: "Uses cached free cash flow",
      piotroski: "Higher is stronger",
    },
    provenance: [
      {
        source_id: "ft_peer_comparison",
        source_tier: "derived_from_official",
        display_label: "Fundamental Terminal Peer Comparison",
        url: "https://github.com/gptvibe/Fundamental-Terminal",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Peer comparison metrics derived from cached public-company filings, model runs, and labeled price inputs.",
        role: "derived",
        as_of: "2025-12-31",
        last_refreshed_at: "2026-03-22T00:00:00Z",
      },
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
        last_refreshed_at: "2026-03-22T00:00:00Z",
      },
    ],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-22T00:00:00Z",
    source_mix: {
      source_ids: ["ft_peer_comparison", "sec_companyfacts", "yahoo_finance"],
      source_tiers: ["commercial_fallback", "derived_from_official", "official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: ["yahoo_finance"],
      official_only: false,
    },
    confidence_flags: ["commercial_fallback_present"],
    refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
  };
}

describe("PeerComparisonDashboard", () => {
  it("loads default peers, supports explicit selection, and resets to focus defaults", async () => {
    const getCompanyPeersMock = vi.mocked(getCompanyPeers);
    getCompanyPeersMock.mockImplementation(async (_ticker: string, peers?: string[]) => buildResponse(peers?.length ? peers : ["MSFT"]));

    render(React.createElement(PeerComparisonDashboard, { ticker: "AAPL", reloadKey: "key-1" }));

    await waitFor(() => {
      expect(getCompanyPeersMock).toHaveBeenCalledWith("AAPL", undefined);
    });

    expect(screen.getByRole("button", { name: "Collapse compare tray" }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Selected 1/4")).toBeTruthy();
    expect(screen.getByText("SEC Company Facts (XBRL)")).toBeTruthy();

    fireEvent.click(screen.getByTitle("GOOG — Alphabet"));

    await waitFor(() => {
      expect(getCompanyPeersMock).toHaveBeenCalledWith("AAPL", ["MSFT", "GOOG"]);
    });

    fireEvent.click(screen.getByRole("button", { name: "Reset to Focus" }));

    await waitFor(() => {
      expect(getCompanyPeersMock).toHaveBeenCalledWith("AAPL", []);
    });

    fireEvent.click(screen.getByRole("button", { name: "Collapse compare tray" }));
    expect(screen.getByRole("button", { name: "Open compare tray" }).getAttribute("aria-expanded")).toBe("false");
  });
});

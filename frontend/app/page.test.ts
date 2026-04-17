// @vitest-environment jsdom

import * as React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";
import { RECENT_COMPANIES_STORAGE_KEY } from "@/lib/recent-companies";

const HOME_SEARCH_DEBOUNCE_MS = 150;

const push = vi.fn();
const mockUseLocalUserData = vi.fn();
const mockUseJobStream = vi.fn();
const getGlobalMarketContext = vi.fn();
const getSourceRegistry = vi.fn();
const getWatchlistSummary = vi.fn();
const resolveCompanyIdentifier = vi.fn();
const searchCompanies = vi.fn();
const showAppToast = vi.fn();
const readStoredActiveJob = vi.fn();
const clearStoredActiveJob = vi.fn();
const syncMetadata = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-local-user-data", () => ({
  useLocalUserData: () => mockUseLocalUserData(),
}));

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: (...args: unknown[]) => mockUseJobStream(...args),
}));

vi.mock("@/lib/api", () => ({
  getGlobalMarketContext: (...args: unknown[]) => getGlobalMarketContext(...args),
  getSourceRegistry: (...args: unknown[]) => getSourceRegistry(...args),
  getWatchlistSummary: (...args: unknown[]) => getWatchlistSummary(...args),
  resolveCompanyIdentifier: (...args: unknown[]) => resolveCompanyIdentifier(...args),
  searchCompanies: (...args: unknown[]) => searchCompanies(...args),
}));

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

vi.mock("@/lib/active-job", () => ({
  ACTIVE_JOB_EVENT: "ft:active-job",
  readStoredActiveJob: () => readStoredActiveJob(),
  clearStoredActiveJob: (...args: unknown[]) => clearStoredActiveJob(...args),
}));

const refreshState = { triggered: false, reason: "fresh", ticker: null, job_id: null } as const;

beforeAll(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

beforeEach(() => {
  push.mockReset();
  mockUseLocalUserData.mockReset();
  mockUseJobStream.mockReset();
  getGlobalMarketContext.mockReset();
  getSourceRegistry.mockReset();
  getWatchlistSummary.mockReset();
  resolveCompanyIdentifier.mockReset();
  searchCompanies.mockReset();
  showAppToast.mockReset();
  readStoredActiveJob.mockReset();
  clearStoredActiveJob.mockReset();
  syncMetadata.mockReset();

  mockUseLocalUserData.mockReturnValue({
    savedCompanies: [],
    watchlist: [],
    watchlistCount: 0,
    noteCount: 0,
    savedCompanyCount: 0,
    syncMetadata,
  });
  mockUseJobStream.mockReturnValue({
    consoleEntries: [],
    connectionState: "idle",
  });
  getGlobalMarketContext.mockResolvedValue(buildMacroContext());
  getSourceRegistry.mockResolvedValue(buildSourceRegistry());
  getWatchlistSummary.mockResolvedValue({ tickers: [], companies: [] });
  resolveCompanyIdentifier.mockResolvedValue({ resolved: false, ticker: null, name: null, error: "not_found" });
  searchCompanies.mockResolvedValue({ query: "", results: [], refresh: refreshState });
  readStoredActiveJob.mockReturnValue(null);
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("HomePage", () => {
  it("renders the search-first terminal with recent, saved, change, and macro context", async () => {
    window.localStorage.setItem(
      RECENT_COMPANIES_STORAGE_KEY,
      JSON.stringify([
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          openedAt: "2026-03-21T10:00:00Z",
        },
      ])
    );
    mockUseLocalUserData.mockReturnValue({
      savedCompanies: [
        {
          ticker: "MSFT",
          name: "Microsoft",
          sector: "Technology",
          savedAt: "2026-03-20T09:00:00Z",
          note: "Track Azure bookings and capital return mix.",
          noteUpdatedAt: "2026-03-22T12:00:00Z",
          isInWatchlist: true,
          hasNote: true,
          activityAt: "2026-03-22T12:00:00Z",
        },
      ],
      watchlist: [{ ticker: "MSFT" }, { ticker: "NVDA" }],
      watchlistCount: 2,
      noteCount: 1,
      savedCompanyCount: 1,
      syncMetadata,
    });
    mockUseJobStream.mockReturnValue({
      consoleEntries: [
        {
          id: "entry-1",
          ticker: "MSFT",
          timestamp: "2026-03-22T12:01:00Z",
          stage: "refresh",
          message: "Refreshed MSFT filings",
          level: "success",
          status: "completed",
          source: "backend",
        },
      ],
      connectionState: "open",
    });
    readStoredActiveJob.mockReturnValue({
      jobId: "job-1",
      ticker: "MSFT",
      storedAt: "2026-03-22T12:00:30Z",
    });
    getWatchlistSummary.mockResolvedValue({
      tickers: ["MSFT", "NVDA"],
      companies: [
        {
          ticker: "MSFT",
          name: "Microsoft",
          sector: "Technology",
          cik: "0000789019",
          last_checked: "2026-03-22T12:00:00Z",
          refresh: refreshState,
          alert_summary: { high: 1, medium: 0, low: 0, total: 1 },
          latest_alert: {
            id: "alert-1",
            level: "high",
            title: "Late filer notice",
            source: "filings",
            date: "2026-03-22",
            href: null,
          },
          latest_activity: {
            id: "activity-1",
            type: "filing",
            badge: "8-K",
            title: "8-K filed",
            date: "2026-03-21",
            href: null,
          },
          coverage: { financial_periods: 8, price_points: 250 },
          fair_value_gap: null,
          roic: null,
          shareholder_yield: null,
          implied_growth: null,
          valuation_band_percentile: null,
          balance_sheet_risk: null,
        },
      ],
    });

    render(React.createElement(HomePage));

    await waitFor(() => {
      expect(screen.getByText("Recent Companies")).toBeTruthy();
    });

    expect(screen.getByText(/Start with a company, then move into evidence/i)).toBeTruthy();
    expect(screen.getByText("Apple Inc.")).toBeTruthy();
    expect(screen.getByText("Saved & Watchlist")).toBeTruthy();
    expect(screen.getByText(/Track Azure bookings and capital return mix/)).toBeTruthy();
    expect(screen.getByText("Recent Changes")).toBeTruthy();
    expect(screen.getByText("Late filer notice")).toBeTruthy();
    expect(screen.getByText("Curve still looks restrictive")).toBeTruthy();
    expect(screen.getByText("Data Health")).toBeTruthy();
    expect(screen.getByText("Companies cached")).toBeTruthy();
    expect(getWatchlistSummary).toHaveBeenCalledWith(["MSFT", "NVDA"]);
  });

  it("routes to a searched company and records the launch locally", async () => {
    searchCompanies.mockResolvedValue({
      query: "MSFT",
      results: [buildCompanyPayload({ ticker: "MSFT", name: "Microsoft Corp." })],
      refresh: refreshState,
    });

    render(React.createElement(HomePage));

    fireEvent.change(screen.getByLabelText(/search by ticker, company, or cik/i), {
      target: { value: "msft" },
    });

    await waitFor(() => {
      expect(searchCompanies).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(screen.getAllByText("Microsoft Corp.").length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByLabelText(/search by ticker, company, or cik/i);
    const searchForm = searchInput.closest("form");
    expect(searchForm).toBeTruthy();
    fireEvent.submit(searchForm as HTMLFormElement);

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/company/MSFT");
    });

    expect(searchCompanies).toHaveBeenCalledTimes(1);
    expect(resolveCompanyIdentifier).not.toHaveBeenCalled();

    const recentCompanies = JSON.parse(window.localStorage.getItem(RECENT_COMPANIES_STORAGE_KEY) ?? "[]");
    expect(recentCompanies[0]).toMatchObject({ ticker: "MSFT", name: "Microsoft Corp." });
    expect(syncMetadata).toHaveBeenCalledWith({ ticker: "MSFT", name: "Microsoft Corp.", sector: "Technology" });
  });

  it("runs an immediate autocomplete lookup before SEC resolve when the user submits before debounce completes", async () => {
    vi.useFakeTimers();
    searchCompanies.mockResolvedValue({
      query: "MSFT",
      results: [buildCompanyPayload({ ticker: "MSFT", name: "Microsoft Corp." })],
      refresh: refreshState,
    });

    render(React.createElement(HomePage));

    const searchInput = screen.getByLabelText(/search by ticker, company, or cik/i);
    fireEvent.change(searchInput, {
      target: { value: "msft" },
    });

    const searchForm = searchInput.closest("form");
    expect(searchForm).toBeTruthy();

    await act(async () => {
      fireEvent.submit(searchForm as HTMLFormElement);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(searchCompanies).toHaveBeenCalledTimes(1);
    expect(resolveCompanyIdentifier).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/company/MSFT");
  });

  it("does not auto-select a fuzzy autocomplete result on fast submit", async () => {
    vi.useFakeTimers();
    searchCompanies.mockResolvedValue({
      query: "NET",
      results: [buildCompanyPayload({ ticker: "NFLX", name: "NETFLIX INC", cik: "0001065280" })],
      refresh: { triggered: false, reason: "none", ticker: "NET", job_id: null },
    });
    resolveCompanyIdentifier.mockResolvedValue({ resolved: true, ticker: "NET", name: "Cloudflare, Inc.", error: null });

    render(React.createElement(HomePage));

    const searchInput = screen.getByLabelText(/search by ticker, company, or cik/i);
    fireEvent.change(searchInput, {
      target: { value: "NET" },
    });

    const searchForm = searchInput.closest("form");
    expect(searchForm).toBeTruthy();

    await act(async () => {
      fireEvent.submit(searchForm as HTMLFormElement);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(searchCompanies).toHaveBeenCalledTimes(1);
    expect(resolveCompanyIdentifier).toHaveBeenCalledWith("NET");
    expect(push).toHaveBeenCalledWith("/company/NET");
  });

  it("aborts stale autocomplete requests without letting older results overwrite newer ones", async () => {
    vi.useFakeTimers();
    const requests = new Map<
      string,
      { signal: AbortSignal | undefined; resolve: (value: { query: string; results: ReturnType<typeof buildCompanyPayload>[]; refresh: typeof refreshState }) => void }
    >();
    searchCompanies.mockImplementation((query: string, options?: { signal?: AbortSignal }) => {
      return new Promise((resolve) => {
        requests.set(query, { signal: options?.signal, resolve });
      });
    });

    render(React.createElement(HomePage));

    const searchInput = screen.getByLabelText(/search by ticker, company, or cik/i);

    fireEvent.change(searchInput, {
      target: { value: "m" },
    });

    await act(async () => {
      vi.advanceTimersByTime(HOME_SEARCH_DEBOUNCE_MS);
      await Promise.resolve();
    });

    const firstRequest = requests.get("m");
    expect(firstRequest?.signal?.aborted).toBe(false);

    fireEvent.change(searchInput, {
      target: { value: "ms" },
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(firstRequest?.signal?.aborted).toBe(true);

    await act(async () => {
      vi.advanceTimersByTime(HOME_SEARCH_DEBOUNCE_MS);
      await Promise.resolve();
    });

    const secondRequest = requests.get("ms");
    expect(secondRequest?.signal?.aborted).toBe(false);

    await act(async () => {
      secondRequest?.resolve({
        query: "ms",
        results: [buildCompanyPayload({ ticker: "MSFT", name: "Microsoft Corp." })],
        refresh: refreshState,
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.getAllByText("Microsoft Corp.").length).toBeGreaterThan(0);

    await act(async () => {
      firstRequest?.resolve({
        query: "m",
        results: [buildCompanyPayload({ ticker: "META", name: "Meta Platforms" })],
        refresh: refreshState,
      });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(screen.queryByText("Meta Platforms")).toBeNull();
    expect(screen.getAllByText("Microsoft Corp.").length).toBeGreaterThan(0);
  });
});

function buildCompanyPayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    ticker: "AAPL",
    cik: "0000320193",
    name: "Apple Inc.",
    sector: "Technology",
    market_sector: "Technology",
    market_industry: "Consumer Electronics",
    regulated_entity: null,
    strict_official_mode: true,
    last_checked: null,
    last_checked_financials: null,
    last_checked_prices: null,
    last_checked_insiders: null,
    last_checked_institutional: null,
    last_checked_filings: null,
    earnings_last_checked: null,
    cache_state: "fresh",
    ...overrides,
  };
}

function buildMacroContext() {
  return {
    provenance: [],
    as_of: "2026-03-22",
    last_refreshed_at: "2026-03-22T12:00:00Z",
    source_mix: {
      source_ids: ["treasury", "fred"],
      source_tiers: ["official_treasury_or_fed", "official_statistical"],
      primary_source_ids: ["treasury", "fred"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    company: null,
    status: "ready",
    curve_points: [
      { tenor: "10y", rate: 0.043, observation_date: "2026-03-22" },
      { tenor: "2y", rate: 0.04, observation_date: "2026-03-22" },
      { tenor: "3m", rate: 0.047, observation_date: "2026-03-22" },
    ],
    slope_2s10s: {
      label: "2s10s",
      value: 0.003,
      short_tenor: "2y",
      long_tenor: "10y",
      observation_date: "2026-03-22",
    },
    slope_3m10y: {
      label: "3m10y",
      value: -0.004,
      short_tenor: "3m",
      long_tenor: "10y",
      observation_date: "2026-03-22",
    },
    fred_series: [
      {
        series_id: "BAA10Y",
        label: "BAA spread",
        category: "credit",
        units: "ratio",
        value: 0.021,
        observation_date: "2026-03-22",
        state: "fresh",
      },
      {
        series_id: "UNRATE",
        label: "Unemployment",
        category: "labor",
        units: "ratio",
        value: 0.041,
        observation_date: "2026-03-22",
        state: "fresh",
      },
    ],
    provenance_details: null,
    fetched_at: "2026-03-22T12:00:00Z",
    refresh: refreshState,
  };
}

function buildSourceRegistry() {
  return {
    strict_official_mode: false,
    generated_at: "2026-03-22T12:00:00Z",
    sources: [
      {
        source_id: "sec_companyfacts",
        source_tier: "official_regulator",
        display_label: "SEC Company Facts (XBRL)",
        url: "https://data.sec.gov/api/xbrl/companyfacts/",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
        strict_official_mode_state: "available",
        strict_official_mode_note: "Strict official mode is disabled, so this source is currently available.",
      },
    ],
    health: {
      total_companies_cached: 412,
      average_data_age_seconds: 5400,
      recent_error_window_hours: 72,
      sources_with_recent_errors: [
        {
          source_id: "yahoo_finance",
          source_tier: "commercial_fallback",
          display_label: "Yahoo Finance",
          affected_dataset_ids: ["prices"],
          affected_company_count: 3,
          failure_count: 5,
          last_error: "timeout",
          last_error_at: "2026-03-22T11:00:00Z",
        },
      ],
    },
  };
}

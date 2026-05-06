// @vitest-environment jsdom

import * as React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WatchlistPage from "@/app/watchlist/page";

const push = vi.fn();
const mockUseLocalUserData = vi.fn();
const mockUseJobStreams = vi.fn();
const getWatchlistCalendar = vi.fn();
const getWatchlistSummary = vi.fn();
const invalidateApiReadCache = vi.fn();
const refreshCompany = vi.fn();
const showAppToast = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-local-user-data", () => ({
  useLocalUserData: () => mockUseLocalUserData(),
}));

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStreams: (...args: unknown[]) => mockUseJobStreams(...args),
}));

vi.mock("@/lib/api", () => ({
  getWatchlistCalendar: (...args: unknown[]) => getWatchlistCalendar(...args),
  getWatchlistSummary: (...args: unknown[]) => getWatchlistSummary(...args),
  invalidateApiReadCache: (...args: unknown[]) => invalidateApiReadCache(...args),
  refreshCompany: (...args: unknown[]) => refreshCompany(...args),
}));

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

function createHookResult(overrides: Record<string, unknown> = {}) {
  return {
    watchlist: [],
    notesByTicker: {},
    monitoringByTicker: {},
    savedWatchlistViews: [],
    isSaved: vi.fn(() => false),
    toggleWatchlist: vi.fn(() => true),
    saveMonitoringEntry: vi.fn(),
    saveWatchlistView: vi.fn(),
    deleteWatchlistView: vi.fn(),
    ...overrides,
  };
}

function createSummaryItem(overrides: Record<string, unknown> = {}) {
  return {
    ticker: "AAPL",
    name: "Apple Inc.",
    sector: "Technology",
    cik: "0000320193",
    last_checked: "2026-04-08T00:00:00Z",
    refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
    alert_summary: { high: 1, medium: 0, low: 0, total: 1 },
    latest_alert: { id: "alert-1", level: "high", title: "Margin warning", source: "capital-markets", date: "2026-04-07", href: null },
    latest_activity: { id: "activity-1", type: "event", badge: "8-K", title: "Filed earnings update", date: "2026-04-07", href: null },
    coverage: { financial_periods: 8, price_points: 250 },
    fair_value_gap: 0.22,
    roic: 0.18,
    shareholder_yield: 0.03,
    implied_growth: 0.07,
    fair_value_gap_status: "fresh",
    implied_growth_status: "fresh",
    valuation_band_percentile: 0.25,
    balance_sheet_risk: 1.4,
    market_context_status: { label: "Context ready", observation_date: "2026-04-08" },
    material_change: {
      status: "ready",
      headline: "2 high-signal changes since the last filing",
      detail: "Management flagged softer iPhone demand and a slower China recovery.",
      current_filing_type: "10-Q",
      current_period_end: "2026-03-31",
      previous_period_end: "2025-12-31",
      high_signal_change_count: 2,
      new_risk_indicator_count: 1,
      share_count_change_count: 0,
      capital_structure_change_count: 0,
      comment_letter_count: 0,
      highlights: [],
    },
    ...overrides,
  };
}

describe("WatchlistPage", () => {
  beforeEach(() => {
    push.mockReset();
    mockUseLocalUserData.mockReset();
    mockUseJobStreams.mockReset();
    getWatchlistCalendar.mockReset();
    getWatchlistSummary.mockReset();
    invalidateApiReadCache.mockReset();
    refreshCompany.mockReset();
    showAppToast.mockReset();
    mockUseJobStreams.mockReturnValue({ lastTerminalEvent: null });
    getWatchlistCalendar.mockResolvedValue({
      tickers: [],
      window_start: "2026-04-08",
      window_end: "2026-07-07",
      events: [],
    });
  });

  afterEach(() => {
    cleanup();
  });

  it("renders polished empty state when watchlist has no tickers", async () => {
    mockUseLocalUserData.mockReturnValue(createHookResult());

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Watchlist is empty")).toBeTruthy();
    });
    expect(screen.getByText("Add your first company to start tracking fundamentals.")).toBeTruthy();
    expect(getWatchlistSummary).not.toHaveBeenCalled();
    expect(getWatchlistCalendar).not.toHaveBeenCalled();
  });

  it("renders investor table with required columns", async () => {
    mockUseLocalUserData.mockReturnValue(createHookResult({
      watchlist: [{ ticker: "AAPL" }],
    }));
    getWatchlistSummary.mockResolvedValue({ tickers: ["AAPL"], companies: [createSummaryItem()] });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    expect(screen.getByRole("columnheader", { name: "Ticker" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Company" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Price" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Revenue growth" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Margin" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "FCF" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Leverage/debt signal" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Last filing" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Alert count" })).toBeTruthy();
    expect(screen.getByText("2 high-signal changes since the last filing")).toBeTruthy();
  });

  it("filters by selected filter in toolbar", async () => {
    mockUseLocalUserData.mockReturnValue(createHookResult({
      watchlist: [{ ticker: "AAPL" }, { ticker: "MSFT" }],
      monitoringByTicker: {
        AAPL: {
          ticker: "AAPL",
          triageState: "reviewing",
          profileKey: "deep-dive",
          rationale: "Due today",
          lastReviewedAt: null,
          nextReviewAt: "2026-04-08",
          snoozedUntil: null,
          holdUntil: null,
          updatedAt: "2026-04-08T00:00:00Z",
        },
        MSFT: {
          ticker: "MSFT",
          triageState: "monitoring",
          profileKey: "quality-compounder",
          rationale: "Parked",
          lastReviewedAt: null,
          nextReviewAt: "2099-12-31",
          snoozedUntil: null,
          holdUntil: "2099-12-31",
          updatedAt: "2026-04-08T00:00:00Z",
        },
      },
    }));

    getWatchlistSummary.mockResolvedValue({
      tickers: ["AAPL", "MSFT"],
      companies: [
        createSummaryItem(),
        createSummaryItem({
          ticker: "MSFT",
          name: "Microsoft",
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
        }),
      ],
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
      expect(screen.getByText("Microsoft")).toBeTruthy();
    });

    fireEvent.change(screen.getByLabelText("Filter watchlist"), { target: { value: "review-due" } });
    expect(screen.getByText("Apple Inc.")).toBeTruthy();
    expect(screen.queryByText("Microsoft")).toBeNull();
  });

  it("adds ticker from toolbar", async () => {
    const toggleWatchlist = vi.fn(() => true);
    mockUseLocalUserData.mockReturnValue(createHookResult({
      watchlist: [],
      isSaved: vi.fn(() => false),
      toggleWatchlist,
    }));

    render(React.createElement(WatchlistPage));

    fireEvent.change(screen.getByLabelText("Add ticker"), { target: { value: "msft" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(toggleWatchlist).toHaveBeenCalledWith({ ticker: "MSFT", name: null, sector: null });
  });

  it("reloads queued refresh jobs after an SSE terminal event", async () => {
    mockUseLocalUserData.mockReturnValue(createHookResult({ watchlist: [{ ticker: "AAPL" }] }));

    getWatchlistSummary
      .mockResolvedValueOnce({ tickers: ["AAPL"], companies: [createSummaryItem()] })
      .mockResolvedValueOnce({
        tickers: ["AAPL"],
        companies: [createSummaryItem({ last_checked: "2026-04-08T01:00:00Z", refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null } })],
      });
    refreshCompany.mockResolvedValue({ status: "queued", ticker: "AAPL", force: false, refresh: { triggered: true, reason: "manual", ticker: "AAPL", job_id: "job-1" } });

    const { rerender } = render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(refreshCompany).toHaveBeenCalledWith("AAPL");
    });

    mockUseJobStreams.mockReturnValue({
      lastTerminalEvent: {
        job_id: "job-1",
        trace_id: "trace-1",
        sequence: 3,
        timestamp: "2026-04-08T01:00:00Z",
        ticker: "AAPL",
        kind: "refresh",
        stage: "complete",
        message: "Refresh completed",
        status: "completed",
        level: "success",
      },
    });

    rerender(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(getWatchlistSummary).toHaveBeenCalledTimes(2);
    });
    expect(invalidateApiReadCache).toHaveBeenCalledWith("/watchlist/calendar");
  });
});

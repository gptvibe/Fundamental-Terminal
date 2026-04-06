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
      window_start: "2026-04-04",
      window_end: "2026-07-03",
      events: [],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  it("renders empty state when no local watchlist tickers exist", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [],
      notesByTicker: {},
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("No companies saved yet")).toBeTruthy();
    });
    expect(getWatchlistSummary).not.toHaveBeenCalled();
    expect(getWatchlistCalendar).not.toHaveBeenCalled();
  });

  it("renders loaded rows with merged local notes", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [{ ticker: "AAPL" }],
      notesByTicker: {
        AAPL: {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          note: "Track gross margin trend and services mix.",
          updatedAt: "2026-03-22T00:00:00Z",
        },
      },
    });
    getWatchlistSummary.mockResolvedValue({
      tickers: ["AAPL"],
      companies: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          cik: "0000320193",
          last_checked: "2026-03-22T00:00:00Z",
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          alert_summary: { high: 1, medium: 0, low: 0, total: 1 },
          latest_alert: { id: "a1", level: "high", title: "Late filer notice", source: "capital-markets", date: "2026-03-20", href: null },
          latest_activity: { id: "e1", type: "event", badge: "8-K", title: "Earnings update", date: "2026-03-20", href: null },
          coverage: { financial_periods: 8, price_points: 250 },
        },
      ],
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    expect(screen.getByText(/Track gross margin trend and services mix/)).toBeTruthy();
    expect(screen.getByLabelText(/Alert summary for AAPL/i)).toBeTruthy();
    expect(screen.getByText(/Late filer notice/)).toBeTruthy();
    expect(getWatchlistCalendar).toHaveBeenCalledWith(["AAPL"]);
  });

  it("renders the events calendar below the company table", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [{ ticker: "AAPL" }],
      notesByTicker: {},
    });
    getWatchlistSummary.mockResolvedValue({
      tickers: ["AAPL"],
      companies: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          cik: "1",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
        },
      ],
    });
    getWatchlistCalendar.mockResolvedValue({
      tickers: ["AAPL"],
      window_start: "2026-04-04",
      window_end: "2026-07-03",
      events: [
        {
          id: "expected-aapl",
          date: "2026-05-10",
          event_type: "expected_filing",
          source: "historical_cadence",
          ticker: "AAPL",
          company_name: "Apple Inc.",
          title: "Expected 10-Q filing",
          form: "10-Q",
          detail: "Median 40-day lag after the 2026-03-31 period end.",
          href: null,
          period_end: "2026-03-31",
        },
        {
          id: "13f-2026-03-31",
          date: "2026-05-15",
          event_type: "institutional_deadline",
          source: "fixed_calendar",
          ticker: null,
          company_name: null,
          title: "13F institutional reporting deadline",
          form: "13F-HR",
          detail: "Managers disclose holdings for the quarter ended 2026-03-31.",
          href: null,
          period_end: "2026-03-31",
        },
      ],
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Events Calendar")).toBeTruthy();
    });

    expect(screen.getByText("Expected 10-Q filing")).toBeTruthy();
    expect(screen.getByText("13F institutional reporting deadline")).toBeTruthy();
  });

  it("applies filters for attention, stale, and no-note", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [{ ticker: "AAPL" }, { ticker: "MSFT" }, { ticker: "TSLA" }],
      notesByTicker: {
        AAPL: {
          ticker: "AAPL",
          name: null,
          sector: null,
          note: "Keep",
          updatedAt: "2026-03-22T00:00:00Z",
        },
      },
    });
    getWatchlistSummary.mockResolvedValue({
      tickers: ["AAPL", "MSFT", "TSLA"],
      companies: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          cik: "1",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          alert_summary: { high: 1, medium: 0, low: 0, total: 1 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
        },
        {
          ticker: "MSFT",
          name: "Microsoft",
          sector: "Technology",
          cik: "2",
          last_checked: null,
          refresh: { triggered: false, reason: "stale", ticker: "MSFT", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
        },
        {
          ticker: "TSLA",
          name: "Tesla",
          sector: "Auto",
          cik: "3",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "TSLA", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
        },
      ],
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Needs attention" }));
    expect(screen.getByText("Apple Inc.")).toBeTruthy();
    expect(screen.queryByText("Microsoft")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Stale" }));
    expect(screen.getByText("Microsoft")).toBeTruthy();
    expect(screen.queryByText("Apple Inc.")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "No note" }));
    expect(screen.getByText("Microsoft")).toBeTruthy();
    expect(screen.getByText("Tesla")).toBeTruthy();
    expect(screen.queryByText("Apple Inc.")).toBeNull();
  });

  it("queues refresh action for a single company", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [{ ticker: "AAPL" }],
      notesByTicker: {},
    });
    getWatchlistSummary.mockResolvedValueOnce({
      tickers: ["AAPL"],
      companies: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          cik: "1",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
        },
      ],
    });
    refreshCompany.mockResolvedValue({ status: "queued", ticker: "AAPL", force: false, refresh: { triggered: true, reason: "manual", ticker: "AAPL", job_id: "job-1" } });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(refreshCompany).toHaveBeenCalledWith("AAPL");
    });
    expect(getWatchlistSummary).toHaveBeenCalledTimes(1);
  });

  it("supports valuation-oriented filters and sort ordering", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [{ ticker: "AAA" }, { ticker: "BBB" }, { ticker: "CCC" }],
      notesByTicker: {},
    });
    getWatchlistSummary.mockResolvedValue({
      tickers: ["AAA", "BBB", "CCC"],
      companies: [
        {
          ticker: "AAA",
          name: "Alpha",
          sector: "Tech",
          cik: "1",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "AAA", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
          fair_value_gap: 0.25,
          roic: 0.16,
          shareholder_yield: 0.03,
          implied_growth: 0.07,
          valuation_band_percentile: 0.2,
          balance_sheet_risk: 1.2,
        },
        {
          ticker: "BBB",
          name: "Beta",
          sector: "Tech",
          cik: "2",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "BBB", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
          fair_value_gap: -0.1,
          roic: 0.08,
          shareholder_yield: 0.0,
          implied_growth: 0.12,
          valuation_band_percentile: 0.8,
          balance_sheet_risk: 4.5,
        },
        {
          ticker: "CCC",
          name: "Gamma",
          sector: "Tech",
          cik: "3",
          last_checked: null,
          refresh: { triggered: false, reason: "fresh", ticker: "CCC", job_id: null },
          alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
          latest_alert: null,
          latest_activity: null,
          coverage: { financial_periods: 1, price_points: 1 },
          fair_value_gap: 0.05,
          roic: 0.2,
          shareholder_yield: 0.01,
          implied_growth: 0.05,
          valuation_band_percentile: 0.4,
          balance_sheet_risk: 2.1,
        },
      ],
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Alpha")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Undervalued" }));
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.getByText("Gamma")).toBeTruthy();
    expect(screen.queryByText("Beta")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Balance risk" }));
    expect(screen.getByText("Beta")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByLabelText("Sort watchlist"), { target: { value: "quality" } });
    const tickerCards = screen.getAllByText(/AAA|BBB|CCC/).map((node) => node.textContent);
    expect(tickerCards[0]).toContain("CCC");
  });

  it("reloads queued refresh jobs after an SSE terminal event", async () => {
    mockUseLocalUserData.mockReturnValue({
      watchlist: [{ ticker: "AAPL" }],
      notesByTicker: {},
    });

    getWatchlistSummary
      .mockResolvedValueOnce({
        tickers: ["AAPL"],
        companies: [
          {
            ticker: "AAPL",
            name: "Apple Inc.",
            sector: "Technology",
            cik: "1",
            last_checked: null,
            refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
            alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
            latest_alert: null,
            latest_activity: null,
            coverage: { financial_periods: 1, price_points: 1 },
          },
        ],
      })
      .mockResolvedValueOnce({
        tickers: ["AAPL"],
        companies: [
          {
            ticker: "AAPL",
            name: "Apple Inc.",
            sector: "Technology",
            cik: "1",
            last_checked: "2026-03-22T01:00:00Z",
            refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
            alert_summary: { high: 0, medium: 0, low: 0, total: 0 },
            latest_alert: null,
            latest_activity: null,
            coverage: { financial_periods: 1, price_points: 1 },
          },
        ],
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
        timestamp: "2026-03-22T01:00:00Z",
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

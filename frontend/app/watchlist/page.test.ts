// @vitest-environment jsdom

import * as React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import WatchlistPage from "@/app/watchlist/page";

const push = vi.fn();
const mockUseLocalUserData = vi.fn();
const getWatchlistSummary = vi.fn();
const refreshCompany = vi.fn();
const showAppToast = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-local-user-data", () => ({
  useLocalUserData: () => mockUseLocalUserData(),
}));

vi.mock("@/lib/api", () => ({
  getWatchlistSummary: (...args: unknown[]) => getWatchlistSummary(...args),
  refreshCompany: (...args: unknown[]) => refreshCompany(...args),
}));

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

describe("WatchlistPage", () => {
  beforeEach(() => {
    push.mockReset();
    mockUseLocalUserData.mockReset();
    getWatchlistSummary.mockReset();
    refreshCompany.mockReset();
    showAppToast.mockReset();
  });

  afterEach(() => {
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
    expect(screen.getByText(/Latest alert:/)).toBeTruthy();
    expect(screen.getByText(/Late filer notice/)).toBeTruthy();
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
            last_checked: null,
            refresh: { triggered: true, reason: "manual", ticker: "AAPL", job_id: "job-1" },
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
    expect(getWatchlistSummary).toHaveBeenCalledTimes(2);
  });
});

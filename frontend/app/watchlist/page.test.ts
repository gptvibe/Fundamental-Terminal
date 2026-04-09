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
      highlights: [
        {
          title: "Demand softening disclosed",
          summary: "MD&A language added a demand moderation callout.",
          why_it_matters: "Volume normalization could pressure gross margin assumptions.",
          importance: "high",
          category: "mda",
          signal_tags: ["demand", "margin"],
        },
      ],
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
    vi.useRealTimers();
    cleanup();
  });

  it("renders empty state when no local watchlist tickers exist", async () => {
    mockUseLocalUserData.mockReturnValue(createHookResult());

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("No companies saved yet")).toBeTruthy();
    });
    expect(getWatchlistSummary).not.toHaveBeenCalled();
    expect(getWatchlistCalendar).not.toHaveBeenCalled();
  });

  it("renders workflow controls and Research Brief material-change summaries", async () => {
    mockUseLocalUserData.mockReturnValue(createHookResult({
      watchlist: [{ ticker: "AAPL" }],
      notesByTicker: {
        AAPL: {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          note: "Watch services mix and the next gross margin reset.",
          updatedAt: "2026-04-07T00:00:00Z",
        },
      },
      monitoringByTicker: {
        AAPL: {
          ticker: "AAPL",
          triageState: "reviewing",
          profileKey: "deep-dive",
          rationale: "Re-rate candidate if gross margin stabilizes before the next iPhone cycle.",
          lastReviewedAt: "2026-04-06T00:00:00Z",
          nextReviewAt: "2026-04-09",
          snoozedUntil: null,
          holdUntil: null,
          updatedAt: "2026-04-06T00:00:00Z",
        },
      },
    }));
    getWatchlistSummary.mockResolvedValue({ tickers: ["AAPL"], companies: [createSummaryItem()] });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    expect(screen.getByDisplayValue("Re-rate candidate if gross margin stabilizes before the next iPhone cycle.")).toBeTruthy();
    expect(screen.getByText("2 high-signal changes since the last filing")).toBeTruthy();
    expect(screen.getByText(/Volume normalization could pressure gross margin assumptions/i)).toBeTruthy();
    expect(screen.getByLabelText(/Triage state for AAPL/i)).toBeTruthy();
  });

  it("filters the list by review-due and applies saved views", async () => {
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
          rationale: "Parked name",
          lastReviewedAt: null,
          nextReviewAt: "2026-05-01",
          snoozedUntil: null,
          holdUntil: "2026-05-01",
          updatedAt: "2026-04-08T00:00:00Z",
        },
      },
      savedWatchlistViews: [
        {
          id: "parked",
          name: "Parked",
          criteria: {
            primaryFilter: "hold",
            triageStates: [],
            sortBy: "review",
            searchText: "",
            profileKey: null,
          },
          createdAt: "2026-04-08T00:00:00Z",
          updatedAt: "2026-04-08T00:00:00Z",
        },
      ],
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
          material_change: {
            status: "warming",
            headline: "Research Brief change digest warming.",
            detail: "Material filing deltas will appear after the first Research Brief build completes.",
            current_filing_type: null,
            current_period_end: null,
            previous_period_end: null,
            high_signal_change_count: 0,
            new_risk_indicator_count: 0,
            share_count_change_count: 0,
            capital_structure_change_count: 0,
            comment_letter_count: 0,
            highlights: [],
          },
        }),
      ],
    });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
      expect(screen.getByText("Microsoft")).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Review due" }));
    expect(screen.getByText("Apple Inc.")).toBeTruthy();
    expect(screen.queryByText("Microsoft")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /ParkedOn hold/i }));
    expect(screen.getByText("Microsoft")).toBeTruthy();
    expect(screen.queryByText("Apple Inc.")).toBeNull();
  });

  it("persists rationale edits, review actions, and saved views", async () => {
    const saveMonitoringEntry = vi.fn();
    const saveWatchlistView = vi.fn();
    mockUseLocalUserData.mockReturnValue(createHookResult({
      watchlist: [{ ticker: "AAPL" }],
      saveMonitoringEntry,
      saveWatchlistView,
    }));
    getWatchlistSummary.mockResolvedValue({ tickers: ["AAPL"], companies: [createSummaryItem({ alert_summary: { high: 0, medium: 0, low: 0, total: 0 } })] });

    render(React.createElement(WatchlistPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    const whyInput = screen.getByLabelText("Why AAPL is on the monitor");
    fireEvent.change(whyInput, { target: { value: "Waiting for margin stabilization and a cleaner China demand setup." } });
    fireEvent.blur(whyInput);

    await waitFor(() => {
      expect(saveMonitoringEntry).toHaveBeenCalledWith(expect.objectContaining({
        ticker: "AAPL",
        rationale: "Waiting for margin stabilization and a cleaner China demand setup.",
      }));
    });

    fireEvent.click(screen.getByRole("button", { name: "Review AAPL now" }));
    expect(saveMonitoringEntry).toHaveBeenCalledWith(expect.objectContaining({
      ticker: "AAPL",
      lastReviewedAt: expect.any(String),
      nextReviewAt: expect.any(String),
    }));

    fireEvent.change(screen.getByLabelText("Saved watchlist view name"), { target: { value: "Morning Sweep" } });
    fireEvent.click(screen.getByRole("button", { name: "Save View" }));

    expect(saveWatchlistView).toHaveBeenCalledWith(expect.objectContaining({
      name: "Morning Sweep",
      criteria: expect.objectContaining({ primaryFilter: "all" }),
    }));
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
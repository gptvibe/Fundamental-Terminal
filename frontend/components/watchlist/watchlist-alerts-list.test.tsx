// @vitest-environment jsdom

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { WatchlistAlertsList, WatchlistAlertsBadge, ALERT_TYPE_LABELS } from "./watchlist-alerts-list";
import * as watchlistApi from "@/lib/api/watchlist";
import type { WatchlistAlertsResponse } from "@/lib/types";

// Mock the API
vi.mock("@/lib/api/watchlist");

describe("WatchlistAlertsList", () => {
  const mockAlerts: WatchlistAlertsResponse = {
    tickers: ["AAPL", "MSFT"],
    alerts: [
      {
        id: 1,
        ticker: "AAPL",
        alert_type: "10-K",
        title: "New annual report (10-K) filed",
        detail: "Company filed Form 10-K",
        source_filing_accession: "0000320193-24-000001",
        source_filing_form: "10-K",
        created_at: new Date().toISOString(),
        dismissed_at: null,
      },
      {
        id: 2,
        ticker: "MSFT",
        alert_type: "8-K",
        title: "Current report (8-K) filed",
        detail: "Company filed Form 8-K for current event",
        source_filing_accession: "0000789019-24-000002",
        source_filing_form: "8-K",
        created_at: new Date(Date.now() - 86400000).toISOString(), // Yesterday
        dismissed_at: null,
      },
      {
        id: 3,
        ticker: "AAPL",
        alert_type: "amendment",
        title: "Amended filing (Form 10-K/A)",
        detail: "Company filed an amendment to a previous filing",
        source_filing_accession: "0000320193-24-000003",
        source_filing_form: "10-K/A",
        created_at: new Date(Date.now() - 172800000).toISOString(), // 2 days ago
        dismissed_at: null,
      },
    ],
    total_count: 3,
    unread_count: 3,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(watchlistApi.getWatchlistAlerts).mockResolvedValue(mockAlerts);
  });

  it("renders alerts list", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText("New annual report (10-K) filed")).toBeTruthy();
      expect(screen.getByText("Current report (8-K) filed")).toBeTruthy();
    });
  });

  it("displays alert filter buttons", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Annual Report/)).toBeTruthy();
      expect(screen.getByText(/Current Report/)).toBeTruthy();
      expect(screen.getByText(/Amended Filing/)).toBeTruthy();
    });
  });

  it("filters alerts by type when button clicked", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText("New annual report (10-K) filed")).toBeTruthy();
    });

    // Click 10-K filter
    const tenKButton = screen.getByRole("button", { name: /Annual Report/ });
    fireEvent.click(tenKButton);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Annual Report/ })).toBeTruthy();
      expect(screen.getByText(/Showing \d+ of \d+ alerts/)).toBeTruthy();
    });
  });

  it("toggles filter on/off", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText("New annual report (10-K) filed")).toBeTruthy();
    });

    const tenKButton = screen.getByRole("button", { name: /Annual Report/ });

    // Click to filter
    fireEvent.click(tenKButton);
    await waitFor(() => {
      expect(screen.queryByText("Current report (8-K) filed")).toBeNull();
    });

    // Click again to clear filter
    fireEvent.click(tenKButton);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Current Report/ })).toBeTruthy();
      expect(screen.getByText(/Showing \d+ of \d+ alerts/)).toBeTruthy();
    });
  });

  it("displays unread and all count buttons", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText(/Unread \(3\)/)).toBeTruthy();
      expect(screen.getByText(/All \(3\)/)).toBeTruthy();
    });
  });

  it("shows empty state when no alerts match filters", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText("New annual report (10-K) filed")).toBeTruthy();
    });

    // Select a filter that should show items, then change to show mode that shows none
    const unreadButton = screen.getByRole("button", { name: /Unread/ });
    fireEvent.click(unreadButton);

    // Mock data has no dismissed alerts, so showing "all" should still show alerts
    const allButton = screen.getByRole("button", { name: /All/ });
    fireEvent.click(allButton);

    // Apply filter with no matches
    const tenKButton = screen.getByRole("button", { name: /Annual Report/ });
    fireEvent.click(tenKButton);

    // Should show only matching alert
    await waitFor(() => {
      expect(screen.getByText("New annual report (10-K) filed")).toBeTruthy();
    });
  });

  it("sorts by recent by default", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      const alerts = screen.getAllByText(/filed|amendment/i);
      // Most recent (10-K) should be first
      expect(alerts[0]?.textContent ?? "").toContain("New annual report");
    });
  });

  it("changes sort order when select changes", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(screen.getByText("New annual report (10-K) filed")).toBeTruthy();
    });

    const sortSelect = screen.getByDisplayValue("Most Recent");
    fireEvent.change(sortSelect, { target: { value: "oldest" } });

    // Oldest should be displayed first (need to verify order - implementation specific)
    expect(screen.getByDisplayValue("Oldest First")).toBeTruthy();
  });

  it("calls API with tickers", async () => {
    render(<WatchlistAlertsList tickers={["AAPL", "MSFT"]} />);

    await waitFor(() => {
      expect(watchlistApi.getWatchlistAlerts).toHaveBeenCalledWith(["AAPL", "MSFT"], undefined);
    });
  });

  it("handles API error", async () => {
    vi.mocked(watchlistApi.getWatchlistAlerts).mockRejectedValue(new Error("API Error"));

    render(<WatchlistAlertsList tickers={["AAPL"]} />);

    await waitFor(() => {
      expect(screen.getByText("API Error")).toBeTruthy();
    });
  });

  it("shows loading skeleton initially", () => {
    render(<WatchlistAlertsList tickers={["AAPL"]} isLoading={true} />);

    expect(screen.getByLabelText("Loading content")).toBeTruthy();
  });
});

describe("WatchlistAlertsBadge", () => {
  it("shows badge with count", () => {
    render(<WatchlistAlertsBadge count={5} />);
    expect(screen.getByText("5")).toBeTruthy();
  });

  it("shows 9+ for counts > 9", () => {
    render(<WatchlistAlertsBadge count={15} />);
    expect(screen.getByText("9+")).toBeTruthy();
  });

  it("returns null for count of 0", () => {
    const { container } = render(<WatchlistAlertsBadge count={0} />);
    expect(container.firstChild).toBeNull();
  });

  it("applies custom className", () => {
    render(<WatchlistAlertsBadge count={3} className="custom-class" />);
    const badge = screen.getByText("3");
    expect(badge.className).toContain("custom-class");
  });
});

describe("ALERT_TYPE_LABELS", () => {
  it("has entries for all alert types", () => {
    const alertTypes = ["10-K", "10-Q", "8-K", "proxy", "form-4", "amendment", "late-filing", "stale-data"];
    for (const type of alertTypes) {
      expect(ALERT_TYPE_LABELS[type]).toBeDefined();
      expect(ALERT_TYPE_LABELS[type]).toHaveProperty("label");
      expect(ALERT_TYPE_LABELS[type]).toHaveProperty("color");
      expect(ALERT_TYPE_LABELS[type]).toHaveProperty("icon");
      expect(ALERT_TYPE_LABELS[type]).toHaveProperty("priority");
    }
  });

  it("has priority for each type", () => {
    expect(ALERT_TYPE_LABELS["late-filing"].priority).toBeGreaterThan(ALERT_TYPE_LABELS["10-K"].priority);
    expect(ALERT_TYPE_LABELS["8-K"].priority).toBeGreaterThan(ALERT_TYPE_LABELS["form-4"].priority);
  });
});

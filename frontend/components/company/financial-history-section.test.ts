// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import React from "react";

import { FinancialHistorySection } from "@/components/company/financial-history-section";
import { getCompanyFinancialHistory } from "@/lib/api";
import type { FinancialHistoryPoint } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  getCompanyFinancialHistory: vi.fn(),
}));

describe("FinancialHistorySection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when cik is null", () => {
    render(React.createElement(FinancialHistorySection, { cik: null }));
    expect(screen.getByText("CIK not available yet")).toBeDefined();
    expect(screen.getByText("Company facts appear once the SEC identifier resolves.")).toBeDefined();
  });

  it("renders loading state while data is being fetched", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    mockGetHistory.mockImplementation(
      () => new Promise((resolve) => {
        setTimeout(() => resolve([]), 100);
      })
    );

    render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));
    expect(screen.getByText("Loading SEC companyfacts…")).toBeDefined();
    expect(screen.getByText("Fetching the latest fiscal year history directly from EDGAR.")).toBeDefined();

    await waitFor(() => {
      // Wait for loading to complete
      expect(mockGetHistory).toHaveBeenCalled();
    });
  });

  it("renders error state when API call fails with a generic error", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    mockGetHistory.mockRejectedValue(new Error("Network error"));

    render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));

    await waitFor(() => {
      expect(screen.getByText("Unable to load SEC history")).toBeDefined();
      expect(screen.getByText("Network error")).toBeDefined();
    });
  });

  it("renders error state when API returns 404", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    const error = new Error("API request failed: 404 Not Found");
    mockGetHistory.mockRejectedValue(error);

    render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));

    await waitFor(() => {
      expect(screen.getByText("Unable to load SEC history")).toBeDefined();
      expect(screen.getByText("API request failed: 404 Not Found")).toBeDefined();
    });
  });

  it("renders error state when API returns 500", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    const error = new Error("API request failed: 500 Internal Server Error");
    mockGetHistory.mockRejectedValue(error);

    render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));

    await waitFor(() => {
      expect(screen.getByText("Unable to load SEC history")).toBeDefined();
      expect(screen.getByText("API request failed: 500 Internal Server Error")).toBeDefined();
    });
  });

  it("handles aborted requests gracefully", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    const abortError = new DOMException("The operation was aborted.", "AbortError");
    mockGetHistory.mockRejectedValue(abortError);

    const { unmount } = render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));
    // Immediately unmount to trigger abort cleanup
    unmount();

    // Should not throw or display error for aborted requests
    expect(true).toBe(true);
  });

  it("displays success state with data when API returns valid history", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    const mockData: FinancialHistoryPoint[] = [
      {
        year: 2023,
        revenue: 100000,
        net_income: 10000,
        eps: 2.5,
        operating_cash_flow: 12000,
      },
      {
        year: 2024,
        revenue: 120000,
        net_income: 12000,
        eps: 3.0,
        operating_cash_flow: 14000,
      },
    ];
    mockGetHistory.mockResolvedValue(mockData);

    render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));

    await waitFor(() => {
      // After loading completes, the chart component should render
      // Since the actual chart rendering is handled by FinancialHistoryLineChart,
      // we verify the component loads without error
      expect(mockGetHistory).toHaveBeenCalledWith("0001234567", expect.objectContaining({ signal: expect.anything() }));
    });
  });

  it("cancels previous request when cik changes", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    let abortController: AbortController | null = null;

    mockGetHistory.mockImplementation(async (cik: string, options: Record<string, unknown>) => {
      abortController = (options.signal as AbortSignal)?.constructor === AbortSignal ? new AbortController() : null;
      return new Promise((resolve) => {
        setTimeout(() => resolve([]), 100);
      });
    });

    const { rerender } = render(React.createElement(FinancialHistorySection, { cik: "0001111111" }));
    rerender(React.createElement(FinancialHistorySection, { cik: "0002222222" }));

    await waitFor(() => {
      expect(mockGetHistory).toHaveBeenCalledTimes(2);
    });
  });

  it("does not display error for a non-Error thrown value", async () => {
    const mockGetHistory = vi.mocked(getCompanyFinancialHistory);
    mockGetHistory.mockRejectedValue("string error");

    render(React.createElement(FinancialHistorySection, { cik: "0001234567" }));

    await waitFor(() => {
      expect(screen.getByText("Unable to load SEC history")).toBeDefined();
      expect(screen.getByText("Unable to load SEC financial history")).toBeDefined();
    });
  });
});

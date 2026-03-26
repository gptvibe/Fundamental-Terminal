// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MetricsExplorerPanel } from "@/components/company/metrics-explorer-panel";
import { getCompanyDerivedMetricsSummary } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCompanyDerivedMetricsSummary: vi.fn(),
}));

describe("MetricsExplorerPanel", () => {
  it("loads persisted metrics summary", async () => {
    vi.mocked(getCompanyDerivedMetricsSummary).mockResolvedValue({
      company: {
        ticker: "AAPL",
        cik: "0000320193",
        name: "Apple Inc.",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Consumer Electronics",
        last_checked: "2026-03-25T00:00:00Z",
        last_checked_financials: "2026-03-25T00:00:00Z",
        last_checked_prices: "2026-03-25T00:00:00Z",
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        earnings_last_checked: null,
        cache_state: "fresh",
      },
      period_type: "ttm",
      latest_period_end: "2025-12-31",
      metrics: [
        {
          metric_key: "revenue_growth",
          metric_value: 0.12,
          is_proxy: true,
          provenance: { formula_version: "sec_metrics_mart_v1", unit: "ratio" },
          quality_flags: [],
        },
      ],
      last_metrics_check: "2026-03-25T00:00:00Z",
      last_financials_check: "2026-03-25T00:00:00Z",
      last_price_check: "2026-03-25T00:00:00Z",
      staleness_reason: "fresh",
      refresh: {
        triggered: false,
        reason: "fresh",
        ticker: "AAPL",
        job_id: null,
      },
    });

    render(React.createElement(MetricsExplorerPanel, { ticker: "AAPL" }));

    await waitFor(() => {
      expect(getCompanyDerivedMetricsSummary).toHaveBeenCalledWith("AAPL", { periodType: "ttm" });
    });

    expect(screen.getByText("Latest: Dec 31, 2025")).toBeTruthy();
    expect(screen.getByText("12.0%")).toBeTruthy();
  });
});

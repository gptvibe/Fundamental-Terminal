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
      provenance: [
        {
          source_id: "ft_derived_metrics_mart",
          source_tier: "derived_from_official",
          display_label: "Fundamental Terminal Derived Metrics Mart",
          url: "https://github.com/gptvibe/Fundamental-Terminal",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Persisted derived metrics computed from official filings plus labeled market context inputs.",
          role: "derived",
          as_of: "2025-12-31",
          last_refreshed_at: "2026-03-25T00:00:00Z",
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
          last_refreshed_at: "2026-03-25T00:00:00Z",
        },
        {
          source_id: "yahoo_finance",
          source_tier: "commercial_fallback",
          display_label: "Yahoo Finance",
          url: "https://finance.yahoo.com/",
          default_freshness_ttl_seconds: 3600,
          disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
          role: "fallback",
          as_of: "2026-03-25",
          last_refreshed_at: "2026-03-25T00:00:00Z",
        },
      ],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-25T00:00:00Z",
      source_mix: {
        source_ids: ["ft_derived_metrics_mart", "sec_companyfacts", "yahoo_finance"],
        source_tiers: ["commercial_fallback", "derived_from_official", "official_regulator"],
        primary_source_ids: ["sec_companyfacts"],
        fallback_source_ids: ["yahoo_finance"],
        official_only: false,
      },
      confidence_flags: ["commercial_fallback_present"],
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
    expect(screen.getByText("Fundamental Terminal Derived Metrics Mart")).toBeTruthy();
  });
});

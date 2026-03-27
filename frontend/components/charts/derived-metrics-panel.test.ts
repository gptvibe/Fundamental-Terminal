// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DerivedMetricsPanel } from "@/components/charts/derived-metrics-panel";
import { getCompanyMetricsTimeseries } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCompanyMetricsTimeseries: vi.fn(),
}));

vi.mock("recharts", () => {
  function Wrapper({ children }: { children?: React.ReactNode }) {
    return React.createElement("div", null, children);
  }

  return {
    CartesianGrid: Wrapper,
    Line: Wrapper,
    LineChart: Wrapper,
    ResponsiveContainer: Wrapper,
    Tooltip: Wrapper,
    XAxis: Wrapper,
    YAxis: Wrapper,
  };
});

describe("DerivedMetricsPanel", () => {
  it("loads and renders latest derived metric cards", async () => {
    vi.mocked(getCompanyMetricsTimeseries).mockResolvedValue({
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
      series: [
        {
          cadence: "ttm",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
          filing_type: "TTM",
          metrics: {
            revenue_growth: 0.12,
            gross_margin: 0.42,
            operating_margin: 0.31,
            fcf_margin: 0.21,
            roic_proxy: 0.18,
            leverage_ratio: 0.45,
            current_ratio: 1.5,
            share_dilution: 0.01,
            sbc_burden: 0.04,
            buyback_yield: 0.02,
            dividend_yield: 0.01,
            working_capital_days: 54,
            accrual_ratio: -0.01,
            cash_conversion: 1.2,
            segment_concentration: 0.83,
          },
          provenance: {
            statement_type: "canonical_xbrl",
            statement_source: "https://data.sec.gov/example",
            price_source: "yahoo_finance",
            formula_version: "sec_metrics_v1",
          },
          quality: {
            available_metrics: 15,
            missing_metrics: [],
            coverage_ratio: 1,
            flags: [],
          },
        },
      ],
      last_financials_check: "2026-03-25T00:00:00Z",
      last_price_check: "2026-03-25T00:00:00Z",
      staleness_reason: "fresh",
      provenance: [
        {
          source_id: "ft_derived_metrics_engine",
          source_tier: "derived_from_official",
          display_label: "Fundamental Terminal Derived Metrics Engine",
          url: "https://github.com/gptvibe/Fundamental-Terminal",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Internal formulas derived from official filings and labeled supplemental price inputs.",
          role: "derived",
          as_of: "2025-12-31",
          last_refreshed_at: "2026-03-25T00:00:00Z",
        },
        {
          source_id: "sec_edgar",
          source_tier: "official_regulator",
          display_label: "SEC EDGAR Filing Archive",
          url: "https://www.sec.gov/edgar/search/",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Official SEC filing archive used for filing metadata, ownership, governance, and event disclosures.",
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
        source_ids: ["ft_derived_metrics_engine", "sec_edgar", "yahoo_finance"],
        source_tiers: ["commercial_fallback", "derived_from_official", "official_regulator"],
        primary_source_ids: ["sec_edgar"],
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

    render(React.createElement(DerivedMetricsPanel, { ticker: "AAPL", reloadKey: "k1" }));

    await waitFor(() => {
      expect(getCompanyMetricsTimeseries).toHaveBeenCalledWith("AAPL", { cadence: "ttm", maxPoints: 24 });
    });

    expect(screen.getByText("Latest Period")).toBeTruthy();
    expect(screen.getByText("Coverage")).toBeTruthy();
    expect(screen.getByText("12.0%")).toBeTruthy();
    expect(screen.getByText("Fundamental Terminal Derived Metrics Engine")).toBeTruthy();
  });
});

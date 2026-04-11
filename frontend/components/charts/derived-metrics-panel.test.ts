// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DerivedMetricsPanel } from "@/components/charts/derived-metrics-panel";
import { getCompanyMetricsTimeseries } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCompanyMetricsTimeseries: vi.fn(),
  invalidateApiReadCacheForTicker: vi.fn(),
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
        strict_official_mode: false,
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
    expect(screen.getAllByText("Fundamental Terminal Derived Metrics Engine").length).toBeGreaterThan(0);
  });

  it("disables price-derived yield selectors in strict official mode", async () => {
    vi.mocked(getCompanyMetricsTimeseries).mockResolvedValue({
      company: {
        ticker: "AAPL",
        cik: "0000320193",
        name: "Apple Inc.",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Consumer Electronics",
        strict_official_mode: true,
        last_checked: "2026-03-25T00:00:00Z",
        last_checked_financials: "2026-03-25T00:00:00Z",
        last_checked_prices: null,
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
            buyback_yield: null,
            dividend_yield: null,
            working_capital_days: 54,
            accrual_ratio: -0.01,
            cash_conversion: 1.2,
            segment_concentration: 0.83,
          },
          provenance: {
            statement_type: "canonical_xbrl",
            statement_source: "https://data.sec.gov/example",
            price_source: null,
            formula_version: "sec_metrics_v1",
          },
          quality: {
            available_metrics: 13,
            missing_metrics: [],
            coverage_ratio: 1,
            flags: ["strict_official_mode_price_disabled"],
          },
        },
      ],
      last_financials_check: "2026-03-25T00:00:00Z",
      last_price_check: null,
      staleness_reason: "fresh",
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-25T00:00:00Z",
      source_mix: {
        source_ids: ["ft_derived_metrics_engine", "sec_edgar"],
        source_tiers: ["derived_from_official", "official_regulator"],
        primary_source_ids: ["sec_edgar"],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: ["strict_official_mode"],
      refresh: {
        triggered: false,
        reason: "fresh",
        ticker: "AAPL",
        job_id: null,
      },
    });

    render(React.createElement(DerivedMetricsPanel, { ticker: "AAPL", reloadKey: "strict" }));

    await waitFor(() => {
      expect(getCompanyMetricsTimeseries).toHaveBeenCalledWith("AAPL", { cadence: "ttm", maxPoints: 24 });
    });

    expect(screen.getByText(/Strict official mode disables price-derived yield overlays/i)).toBeTruthy();
    expect(screen.getByText("Disabled in strict mode")).toBeTruthy();
    expect((screen.getByRole("option", { name: /Buyback Yield \(strict mode unavailable\)/i }) as HTMLOptionElement).disabled).toBe(true);
  });

  it("switches to bank metrics when regulated-bank series are returned", async () => {
    vi.mocked(getCompanyMetricsTimeseries).mockResolvedValue({
      company: {
        ticker: "WFC",
        cik: "0000072971",
        name: "Wells Fargo & Company",
        sector: "Financials",
        market_sector: "Financials",
        market_industry: "Banks",
        strict_official_mode: false,
        last_checked: "2026-03-25T00:00:00Z",
        last_checked_financials: "2026-03-25T00:00:00Z",
        last_checked_prices: "2026-03-25T00:00:00Z",
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        earnings_last_checked: null,
        cache_state: "fresh",
        regulated_entity: {
          issuer_type: "bank",
          reporting_basis: "fdic_call_report",
          confidence_score: 0.99,
          confidence_flags: [],
        },
      },
      series: [
        {
          cadence: "ttm",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
          filing_type: "TTM",
          metrics: {
            net_interest_margin: 0.038,
            provision_burden: 0.11,
            asset_quality_ratio: 0.012,
            cet1_ratio: 0.121,
            tier1_capital_ratio: 0.132,
            total_capital_ratio: 0.149,
            core_deposit_ratio: 0.73,
            uninsured_deposit_ratio: 0.17,
            tangible_book_value_per_share: 41.2,
            roatce: 0.146,
          },
          provenance: {
            statement_type: "canonical_bank_regulatory",
            statement_source: "https://api.fdic.gov/banks/financials",
            price_source: null,
            formula_version: "sec_metrics_v1",
          },
          quality: {
            available_metrics: 10,
            missing_metrics: [],
            coverage_ratio: 1,
            flags: [],
          },
        },
      ],
      last_financials_check: "2026-03-25T00:00:00Z",
      last_price_check: null,
      staleness_reason: "fresh",
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-25T00:00:00Z",
      source_mix: {
        source_ids: ["ft_derived_metrics_engine", "fdic_bankfind_financials"],
        source_tiers: ["derived_from_official", "official_regulator"],
        primary_source_ids: ["fdic_bankfind_financials"],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: [],
      refresh: {
        triggered: false,
        reason: "fresh",
        ticker: "WFC",
        job_id: null,
      },
    });

    render(React.createElement(DerivedMetricsPanel, { ticker: "WFC", reloadKey: "bank" }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: "Net Interest Margin" })).toBeTruthy();
    });

    fireEvent.change(screen.getByLabelText("Select derived metric"), { target: { value: "roatce" } });
    expect(screen.getByRole("option", { name: "ROATCE" })).toBeTruthy();
    expect(screen.getByText("14.6%")).toBeTruthy();
  });
});

// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { OilScenarioOverlayPanel } from "@/components/models/oil-scenario-overlay-panel";

const downloadJsonFile = vi.fn();
const exportRowsToCsv = vi.fn();
const showAppToast = vi.fn();

vi.mock("@/lib/export", async () => {
  const actual = await vi.importActual<typeof import("@/lib/export")>("@/lib/export");
  return {
    ...actual,
    downloadJsonFile: (...args: unknown[]) => downloadJsonFile(...args),
    exportRowsToCsv: (...args: unknown[]) => exportRowsToCsv(...args),
  };
});

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

describe("OilScenarioOverlayPanel", () => {
  it("renders controls, computes outputs, and exports overlay results", () => {
    render(
      React.createElement(OilScenarioOverlayPanel, {
        ticker: "CVX",
        strictOfficialMode: true,
        companySupportStatus: "supported",
        companySupportReasons: ["integrated_upstream_supported"],
        models: [
          {
            model_name: "dcf",
            model_version: "2.2.0",
            created_at: "2026-04-04T00:00:00Z",
            input_periods: {},
            result: { fair_value_per_share: 100 },
          },
        ],
        financials: [
          {
            filing_type: "10-K",
            statement_type: "annual",
            period_start: "2025-01-01",
            period_end: "2025-12-31",
            source: "sec",
            last_updated: "2026-04-04T00:00:00Z",
            last_checked: "2026-04-04T00:00:00Z",
            revenue: null,
            gross_profit: null,
            operating_income: null,
            net_income: null,
            total_assets: null,
            current_assets: null,
            total_liabilities: null,
            current_liabilities: null,
            retained_earnings: null,
            sga: null,
            research_and_development: null,
            interest_expense: null,
            income_tax_expense: null,
            inventory: null,
            cash_and_cash_equivalents: null,
            short_term_investments: null,
            cash_and_short_term_investments: null,
            accounts_receivable: null,
            accounts_payable: null,
            goodwill_and_intangibles: null,
            current_debt: null,
            long_term_debt: null,
            stockholders_equity: null,
            lease_liabilities: null,
            operating_cash_flow: null,
            depreciation_and_amortization: null,
            capex: null,
            acquisitions: null,
            debt_changes: null,
            dividends: null,
            share_buybacks: null,
            free_cash_flow: null,
            eps: null,
            shares_outstanding: 11,
            stock_based_compensation: null,
            weighted_average_diluted_shares: 10,
            segment_breakdown: [],
            reconciliation: null,
          },
        ],
        priceHistory: [],
        overlay: {
          company: null,
          status: "supported",
          fetched_at: "2026-04-04T00:00:00Z",
          as_of: "2026-04-04",
          last_refreshed_at: "2026-04-04T00:00:00Z",
          strict_official_mode: true,
          exposure_profile: {
            profile_id: "integrated",
            label: "Integrated",
            oil_exposure_type: "integrated",
            oil_support_status: "supported",
            oil_support_reasons: ["integrated_upstream_supported"],
            relevance_reasons: ["integrated_upstream_supported"],
            hedging_signal: "unknown",
            pass_through_signal: "unknown",
            evidence: [],
          },
          benchmark_series: [
            {
              series_id: "wti_short_term_baseline",
              label: "WTI short-term official baseline",
              units: "usd_per_barrel",
              status: "ok",
              points: [
                { label: "2026-01", value: 80, units: "usd_per_barrel", observation_date: "2026-01" },
                { label: "2027-01", value: 78, units: "usd_per_barrel", observation_date: "2027-01" },
                { label: "2028-01", value: 76, units: "usd_per_barrel", observation_date: "2028-01" },
              ],
              latest_value: 76,
              latest_observation_date: "2028-01",
            },
            {
              series_id: "brent_short_term_baseline",
              label: "Brent short-term official baseline",
              units: "usd_per_barrel",
              status: "ok",
              points: [
                { label: "2026-01", value: 85, units: "usd_per_barrel", observation_date: "2026-01" },
                { label: "2027-01", value: 83, units: "usd_per_barrel", observation_date: "2027-01" },
                { label: "2028-01", value: 81, units: "usd_per_barrel", observation_date: "2028-01" },
              ],
              latest_value: 81,
              latest_observation_date: "2028-01",
            },
          ],
          scenarios: [],
          sensitivity: {
            metric_basis: "operating_margin",
            lookback_quarters: 8,
            elasticity: null,
            r_squared: null,
            sample_size: 0,
            direction: "unknown",
            status: "placeholder",
            confidence_flags: ["sensitivity_not_computed"],
          },
          diagnostics: {
            coverage_ratio: 1,
            fallback_ratio: 0,
            stale_flags: [],
            parser_confidence: 1,
            missing_field_flags: [],
            reconciliation_penalty: null,
            reconciliation_disagreement_count: 0,
          },
          provenance: [
            {
              source_id: "eia_steo",
              source_tier: "official_statistical",
              display_label: "U.S. Energy Information Administration Short-Term Energy Outlook",
              url: "https://api.eia.gov/v2/steo/",
              default_freshness_ttl_seconds: 86400,
              disclosure_note: "Official EIA Short-Term Energy Outlook series intended for oil and petroleum scenario context.",
              role: "primary",
              as_of: "2028-01",
              last_refreshed_at: "2026-04-04T00:00:00Z",
            },
          ],
          source_mix: {
            source_ids: ["eia_steo"],
            source_tiers: ["official_statistical"],
            primary_source_ids: ["eia_steo"],
            fallback_source_ids: [],
            official_only: true,
          },
          confidence_flags: [],
          refresh: { triggered: false, reason: "fresh", ticker: "CVX", job_id: null },
        },
      }),
    );

    fireEvent.change(screen.getByLabelText("Annual after-tax sensitivity input"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Current share price input"), { target: { value: "90" } });
  fireEvent.change(screen.getByLabelText("Short-term curve 2026"), { target: { value: "100" } });

    expect(screen.getByText("Oil Scenario Overlay")).toBeTruthy();
    expect(screen.getByLabelText("Benchmark Selector")).toBeTruthy();
    expect(screen.getByLabelText("Long-term anchor input")).toBeTruthy();
    expect(screen.getByLabelText("Fade years input")).toBeTruthy();
    expect(screen.getByLabelText("Annual after-tax sensitivity input")).toBeTruthy();
  expect(screen.getByText("$118.18")).toBeTruthy();
  expect(screen.getAllByText("+$18.18").length).toBeGreaterThan(0);
    expect(screen.getByText("+1")).toBeTruthy();
  expect(screen.getByText("31.31%")).toBeTruthy();
    expect(screen.getByText("integrated_upstream_supported")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(downloadJsonFile).toHaveBeenCalledTimes(1);
    expect(exportRowsToCsv).toHaveBeenCalledTimes(1);
    expect(showAppToast).toHaveBeenCalled();
  });

  it("shows a +5 percent example when official benchmark points are missing", () => {
    render(
      React.createElement(OilScenarioOverlayPanel, {
        ticker: "CVX",
        strictOfficialMode: false,
        companySupportStatus: "partial",
        companySupportReasons: ["refining_margin_exposure_partial_v1"],
        models: [
          {
            model_name: "dcf",
            model_version: "2.2.0",
            created_at: "2026-04-04T00:00:00Z",
            input_periods: {},
            result: { fair_value_per_share: 100 },
          },
        ],
        financials: [
          {
            filing_type: "10-K",
            statement_type: "annual",
            period_start: "2025-01-01",
            period_end: "2025-12-31",
            source: "sec",
            last_updated: "2026-04-04T00:00:00Z",
            last_checked: "2026-04-04T00:00:00Z",
            revenue: null,
            gross_profit: null,
            operating_income: null,
            net_income: null,
            total_assets: null,
            current_assets: null,
            total_liabilities: null,
            current_liabilities: null,
            retained_earnings: null,
            sga: null,
            research_and_development: null,
            interest_expense: null,
            income_tax_expense: null,
            inventory: null,
            cash_and_cash_equivalents: null,
            short_term_investments: null,
            cash_and_short_term_investments: null,
            accounts_receivable: null,
            accounts_payable: null,
            goodwill_and_intangibles: null,
            current_debt: null,
            long_term_debt: null,
            stockholders_equity: null,
            lease_liabilities: null,
            operating_cash_flow: null,
            depreciation_and_amortization: null,
            capex: null,
            acquisitions: null,
            debt_changes: null,
            dividends: null,
            share_buybacks: null,
            free_cash_flow: null,
            eps: null,
            shares_outstanding: 11,
            stock_based_compensation: null,
            weighted_average_diluted_shares: 10,
            segment_breakdown: [],
            reconciliation: null,
          },
        ],
        priceHistory: [{ date: "2026-04-04", close: 90, volume: 1000 }],
        overlay: {
          company: null,
          status: "partial",
          fetched_at: "2026-04-04T00:00:00Z",
          as_of: "2026-04-04",
          last_refreshed_at: "2026-04-04T00:00:00Z",
          strict_official_mode: false,
          exposure_profile: {
            profile_id: "refiner",
            label: "Refiner",
            oil_exposure_type: "refiner",
            oil_support_status: "partial",
            oil_support_reasons: ["refining_margin_exposure_partial_v1"],
            relevance_reasons: ["refining_margin_exposure_partial_v1"],
            hedging_signal: "unknown",
            pass_through_signal: "unknown",
            evidence: [],
          },
          benchmark_series: [],
          scenarios: [],
          sensitivity: null,
          diagnostics: {
            coverage_ratio: 0,
            fallback_ratio: 0,
            stale_flags: [],
            parser_confidence: null,
            missing_field_flags: ["official_oil_curve_missing"],
            reconciliation_penalty: null,
            reconciliation_disagreement_count: 0,
          },
          provenance: [],
          source_mix: {
            source_ids: [],
            source_tiers: [],
            primary_source_ids: [],
            fallback_source_ids: [],
            official_only: true,
          },
          confidence_flags: [],
          user_editable_defaults: {
            benchmark_options: [],
            current_oil_price: 83.4,
            current_oil_price_source: "wti_spot_history",
          },
          refresh: { triggered: false, reason: "fresh", ticker: "CVX", job_id: null },
        },
      }),
    );

    expect(screen.getByText("Load +5% example")).toBeTruthy();
    expect(screen.getByText(/Example mode uses \$83.40\/bbl/)).toBeTruthy();
    expect(screen.getByRole("option", { name: "Example benchmark ($83.40/bbl baseline)" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Load +5% example" }));

    expect((screen.getByLabelText("Long-term anchor input") as HTMLInputElement).value).toBe("83.4");
    expect((screen.getByLabelText("Short-term curve 2026") as HTMLInputElement).value).toBe("87.57");
  });
});
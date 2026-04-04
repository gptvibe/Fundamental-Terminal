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
        oilOverlayEvaluation: null,
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
          sensitivity_source: {
            kind: "manual_override",
            value: null,
            metric_basis: null,
            status: null,
            confidence_flags: [],
          },
          user_editable_defaults: {
            benchmark_id: "wti_short_term_baseline",
            benchmark_options: [
              { value: "wti_short_term_baseline", label: "WTI" },
              { value: "brent_short_term_baseline", label: "Brent" },
            ],
            short_term_curve: [
              { year: 2026, price: 80 },
              { year: 2027, price: 78 },
              { year: 2028, price: 76 },
            ],
            long_term_anchor: 76,
            fade_years: 2,
            annual_after_tax_sensitivity: null,
            base_fair_value_per_share: 100,
            diluted_shares: 10,
            current_realized_spread: -4,
            current_realized_spread_source: "sec_realized_price_comparison",
            custom_realized_spread: -4,
            mean_reversion_target_spread: 0,
            mean_reversion_years: 2,
            realized_spread_mode: "hold_current_spread",
            realized_spread_reference_benchmark: "wti",
          },
          requirements: {
            strict_official_mode: true,
            manual_price_required: true,
            manual_price_reason: "Company cache is missing.",
            manual_sensitivity_required: true,
            manual_sensitivity_reason: "No disclosed or derived official oil sensitivity is cached yet.",
            price_input_mode: "manual",
            realized_spread_supported: true,
            realized_spread_reason: null,
            realized_spread_fallback_label: null,
          },
          direct_company_evidence: {
            status: "partial",
            checked_at: "2026-04-04T00:00:00Z",
            parser_confidence_flags: ["realized_vs_benchmark_available"],
            disclosed_sensitivity: {
              status: "not_available",
              reason: "No explicit annual oil sensitivity was disclosed.",
              confidence_flags: ["oil_sensitivity_not_available"],
              provenance_sources: ["sec_edgar"],
            },
            diluted_shares: {
              status: "available",
              value: 10,
              unit: "shares",
              taxonomy: "us-gaap",
              tag: "WeightedAverageNumberOfDilutedSharesOutstanding",
              confidence_flags: ["weighted_average_diluted_shares_companyfacts"],
              provenance_sources: ["sec_companyfacts"],
            },
            realized_price_comparison: {
              status: "available",
              benchmark: "wti",
              rows: [
                {
                  period_label: "2025",
                  benchmark: "wti",
                  realized_price: 72,
                  benchmark_price: 76,
                  realized_percent_of_benchmark: 94.74,
                  premium_discount: -4,
                },
              ],
              confidence_flags: ["realized_vs_benchmark_available"],
              provenance_sources: ["sec_edgar"],
            },
          },
          confidence_flags: [],
          refresh: { triggered: false, reason: "fresh", ticker: "CVX", job_id: null },
        },
      }),
    );

    fireEvent.change(screen.getByLabelText("Annual after-tax sensitivity input"), { target: { value: "10" } });
    fireEvent.change(screen.getByLabelText("Current share price input"), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText("Short-term curve 2026"), { target: { value: "100" } });
    fireEvent.change(screen.getByLabelText("Realized spread mode"), { target: { value: "custom_spread" } });
    fireEvent.change(screen.getByLabelText("Custom realized spread input"), { target: { value: "-1" } });

    expect(screen.getByText("Oil Scenario Overlay")).toBeTruthy();
    expect(screen.getByText(/v1 models realized-vs-benchmark economics for producers/i)).toBeTruthy();
    expect(screen.getByLabelText("Benchmark Selector")).toBeTruthy();
    expect(screen.getByLabelText("Long-term anchor input")).toBeTruthy();
    expect(screen.getByLabelText("Fade years input")).toBeTruthy();
    expect(screen.getByLabelText("Annual after-tax sensitivity input")).toBeTruthy();
    expect(screen.getByLabelText("Realized spread mode")).toBeTruthy();
    expect(screen.getByText("$129.55")).toBeTruthy();
    expect(screen.getAllByText("+$29.55").length).toBeGreaterThan(0);
    expect(screen.getByText("+1")).toBeTruthy();
    expect(screen.getByText("43.95%")).toBeTruthy();
    expect(screen.getByText("integrated upstream supported")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(downloadJsonFile).toHaveBeenCalledTimes(1);
    expect(exportRowsToCsv).toHaveBeenCalledTimes(1);
    expect(showAppToast).toHaveBeenCalled();
  });

  it("shows benchmark-only fallback labeling when realized spread evidence is unavailable", () => {
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
        oilOverlayEvaluation: null,
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
          benchmark_series: [
            {
              series_id: "wti_short_term_baseline",
              label: "WTI short-term official baseline",
              units: "usd_per_barrel",
              status: "ok",
              points: [
                { label: "2026-01", value: 80, units: "usd_per_barrel", observation_date: "2026-01" },
              ],
              latest_value: 80,
              latest_observation_date: "2026-01",
            },
          ],
          scenarios: [],
          sensitivity: null,
          sensitivity_source: {
            kind: "manual_override",
            value: null,
            metric_basis: null,
            status: null,
            confidence_flags: [],
          },
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
            benchmark_id: "wti_short_term_baseline",
            benchmark_options: [{ value: "wti_short_term_baseline", label: "WTI" }],
            current_oil_price: 83.4,
            current_oil_price_source: "wti_spot_history",
            realized_spread_mode: "benchmark_only",
            current_realized_spread: null,
            custom_realized_spread: null,
            mean_reversion_target_spread: 0,
            mean_reversion_years: 3,
            realized_spread_reference_benchmark: "wti",
          },
          requirements: {
            strict_official_mode: false,
            manual_price_required: false,
            manual_price_reason: null,
            manual_sensitivity_required: true,
            manual_sensitivity_reason: "No disclosed or derived official oil sensitivity is cached yet.",
            price_input_mode: "cached_market_price",
            realized_spread_supported: false,
            realized_spread_reason: "v1 realized-spread controls are only supported for producer and integrated-upstream oil names.",
            realized_spread_fallback_label: "Producer-only v1 model",
          },
          direct_company_evidence: {
            status: "not_available",
            checked_at: "2026-04-04T00:00:00Z",
            parser_confidence_flags: ["realized_vs_benchmark_not_available"],
            disclosed_sensitivity: {
              status: "not_available",
              reason: "No explicit annual oil sensitivity was disclosed.",
              confidence_flags: ["oil_sensitivity_not_available"],
              provenance_sources: ["sec_edgar"],
            },
            diluted_shares: {
              status: "not_available",
              reason: "No diluted share evidence was cached.",
              confidence_flags: ["diluted_shares_not_available"],
              provenance_sources: ["sec_companyfacts"],
            },
            realized_price_comparison: {
              status: "not_available",
              reason: "No clear SEC realized-price-versus-benchmark table is cached for this producer yet.",
              benchmark: "wti",
              rows: [],
              confidence_flags: ["realized_vs_benchmark_not_available"],
              provenance_sources: ["sec_edgar"],
            },
          },
          refresh: { triggered: false, reason: "fresh", ticker: "CVX", job_id: null },
        },
      }),
    );

    expect(screen.getByText("Producer-only v1 model")).toBeTruthy();
    expect(screen.getAllByText(/only supported for producer and integrated-upstream oil names/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("Load +5% example")).toBeNull();
  });

  it("shows a blocked-data workflow with evaluation context when the official curve is missing", () => {
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
        oilOverlayEvaluation: {
          run: {
            id: 1,
            suite_key: "oil_overlay_point_in_time_v1",
            candidate_label: "oil_overlay_fixture_v1",
            baseline_label: null,
            status: "completed",
            completed_at: "2026-04-04T00:00:00Z",
            configuration: {},
            summary: {
              evaluation_focus: "oil_overlay",
              latest_as_of: "2026-03-31",
              comparison: { sample_count: 12, improvement_rate: 0.58, mean_absolute_error_lift: 0.03 },
            },
            artifacts: {
              company_summaries: {
                CVX: {
                  ticker: "CVX",
                  sample_count: 4,
                  latest_as_of: "2026-03-31",
                  improvement_rate: 0.5,
                  mean_absolute_error_lift: 0.02,
                },
              },
            },
            models: [],
            deltas_present: false,
          },
          provenance: [],
          as_of: "2026-03-31",
          last_refreshed_at: "2026-04-04T00:00:00Z",
          source_mix: {
            source_ids: ["ft_oil_scenario_overlay"],
            source_tiers: ["derived_from_official"],
            primary_source_ids: ["ft_oil_scenario_overlay"],
            fallback_source_ids: [],
            official_only: false,
          },
          confidence_flags: [],
        },
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
          benchmark_series: [
            {
              series_id: "wti_short_term_baseline",
              label: "WTI short-term official baseline",
              units: "usd_per_barrel",
              status: "unavailable",
              points: [],
              latest_value: null,
              latest_observation_date: null,
            },
          ],
          scenarios: [],
          sensitivity: null,
          sensitivity_source: {
            kind: "manual_override",
            value: null,
            metric_basis: null,
            status: null,
            confidence_flags: [],
          },
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
            benchmark_id: "wti_short_term_baseline",
            benchmark_options: [{ value: "wti_short_term_baseline", label: "WTI" }],
            current_oil_price: 83.4,
            current_oil_price_source: "wti_spot_history",
            realized_spread_mode: "benchmark_only",
            current_realized_spread: null,
            custom_realized_spread: null,
            mean_reversion_target_spread: 0,
            mean_reversion_years: 3,
            realized_spread_reference_benchmark: "wti",
          },
          requirements: {
            strict_official_mode: false,
            manual_price_required: false,
            manual_price_reason: null,
            manual_sensitivity_required: true,
            manual_sensitivity_reason: "No disclosed or derived official oil sensitivity is cached yet.",
            price_input_mode: "cached_market_price",
            realized_spread_supported: false,
            realized_spread_reason: "v1 realized-spread controls are only supported for producer and integrated-upstream oil names.",
            realized_spread_fallback_label: "Producer-only v1 model",
          },
          direct_company_evidence: {
            status: "not_available",
            checked_at: "2026-04-04T00:00:00Z",
            parser_confidence_flags: ["realized_vs_benchmark_not_available"],
            disclosed_sensitivity: {
              status: "not_available",
              reason: "No explicit annual oil sensitivity was disclosed.",
              confidence_flags: ["oil_sensitivity_not_available"],
              provenance_sources: ["sec_edgar"],
            },
            diluted_shares: {
              status: "not_available",
              reason: "No diluted share evidence was cached.",
              confidence_flags: ["diluted_shares_not_available"],
              provenance_sources: ["sec_companyfacts"],
            },
            realized_price_comparison: {
              status: "not_available",
              reason: "No clear SEC realized-price-versus-benchmark table is cached for this producer yet.",
              benchmark: "wti",
              rows: [],
              confidence_flags: ["realized_vs_benchmark_not_available"],
              provenance_sources: ["sec_edgar"],
            },
          },
          refresh: { triggered: false, reason: "fresh", ticker: "CVX", job_id: null },
        },
      }),
    );

    expect(screen.getByText("Latest Oil Overlay Evaluation")).toBeTruthy();
    expect(screen.getByText("CVX point-in-time comparison of the base model versus base-plus-oil-overlay.")).toBeTruthy();
    expect(screen.getByText("Official EIA benchmark curves are not cached yet for the selected oil benchmark.")).toBeTruthy();
    expect(screen.getByText(/interactive overlay stays blocked until EIA inputs are available/i)).toBeTruthy();
    expect(screen.queryByLabelText("Benchmark Selector")).toBeNull();
  });
});
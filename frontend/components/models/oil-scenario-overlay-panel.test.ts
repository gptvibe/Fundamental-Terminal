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

describe("OilScenarioOverlayPanel redesigned UX", () => {
  it("defaults to simple mode and can switch to advanced mode", () => {
    renderPanel();

    expect(screen.getByRole("button", { name: "Simple View" }).className).toContain("is-active");
    expect(screen.getByText("Advanced Modeling Controls")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Advanced View" }));

    expect(screen.getByRole("button", { name: "Advanced View" }).className).toContain("is-active");
    expect(screen.getByLabelText("Fade years slider")).toBeTruthy();
  });

  it("applies scenario presets and supports scenario node editing with live output formatting", () => {
    renderPanel();

    expect(screen.getByLabelText("Oil top summary strip")).toBeTruthy();
    expect(screen.getAllByText("$100.00").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Bull" }));
    const nodeInput = screen.getByLabelText("Scenario node 2026") as HTMLInputElement;
    expect(nodeInput.value).not.toBe("80.0");

    fireEvent.change(nodeInput, { target: { value: "92.5" } });
    expect((screen.getByRole("button", { name: "Custom" }) as HTMLButtonElement).disabled).toBe(true);

    expect(screen.getAllByText(/\$\d+\.\d{2}/).length).toBeGreaterThan(0);
    expect(screen.getByText(/^\+\d+\.\d%$/)).toBeTruthy();
  });

  it("shows partial support explanatory banner and sensitivity guidance", () => {
    renderPanel({
      companySupportStatus: "partial",
      companySupportReasons: ["refining_margin_exposure_partial_v1"],
      overlay: buildOverlay({
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
        sensitivity: null,
      }) as any,
    });

    expect(screen.getByText(/Partial support: benchmark is official, but some company inputs are estimated or manual\./i)).toBeTruthy();
    expect(screen.getByLabelText("Sensitivity guidance")).toBeTruthy();
  });

  it("shows sparse official curve guidance while keeping a visual chart", () => {
    renderPanel({
      overlay: buildOverlay({
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
      }) as any,
    });

    expect(screen.getByLabelText("Oil curve preview chart")).toBeTruthy();
    expect(screen.getByText(/Official benchmark coverage is limited right now\./i)).toBeTruthy();
  });

  it("keeps exports in advanced section", () => {
    renderPanel();

    fireEvent.click(screen.getByRole("button", { name: "Advanced View" }));
    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(downloadJsonFile).toHaveBeenCalledTimes(1);
    expect(exportRowsToCsv).toHaveBeenCalledTimes(1);
    expect(showAppToast).toHaveBeenCalled();
  });
});

function renderPanel(overrides?: Partial<React.ComponentProps<typeof OilScenarioOverlayPanel>>) {
  return render(
    React.createElement(OilScenarioOverlayPanel, {
      ticker: "CVX",
      strictOfficialMode: false,
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
      priceHistory: [{ date: "2026-04-04", close: 90, volume: 1000 }],
      oilOverlayEvaluation: null,
      overlay: buildOverlay() as any,
      ...overrides,
    }),
  );
}

function buildOverlay(overrides?: Record<string, unknown>): unknown {
  return {
    company: null,
    status: "supported",
    fetched_at: "2026-04-04T00:00:00Z",
    as_of: "2026-04-04",
    last_refreshed_at: "2026-04-04T00:00:00Z",
    strict_official_mode: false,
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
      metric_basis: "after_tax_earnings",
      lookback_quarters: 8,
      elasticity: 10,
      r_squared: 0.7,
      sample_size: 8,
      direction: "positive",
      status: "ok",
      confidence_flags: [],
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
    provenance: [],
    source_mix: {
      source_ids: ["eia_steo"],
      source_tiers: ["official_statistical"],
      primary_source_ids: ["eia_steo"],
      fallback_source_ids: [],
      official_only: true,
    },
    sensitivity_source: {
      kind: "derived_from_official",
      value: 10,
      metric_basis: "after_tax_earnings",
      status: "ok",
      confidence_flags: [],
    },
    phase2_extensions: {
      downstream_offset_supported: true,
      downstream_offset_percent: 0,
      downstream_offset_reason: null,
      refiner_rac_supported: false,
      refiner_rac_reason: "pending",
      aeo_presets_supported: false,
      aeo_presets_reason: "pending",
      aeo_preset_options: [],
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
      annual_after_tax_sensitivity: 10,
      base_fair_value_per_share: 100,
      diluted_shares: 10,
      current_realized_spread: -4,
      current_realized_spread_source: "sec_realized_price_comparison",
      custom_realized_spread: -4,
      mean_reversion_target_spread: 0,
      mean_reversion_years: 2,
      realized_spread_mode: "hold_current_spread",
      realized_spread_reference_benchmark: "wti",
      current_oil_price: 77,
      current_oil_price_source: "wti_spot_history",
    },
    requirements: {
      strict_official_mode: false,
      manual_price_required: false,
      manual_price_reason: null,
      manual_sensitivity_required: false,
      manual_sensitivity_reason: null,
      price_input_mode: "cached_market_price",
      realized_spread_supported: true,
      realized_spread_reason: null,
      realized_spread_fallback_label: null,
    },
    direct_company_evidence: {
      status: "partial",
      checked_at: "2026-04-04T00:00:00Z",
      parser_confidence_flags: [],
      disclosed_sensitivity: {
        status: "available",
        benchmark: "wti",
        oil_price_change_per_bbl: 1,
        annual_after_tax_earnings_change: 10,
        annual_after_tax_sensitivity: 10,
        metric_basis: "after_tax_earnings",
        confidence_flags: [],
        provenance_sources: ["sec_edgar"],
      },
      diluted_shares: {
        status: "available",
        value: 10,
        unit: "shares",
        taxonomy: "us-gaap",
        tag: "WeightedAverageNumberOfDilutedSharesOutstanding",
        confidence_flags: [],
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
        confidence_flags: [],
        provenance_sources: ["sec_edgar"],
      },
    },
    confidence_flags: [],
    refresh: { triggered: false, reason: "fresh", ticker: "CVX", job_id: null },
    ...overrides,
  };
}

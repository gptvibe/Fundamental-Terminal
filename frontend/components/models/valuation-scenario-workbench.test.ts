// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ValuationScenarioWorkbench } from "@/components/models/valuation-scenario-workbench";

describe("ValuationScenarioWorkbench", () => {
  it("renders overlap, editable sensitivities, and traceability for valuation models", () => {
    render(
      React.createElement(ValuationScenarioWorkbench, {
        ticker: "ACME",
        models: [
          {
            model_name: "dcf",
            model_version: "2.2.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              fair_value_per_share: 112,
              enterprise_value: 11200,
              equity_value: 10500,
              net_debt: 700,
              assumptions: {
                discount_rate: 0.1,
                terminal_growth_rate: 0.025,
                starting_growth_rate: 0.08,
                projection_years: 5,
              },
              assumption_provenance: {
                risk_free_rate: {
                  source_name: "U.S. Treasury",
                  observation_date: "2026-03-21",
                },
              },
              fields_used: ["revenue", "free_cash_flow"],
              confidence_reasons: ["Core model inputs were available without a blocking sector constraint."],
              proxy_usage: { used: false, items: [] },
              stale_inputs: [],
              sector_suitability: { status: "supported", reason: "Model is broadly suitable for this issuer." },
              misleading_reasons: ["Terminal assumptions can dominate the valuation."],
            },
          },
          {
            model_name: "reverse_dcf",
            model_version: "1.1.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              implied_margin: 0.12,
              assumption_provenance: {
                discount_rate_inputs: {
                  discount_rate: 0.11,
                  terminal_growth: 0.025,
                },
                price_snapshot: {
                  latest_price: 100,
                  price_source: "Yahoo Finance",
                },
              },
              price_snapshot: {
                latest_price: 100,
                price_source: "Yahoo Finance",
              },
              fields_used: ["revenue", "market_snapshot.latest_price"],
              confidence_reasons: ["Core model inputs were available without a blocking sector constraint."],
              proxy_usage: { used: false, items: [] },
              stale_inputs: [],
              sector_suitability: { status: "supported", reason: "Model is broadly suitable for this issuer." },
              misleading_reasons: ["Market prices can imply implausible growth if current sentiment is extreme."],
            },
          },
          {
            model_name: "residual_income",
            model_version: "1.0.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              primary_for_sector: false,
              inputs: {
                book_equity: 700,
                avg_roe_5y: 0.14,
                cost_of_equity: 0.095,
                terminal_growth_rate: 0.025,
                payout_ratio_assumed: 0.35,
                shares_outstanding: 100,
              },
              intrinsic_value: {
                intrinsic_value_per_share: 112,
              },
              assumption_provenance: {
                risk_free_rate: {
                  source_name: "U.S. Treasury",
                },
              },
              fields_used: ["net_income", "stockholders_equity"],
              confidence_reasons: ["Core model inputs were available without a blocking sector constraint."],
              proxy_usage: { used: false, items: [] },
              stale_inputs: [],
              sector_suitability: { status: "supported", reason: "Residual income is suitable for this issuer." },
              misleading_reasons: ["Residual income is sensitive to book-value quality and fade assumptions."],
            },
          },
        ],
        financials: [
          {
            filing_type: "10-K",
            statement_type: "annual",
            period_start: "2025-01-01",
            period_end: "2025-12-31",
            source: "sec",
            last_updated: "2026-03-21T00:00:00Z",
            last_checked: "2026-03-21T00:00:00Z",
            revenue: 1000,
            operating_income: 180,
            net_income: 120,
            interest_expense: 20,
            income_tax_expense: 30,
            total_assets: 1500,
            total_liabilities: 800,
            operating_cash_flow: 190,
            free_cash_flow: 140,
            eps: 1.2,
            shares_outstanding: 100,
            weighted_average_diluted_shares: 100,
            segment_breakdown: [],
          },
          {
            filing_type: "10-K",
            statement_type: "annual",
            period_start: "2024-01-01",
            period_end: "2024-12-31",
            source: "sec",
            last_updated: "2025-03-21T00:00:00Z",
            last_checked: "2025-03-21T00:00:00Z",
            revenue: 920,
            operating_income: 160,
            net_income: 110,
            interest_expense: 18,
            income_tax_expense: 28,
            total_assets: 1400,
            total_liabilities: 760,
            operating_cash_flow: 170,
            free_cash_flow: 125,
            eps: 1.1,
            shares_outstanding: 100,
            weighted_average_diluted_shares: 100,
            segment_breakdown: [],
          },
        ] as never,
        priceHistory: [{ date: "2026-03-21", close: 100, volume: 1000 }],
      })
    );

    expect(screen.getByText("Per-share valuation overlap")).toBeTruthy();
    expect(screen.getByRole("tab", { name: /^DCFSupported$/i })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /^Reverse DCFSupported$/i })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /^Residual IncomeSupported$/i })).toBeTruthy();
    expect(screen.getByText("Interactive Scenario Builder")).toBeTruthy();
    expect(screen.getByText("Assumption lineage")).toBeTruthy();
    expect(screen.getByText("Exact fields used")).toBeTruthy();
    expect(screen.getAllByText("revenue").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Revenue Growth Rate")).toBeTruthy();
    expect(screen.getByLabelText("WACC")).toBeTruthy();
    expect(screen.getByText("Sensitivity table")).toBeTruthy();

    const fairValueBefore = screen.getByTestId("dcf-scenario-after-fair-value").textContent;
    fireEvent.change(screen.getByLabelText("WACC"), { target: { value: "11" } });

    expect(screen.getByText("Assumptions changed")).toBeTruthy();
    expect(screen.getByTestId("dcf-scenario-after-fair-value").textContent).not.toBe(fairValueBefore);

    fireEvent.click(screen.getByRole("tab", { name: /^Reverse DCFSupported$/i }));

    expect(screen.getByText("Implied growth range")).toBeTruthy();
    expect(screen.getByLabelText("Free Cash Flow Margin")).toBeTruthy();
    expect(screen.getByText("Price Anchor")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: /^Residual IncomeSupported$/i }));

    expect(screen.getByText("Residual income bear / base / bull range")).toBeTruthy();
    expect(screen.getByLabelText("Average ROE")).toBeTruthy();
    expect(screen.getByText("Book Equity / Share")).toBeTruthy();
  });

  it("suppresses interactive DCF controls when the backend marks DCF as insufficient data", () => {
    render(
      React.createElement(ValuationScenarioWorkbench, {
        ticker: "CVX",
        models: [
          {
            model_name: "dcf",
            model_version: "2.2.0",
            created_at: "2026-04-04T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "insufficient_data",
              fair_value_per_share: -366.47,
              enterprise_value: -636756971013.88,
              equity_value: -680170971013.88,
              net_debt: 43414000000,
              explanation: "Required base inputs were not sufficient to produce a directional output.",
              assumptions: {
                discount_rate: 0.0938,
                terminal_growth_rate: 0.0203,
                starting_growth_rate: -0.1,
                projection_years: 5,
              },
              historical_free_cash_flow: [{ period_end: "2025-12-31", free_cash_flow: -57629000000 }],
            },
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
            revenue: 1000,
            operating_income: 180,
            net_income: 120,
            interest_expense: 20,
            income_tax_expense: 30,
            total_assets: 1500,
            total_liabilities: 800,
            operating_cash_flow: 190,
            free_cash_flow: 140,
            eps: 1.2,
            shares_outstanding: 100,
            weighted_average_diluted_shares: 100,
            segment_breakdown: [],
          },
        ] as never,
        priceHistory: [{ date: "2026-04-04", close: 100, volume: 1000 }],
      })
    );

    expect(screen.getByText("DCF scenario analysis unavailable")).toBeTruthy();
    expect(screen.getByText("Required base inputs were not sufficient to produce a directional output.")).toBeTruthy();
    expect(screen.queryByLabelText("WACC")).toBeNull();
    expect(screen.queryByText("Sensitivity table")).toBeNull();
  });
});

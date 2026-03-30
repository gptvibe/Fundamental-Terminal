// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BankRegulatoryOverview } from "@/components/company/bank-regulatory-overview";
import type { FinancialPayload } from "@/lib/types";

function makeBankFinancial(periodEnd: string, overrides?: Partial<FinancialPayload>): FinancialPayload {
  return {
    filing_type: "CALL",
    statement_type: "canonical_bank_regulatory",
    period_start: `${periodEnd.slice(0, 4)}-01-01`,
    period_end: periodEnd,
    source: "https://fdic.example/bank",
    last_updated: "2026-03-30T00:00:00Z",
    last_checked: "2026-03-30T00:00:00Z",
    revenue: null,
    gross_profit: null,
    operating_income: null,
    net_income: 200,
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
    accounts_receivable: null,
    accounts_payable: null,
    goodwill_and_intangibles: null,
    cash_and_cash_equivalents: null,
    short_term_investments: null,
    cash_and_short_term_investments: null,
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
    shares_outstanding: null,
    stock_based_compensation: null,
    weighted_average_diluted_shares: null,
    segment_breakdown: [],
    reconciliation: null,
    regulated_bank: {
      source_id: "fdic_bankfind_financials",
      reporting_basis: "fdic_call_report",
      confidence_score: 0.95,
      confidence_flags: [],
      net_interest_income: 1200,
      noninterest_income: 400,
      noninterest_expense: 900,
      pretax_income: 500,
      provision_for_credit_losses: 200,
      deposits_total: 80000,
      core_deposits: 60000,
      uninsured_deposits: 12000,
      loans_net: 55000,
      net_interest_margin: 0.038,
      nonperforming_assets_ratio: 0.011,
      common_equity_tier1_ratio: 0.121,
      tier1_risk_weighted_ratio: 0.133,
      total_risk_based_capital_ratio: 0.149,
      return_on_assets_ratio: 0.011,
      return_on_equity_ratio: 0.124,
      tangible_common_equity: 9000,
    },
    ...overrides,
  };
}

describe("BankRegulatoryOverview", () => {
  it("shows selected, compare, and trend state for regulated-bank snapshots", () => {
    const selected = makeBankFinancial("2025-12-31");
    const comparisonBase = makeBankFinancial("2024-12-31");
    const comparison = makeBankFinancial("2024-12-31", {
      regulated_bank: {
        ...comparisonBase.regulated_bank!,
        net_interest_margin: 0.035,
        common_equity_tier1_ratio: 0.116,
        deposits_total: 78000,
        tangible_common_equity: 8600,
      },
    });

    render(
      React.createElement(BankRegulatoryOverview, {
        latestFinancial: selected,
        financials: [selected, comparison],
        selectedFinancial: selected,
        comparisonFinancial: comparison,
      })
    );

    expect(screen.getByText("supports_selected_period")).toBeTruthy();
    expect(screen.getByText("supports_compare_mode")).toBeTruthy();
    expect(screen.getByText("supports_trend_mode")).toBeTruthy();
    expect(screen.getByText("NIM Delta")).toBeTruthy();
    expect(screen.getByText(/Focus CALL 2025-12-31/i)).toBeTruthy();
    expect(screen.getByText(/Compare CALL 2024-12-31/i)).toBeTruthy();
    expect(screen.getByText("Sparklines")).toBeTruthy();

    fireEvent.click(screen.getByText("Trend Table"));

    expect(screen.getAllByText("Provision Burden").length).toBeGreaterThan(0);
  });
});

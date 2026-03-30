// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FinancialQualitySummary } from "@/components/company/financial-quality-summary";
import type { FinancialPayload } from "@/lib/types";

function makeFinancial(partial: Partial<FinancialPayload>): FinancialPayload {
  return {
    filing_type: partial.filing_type ?? "10-K",
    statement_type: partial.statement_type ?? "canonical_xbrl",
    period_start: partial.period_start ?? "2025-01-01",
    period_end: partial.period_end ?? "2025-12-31",
    source: partial.source ?? "https://sec.example/financials",
    last_updated: partial.last_updated ?? "2026-03-30T00:00:00Z",
    last_checked: partial.last_checked ?? "2026-03-30T00:00:00Z",
    revenue: partial.revenue ?? null,
    gross_profit: partial.gross_profit ?? null,
    operating_income: partial.operating_income ?? null,
    net_income: partial.net_income ?? null,
    total_assets: partial.total_assets ?? null,
    current_assets: partial.current_assets ?? null,
    total_liabilities: partial.total_liabilities ?? null,
    current_liabilities: partial.current_liabilities ?? null,
    retained_earnings: partial.retained_earnings ?? null,
    sga: partial.sga ?? null,
    research_and_development: partial.research_and_development ?? null,
    interest_expense: partial.interest_expense ?? null,
    income_tax_expense: partial.income_tax_expense ?? null,
    inventory: partial.inventory ?? null,
    accounts_receivable: partial.accounts_receivable ?? null,
    accounts_payable: partial.accounts_payable ?? null,
    goodwill_and_intangibles: partial.goodwill_and_intangibles ?? null,
    cash_and_cash_equivalents: partial.cash_and_cash_equivalents ?? null,
    short_term_investments: partial.short_term_investments ?? null,
    cash_and_short_term_investments: partial.cash_and_short_term_investments ?? null,
    current_debt: partial.current_debt ?? null,
    long_term_debt: partial.long_term_debt ?? null,
    stockholders_equity: partial.stockholders_equity ?? null,
    lease_liabilities: partial.lease_liabilities ?? null,
    operating_cash_flow: partial.operating_cash_flow ?? null,
    depreciation_and_amortization: partial.depreciation_and_amortization ?? null,
    capex: partial.capex ?? null,
    acquisitions: partial.acquisitions ?? null,
    debt_changes: partial.debt_changes ?? null,
    dividends: partial.dividends ?? null,
    share_buybacks: partial.share_buybacks ?? null,
    free_cash_flow: partial.free_cash_flow ?? null,
    eps: partial.eps ?? null,
    shares_outstanding: partial.shares_outstanding ?? null,
    stock_based_compensation: partial.stock_based_compensation ?? null,
    weighted_average_diluted_shares: partial.weighted_average_diluted_shares ?? null,
    regulated_bank: partial.regulated_bank ?? null,
    segment_breakdown: partial.segment_breakdown ?? [],
    reconciliation: partial.reconciliation ?? null,
  };
}

describe("FinancialQualitySummary", () => {
  it("shows selected, compare, and trend state with annual fallback warnings", () => {
    const annual2025 = makeFinancial({
      period_end: "2025-12-31",
      revenue: 1200,
      gross_profit: 600,
      operating_income: 320,
      free_cash_flow: 240,
      total_liabilities: 900,
      total_assets: 2400,
      net_income: 210,
      shares_outstanding: 100,
    });
    const annual2024 = makeFinancial({
      period_end: "2024-12-31",
      revenue: 1000,
      gross_profit: 500,
      operating_income: 250,
      free_cash_flow: 180,
      total_liabilities: 920,
      total_assets: 2200,
      net_income: 180,
      shares_outstanding: 104,
    });
    const annual2023 = makeFinancial({
      period_end: "2023-12-31",
      revenue: 920,
      gross_profit: 430,
      operating_income: 220,
      free_cash_flow: 160,
      total_liabilities: 910,
      total_assets: 2100,
      net_income: 160,
      shares_outstanding: 106,
    });
    const quarterly2025 = makeFinancial({
      filing_type: "10-Q",
      period_start: "2025-10-01",
      period_end: "2025-12-31",
      revenue: 320,
    });

    render(
      React.createElement(FinancialQualitySummary, {
        financials: [annual2025, annual2024, annual2023, quarterly2025],
        visibleFinancials: [annual2025, annual2024, annual2023],
        selectedFinancial: quarterly2025,
        comparisonFinancial: annual2024,
      })
    );

    expect(screen.getByText("supports_selected_period")).toBeTruthy();
    expect(screen.getByText("supports_compare_mode")).toBeTruthy();
    expect(screen.getByText("supports_trend_mode")).toBeTruthy();
    expect(screen.getByText(/Annual fallback applied/i)).toBeTruthy();
    expect(screen.getByText(/Focus 10-K 2025/i)).toBeTruthy();
    expect(screen.getByText(/Compare 10-K 2024/i)).toBeTruthy();
    expect(screen.getByText("Operating Margin Delta")).toBeTruthy();
    expect(screen.getByText("Sparklines")).toBeTruthy();

    fireEvent.click(screen.getByText("Trend Table"));

    expect(screen.getByText("10-K 2023")).toBeTruthy();
  });
});

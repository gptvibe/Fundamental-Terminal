import { describe, expect, it } from "vitest";

import { resolveAnnualFinancialScope } from "@/lib/annual-financial-scope";
import type { FinancialPayload } from "@/lib/types";

function statement(periodEnd: string, filingType: string): FinancialPayload {
  return {
    period_start: `${periodEnd.slice(0, 4)}-01-01`,
    period_end: periodEnd,
    filing_type: filingType,
    statement_type: "consolidated",
    source: "test",
    revenue: 100,
    gross_profit: 40,
    operating_income: 20,
    net_income: 10,
    eps: 1,
    operating_cash_flow: 15,
    free_cash_flow: 12,
    total_assets: 300,
    current_assets: 120,
    total_liabilities: 180,
    current_liabilities: 60,
    retained_earnings: 50,
    sga: 10,
    research_and_development: 5,
    interest_expense: 2,
    income_tax_expense: 3,
    inventory: 4,
    accounts_receivable: 5,
    goodwill_and_intangibles: 6,
    long_term_debt: 40,
    lease_liabilities: 10,
    shares_outstanding: 100,
    weighted_average_diluted_shares: 100,
    stock_based_compensation: 1,
    capex: 3,
    acquisitions: 0,
    debt_changes: 0,
    dividends: 0,
    share_buybacks: 0,
    segment_breakdown: [],
  } as FinancialPayload;
}

describe("resolveAnnualFinancialScope", () => {
  const financials = [
    statement("2024-12-31", "10-K"),
    statement("2024-09-30", "10-Q"),
    statement("2023-12-31", "10-K"),
    statement("2023-09-30", "10-Q"),
    statement("2022-12-31", "10-K"),
  ];

  it("maps quarterly custom comparison to the matching annual filing", () => {
    const scope = resolveAnnualFinancialScope({
      financials,
      visibleFinancials: [financials[1], financials[3]],
      selectedFinancial: financials[1],
      comparisonFinancial: financials[3],
    });

    expect(scope.selectedAnnual?.period_end).toBe("2024-12-31");
    expect(scope.comparisonAnnual?.period_end).toBe("2023-12-31");
    expect(scope.usedSelectedAnnualFallback).toBe(true);
    expect(scope.usedComparisonAnnualFallback).toBe(true);
  });

  it("keeps the full visible annual range instead of truncating it", () => {
    const scope = resolveAnnualFinancialScope({
      financials,
      visibleFinancials: [financials[0], financials[2], financials[4]],
      selectedFinancial: financials[0],
      comparisonFinancial: null,
    });

    expect(scope.scopedAnnuals.map((item) => item.period_end)).toEqual([
      "2024-12-31",
      "2023-12-31",
      "2022-12-31",
    ]);
  });

  it("does not silently substitute a previous annual when custom compare collapses to the same fiscal year", () => {
    const scope = resolveAnnualFinancialScope({
      financials,
      visibleFinancials: [financials[0], financials[1]],
      selectedFinancial: financials[0],
      comparisonFinancial: financials[1],
    });

    expect(scope.comparisonAnnual).toBeNull();
    expect(scope.comparisonCollapsedToSelected).toBe(true);
  });
});
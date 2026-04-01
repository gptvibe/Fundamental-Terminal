import { describe, expect, it } from "vitest";

import { buildWindowedSeries, downsampleSeries, filterSeriesByTimeframe, selectFinancialSeriesByCadence } from "@/lib/chart-windowing";
import type { FinancialPayload } from "@/lib/types";

describe("chart windowing", () => {
  it("filters a date series to the selected trailing window without mutating the source array", () => {
    const source = [
      { date: "2020-01-01", value: 10 },
      { date: "2021-01-01", value: 11 },
      { date: "2022-01-01", value: 12 },
      { date: "2023-01-01", value: 13 },
      { date: "2024-01-01", value: 14 },
    ];

    const result = filterSeriesByTimeframe(source, "3y", { getDate: (point) => point.date });

    expect(result).toEqual([
      { date: "2021-01-01", value: 11 },
      { date: "2022-01-01", value: 12 },
      { date: "2023-01-01", value: 13 },
      { date: "2024-01-01", value: 14 },
    ]);
    expect(result).not.toBe(source);
    expect(source).toHaveLength(5);
  });

  it("downsamples large series while preserving the first and last points", () => {
    const source = Array.from({ length: 12 }, (_, index) => ({ point: index }));

    const result = downsampleSeries(source, 5);

    expect(result).toHaveLength(5);
    expect(result[0]).toEqual({ point: 0 });
    expect(result[result.length - 1]).toEqual({ point: 11 });
  });

  it("builds derived TTM rows from quarterly filings and preserves period labels", () => {
    const quarterlyFinancials = [
      createFinancialPayload("2023-03-31", "10-Q", 100, 10, 7),
      createFinancialPayload("2023-06-30", "10-Q", 110, 11, 8),
      createFinancialPayload("2023-09-30", "10-Q", 120, 12, 9),
      createFinancialPayload("2023-12-31", "10-Q", 130, 13, 10),
      createFinancialPayload("2024-03-31", "10-Q", 140, 14, 11),
    ];

    const result = selectFinancialSeriesByCadence(quarterlyFinancials, "ttm");

    expect(result.map((statement) => ({
      filing_type: statement.filing_type,
      period_end: statement.period_end,
      revenue: statement.revenue,
      net_income: statement.net_income,
      free_cash_flow: statement.free_cash_flow,
    }))).toEqual([
      {
        filing_type: "TTM",
        period_end: "2023-12-31",
        revenue: 460,
        net_income: 46,
        free_cash_flow: 34,
      },
      {
        filing_type: "TTM",
        period_end: "2024-03-31",
        revenue: 500,
        net_income: 50,
        free_cash_flow: 38,
      },
    ]);
  });

  it("applies range filtering before downsampling", () => {
    const source = [
      { date: "2019-01-01", value: 1 },
      { date: "2020-01-01", value: 2 },
      { date: "2021-01-01", value: 3 },
      { date: "2022-01-01", value: 4 },
      { date: "2023-01-01", value: 5 },
      { date: "2024-01-01", value: 6 },
      { date: "2025-01-01", value: 7 },
    ];

    const result = buildWindowedSeries(source, {
      timeframeMode: "3y",
      getDate: (point) => point.date,
      maxPoints: 2,
    });

    expect(result).toEqual([
      { date: "2022-01-01", value: 4 },
      { date: "2025-01-01", value: 7 },
    ]);
  });
});

function createFinancialPayload(
  periodEnd: string,
  filingType: string,
  revenue: number,
  netIncome: number,
  freeCashFlow: number
): FinancialPayload {
  return {
    filing_type: filingType,
    statement_type: "income_statement",
    period_start: `${periodEnd.slice(0, 4)}-01-01`,
    period_end: periodEnd,
    source: "https://example.com",
    last_updated: `${periodEnd}T00:00:00Z`,
    last_checked: `${periodEnd}T00:00:00Z`,
    revenue,
    gross_profit: null,
    operating_income: null,
    net_income: netIncome,
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
    free_cash_flow: freeCashFlow,
    eps: null,
    shares_outstanding: null,
    stock_based_compensation: null,
    weighted_average_diluted_shares: null,
    regulated_bank: null,
    segment_breakdown: [],
    reconciliation: null,
  };
}
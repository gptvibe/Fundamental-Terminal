import { describe, expect, it } from "vitest";

import { buildCapitalMarketsSignalSeries, buildOperatingCostSeries } from "@/lib/financial-chart-transforms";
import type { FilingEventPayload, FinancialPayload } from "@/lib/types";

function makeFinancial(partial: Partial<FinancialPayload>): FinancialPayload {
  return {
    filing_type: partial.filing_type ?? "10-K",
    statement_type: partial.statement_type ?? "canonical",
    period_start: partial.period_start ?? "2025-01-01",
    period_end: partial.period_end ?? "2025-12-31",
    source: partial.source ?? "https://sec.example",
    last_updated: partial.last_updated ?? "2026-01-01T00:00:00Z",
    last_checked: partial.last_checked ?? "2026-01-01T00:00:00Z",
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
    goodwill_and_intangibles: partial.goodwill_and_intangibles ?? null,
    long_term_debt: partial.long_term_debt ?? null,
    lease_liabilities: partial.lease_liabilities ?? null,
    operating_cash_flow: partial.operating_cash_flow ?? null,
    capex: partial.capex ?? null,
    acquisitions: partial.acquisitions ?? null,
    debt_changes: partial.debt_changes ?? null,
    share_buybacks: partial.share_buybacks ?? null,
    dividends: partial.dividends ?? null,
    free_cash_flow: partial.free_cash_flow ?? null,
    eps: partial.eps ?? null,
    shares_outstanding: partial.shares_outstanding ?? null,
    stock_based_compensation: partial.stock_based_compensation ?? null,
    weighted_average_diluted_shares: partial.weighted_average_diluted_shares ?? null,
    segment_breakdown: partial.segment_breakdown ?? [],
  };
}

function makeEvent(partial: Partial<FilingEventPayload>): FilingEventPayload {
  return {
    accession_number: partial.accession_number ?? null,
    form: partial.form ?? "8-K",
    filing_date: partial.filing_date ?? null,
    report_date: partial.report_date ?? null,
    items: partial.items ?? null,
    category: partial.category ?? "Other",
    primary_document: partial.primary_document ?? null,
    primary_doc_description: partial.primary_doc_description ?? null,
    source_url: partial.source_url ?? "https://sec.example/event",
    summary: partial.summary ?? "event",
  };
}

describe("financial chart transforms", () => {
  it("buildOperatingCostSeries sorts by period and keeps mapped cost fields", () => {
    const rows = buildOperatingCostSeries([
      makeFinancial({ period_end: "2025-12-31", sga: 100, stock_based_compensation: 10 }),
      makeFinancial({ period_end: "2024-12-31", research_and_development: 55, income_tax_expense: 14 }),
      makeFinancial({ period_end: "2023-12-31" }),
    ]);

    expect(rows).toHaveLength(2);
    expect(rows[0].periodEnd).toBe("2024-12-31");
    expect(rows[0].researchAndDevelopment).toBe(55);
    expect(rows[1].periodEnd).toBe("2025-12-31");
    expect(rows[1].sga).toBe(100);
    expect(rows[1].stockBasedCompensation).toBe(10);
  });

  it("buildCapitalMarketsSignalSeries aligns financing events to annual statement years", () => {
    const rows = buildCapitalMarketsSignalSeries(
      [
        makeFinancial({ filing_type: "10-K", period_end: "2024-12-31", debt_changes: -20 }),
        makeFinancial({ filing_type: "10-K", period_end: "2025-12-31", debt_changes: 35 }),
      ],
      [
        makeEvent({ category: "Financing", filing_date: "2025-01-10" }),
        makeEvent({ category: "Capital Markets", report_date: "2025-07-11" }),
        makeEvent({ category: "Deal", filing_date: "2025-05-09" }),
      ]
    );

    expect(rows).toEqual([
      { period: "2024", financingEvents: 0, debtChanges: -20 },
      { period: "2025", financingEvents: 2, debtChanges: 35 },
    ]);
  });
});

// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FinancialStatementChangeHeatmap } from "@/components/company/financial-statement-change-heatmap";
import type { FinancialPayload } from "@/lib/types";

function makeStatement(periodEnd: string, filingType: string, revenue: number, assets: number, operatingCashFlow: number): FinancialPayload {
  return {
    filing_type: filingType,
    statement_type: "canonical_xbrl",
    period_start: `${periodEnd.slice(0, 4)}-01-01`,
    period_end: periodEnd,
    source: `https://www.sec.gov/Archives/edgar/data/1/${periodEnd.replaceAll("-", "")}.htm`,
    last_updated: "2026-04-26T00:00:00Z",
    last_checked: "2026-04-26T00:00:00Z",
    revenue,
    gross_profit: Math.round(revenue * 0.5),
    operating_income: Math.round(revenue * 0.2),
    net_income: Math.round(revenue * 0.12),
    total_assets: assets,
    current_assets: Math.round(assets * 0.35),
    total_liabilities: Math.round(assets * 0.52),
    current_liabilities: Math.round(assets * 0.18),
    retained_earnings: 100_000_000,
    sga: Math.round(revenue * 0.12),
    research_and_development: Math.round(revenue * 0.08),
    interest_expense: 35_000_000,
    income_tax_expense: 45_000_000,
    inventory: 60_000_000,
    cash_and_cash_equivalents: 80_000_000,
    short_term_investments: 20_000_000,
    cash_and_short_term_investments: 100_000_000,
    accounts_receivable: 70_000_000,
    accounts_payable: 55_000_000,
    goodwill_and_intangibles: 120_000_000,
    current_debt: 45_000_000,
    long_term_debt: 260_000_000,
    stockholders_equity: 540_000_000,
    lease_liabilities: 30_000_000,
    operating_cash_flow: operatingCashFlow,
    depreciation_and_amortization: 55_000_000,
    capex: 65_000_000,
    acquisitions: 0,
    debt_changes: 10_000_000,
    dividends: 14_000_000,
    share_buybacks: 8_000_000,
    free_cash_flow: operatingCashFlow - 65_000_000,
    eps: 2.2,
    shares_outstanding: 100_000_000,
    stock_based_compensation: 20_000_000,
    weighted_average_diluted_shares: 99_500_000,
    regulated_bank: null,
    segment_breakdown: [],
    reconciliation: null,
  };
}

describe("FinancialStatementChangeHeatmap", () => {
  it("renders statement toggles, mode toggles, and source-linked heatmap cells", () => {
    const financials = [
      makeStatement("2025-12-31", "10-K", 1_000_000_000, 2_000_000_000, 230_000_000),
      makeStatement("2024-12-31", "10-K", 920_000_000, 1_820_000_000, 205_000_000),
      makeStatement("2023-12-31", "10-K", 880_000_000, 1_760_000_000, 190_000_000),
    ];

    render(React.createElement(FinancialStatementChangeHeatmap, { financials }));

    expect(screen.getByRole("button", { name: "Income Statement" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Balance Sheet" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cash Flow" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Absolute Change" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Percent Change" })).toBeTruthy();

    expect(screen.getByText("Rows: 9")).toBeTruthy();
    expect(screen.getByText("Columns: 3")).toBeTruthy();

    const anchors = screen.getAllByRole("link");
    expect(anchors.length).toBeGreaterThan(0);
    expect(anchors[0]?.getAttribute("href")).toContain("sec.gov/Archives/edgar/data/1");

    fireEvent.click(screen.getByRole("button", { name: "Percent Change" }));
    expect(screen.getAllByText(/%/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Balance Sheet" }));
    expect(screen.getByText("Total Assets")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Cash Flow" }));
    expect(screen.getByText("Operating Cash Flow")).toBeTruthy();
  });

  it("shows an explanatory state when less than two periods are available", () => {
    const financials = [makeStatement("2025-12-31", "10-K", 1_000_000_000, 2_000_000_000, 230_000_000)];

    render(React.createElement(FinancialStatementChangeHeatmap, { financials }));

    expect(screen.getByText("Need at least two comparable fiscal periods to render the change heatmap.")).toBeTruthy();
  });
});

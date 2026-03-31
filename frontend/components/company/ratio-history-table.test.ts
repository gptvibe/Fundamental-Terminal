// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RatioHistoryTable } from "@/components/company/ratio-history-table";
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

describe("RatioHistoryTable", () => {
  it("renders annual ratio history from the visible range with tone-coded cells", () => {
    const annual2025 = makeFinancial({
      period_end: "2025-12-31",
      revenue: 1200,
      gross_profit: 600,
      operating_income: 330,
      net_income: 210,
      free_cash_flow: 240,
      total_assets: 2400,
      total_liabilities: 900,
      stockholders_equity: 1500,
      current_assets: 680,
      current_liabilities: 340,
    });
    const annual2024 = makeFinancial({
      period_end: "2024-12-31",
      revenue: 1000,
      gross_profit: 470,
      operating_income: 240,
      net_income: 180,
      free_cash_flow: 180,
      total_assets: 2200,
      total_liabilities: 920,
      stockholders_equity: 1280,
      current_assets: 620,
      current_liabilities: 310,
    });
    const annual2023 = makeFinancial({
      period_end: "2023-12-31",
      revenue: 920,
      gross_profit: 400,
      operating_income: 210,
      net_income: 160,
      free_cash_flow: null,
      total_assets: 2100,
      total_liabilities: 980,
      stockholders_equity: 1120,
      current_assets: 570,
      current_liabilities: 0,
    });
    const annual2022 = makeFinancial({
      period_end: "2022-12-31",
      revenue: 860,
      gross_profit: 360,
      operating_income: 180,
      net_income: 140,
      free_cash_flow: 120,
      total_assets: 1980,
      total_liabilities: 990,
      stockholders_equity: 990,
      current_assets: 500,
      current_liabilities: 280,
    });
    const quarterly2025 = makeFinancial({
      filing_type: "10-Q",
      period_start: "2025-10-01",
      period_end: "2025-12-31",
      revenue: 320,
    });

    const { container } = render(
      React.createElement(RatioHistoryTable, {
        financials: [annual2025, annual2024, annual2023, annual2022, quarterly2025],
        visibleFinancials: [annual2025, annual2024, annual2023],
        selectedFinancial: quarterly2025,
        comparisonFinancial: annual2024,
      })
    );

    expect(screen.getByText(/Focus 10-K 2025/i)).toBeTruthy();
    expect(screen.getByText(/Compare 10-K 2024/i)).toBeTruthy();
    expect(screen.getByText(/Annual fallback applied/i)).toBeTruthy();
    expect(screen.getByText("Annual periods 3")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Ratio history table" })).toBeTruthy();
    expect(screen.getByText("10-K 2023")).toBeTruthy();
    expect(screen.getByText("10-K 2024")).toBeTruthy();
    expect(screen.getByText("10-K 2025")).toBeTruthy();
    expect(screen.queryByText("10-K 2022")).toBeNull();
    expect(screen.getByText("Revenue Growth YoY")).toBeTruthy();
    expect(screen.getByText("Current Ratio")).toBeTruthy();

    const improvedGrossMarginCell = container.querySelector('[data-ratio-key="grossMargin"] [data-period-key="2024-12-31|10-K"] [data-tone="positive"]');
    const improvedDebtCell = container.querySelector('[data-ratio-key="debtToAssets"] [data-period-key="2024-12-31|10-K"] [data-tone="positive"]');
    const unavailableCurrentRatioCell = container.querySelector('[data-ratio-key="currentRatio"] [data-period-key="2023-12-31|10-K"] [data-tone="na"]');

    expect(improvedGrossMarginCell?.textContent).toBe("47.00%");
    expect(improvedDebtCell?.textContent).toBe("41.82%");
    expect(unavailableCurrentRatioCell?.textContent).toBe("—");
  });

  it("maps quarterly selections into annual ratio math and keeps the visible annual range", () => {
    const annual2025 = makeFinancial({
      period_end: "2025-12-31",
      revenue: 1200,
      gross_profit: 600,
      operating_income: 330,
      net_income: 210,
      free_cash_flow: 240,
      total_assets: 2400,
      total_liabilities: 900,
      stockholders_equity: 1500,
      current_assets: 680,
      current_liabilities: 340,
    });
    const annual2024 = makeFinancial({
      period_end: "2024-12-31",
      revenue: 1000,
      gross_profit: 470,
      operating_income: 240,
      net_income: 180,
      free_cash_flow: 180,
      total_assets: 2200,
      total_liabilities: 920,
      stockholders_equity: 1280,
      current_assets: 620,
      current_liabilities: 310,
    });
    const annual2023 = makeFinancial({
      period_end: "2023-12-31",
      revenue: 920,
      gross_profit: 400,
      operating_income: 210,
      net_income: 160,
      free_cash_flow: 140,
      total_assets: 2100,
      total_liabilities: 980,
      stockholders_equity: 1120,
      current_assets: 570,
      current_liabilities: 300,
    });
    const quarterly2025 = makeFinancial({
      filing_type: "10-Q",
      period_start: "2025-10-01",
      period_end: "2025-12-31",
      revenue: 320,
    });
    const quarterly2024 = makeFinancial({
      filing_type: "10-Q",
      period_start: "2024-10-01",
      period_end: "2024-12-31",
      revenue: 280,
    });

    const { container } = render(
      React.createElement(RatioHistoryTable, {
        financials: [annual2025, annual2024, annual2023, quarterly2025, quarterly2024],
        visibleFinancials: [annual2025, annual2024, annual2023],
        selectedFinancial: quarterly2025,
        comparisonFinancial: quarterly2024,
      })
    );

    expect(screen.getByText(/Annual fallback applied/i)).toBeTruthy();
    expect(screen.getByText(/Comparison mapped to fiscal year/i)).toBeTruthy();

    const debtToAssets2025Cell = container.querySelector('[data-ratio-key="debtToAssets"] [data-period-key="2025-12-31|10-K"]');
    const currentRatio2025Cell = container.querySelector('[data-ratio-key="currentRatio"] [data-period-key="2025-12-31|10-K"]');
    const revenueGrowth2025Cell = container.querySelector('[data-ratio-key="revenueGrowth"] [data-period-key="2025-12-31|10-K"]');

    expect(debtToAssets2025Cell?.textContent).toBe("37.50%");
    expect(currentRatio2025Cell?.textContent).toBe("2.00x");
    expect(revenueGrowth2025Cell?.textContent).toBe("20.00%");
  });
});
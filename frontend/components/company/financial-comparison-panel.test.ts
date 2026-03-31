// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FinancialComparisonPanel } from "@/components/company/financial-comparison-panel";
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
    segment_breakdown: partial.segment_breakdown ?? [],
    regulated_bank: partial.regulated_bank ?? null,
    reconciliation: partial.reconciliation ?? null,
  };
}

describe("FinancialComparisonPanel", () => {
  it("uses shared selected and comparison state with annual fallback and formats missing fields safely", () => {
    const annual2025 = makeFinancial({ period_end: "2025-12-31", revenue: 1_200_000_000, net_income: 240_000_000, eps: 2.4, shares_outstanding: 100_000_000 });
    const annual2024 = makeFinancial({ period_end: "2024-12-31", revenue: 1_000_000_000, net_income: 180_000_000, eps: 1.9, shares_outstanding: 102_000_000 });
    const annual2023 = makeFinancial({ period_end: "2023-12-31", revenue: 920_000_000, gross_profit: 400_000_000 });
    const quarterly2025 = makeFinancial({ filing_type: "10-Q", period_start: "2025-10-01", period_end: "2025-12-31", revenue: 320_000_000 });

    render(
      React.createElement(FinancialComparisonPanel, {
        financials: [annual2025, annual2024, annual2023, quarterly2025],
        visibleFinancials: [annual2025, annual2024, annual2023],
        selectedFinancial: quarterly2025,
        comparisonFinancial: annual2024,
      })
    );

    expect(screen.getByText(/Annual fallback applied/i)).toBeTruthy();
    expect(screen.getByText(/Focus 10-K Dec 31, 2025/i)).toBeTruthy();
    expect(screen.getByText(/Compare 10-K Dec 31, 2024/i)).toBeTruthy();
    expect(screen.getByText("Chart Revenue")).toBeTruthy();

    const table = screen.getByRole("table");
    const revenueRow = within(table).getByText("Revenue").closest("tr");
    expect(revenueRow).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("1.2B")).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("1B")).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("+200M")).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("20.00%")).toBeTruthy();

    const grossProfitRow = within(table).getByText("Gross Profit").closest("tr");
    expect(grossProfitRow).toBeTruthy();
    expect(within(grossProfitRow as HTMLTableRowElement).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("lets the user switch the comparison metric while keeping page-level period state", () => {
    render(
      React.createElement(FinancialComparisonPanel, {
        financials: [
          makeFinancial({ period_end: "2025-12-31", revenue: 1_200_000_000, eps: 2.4 }),
          makeFinancial({ period_end: "2024-12-31", revenue: 1_000_000_000, eps: 1.9 }),
          makeFinancial({ period_end: "2023-12-31", revenue: 900_000_000, eps: 1.4 }),
        ],
      })
    );

    expect(screen.queryByLabelText("Period A")).toBeNull();
    expect(screen.queryByLabelText("Period B")).toBeNull();

    fireEvent.change(screen.getByLabelText("Metric"), { target: { value: "eps" } });

    expect(screen.getByText("Chart EPS")).toBeTruthy();

    const table = screen.getByRole("table");
    const epsRow = within(table).getByText("EPS").closest("tr");
    expect(epsRow).toBeTruthy();
    expect(within(epsRow as HTMLTableRowElement).getByText("+0.50")).toBeTruthy();
    expect(within(epsRow as HTMLTableRowElement).getByText("26.32%")).toBeTruthy();
  });

  it("does not silently fall back to a different annual when custom compare collapses to the same fiscal year", () => {
    const annual2025 = makeFinancial({ period_end: "2025-12-31", revenue: 1_200_000_000 });
    const annual2024 = makeFinancial({ period_end: "2024-12-31", revenue: 1_000_000_000 });
    const quarterly2025 = makeFinancial({ filing_type: "10-Q", period_start: "2025-10-01", period_end: "2025-12-31", revenue: 320_000_000 });

    render(
      React.createElement(FinancialComparisonPanel, {
        financials: [annual2025, annual2024, quarterly2025],
        visibleFinancials: [annual2025, annual2024, quarterly2025],
        selectedFinancial: quarterly2025,
        comparisonFinancial: annual2025,
      })
    );

    expect(screen.getByText(/Comparison resolves to the same fiscal year/i)).toBeTruthy();
    expect(screen.getByText(/Need a second annual filing for full deltas/i)).toBeTruthy();
    expect(screen.queryByText(/Compare 10-K Dec 31, 2024/i)).toBeNull();
  });
});
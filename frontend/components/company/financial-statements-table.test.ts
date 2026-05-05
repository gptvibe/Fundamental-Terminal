// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BankFinancialStatementsTable } from "@/components/company/bank-financial-statements-table";
import { FinancialStatementsTable } from "@/components/company/financial-statements-table";
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
    reconciliation: partial.reconciliation ?? null,
    regulated_bank: partial.regulated_bank ?? null,
  };
}

describe("financial statements tables", () => {
  const createObjectUrl = vi.fn(() => "blob:mock-url");
  const revokeObjectUrl = vi.fn();

  beforeEach(() => {
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: createObjectUrl,
      revokeObjectURL: revokeObjectUrl,
    });
  });

  afterEach(() => {
    createObjectUrl.mockReset();
    revokeObjectUrl.mockReset();
    vi.unstubAllGlobals();
  });

  it("shows selected and comparison columns with deltas and exports only the visible statements", async () => {
    const selected = makeFinancial({
      period_end: "2025-12-31",
      revenue: 1_200_000_000,
      gross_profit: 600_000_000,
      operating_income: 320_000_000,
      net_income: 210_000_000,
      operating_cash_flow: 350_000_000,
      free_cash_flow: 260_000_000,
      total_assets: 2_400_000_000,
      total_liabilities: 900_000_000,
      eps: 2.4,
    });
    const comparison = makeFinancial({
      period_end: "2024-12-31",
      revenue: 1_000_000_000,
      gross_profit: 520_000_000,
      operating_income: 280_000_000,
      net_income: 180_000_000,
      operating_cash_flow: 310_000_000,
      free_cash_flow: 220_000_000,
      total_assets: 2_100_000_000,
      total_liabilities: 950_000_000,
      eps: 1.9,
    });
    const extra = makeFinancial({ period_end: "2023-12-31", revenue: 900_000_000 });

    render(
      React.createElement(FinancialStatementsTable, {
        financials: [selected, comparison, extra],
        ticker: "ACME",
        showComparison: true,
        selectedFinancial: selected,
        comparisonFinancial: comparison,
      })
    );

    expect(screen.getByText("Absolute Change")).toBeTruthy();
    expect(screen.getByText("Percent Change")).toBeTruthy();

    const statementTable = screen.getAllByRole("table")[1];
    const revenueRow = within(statementTable).getByText("Revenue").closest("tr");
    expect(revenueRow).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("1.2B")).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("1B")).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("+200M")).toBeTruthy();
    expect(within(revenueRow as HTMLTableRowElement).getByText("20.00%")).toBeTruthy();

    fireEvent.click(screen.getByText("Download JSON"));

    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    const firstCall = createObjectUrl.mock.calls.at(0);
    expect(firstCall).toBeDefined();
    const blob = firstCall![0] as Blob;
    expect(blob).toBeInstanceOf(Blob);
    const payload = JSON.parse(await blob.text()) as FinancialPayload[];
    expect(payload).toHaveLength(2);
    expect(payload[0]?.period_end).toBe("2025-12-31");
    expect(payload[1]?.period_end).toBe("2024-12-31");
  });

  it("shows regulated-bank comparison columns in sync with selected periods", () => {
    const selected = makeFinancial({
      period_end: "2025-12-31",
      net_income: 200_000_000,
      regulated_bank: {
        source_id: "fdic_bankfind_financials",
        reporting_basis: "fdic_call_report",
        confidence_score: 0.94,
        confidence_flags: [],
        net_interest_income: 1_200_000_000,
        noninterest_income: 400_000_000,
        noninterest_expense: 900_000_000,
        pretax_income: 500_000_000,
        provision_for_credit_losses: 200_000_000,
        deposits_total: 80_000_000_000,
        core_deposits: 60_000_000_000,
        uninsured_deposits: 12_000_000_000,
        loans_net: 55_000_000_000,
        net_interest_margin: 0.038,
        nonperforming_assets_ratio: 0.011,
        common_equity_tier1_ratio: 0.121,
        tier1_risk_weighted_ratio: 0.133,
        total_risk_based_capital_ratio: 0.149,
        return_on_assets_ratio: 0.011,
        return_on_equity_ratio: 0.124,
        tangible_common_equity: 9_000_000_000,
      },
    });
    const comparison = makeFinancial({
      period_end: "2024-12-31",
      net_income: 180_000_000,
      regulated_bank: {
        ...selected.regulated_bank!,
        net_interest_income: 1_100_000_000,
        provision_for_credit_losses: 160_000_000,
        deposits_total: 78_000_000_000,
        core_deposits: 57_000_000_000,
        uninsured_deposits: 11_700_000_000,
        net_interest_margin: 0.035,
        common_equity_tier1_ratio: 0.116,
        total_risk_based_capital_ratio: 0.145,
      },
    });

    render(
      React.createElement(BankFinancialStatementsTable, {
        financials: [selected, comparison],
        ticker: "BANK",
        showComparison: true,
        selectedFinancial: selected,
        comparisonFinancial: comparison,
      })
    );

    expect(screen.getByText("Absolute Change")).toBeTruthy();

    const bankTable = screen.getByRole("table");
    const niiRow = within(bankTable).getByText("Net Interest Income").closest("tr");
    expect(niiRow).toBeTruthy();
    expect(within(niiRow as HTMLTableRowElement).getByText("1.2B")).toBeTruthy();
    expect(within(niiRow as HTMLTableRowElement).getByText("1.1B")).toBeTruthy();
    expect(within(niiRow as HTMLTableRowElement).getByText("+100M")).toBeTruthy();
  });
});
// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GrowthWaterfallChart } from "@/components/charts/growth-waterfall-chart";
import type { FinancialPayload } from "@/lib/types";

vi.mock("recharts", () => {
  function Wrapper({ children }: { children?: React.ReactNode }) {
    return React.createElement("div", null, children);
  }

  return {
    Bar: Wrapper,
    CartesianGrid: Wrapper,
    ComposedChart: Wrapper,
    Legend: Wrapper,
    Line: Wrapper,
    ReferenceLine: Wrapper,
    ResponsiveContainer: Wrapper,
    Tooltip: Wrapper,
    XAxis: Wrapper,
    YAxis: Wrapper,
  };
});

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
    cash_and_cash_equivalents: partial.cash_and_cash_equivalents ?? null,
    short_term_investments: partial.short_term_investments ?? null,
    cash_and_short_term_investments: partial.cash_and_short_term_investments ?? null,
    accounts_receivable: partial.accounts_receivable ?? null,
    accounts_payable: partial.accounts_payable ?? null,
    goodwill_and_intangibles: partial.goodwill_and_intangibles ?? null,
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

describe("GrowthWaterfallChart", () => {
  it("scopes to the shared annual range and switches metrics", () => {
    const annual2025 = makeFinancial({
      period_end: "2025-12-31",
      revenue: 1200,
      net_income: 250,
      free_cash_flow: 220,
    });
    const annual2024 = makeFinancial({
      period_end: "2024-12-31",
      revenue: 1000,
      net_income: 200,
      free_cash_flow: 170,
    });
    const annual2023 = makeFinancial({
      period_end: "2023-12-31",
      revenue: 900,
      net_income: 180,
      free_cash_flow: 150,
    });
    const annual2022 = makeFinancial({
      period_end: "2022-12-31",
      revenue: 820,
      net_income: 155,
      free_cash_flow: 120,
    });
    const quarterly2025 = makeFinancial({
      filing_type: "10-Q",
      period_start: "2025-10-01",
      period_end: "2025-12-31",
      revenue: 320,
      net_income: 60,
      free_cash_flow: 55,
    });

    render(
      React.createElement(GrowthWaterfallChart, {
        financials: [annual2025, annual2024, annual2023, annual2022, quarterly2025],
        visibleFinancials: [annual2025, annual2024, annual2023],
        chartState: {
          cadence: "quarterly",
          effectiveCadence: "annual",
          requestedCadence: "quarterly",
          visiblePeriodCount: 3,
          selectedFinancial: quarterly2025,
          comparisonFinancial: annual2024,
          selectedPeriodLabel: "10-Q Dec 31, 2025",
          comparisonPeriodLabel: "10-K Dec 31, 2024",
          cadenceNote: "Quarterly selection is unavailable for this issuer's cached statements, so filing-based panels fall back to annual history.",
        },
      })
    );

    expect(screen.getByText("supports_selected_period")).toBeTruthy();
    expect(screen.getByText("supports_compare_mode")).toBeTruthy();
    expect(screen.getByText("supports_trend_mode")).toBeTruthy();
    expect(screen.getByText(/Annual fallback applied/i)).toBeTruthy();
    expect(screen.getByText(/Focus 10-K Dec 31, 2025/i)).toBeTruthy();
    expect(screen.getByText(/Compare 10-K Dec 31, 2024/i)).toBeTruthy();
    expect(screen.getByText("Visible annual periods 3")).toBeTruthy();
    expect(screen.getByText("Metric Revenue")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Net Income" }));

    expect(screen.getByText("Metric Net Income")).toBeTruthy();
    expect(screen.getByText(/Net Income Δ/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Free Cash Flow" }));

    expect(screen.getByText("Metric Free Cash Flow")).toBeTruthy();
    expect(screen.getByText(/Free Cash Flow Δ/i)).toBeTruthy();
  });
});
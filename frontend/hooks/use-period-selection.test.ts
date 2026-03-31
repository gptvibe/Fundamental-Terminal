// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { buildFinancialPeriodKey, usePeriodSelection } from "@/hooks/use-period-selection";
import type { FinancialPayload } from "@/lib/types";

const navigationFixture = vi.hoisted(() => ({
  pathname: "/company/acme/financials",
  searchParams: new URLSearchParams(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: navigationFixture.replace }),
  usePathname: () => navigationFixture.pathname,
  useSearchParams: () => navigationFixture.searchParams,
}));

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

describe("usePeriodSelection", () => {
  beforeEach(() => {
    navigationFixture.searchParams = new URLSearchParams();
    navigationFixture.replace.mockReset();
  });

  it("falls back from quarterly requests to annual filings and keeps comparison state coherent", () => {
    const annual2025 = makeFinancial({ period_end: "2025-12-31" });
    const annual2024 = makeFinancial({ period_end: "2024-12-31" });
    const annual2023 = makeFinancial({ period_end: "2023-12-31" });

    navigationFixture.searchParams = new URLSearchParams("fin_cadence=quarterly&fin_compare=previous&fin_range=3Y");

    const { result } = renderHook(() => usePeriodSelection([annual2025, annual2024, annual2023]));

    expect(result.current.cadence).toBe("quarterly");
    expect(result.current.effectiveStatementCadence).toBe("annual");
    expect(result.current.visibleFinancials.map((statement) => statement.period_end)).toEqual([
      "2025-12-31",
      "2024-12-31",
      "2023-12-31",
    ]);
    expect(result.current.selectedFinancial?.period_end).toBe("2025-12-31");
    expect(result.current.comparisonFinancial?.period_end).toBe("2024-12-31");
    expect(result.current.activeComparisonPeriodKey).toBe(buildFinancialPeriodKey(annual2024));
    expect(result.current.cadenceNote).toMatch(/fall back to annual history/i);
    expect(result.current.metricsMaxPoints).toBe(12);
    expect(result.current.capitalStructureMaxPeriods).toBe(12);
  });

  it("keeps custom comparison selections distinct when the focused period changes", () => {
    const q4 = makeFinancial({ filing_type: "10-Q", period_start: "2025-10-01", period_end: "2025-12-31" });
    const q3 = makeFinancial({ filing_type: "10-Q", period_start: "2025-07-01", period_end: "2025-09-30" });
    const q2 = makeFinancial({ filing_type: "10-Q", period_start: "2025-04-01", period_end: "2025-06-30" });
    const q1 = makeFinancial({ filing_type: "10-Q", period_start: "2025-01-01", period_end: "2025-03-31" });

    navigationFixture.searchParams = new URLSearchParams(
      `fin_cadence=quarterly&fin_compare=custom&fin_period=${encodeURIComponent(buildFinancialPeriodKey(q4))}&fin_compare_period=${encodeURIComponent(buildFinancialPeriodKey(q3))}`
    );

    const { result } = renderHook(() => usePeriodSelection([q4, q3, q2, q1]));

    expect(result.current.selectedFinancial?.period_end).toBe("2025-12-31");
    expect(result.current.comparisonFinancial?.period_end).toBe("2025-09-30");

    act(() => {
      result.current.setSelectedPeriodKey(buildFinancialPeriodKey(q3));
    });

    const nextSelectionQuery = String(navigationFixture.replace.mock.calls.at(-1)?.[0] ?? "");
    const nextSelectionParams = new URLSearchParams(nextSelectionQuery.split("?")[1] ?? "");
    expect(nextSelectionParams.get("fin_period")).toBe(buildFinancialPeriodKey(q3));
    expect(nextSelectionParams.get("fin_compare_period")).toBe(buildFinancialPeriodKey(q2));

    act(() => {
      result.current.setCadence("annual");
    });

    const nextCadenceQuery = String(navigationFixture.replace.mock.calls.at(-1)?.[0] ?? "");
    const nextCadenceParams = new URLSearchParams(nextCadenceQuery.split("?")[1] ?? "");
    expect(nextCadenceParams.get("fin_cadence")).toBeNull();
    expect(nextCadenceParams.get("fin_period")).toBeNull();
    expect(nextCadenceParams.get("fin_compare_period")).toBeNull();
  });
});
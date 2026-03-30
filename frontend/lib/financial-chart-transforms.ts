import type { FilingEventPayload, FinancialPayload } from "@/lib/types";
import { formatStatementAxisLabel } from "@/lib/financial-chart-state";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

export type OperatingCostSeriesRow = {
  period: string;
  periodEnd: string;
  filingType: string;
  sga: number | null;
  researchAndDevelopment: number | null;
  stockBasedCompensation: number | null;
  interestExpense: number | null;
  incomeTaxExpense: number | null;
};

export type CapitalMarketsSignalRow = {
  period: string;
  financingEvents: number;
  debtChanges: number | null;
};

export function buildOperatingCostSeries(
  financials: FinancialPayload[],
  cadence?: "annual" | "quarterly" | "ttm" | "reported"
): OperatingCostSeriesRow[] {
  return [...financials]
    .sort((left, right) => Date.parse(left.period_end) - Date.parse(right.period_end))
    .filter(
      (statement) =>
        statement.sga != null ||
        statement.research_and_development != null ||
        statement.stock_based_compensation != null ||
        statement.interest_expense != null ||
        statement.income_tax_expense != null
    )
    .map((statement) => ({
      period: formatStatementAxisLabel(statement, cadence),
      periodEnd: statement.period_end,
      filingType: statement.filing_type,
      sga: statement.sga,
      researchAndDevelopment: statement.research_and_development,
      stockBasedCompensation: statement.stock_based_compensation,
      interestExpense: statement.interest_expense,
      incomeTaxExpense: statement.income_tax_expense,
    }));
}

export function buildCapitalMarketsSignalSeries(
  financials: FinancialPayload[],
  events: FilingEventPayload[]
): CapitalMarketsSignalRow[] {
  const annuals = financials
    .filter((statement) => ANNUAL_FORMS.has(statement.filing_type))
    .sort((left, right) => Date.parse(left.period_end) - Date.parse(right.period_end));

  const eventCounts = new Map<string, number>();
  for (const event of events) {
    if (event.category !== "Financing" && event.category !== "Capital Markets") {
      continue;
    }
    const dateValue = event.filing_date ?? event.report_date;
    if (!dateValue) {
      continue;
    }
    const year = new Date(dateValue).getUTCFullYear();
    eventCounts.set(String(year), (eventCounts.get(String(year)) ?? 0) + 1);
  }

  const financialRows = annuals.map((statement) => ({
    period: String(new Date(statement.period_end).getUTCFullYear()),
    financingEvents: eventCounts.get(String(new Date(statement.period_end).getUTCFullYear())) ?? 0,
    debtChanges: statement.debt_changes,
  }));

  if (financialRows.length) {
    return financialRows;
  }

  return [...eventCounts.entries()].map(([period, financingEvents]) => ({ period, financingEvents, debtChanges: null }));
}
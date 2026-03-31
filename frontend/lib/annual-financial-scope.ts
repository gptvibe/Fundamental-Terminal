import type { FinancialCadence } from "@/hooks/use-period-selection";
import type { SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatDate } from "@/lib/format";
import type { SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type { FinancialPayload } from "@/lib/types";

export const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

export interface AnnualFinancialScope {
  annuals: FinancialPayload[];
  scopedAnnuals: FinancialPayload[];
  selectedAnnual: FinancialPayload | null;
  comparisonAnnual: FinancialPayload | null;
  usedSelectedAnnualFallback: boolean;
  usedComparisonAnnualFallback: boolean;
  comparisonUnavailable: boolean;
  comparisonCollapsedToSelected: boolean;
}

export function buildAnnualKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

export function formatAnnualLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

export function formatAnnualHeader(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${new Date(statement.period_end).getUTCFullYear()}`;
}

export function resolveAnnualFinancialScope({
  financials,
  visibleFinancials = [],
  selectedFinancial = null,
  comparisonFinancial = null,
}: {
  financials: FinancialPayload[];
  visibleFinancials?: FinancialPayload[];
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
}): AnnualFinancialScope {
  const annuals = [...financials]
    .filter((statement) => ANNUAL_FORMS.has(statement.filing_type))
    .sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end));

  const selectedAnnual = coerceAnnualStatement(selectedFinancial, annuals);
  const explicitComparisonAnnual = comparisonFinancial ? coerceAnnualStatement(comparisonFinancial, annuals) : null;
  const comparisonCollapsedToSelected = Boolean(
    selectedAnnual && explicitComparisonAnnual && buildAnnualKey(selectedAnnual) === buildAnnualKey(explicitComparisonAnnual)
  );
  const comparisonAnnual = comparisonFinancial
    ? comparisonCollapsedToSelected
      ? null
      : explicitComparisonAnnual
    : resolvePreviousAnnual(selectedAnnual, annuals);

  return {
    annuals,
    scopedAnnuals: scopeAnnuals(annuals, visibleFinancials, selectedAnnual, comparisonAnnual),
    selectedAnnual,
    comparisonAnnual,
    usedSelectedAnnualFallback: Boolean(selectedFinancial && !ANNUAL_FORMS.has(selectedFinancial.filing_type) && selectedAnnual),
    usedComparisonAnnualFallback: Boolean(comparisonFinancial && !ANNUAL_FORMS.has(comparisonFinancial.filing_type) && explicitComparisonAnnual),
    comparisonUnavailable: Boolean(comparisonFinancial && !comparisonCollapsedToSelected && !explicitComparisonAnnual),
    comparisonCollapsedToSelected,
  };
}

export function buildAnnualSurfaceWarnings({
  chartState,
  scope,
  selectedFinancial,
  comparisonFinancial,
  sparseHistoryDetail,
  trendPointCount,
}: {
  chartState?: SharedFinancialChartState;
  scope: AnnualFinancialScope;
  selectedFinancial: FinancialPayload | null;
  comparisonFinancial: FinancialPayload | null;
  sparseHistoryDetail?: string;
  trendPointCount?: number;
}): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];

  if (chartState?.requestedCadence && chartState.requestedCadence !== "annual") {
    warnings.push({
      code: "annual_only_surface",
      label: "Annual-only surface",
      detail: "This surface compares fiscal years only. Quarterly and TTM selections are mapped to matching annual filings when available.",
      tone: "info",
    });
  }

  if (scope.usedSelectedAnnualFallback && selectedFinancial && scope.selectedAnnual) {
    warnings.push({
      code: "selected_annual_fallback",
      label: "Annual fallback applied",
      detail: `Focus maps to ${formatAnnualLabel(scope.selectedAnnual)} because this surface compares normalized fiscal years.`,
      tone: "info",
    });
  }

  if (comparisonFinancial && scope.usedComparisonAnnualFallback && scope.comparisonAnnual) {
    warnings.push({
      code: "comparison_annual_fallback",
      label: "Comparison mapped to fiscal year",
      detail: `Compare maps to ${formatAnnualLabel(scope.comparisonAnnual)} because this surface compares normalized fiscal years.`,
      tone: "info",
    });
  }

  if (comparisonFinancial && scope.comparisonCollapsedToSelected) {
    warnings.push({
      code: "comparison_collapsed_to_selected",
      label: "Comparison resolves to the same fiscal year",
      detail: "The selected focus and comparison periods roll up to the same annual filing, so this surface cannot show a distinct annual comparison.",
      tone: "warning",
    });
  }

  if (comparisonFinancial && scope.comparisonUnavailable) {
    warnings.push({
      code: "comparison_annual_missing",
      label: "Comparison annual unavailable",
      detail: "The selected comparison period does not have a matching annual filing in the current history window.",
      tone: "warning",
    });
  }

  if (sparseHistoryDetail && trendPointCount != null && trendPointCount < 2) {
    warnings.push({
      code: "annual_history_sparse",
      label: "Sparse annual history",
      detail: sparseHistoryDetail,
      tone: "info",
    });
  }

  return warnings;
}

export function resolveFilingChartCadence(
  requestedCadence: FinancialCadence,
  effectiveStatementCadence: "annual" | "quarterly" | "reported"
): "annual" | "quarterly" | "reported" {
  if (effectiveStatementCadence === "annual" || effectiveStatementCadence === "quarterly") {
    return effectiveStatementCadence;
  }
  return requestedCadence === "annual" ? "annual" : "reported";
}

function coerceAnnualStatement(selectedFinancial: FinancialPayload | null, annuals: FinancialPayload[]): FinancialPayload | null {
  if (!selectedFinancial) {
    return annuals[0] ?? null;
  }
  if (ANNUAL_FORMS.has(selectedFinancial.filing_type)) {
    return selectedFinancial;
  }
  const selectedYear = new Date(selectedFinancial.period_end).getUTCFullYear();
  return annuals.find((statement) => new Date(statement.period_end).getUTCFullYear() === selectedYear) ?? null;
}

function resolvePreviousAnnual(selectedAnnual: FinancialPayload | null, annuals: FinancialPayload[]): FinancialPayload | null {
  if (!selectedAnnual) {
    return null;
  }
  const selectedIndex = annuals.findIndex((statement) => buildAnnualKey(statement) === buildAnnualKey(selectedAnnual));
  if (selectedIndex < 0) {
    return annuals[1] ?? null;
  }
  return annuals[selectedIndex + 1] ?? null;
}

function scopeAnnuals(
  annuals: FinancialPayload[],
  visibleFinancials: FinancialPayload[],
  selectedAnnual: FinancialPayload | null,
  comparisonAnnual: FinancialPayload | null
): FinancialPayload[] {
  const pinnedYears = new Set<number>();
  if (selectedAnnual) {
    pinnedYears.add(new Date(selectedAnnual.period_end).getUTCFullYear());
  }
  if (comparisonAnnual) {
    pinnedYears.add(new Date(comparisonAnnual.period_end).getUTCFullYear());
  }

  const visibleYears = new Set(
    visibleFinancials
      .map((statement) => new Date(statement.period_end).getUTCFullYear())
      .filter((year) => Number.isFinite(year))
  );

  if (!visibleYears.size) {
    return annuals;
  }

  const scopedAnnuals = annuals.filter((statement) => {
    const year = new Date(statement.period_end).getUTCFullYear();
    return visibleYears.has(year) || pinnedYears.has(year);
  });

  return scopedAnnuals.length ? scopedAnnuals : annuals;
}
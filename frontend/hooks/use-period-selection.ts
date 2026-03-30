"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { formatDate } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);
const RANGE_YEARS: Record<Exclude<FinancialRangePreset, "All">, number> = {
  "3Y": 3,
  "5Y": 5,
  "10Y": 10,
};

const SEARCH_PARAM_KEYS = {
  cadence: "fin_cadence",
  rangePreset: "fin_range",
  compareMode: "fin_compare",
  selectedPeriod: "fin_period",
  comparePeriod: "fin_compare_period",
} as const;

export type FinancialCadence = "annual" | "quarterly" | "ttm";
export type FinancialRangePreset = "3Y" | "5Y" | "10Y" | "All";
export type FinancialCompareMode = "off" | "previous" | "custom";
export type EffectiveStatementCadence = "annual" | "quarterly" | "reported";

export interface FinancialPeriodOption {
  key: string;
  label: string;
  shortLabel: string;
  periodEnd: string;
  filingType: string;
  year: number | null;
}

interface SearchParamUpdates {
  [SEARCH_PARAM_KEYS.cadence]?: string | null;
  [SEARCH_PARAM_KEYS.rangePreset]?: string | null;
  [SEARCH_PARAM_KEYS.compareMode]?: string | null;
  [SEARCH_PARAM_KEYS.selectedPeriod]?: string | null;
  [SEARCH_PARAM_KEYS.comparePeriod]?: string | null;
}

export interface PeriodSelectionResult {
  cadence: FinancialCadence;
  rangePreset: FinancialRangePreset;
  compareMode: FinancialCompareMode;
  selectedPeriodKey: string | null;
  customComparePeriodKey: string | null;
  activeComparisonPeriodKey: string | null;
  periodOptions: FinancialPeriodOption[];
  comparisonOptions: FinancialPeriodOption[];
  visibleFinancials: FinancialPayload[];
  selectedFinancial: FinancialPayload | null;
  comparisonFinancial: FinancialPayload | null;
  effectiveStatementCadence: EffectiveStatementCadence;
  cadenceNote: string | null;
  metricsMaxPoints: number;
  capitalStructureMaxPeriods: number;
  visiblePeriodCount: number;
  totalFinancialCount: number;
  selectedPeriodLabel: string | null;
  comparisonPeriodLabel: string | null;
  setCadence: (next: FinancialCadence) => void;
  setRangePreset: (next: FinancialRangePreset) => void;
  setCompareMode: (next: FinancialCompareMode) => void;
  setSelectedPeriodKey: (next: string | null) => void;
  setCustomComparePeriodKey: (next: string | null) => void;
}

export function usePeriodSelection(financials: FinancialPayload[]): PeriodSelectionResult {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const cadence = parseCadence(searchParams.get(SEARCH_PARAM_KEYS.cadence));
  const rangePreset = parseRangePreset(searchParams.get(SEARCH_PARAM_KEYS.rangePreset));

  const effectiveStatementCadence = useMemo(
    () => resolveEffectiveStatementCadence(financials, cadence),
    [cadence, financials]
  );

  const cadenceFinancials = useMemo(
    () => selectCadenceFinancials(financials, effectiveStatementCadence),
    [effectiveStatementCadence, financials]
  );

  const visibleFinancials = useMemo(
    () => applyRangePreset(cadenceFinancials, rangePreset),
    [cadenceFinancials, rangePreset]
  );

  const periodOptions = useMemo(
    () => visibleFinancials.map((statement) => toPeriodOption(statement)),
    [visibleFinancials]
  );

  const selectedPeriodKey = normalizeSelectedPeriodKey(
    searchParams.get(SEARCH_PARAM_KEYS.selectedPeriod),
    periodOptions
  );
  const selectedFinancial = findFinancialByKey(visibleFinancials, selectedPeriodKey);
  const comparisonOptions = useMemo(
    () => periodOptions.filter((option) => option.key !== selectedPeriodKey),
    [periodOptions, selectedPeriodKey]
  );

  const compareMode = normalizeCompareMode(
    searchParams.get(SEARCH_PARAM_KEYS.compareMode),
    comparisonOptions.length
  );
  const customComparePeriodKey = normalizeSelectedPeriodKey(
    searchParams.get(SEARCH_PARAM_KEYS.comparePeriod),
    comparisonOptions
  );
  const comparisonFinancial = resolveComparisonFinancial({
    financials: visibleFinancials,
    selectedPeriodKey,
    compareMode,
    customComparePeriodKey,
  });
  const activeComparisonPeriodKey = comparisonFinancial ? buildFinancialPeriodKey(comparisonFinancial) : null;

  function replaceSearchParams(updates: SearchParamUpdates) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (!value) {
        params.delete(key);
      } else {
        params.set(key, value);
      }
    }
    const nextQuery = params.toString();
    router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false });
  }

  function setCadence(next: FinancialCadence) {
    replaceSearchParams({
      [SEARCH_PARAM_KEYS.cadence]: next === "annual" ? null : next,
      [SEARCH_PARAM_KEYS.selectedPeriod]: null,
      [SEARCH_PARAM_KEYS.comparePeriod]: null,
    });
  }

  function setRangePreset(next: FinancialRangePreset) {
    replaceSearchParams({
      [SEARCH_PARAM_KEYS.rangePreset]: next === "5Y" ? null : next,
      [SEARCH_PARAM_KEYS.selectedPeriod]: null,
      [SEARCH_PARAM_KEYS.comparePeriod]: null,
    });
  }

  function setCompareMode(next: FinancialCompareMode) {
    replaceSearchParams({
      [SEARCH_PARAM_KEYS.compareMode]: next === "off" ? null : next,
      [SEARCH_PARAM_KEYS.comparePeriod]:
        next === "custom" ? comparisonOptions[0]?.key ?? null : null,
    });
  }

  function setSelectedPeriodKey(next: string | null) {
    const nextComparisonKey =
      compareMode === "custom" && next && next === customComparePeriodKey
        ? comparisonOptions.find((option) => option.key !== next)?.key ?? null
        : customComparePeriodKey;

    replaceSearchParams({
      [SEARCH_PARAM_KEYS.selectedPeriod]: next,
      [SEARCH_PARAM_KEYS.comparePeriod]: compareMode === "custom" ? nextComparisonKey : null,
    });
  }

  function setCustomComparePeriodKey(next: string | null) {
    replaceSearchParams({
      [SEARCH_PARAM_KEYS.compareMode]: "custom",
      [SEARCH_PARAM_KEYS.comparePeriod]: next,
    });
  }

  const cadenceNote = buildCadenceNote(cadence, effectiveStatementCadence, financials.length > 0);

  return {
    cadence,
    rangePreset,
    compareMode,
    selectedPeriodKey,
    customComparePeriodKey,
    activeComparisonPeriodKey,
    periodOptions,
    comparisonOptions,
    visibleFinancials,
    selectedFinancial,
    comparisonFinancial,
    effectiveStatementCadence,
    cadenceNote,
    metricsMaxPoints: estimateMetricsMaxPoints(cadence, rangePreset),
    capitalStructureMaxPeriods: estimateCapitalStructureMaxPeriods(rangePreset),
    visiblePeriodCount: visibleFinancials.length,
    totalFinancialCount: financials.length,
    selectedPeriodLabel: selectedFinancial ? formatPeriodOptionLabel(selectedFinancial) : null,
    comparisonPeriodLabel: comparisonFinancial ? formatPeriodOptionLabel(comparisonFinancial) : null,
    setCadence,
    setRangePreset,
    setCompareMode,
    setSelectedPeriodKey,
    setCustomComparePeriodKey,
  };
}

export function buildFinancialPeriodKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function parseCadence(value: string | null): FinancialCadence {
  if (value === "quarterly" || value === "ttm") {
    return value;
  }
  return "annual";
}

function parseRangePreset(value: string | null): FinancialRangePreset {
  if (value === "3Y" || value === "10Y" || value === "All") {
    return value;
  }
  return "5Y";
}

function normalizeCompareMode(value: string | null, comparisonOptionCount: number): FinancialCompareMode {
  if (comparisonOptionCount < 1) {
    return "off";
  }
  if (value === "previous" || value === "custom") {
    return value;
  }
  return "off";
}

function resolveEffectiveStatementCadence(
  financials: FinancialPayload[],
  cadence: FinancialCadence
): EffectiveStatementCadence {
  const annualFinancials = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
  const quarterlyFinancials = financials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type));

  if (!annualFinancials.length && !quarterlyFinancials.length) {
    return "reported";
  }
  if (cadence === "annual") {
    return annualFinancials.length ? "annual" : "reported";
  }
  if (quarterlyFinancials.length) {
    return "quarterly";
  }
  if (annualFinancials.length) {
    return "annual";
  }
  return "reported";
}

function selectCadenceFinancials(
  financials: FinancialPayload[],
  cadence: EffectiveStatementCadence
): FinancialPayload[] {
  if (cadence === "annual") {
    return financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
  }
  if (cadence === "quarterly") {
    return financials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type));
  }
  return financials;
}

function applyRangePreset(
  financials: FinancialPayload[],
  rangePreset: FinancialRangePreset
): FinancialPayload[] {
  if (rangePreset === "All" || financials.length === 0) {
    return financials;
  }

  const latestYear = getStatementYear(financials[0]);
  const spanYears = RANGE_YEARS[rangePreset];
  if (latestYear === null || spanYears == null) {
    return financials;
  }

  const thresholdYear = latestYear - (spanYears - 1);
  return financials.filter((statement) => {
    const statementYear = getStatementYear(statement);
    return statementYear === null || statementYear >= thresholdYear;
  });
}

function toPeriodOption(statement: FinancialPayload): FinancialPeriodOption {
  const year = getStatementYear(statement);
  return {
    key: buildFinancialPeriodKey(statement),
    label: formatPeriodOptionLabel(statement),
    shortLabel: year == null ? formatDate(statement.period_end) : `${statement.filing_type} ${year}`,
    periodEnd: statement.period_end,
    filingType: statement.filing_type,
    year,
  };
}

function formatPeriodOptionLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

function normalizeSelectedPeriodKey(value: string | null, options: FinancialPeriodOption[]): string | null {
  if (options.length === 0) {
    return null;
  }
  if (value && options.some((option) => option.key === value)) {
    return value;
  }
  return options[0]?.key ?? null;
}

function findFinancialByKey(financials: FinancialPayload[], key: string | null): FinancialPayload | null {
  if (!key) {
    return financials[0] ?? null;
  }
  return financials.find((statement) => buildFinancialPeriodKey(statement) === key) ?? null;
}

function resolveComparisonFinancial({
  financials,
  selectedPeriodKey,
  compareMode,
  customComparePeriodKey,
}: {
  financials: FinancialPayload[];
  selectedPeriodKey: string | null;
  compareMode: FinancialCompareMode;
  customComparePeriodKey: string | null;
}): FinancialPayload | null {
  if (compareMode === "off") {
    return null;
  }

  const selectedIndex = selectedPeriodKey
    ? financials.findIndex((statement) => buildFinancialPeriodKey(statement) === selectedPeriodKey)
    : 0;
  if (selectedIndex < 0) {
    return null;
  }

  if (compareMode === "previous") {
    return financials[selectedIndex + 1] ?? null;
  }

  if (!customComparePeriodKey) {
    return null;
  }
  return financials.find((statement) => buildFinancialPeriodKey(statement) === customComparePeriodKey) ?? null;
}

function buildCadenceNote(
  cadence: FinancialCadence,
  effectiveCadence: EffectiveStatementCadence,
  hasFinancials: boolean
): string | null {
  if (!hasFinancials) {
    return null;
  }
  if (cadence === "ttm") {
    if (effectiveCadence === "quarterly") {
      return "TTM applies to derived metrics. Filing-based charts and tables use quarterly statements.";
    }
    if (effectiveCadence === "annual") {
      return "TTM applies to derived metrics. Filing-based charts and tables fall back to annual statements because quarterly filings are not available.";
    }
    return "TTM applies to derived metrics. Filing-based charts and tables use the issuer's reported filing periods.";
  }
  if (effectiveCadence === "reported") {
    return "Filing-based charts and tables use the issuer's reported filing periods on this page.";
  }
  if (cadence === "quarterly" && effectiveCadence === "annual") {
    return "Quarterly selection is unavailable for this issuer's cached statements, so filing-based panels fall back to annual history.";
  }
  return null;
}

function estimateMetricsMaxPoints(cadence: FinancialCadence, rangePreset: FinancialRangePreset): number {
  if (rangePreset === "All") {
    return cadence === "annual" ? 24 : 60;
  }
  const years = RANGE_YEARS[rangePreset];
  return cadence === "annual" ? years : years * 4;
}

function estimateCapitalStructureMaxPeriods(rangePreset: FinancialRangePreset): number {
  if (rangePreset === "All") {
    return 24;
  }
  return RANGE_YEARS[rangePreset] * 4;
}

function getStatementYear(statement: Pick<FinancialPayload, "period_end">): number | null {
  const timestamp = Date.parse(statement.period_end);
  if (Number.isNaN(timestamp)) {
    return null;
  }
  return new Date(timestamp).getUTCFullYear();
}
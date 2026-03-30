import type { FinancialCadence } from "@/hooks/use-period-selection";
import { formatDate } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

interface PeriodStatementLike {
  period_end: string;
  filing_type: string | null;
}

export interface FinancialPeriodPoint {
  periodEnd: string;
  filingType?: string | null;
}

export interface SharedFinancialChartState {
  cadence: FinancialCadence;
  visiblePeriodCount: number;
  selectedFinancial: FinancialPayload | null;
  comparisonFinancial: FinancialPayload | null;
  selectedPeriodLabel: string | null;
  comparisonPeriodLabel: string | null;
}

export function formatFinancialCadenceLabel(cadence: FinancialCadence): string {
  if (cadence === "ttm") {
    return "TTM";
  }
  return cadence === "annual" ? "Annual" : "Quarterly";
}

export function formatStatementAxisLabel(
  statement: Pick<PeriodStatementLike, "period_end" | "filing_type">,
  cadence?: FinancialCadence | "reported"
): string {
  const { date, isDateOnly } = parseDateValue(statement.period_end);
  if (Number.isNaN(date.getTime())) {
    return formatDate(statement.period_end);
  }

  const useAnnualLabel = cadence === "annual" || (cadence == null && isAnnualFiling(statement.filing_type));
  if (useAnnualLabel) {
    return String(isDateOnly ? date.getUTCFullYear() : date.getFullYear());
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "2-digit",
    ...(isDateOnly ? { timeZone: "UTC" } : {}),
  }).format(date);
}

export function findPointForStatement<Row extends FinancialPeriodPoint>(
  rows: Row[],
  statement: PeriodStatementLike | null | undefined
): Row | null {
  if (!statement) {
    return null;
  }
  return rows.find((row) => matchesStatementPeriod(statement, row)) ?? null;
}

export function matchesStatementPeriod(
  statement: PeriodStatementLike | null | undefined,
  point: FinancialPeriodPoint | null | undefined
): boolean {
  if (!statement || !point) {
    return false;
  }
  if (statement.period_end !== point.periodEnd) {
    return false;
  }
  if (!point.filingType) {
    return true;
  }
  return point.filingType === statement.filing_type;
}

export function difference(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (!isFiniteNumber(current) || !isFiniteNumber(previous)) {
    return null;
  }
  return current - previous;
}

export function formatSignedCompactDelta(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) {
    return "\u2014";
  }
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2,
    signDisplay: "exceptZero",
  }).format(value);
}

export function formatSignedPointDelta(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) {
    return "\u2014";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} pts`;
}

export function formatSignedMultipleDelta(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) {
    return "\u2014";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}x`;
}

function parseDateValue(value: string): { date: Date; isDateOnly: boolean } {
  if (DATE_ONLY_PATTERN.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return { date: new Date(Date.UTC(year, month - 1, day)), isDateOnly: true };
  }
  return { date: new Date(value), isDateOnly: false };
}

function isAnnualFiling(filingType: string | null | undefined): boolean {
  return filingType === "10-K" || filingType === "20-F" || filingType === "40-F";
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
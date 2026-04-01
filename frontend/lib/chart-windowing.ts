import type { ChartCadenceMode, ChartTimeframeMode } from "@/lib/chart-capabilities";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);
const RANGE_YEARS: Record<RangeTimeframeMode, number> = {
  "1y": 1,
  "3y": 3,
  "5y": 5,
  "10y": 10,
  max: Number.POSITIVE_INFINITY,
};

const TTM_FLOW_FIELDS = ["revenue", "net_income", "free_cash_flow"] as const satisfies readonly (keyof FinancialPayload)[];

export type RangeTimeframeMode = Extract<ChartTimeframeMode, "1y" | "3y" | "5y" | "10y" | "max">;

interface DateSeriesOptions<T> {
  getDate: (point: T) => string | null | undefined;
  anchorDate?: string | null;
}

interface WindowedSeriesOptions<T> extends DateSeriesOptions<T> {
  timeframeMode: ChartTimeframeMode;
  maxPoints?: number;
}

export function sortSeriesByDate<T>(
  series: readonly T[],
  getDate: (point: T) => string | null | undefined,
  direction: "asc" | "desc" = "asc"
): T[] {
  const sorted = [...series];
  sorted.sort((left, right) => {
    const leftValue = toTimestamp(getDate(left));
    const rightValue = toTimestamp(getDate(right));
    return direction === "asc" ? leftValue - rightValue : rightValue - leftValue;
  });
  return sorted;
}

export function filterSeriesByTimeframe<T>(
  series: readonly T[],
  timeframeMode: ChartTimeframeMode,
  options: DateSeriesOptions<T>
): T[] {
  const orderedSeries = [...series];
  if (!orderedSeries.length || !isRangeTimeframeMode(timeframeMode) || timeframeMode === "max") {
    return orderedSeries;
  }

  const anchorDate = options.anchorDate ?? getLatestDate(series, options.getDate);
  if (!anchorDate) {
    return orderedSeries;
  }

  const anchor = new Date(anchorDate);
  const start = new Date(anchorDate);
  start.setFullYear(anchor.getFullYear() - RANGE_YEARS[timeframeMode]);

  return orderedSeries.filter((point) => {
    const rawDate = options.getDate(point);
    if (!rawDate) {
      return true;
    }

    const current = new Date(rawDate);
    return current >= start && current <= anchor;
  });
}

export function downsampleSeries<T>(series: readonly T[], maxPoints: number): T[] {
  if (maxPoints <= 0) {
    return [];
  }

  if (series.length <= maxPoints) {
    return [...series];
  }

  const lastIndex = series.length - 1;
  const sampled: T[] = [];
  const usedIndexes = new Set<number>();

  for (let index = 0; index < maxPoints; index += 1) {
    const scaledIndex = Math.round((index * lastIndex) / Math.max(maxPoints - 1, 1));
    if (usedIndexes.has(scaledIndex)) {
      continue;
    }
    usedIndexes.add(scaledIndex);
    sampled.push(series[scaledIndex]);
  }

  if (sampled[sampled.length - 1] !== series[lastIndex]) {
    sampled[sampled.length - 1] = series[lastIndex];
  }

  return sampled;
}

export function buildWindowedSeries<T>(series: readonly T[], options: WindowedSeriesOptions<T>): T[] {
  const filteredSeries = filterSeriesByTimeframe(series, options.timeframeMode, options);
  if (!options.maxPoints) {
    return filteredSeries;
  }

  return downsampleSeries(filteredSeries, options.maxPoints);
}

export function getSupportedFinancialCadenceModes(financials: readonly FinancialPayload[]): ChartCadenceMode[] {
  const annualFinancials = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
  const quarterlyFinancials = financials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type));
  const modes: ChartCadenceMode[] = ["reported"];

  if (annualFinancials.length) {
    modes.push("annual");
  }

  if (quarterlyFinancials.length) {
    modes.push("quarterly");
  }

  if (quarterlyFinancials.length >= 4) {
    modes.push("ttm");
  }

  return modes;
}

export function selectFinancialSeriesByCadence(
  financials: readonly FinancialPayload[],
  cadenceMode: ChartCadenceMode
): FinancialPayload[] {
  const chronologicalFinancials = sortSeriesByDate(financials, (statement) => statement.period_end, "asc");

  switch (cadenceMode) {
    case "annual":
      return chronologicalFinancials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
    case "quarterly":
      return chronologicalFinancials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type));
    case "ttm":
      return buildTrailingTwelveMonthFinancials(chronologicalFinancials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type)));
    case "reported":
      return chronologicalFinancials;
  }
}

export function isRangeTimeframeMode(mode: ChartTimeframeMode): mode is RangeTimeframeMode {
  return mode === "1y" || mode === "3y" || mode === "5y" || mode === "10y" || mode === "max";
}

function buildTrailingTwelveMonthFinancials(quarterlyFinancials: readonly FinancialPayload[]): FinancialPayload[] {
  if (quarterlyFinancials.length < 4) {
    return [];
  }

  const aggregatedRows: FinancialPayload[] = [];

  for (let index = 3; index < quarterlyFinancials.length; index += 1) {
    const trailingRows = quarterlyFinancials.slice(index - 3, index + 1);
    const latestRow = trailingRows[trailingRows.length - 1];
    const aggregatedMetrics = Object.fromEntries(
      TTM_FLOW_FIELDS.map((field) => [field, sumFinancialField(trailingRows, field)])
    ) as Pick<FinancialPayload, (typeof TTM_FLOW_FIELDS)[number]>;

    aggregatedRows.push({
      ...latestRow,
      ...aggregatedMetrics,
      filing_type: "TTM",
      period_start: trailingRows[0].period_start,
    });
  }

  return aggregatedRows;
}

function sumFinancialField(
  financials: readonly FinancialPayload[],
  field: (typeof TTM_FLOW_FIELDS)[number]
): number | null {
  const values = financials
    .map((statement) => statement[field])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));

  return values.length ? values.reduce((sum, value) => sum + value, 0) : null;
}

function getLatestDate<T>(series: readonly T[], getDate: (point: T) => string | null | undefined): string | null {
  let latestDate: string | null = null;
  let latestTimestamp = Number.NEGATIVE_INFINITY;

  for (const point of series) {
    const currentDate = getDate(point);
    const currentTimestamp = toTimestamp(currentDate);
    if (Number.isNaN(currentTimestamp) || currentTimestamp <= latestTimestamp) {
      continue;
    }

    latestTimestamp = currentTimestamp;
    latestDate = currentDate ?? null;
  }

  return latestDate;
}

function toTimestamp(value: string | null | undefined): number {
  if (!value) {
    return Number.NEGATIVE_INFINITY;
  }

  return Date.parse(value);
}
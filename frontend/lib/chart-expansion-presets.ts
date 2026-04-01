import type { ChartCadenceMode, ChartTimeframeMode, ChartType } from "@/lib/chart-capabilities";
import { getSupportedFinancialCadenceModes } from "@/lib/chart-windowing";
import type { FinancialPayload } from "@/lib/types";

export const RANGE_TIMEFRAME_OPTIONS = ["1y", "3y", "5y", "10y", "max"] as const satisfies readonly ChartTimeframeMode[];
export const TIME_SERIES_CHART_TYPE_OPTIONS = ["line", "area", "bar", "composed"] as const satisfies readonly ChartType[];
export const MIXED_TIME_SERIES_CHART_TYPE_OPTIONS = ["bar", "composed"] as const satisfies readonly ChartType[];
export const STACKED_TIME_SERIES_CHART_TYPE_OPTIONS = ["line", "area", "stacked_bar", "composed"] as const satisfies readonly ChartType[];
export const SNAPSHOT_BAR_CHART_TYPE_OPTIONS = ["bar"] as const satisfies readonly ChartType[];
export const WATERFALL_CHART_TYPE_OPTIONS = ["bar"] as const satisfies readonly ChartType[];
export const OWNERSHIP_MIX_CHART_TYPE_OPTIONS = ["donut", "pie", "bar"] as const satisfies readonly ChartType[];
export const SEGMENT_MIX_CHART_TYPE_OPTIONS = ["donut", "pie", "stacked_bar"] as const satisfies readonly ChartType[];
export const FINANCIAL_STOCK_CADENCE_OPTIONS = ["reported", "annual", "quarterly"] as const satisfies readonly ChartCadenceMode[];
export const FINANCIAL_FLOW_CADENCE_OPTIONS = ["reported", "annual", "quarterly", "ttm"] as const satisfies readonly ChartCadenceMode[];
export const SNAPSHOT_FINANCIAL_CADENCE_OPTIONS = ["annual", "quarterly"] as const satisfies readonly ChartCadenceMode[];

export function getSupportedRequestedCadenceModes(
  financials: readonly FinancialPayload[],
  requestedModes: readonly ChartCadenceMode[]
): ChartCadenceMode[] {
  if (!requestedModes.length) {
    return [];
  }

  const availableModes = new Set(getSupportedFinancialCadenceModes(financials));
  const filteredModes = requestedModes.filter((mode, index) => requestedModes.indexOf(mode) === index && availableModes.has(mode));

  return filteredModes.length ? filteredModes : [requestedModes[0]];
}

export function getPreferredCadenceMode(
  supportedModes: readonly ChartCadenceMode[],
  preferredModes: readonly ChartCadenceMode[]
): ChartCadenceMode | undefined {
  for (const mode of preferredModes) {
    if (supportedModes.includes(mode)) {
      return mode;
    }
  }
  return supportedModes[0];
}
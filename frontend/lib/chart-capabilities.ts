export type ChartDatasetKind =
  | "time_series"
  | "categorical_snapshot"
  | "stacked_time_series"
  | "waterfall"
  | "ownership_mix"
  | "segment_mix";

export type ChartType = "line" | "area" | "bar" | "stacked_bar" | "pie" | "donut" | "composed";

export type ChartTimeframeMode =
  | "snapshot"
  | "1y"
  | "3y"
  | "5y"
  | "10y"
  | "max"
  | "all";

export type ChartCadenceMode = "reported" | "quarterly" | "annual" | "ttm";

export interface ChartCapabilityDefinition {
  datasetKind: ChartDatasetKind;
  allowedChartTypes: readonly ChartType[];
  allowedTimeframeModes: readonly ChartTimeframeMode[];
  allowedCadenceModes?: readonly ChartCadenceMode[];
  defaultChartType: ChartType;
}

const TIME_SERIES_DATASET_KINDS = new Set<ChartDatasetKind>(["time_series", "stacked_time_series"]);
const SNAPSHOT_COMPOSITION_DATASET_KINDS = new Set<ChartDatasetKind>(["ownership_mix", "segment_mix"]);
const PIE_FAMILY_TYPES = new Set<ChartType>(["pie", "donut"]);
const TIME_SERIES_PREFERRED_DEFAULTS = new Set<ChartType>(["line", "area", "composed"]);

const CHART_CAPABILITIES = {
  time_series: defineChartCapability({
    datasetKind: "time_series",
    allowedChartTypes: ["line", "area", "bar", "composed"],
    allowedTimeframeModes: ["1y", "3y", "5y", "10y", "max"],
    allowedCadenceModes: ["reported", "quarterly", "annual", "ttm"],
    defaultChartType: "line",
  }),
  categorical_snapshot: defineChartCapability({
    datasetKind: "categorical_snapshot",
    allowedChartTypes: ["bar"],
    allowedTimeframeModes: ["snapshot"],
    defaultChartType: "bar",
  }),
  stacked_time_series: defineChartCapability({
    datasetKind: "stacked_time_series",
    allowedChartTypes: ["area", "stacked_bar", "composed"],
    allowedTimeframeModes: ["3y", "5y", "10y", "max"],
    allowedCadenceModes: ["quarterly", "annual", "ttm"],
    defaultChartType: "area",
  }),
  waterfall: defineChartCapability({
    datasetKind: "waterfall",
    allowedChartTypes: ["bar", "composed"],
    allowedTimeframeModes: ["snapshot"],
    allowedCadenceModes: ["quarterly", "annual", "ttm"],
    defaultChartType: "bar",
  }),
  ownership_mix: defineChartCapability({
    datasetKind: "ownership_mix",
    allowedChartTypes: ["donut", "pie", "bar"],
    allowedTimeframeModes: ["snapshot"],
    allowedCadenceModes: ["quarterly", "annual"],
    defaultChartType: "donut",
  }),
  segment_mix: defineChartCapability({
    datasetKind: "segment_mix",
    allowedChartTypes: ["donut", "pie", "bar", "stacked_bar"],
    allowedTimeframeModes: ["snapshot"],
    allowedCadenceModes: ["reported", "quarterly", "annual"],
    defaultChartType: "donut",
  }),
} satisfies Record<ChartDatasetKind, ChartCapabilityDefinition>;

export function getChartCapabilities(datasetKind: ChartDatasetKind): ChartCapabilityDefinition {
  return CHART_CAPABILITIES[datasetKind];
}

export function getDefaultChartType(datasetKind: ChartDatasetKind): ChartType {
  return getChartCapabilities(datasetKind).defaultChartType;
}

export function getAllowedChartTypes(datasetKind: ChartDatasetKind, requestedTypes?: readonly ChartType[]): ChartType[] {
  const allowedTypes = getChartCapabilities(datasetKind).allowedChartTypes;
  return filterAllowedValues(allowedTypes, requestedTypes);
}

export function getAllowedTimeframeModes(
  datasetKind: ChartDatasetKind,
  requestedModes?: readonly ChartTimeframeMode[]
): ChartTimeframeMode[] {
  const allowedModes = getChartCapabilities(datasetKind).allowedTimeframeModes;
  return filterAllowedValues(allowedModes, requestedModes);
}

export function getAllowedCadenceModes(
  datasetKind: ChartDatasetKind,
  requestedModes?: readonly ChartCadenceMode[]
): ChartCadenceMode[] {
  const allowedModes = getChartCapabilities(datasetKind).allowedCadenceModes ?? [];
  return filterAllowedValues(allowedModes, requestedModes);
}

export function isChartTypeAllowed(datasetKind: ChartDatasetKind, chartType: ChartType): boolean {
  return getChartCapabilities(datasetKind).allowedChartTypes.includes(chartType);
}

export function resolveChartType(datasetKind: ChartDatasetKind, requestedType?: ChartType | null): ChartType {
  if (requestedType && isChartTypeAllowed(datasetKind, requestedType)) {
    return requestedType;
  }
  return getDefaultChartType(datasetKind);
}

export function formatChartTypeLabel(chartType: ChartType): string {
  switch (chartType) {
    case "line":
      return "Line";
    case "area":
      return "Area";
    case "bar":
      return "Bar";
    case "stacked_bar":
      return "Stacked Bar";
    case "pie":
      return "Pie";
    case "donut":
      return "Donut";
    case "composed":
      return "Composed";
  }
}

export function formatChartTimeframeLabel(mode: ChartTimeframeMode): string {
  switch (mode) {
    case "snapshot":
      return "Snapshot";
    case "1y":
      return "1Y";
    case "3y":
      return "3Y";
    case "5y":
      return "5Y";
    case "10y":
      return "10Y";
    case "max":
      return "MAX";
    case "all":
      return "All";
  }
}

export function formatChartCadenceLabel(mode: ChartCadenceMode): string {
  switch (mode) {
    case "reported":
      return "Reported";
    case "quarterly":
      return "Quarterly";
    case "annual":
      return "Annual";
    case "ttm":
      return "TTM";
  }
}

function defineChartCapability(definition: ChartCapabilityDefinition): ChartCapabilityDefinition {
  validateChartCapability(definition);
  return Object.freeze({
    ...definition,
    allowedChartTypes: [...definition.allowedChartTypes],
    allowedTimeframeModes: [...definition.allowedTimeframeModes],
    allowedCadenceModes: definition.allowedCadenceModes ? [...definition.allowedCadenceModes] : undefined,
  });
}

function validateChartCapability(definition: ChartCapabilityDefinition) {
  if (!definition.allowedChartTypes.length) {
    throw new Error(`Chart capability ${definition.datasetKind} must expose at least one chart type.`);
  }

  if (!definition.allowedTimeframeModes.length) {
    throw new Error(`Chart capability ${definition.datasetKind} must expose at least one timeframe mode.`);
  }

  if (!definition.allowedChartTypes.includes(definition.defaultChartType)) {
    throw new Error(`Chart capability ${definition.datasetKind} has a default chart type that is not allowed.`);
  }

  if (TIME_SERIES_DATASET_KINDS.has(definition.datasetKind)) {
    for (const chartType of definition.allowedChartTypes) {
      if (PIE_FAMILY_TYPES.has(chartType)) {
        throw new Error(`Time-series dataset ${definition.datasetKind} cannot expose ${chartType}.`);
      }
    }

    if (!TIME_SERIES_PREFERRED_DEFAULTS.has(definition.defaultChartType)) {
      throw new Error(`Time-series dataset ${definition.datasetKind} must default to line, area, or composed.`);
    }
  }

  if (SNAPSHOT_COMPOSITION_DATASET_KINDS.has(definition.datasetKind)) {
    const hasPieFamilyType = definition.allowedChartTypes.some((chartType) => PIE_FAMILY_TYPES.has(chartType));
    if (!hasPieFamilyType) {
      throw new Error(`Snapshot composition dataset ${definition.datasetKind} must expose pie or donut.`);
    }
  }
}

function filterAllowedValues<T extends string>(allowedValues: readonly T[], requestedValues?: readonly T[]): T[] {
  if (!requestedValues?.length) {
    return [...allowedValues];
  }

  const allowedValueSet = new Set(allowedValues);
  const filteredValues = requestedValues.filter((value, index) => allowedValueSet.has(value) && requestedValues.indexOf(value) === index);

  return filteredValues.length ? filteredValues : [...allowedValues];
}
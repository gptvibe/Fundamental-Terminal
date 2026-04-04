import type { FinancialPayload, ModelPayload, OilCurveSeriesPayload, OilSensitivityPayload } from "@/lib/types";

export type OilOverlayModelStatus = "supported" | "partial" | "insufficient_data" | "unsupported";
export type OilSupportStatus = "supported" | "partial" | "unsupported";
export type OilSensitivitySource = "manual" | "dataset";

export interface OilOverlayYearPoint {
  year: number;
  price: number;
}

export interface OilOverlayScenarioInputs {
  baseFairValuePerShare: number | null;
  officialBaseCurve: OilOverlayYearPoint[];
  userEditedShortTermCurve: OilOverlayYearPoint[];
  userLongTermAnchor: number | null;
  fadeYears: number;
  annualAfterTaxOilSensitivity: number | null;
  dilutedShares: number | null;
  currentSharePrice?: number | null;
  annualDiscountRate: number;
  oilSupportStatus: OilSupportStatus;
  confidenceFlags?: string[];
}

export interface OilOverlayYearResult {
  year: number;
  baseOilPrice: number;
  scenarioOilPrice: number;
  oilPriceDelta: number;
  earningsDeltaAfterTax: number;
  perShareDelta: number;
  presentValuePerShare: number;
  discountFactor: number;
}

export interface OilOverlayScenarioResult {
  modelStatus: OilOverlayModelStatus;
  reason: string;
  epsDeltaPerDollarOil: number | null;
  overlayPvPerShare: number | null;
  scenarioFairValuePerShare: number | null;
  deltaVsBasePerShare: number | null;
  deltaVsBasePercent: number | null;
  impliedUpsideDownside: number | null;
  yearlyDeltas: OilOverlayYearResult[];
  confidenceFlags: string[];
}

const LOW_CONFIDENCE_FLAGS = new Set([
  "oil_sensitivity_low_confidence",
  "oil_curve_partial",
  "oil_curve_interpolated",
  "oil_support_partial",
]);

export function resolveBaseFairValuePerShare(models: ModelPayload[]): number | null {
  const dcfModel = models.find((model) => model.model_name === "dcf");
  const dcfFairValue = asNumber(dcfModel?.result?.fair_value_per_share);
  if (dcfFairValue != null) {
    return dcfFairValue;
  }

  const residualIncomeModel = models.find((model) => model.model_name === "residual_income");
  return asNumber(residualIncomeModel?.result?.intrinsic_value_per_share);
}

export function resolveDilutedShares(financials: FinancialPayload[]): number | null {
  const latest = financials[0];
  if (!latest) {
    return null;
  }
  return asNumber(latest.weighted_average_diluted_shares) ?? asNumber(latest.shares_outstanding);
}

export function annualizeOilCurveSeries(series: OilCurveSeriesPayload | null | undefined): OilOverlayYearPoint[] {
  if (!series) {
    return [];
  }

  const grouped = new Map<number, number[]>();
  for (const point of series.points ?? []) {
    const year = extractYear(point.observation_date ?? point.label);
    if (year == null || point.value == null) {
      continue;
    }
    const current = grouped.get(year) ?? [];
    current.push(point.value);
    grouped.set(year, current);
  }

  return Array.from(grouped.entries())
    .sort(([left], [right]) => left - right)
    .map(([year, values]) => ({ year, price: values.reduce((sum, value) => sum + value, 0) / values.length }));
}

export function buildDefaultShortTermCurve(points: OilOverlayYearPoint[]): OilOverlayYearPoint[] {
  if (!points.length) {
    return [];
  }
  return points.slice(-Math.min(3, points.length)).map((point) => ({ ...point }));
}

export function resolveDefaultLongTermAnchor(points: OilOverlayYearPoint[]): number | null {
  return points.length ? points[points.length - 1]?.price ?? null : null;
}

export function resolveBenchmarkOptions(series: OilCurveSeriesPayload[]): Array<{ value: string; label: string }> {
  return series
    .filter((item) => item.points.some((point) => point.value != null))
    .map((item) => ({
      value: item.series_id,
      label: item.series_id.toLowerCase().includes("wti") ? "WTI" : item.series_id.toLowerCase().includes("brent") ? "Brent" : item.label,
    }));
}

export function resolveDatasetAnnualSensitivity(sensitivity: OilSensitivityPayload | null | undefined): number | null {
  if (!sensitivity || sensitivity.status === "placeholder") {
    return null;
  }
  const basis = sensitivity.metric_basis.toLowerCase();
  if (!basis.includes("after_tax") && !basis.includes("earnings")) {
    return null;
  }
  return asNumber(sensitivity.elasticity);
}

export function computeOilOverlayScenario(inputs: OilOverlayScenarioInputs): OilOverlayScenarioResult {
  const validationError = validateOilOverlayInputs(inputs);
  if (validationError) {
    return {
      modelStatus: "insufficient_data",
      reason: validationError,
      epsDeltaPerDollarOil: null,
      overlayPvPerShare: null,
      scenarioFairValuePerShare: null,
      deltaVsBasePerShare: null,
      deltaVsBasePercent: null,
      impliedUpsideDownside: null,
      yearlyDeltas: [],
      confidenceFlags: Array.from(new Set([...(inputs.confidenceFlags ?? []), "oil_overlay_missing_inputs"])).sort(),
    };
  }

  if (inputs.oilSupportStatus === "unsupported") {
    return {
      modelStatus: "unsupported",
      reason: "Oil overlay is disabled for unsupported oil-exposure profiles.",
      epsDeltaPerDollarOil: null,
      overlayPvPerShare: null,
      scenarioFairValuePerShare: null,
      deltaVsBasePerShare: null,
      deltaVsBasePercent: null,
      impliedUpsideDownside: null,
      yearlyDeltas: [],
      confidenceFlags: Array.from(new Set([...(inputs.confidenceFlags ?? []), "oil_overlay_unsupported"])).sort(),
    };
  }

  const baseCurve = dedupeCurve(inputs.officialBaseCurve);
  const userCurve = dedupeCurve(inputs.userEditedShortTermCurve);
  const startYear = Math.min(...Array.from(new Set([...baseCurve.keys(), ...userCurve.keys()])));
  const endYear = Math.max(Math.max(...baseCurve.keys()), Math.max(...userCurve.keys()) + inputs.fadeYears);

  const yearlyDeltas: OilOverlayYearResult[] = [];
  let overlayPvPerShare = 0;
  for (let offset = 0; offset <= endYear - startYear; offset += 1) {
    const year = startYear + offset;
    const baseOilPrice = interpolateCurve(baseCurve, year);
    const scenarioOilPrice = evaluateScenarioCurve(year, baseCurve, userCurve, Number(inputs.userLongTermAnchor), inputs.fadeYears);
    const oilPriceDelta = scenarioOilPrice - baseOilPrice;
    const earningsDeltaAfterTax = Number(inputs.annualAfterTaxOilSensitivity) * oilPriceDelta;
    const perShareDelta = earningsDeltaAfterTax / Number(inputs.dilutedShares);
    const discountFactor = (1 + inputs.annualDiscountRate) ** (offset + 1);
    const presentValuePerShare = perShareDelta / discountFactor;
    overlayPvPerShare += presentValuePerShare;
    yearlyDeltas.push({
      year,
      baseOilPrice,
      scenarioOilPrice,
      oilPriceDelta,
      earningsDeltaAfterTax,
      perShareDelta,
      presentValuePerShare,
      discountFactor,
    });
  }

  const scenarioFairValuePerShare = Number(inputs.baseFairValuePerShare) + overlayPvPerShare;
  const deltaVsBasePerShare = overlayPvPerShare;
  const deltaVsBasePercent = safeDivide(deltaVsBasePerShare, Number(inputs.baseFairValuePerShare));
  const impliedUpsideDownside =
    inputs.currentSharePrice == null ? null : safeDivide(scenarioFairValuePerShare - inputs.currentSharePrice, inputs.currentSharePrice);

  const flags = new Set(inputs.confidenceFlags ?? []);
  if (inputs.oilSupportStatus === "partial") {
    flags.add("oil_support_partial");
  }
  const modelStatus: OilOverlayModelStatus = Array.from(flags).some((flag) => LOW_CONFIDENCE_FLAGS.has(flag)) ? "partial" : "supported";
  if (modelStatus === "partial") {
    flags.add("oil_overlay_low_confidence");
  }

  return {
    modelStatus,
    reason: "Fair-value overlay computed as discounted per-share earnings deltas on top of the base model output.",
    epsDeltaPerDollarOil: safeDivide(Number(inputs.annualAfterTaxOilSensitivity), Number(inputs.dilutedShares)),
    overlayPvPerShare,
    scenarioFairValuePerShare,
    deltaVsBasePerShare,
    deltaVsBasePercent,
    impliedUpsideDownside,
    yearlyDeltas,
    confidenceFlags: Array.from(flags).sort(),
  };
}

export function humanizeFlag(value: string): string {
  return value.replaceAll("_", " ");
}

function validateOilOverlayInputs(inputs: OilOverlayScenarioInputs): string | null {
  if (inputs.baseFairValuePerShare == null) {
    return "Base fair value per share is unavailable from the current models workspace.";
  }
  if (!inputs.officialBaseCurve.length) {
    return "Official benchmark curve is unavailable for the selected oil benchmark.";
  }
  if (!inputs.userEditedShortTermCurve.length) {
    return "Short-term oil curve edits require at least one annual point.";
  }
  if (inputs.userLongTermAnchor == null) {
    return "A long-term oil anchor is required to extend the overlay beyond the edited years.";
  }
  if (inputs.annualAfterTaxOilSensitivity == null) {
    return "Annual after-tax oil sensitivity is required to compute the overlay.";
  }
  if (inputs.dilutedShares == null || inputs.dilutedShares === 0) {
    return "Diluted shares are required for per-share overlay calculations.";
  }
  if (inputs.fadeYears < 0) {
    return "Fade years must be zero or greater.";
  }
  if (inputs.annualDiscountRate <= -1) {
    return "Discount rate must be greater than -100%.";
  }
  return null;
}

function extractYear(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }
  const match = value.match(/(19|20)\d{2}/);
  return match ? Number(match[0]) : null;
}

function dedupeCurve(points: OilOverlayYearPoint[]): Map<number, number> {
  return new Map(points.slice().sort((left, right) => left.year - right.year).map((point) => [point.year, point.price]));
}

function evaluateScenarioCurve(
  year: number,
  baseCurve: Map<number, number>,
  userCurve: Map<number, number>,
  longTermAnchor: number,
  fadeYears: number,
): number {
  const userYears = Array.from(userCurve.keys()).sort((left, right) => left - right);
  const firstUserYear = userYears[0];
  const lastUserYear = userYears[userYears.length - 1];
  if (year < firstUserYear) {
    return interpolateCurve(baseCurve, year);
  }
  if (year <= lastUserYear) {
    return interpolateCurve(userCurve, year);
  }
  if (fadeYears === 0) {
    return longTermAnchor;
  }
  const fadeEndYear = lastUserYear + fadeYears;
  if (year <= fadeEndYear) {
    const startPrice = interpolateCurve(userCurve, lastUserYear);
    const progress = (year - lastUserYear) / fadeYears;
    return startPrice + (longTermAnchor - startPrice) * progress;
  }
  return longTermAnchor;
}

function interpolateCurve(points: Map<number, number>, year: number): number {
  if (points.has(year)) {
    return points.get(year) as number;
  }
  const years = Array.from(points.keys()).sort((left, right) => left - right);
  if (year <= years[0]) {
    return points.get(years[0]) as number;
  }
  if (year >= years[years.length - 1]) {
    return points.get(years[years.length - 1]) as number;
  }
  let previousYear = years[0];
  let nextYear = years[years.length - 1];
  for (const candidate of years) {
    if (candidate < year) {
      previousYear = candidate;
      continue;
    }
    nextYear = candidate;
    break;
  }
  const previousValue = points.get(previousYear) as number;
  const nextValue = points.get(nextYear) as number;
  const progress = (year - previousYear) / (nextYear - previousYear);
  return previousValue + (nextValue - previousValue) * progress;
}

function safeDivide(numerator: number, denominator: number): number | null {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator) || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
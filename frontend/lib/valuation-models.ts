import type { ModelPayload } from "@/lib/types";

export interface DcfDisplayState {
  calculationVersion: string | null;
  isLegacy: boolean;
  valueBasis: string | null;
  isEnterpriseValueProxy: boolean;
  capitalStructureProxied: boolean;
  enterpriseValue: number | null;
  equityValue: number | null;
  fairValuePerShare: number | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function resolveDcfDisplayState(model: ModelPayload | null | undefined): DcfDisplayState {
  const result = asRecord(model?.result);
  const inputQuality = asRecord(result.input_quality);
  const resultCalculationVersion = typeof result.calculation_version === "string" ? result.calculation_version : null;
  const calculationVersion = typeof model?.calculation_version === "string" ? model.calculation_version : resultCalculationVersion;
  const isLegacy = model?.model_name === "dcf" && calculationVersion == null;
  const valueBasis = typeof result.value_basis === "string" ? result.value_basis : null;
  const capitalStructureProxied = inputQuality.capital_structure_proxied === true || result.capital_structure_proxied === true;
  const isEnterpriseValueProxy = valueBasis === "enterprise_value_proxy";
  const enterpriseValue = isLegacy ? null : asNumber(result.enterprise_value) ?? asNumber(result.enterprise_value_proxy);
  const equityValue = isLegacy ? null : asNumber(result.equity_value);
  const fairValuePerShare = isLegacy ? null : asNumber(result.fair_value_per_share);

  return {
    calculationVersion,
    isLegacy,
    valueBasis,
    isEnterpriseValueProxy,
    capitalStructureProxied,
    enterpriseValue,
    equityValue,
    fairValuePerShare,
  };
}

export function dcfEnterpriseValueLabel(state: DcfDisplayState): string {
  return state.isEnterpriseValueProxy ? "Enterprise Value Proxy" : "Enterprise Value";
}

export function describeDcfDisplayCaveat(state: DcfDisplayState): string | null {
  if (state.isLegacy) {
    return "Legacy cached DCF payload detected. Equity value and fair value per share are withheld until the model is recomputed under the current EV-to-equity bridge.";
  }
  if (state.isEnterpriseValueProxy || state.capitalStructureProxied) {
    return "Incomplete capital-structure data means this DCF run is shown as an Enterprise Value Proxy, not a precise equity fair value.";
  }
  return null;
}
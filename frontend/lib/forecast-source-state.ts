import type { ForecastHandoffPayload } from "@/lib/forecast-handoff";
import type { CompanyChartsDashboardResponse, CompanyChartsDriverCardPayload } from "@/lib/types";

export type ForecastSourceState = "sec_default" | "partial_default" | "fallback" | "user_scenario";

export interface ForecastSourceStateDescriptor {
  key: ForecastSourceState;
  label: string;
  compactLabel: string;
  description: string;
  tone: "positive" | "warning" | "danger" | "accent";
}

const FORECAST_SOURCE_STATE_DESCRIPTORS: Record<ForecastSourceState, ForecastSourceStateDescriptor> = {
  sec_default: {
    key: "sec_default",
    label: "SEC-Derived Default",
    compactLabel: "SEC Default",
    description: "Forecast remains on the SEC-derived default path without user overrides or fallback-heavy assumptions.",
    tone: "positive",
  },
  partial_default: {
    key: "partial_default",
    label: "Partial Default",
    compactLabel: "Partial Default",
    description: "Forecast stays rooted in SEC-derived inputs, but some assumptions are still supported by fallback defaults.",
    tone: "warning",
  },
  fallback: {
    key: "fallback",
    label: "Fallback State",
    compactLabel: "Fallback",
    description: "Forecast is currently relying heavily on fallback assumptions because direct disclosure support is thin.",
    tone: "danger",
  },
  user_scenario: {
    key: "user_scenario",
    label: "User Scenario",
    compactLabel: "User Scenario",
    description: "Forecast reflects user-entered scenario overrides on top of the SEC-derived baseline.",
    tone: "accent",
  },
};

export function getForecastSourceStateDescriptor(state: ForecastSourceState): ForecastSourceStateDescriptor {
  return FORECAST_SOURCE_STATE_DESCRIPTORS[state];
}

export function resolveForecastSourceState({
  userScenario = false,
  fallbackRatio = 0,
  defaultMarkersCount = 0,
  fallbackMarkersCount = 0,
}: {
  userScenario?: boolean;
  fallbackRatio?: number | null;
  defaultMarkersCount?: number;
  fallbackMarkersCount?: number;
}): ForecastSourceState {
  if (userScenario) {
    return "user_scenario";
  }

  const normalizedFallbackRatio = Math.max(0, fallbackRatio ?? 0);
  if (fallbackMarkersCount > 0 || normalizedFallbackRatio > 0) {
    if (defaultMarkersCount > 0 || (normalizedFallbackRatio > 0 && normalizedFallbackRatio < 1)) {
      return "partial_default";
    }
    return "fallback";
  }

  return "sec_default";
}

export function resolveChartsForecastSourceState(payload: CompanyChartsDashboardResponse): ForecastSourceState {
  return resolveForecastSourceState({
    fallbackRatio: payload.diagnostics?.fallback_ratio ?? 0,
  });
}

export function resolveProjectionForecastSourceState(
  payload: CompanyChartsDashboardResponse,
  activeOverrideCount: number
): ForecastSourceState {
  const drivers = payload.projection_studio?.drivers_used ?? [];
  return resolveForecastSourceState({
    userScenario: activeOverrideCount > 0 || Boolean(payload.what_if?.overrides_applied?.length),
    fallbackRatio: payload.diagnostics?.fallback_ratio ?? 0,
    defaultMarkersCount: countMarkers(drivers, "default_markers"),
    fallbackMarkersCount: countMarkers(drivers, "fallback_markers"),
  });
}

export function resolveForecastHandoffSourceState(
  handoff: ForecastHandoffPayload | null
): ForecastSourceState | null {
  if (!handoff) {
    return null;
  }
  return handoff.source === "user_scenario" ? "user_scenario" : "sec_default";
}

export function resolveSavedScenarioSourceState(source: "sec_base_forecast" | "user_scenario"): ForecastSourceState {
  return source === "user_scenario" ? "user_scenario" : "sec_default";
}

function countMarkers(
  drivers: CompanyChartsDriverCardPayload[],
  key: "default_markers" | "fallback_markers"
): number {
  return drivers.reduce((sum, driver) => sum + (driver[key]?.length ?? 0), 0);
}

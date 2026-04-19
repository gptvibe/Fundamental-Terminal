export const FORECAST_HANDOFF_QUERY_PARAM = "forecast_context";

export type ForecastHandoffSource = "sec_base_forecast" | "user_scenario";

export interface ForecastHandoffMetric {
  key: string;
  label: string;
  unit: string;
  base: number | null;
  scenario: number | null;
}

export interface ForecastHandoffPayload {
  version: 1;
  ticker: string;
  asOf: string | null;
  forecastYear: number | null;
  source: ForecastHandoffSource;
  scenarioName: string | null;
  overrideCount: number;
  metrics: ForecastHandoffMetric[];
  createdAt: string;
}

export function encodeForecastHandoffPayload(payload: ForecastHandoffPayload): string {
  return encodeURIComponent(JSON.stringify(payload));
}

export function decodeForecastHandoffPayload(rawValue: string | null): ForecastHandoffPayload | null {
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(decodeURIComponent(rawValue)) as Partial<ForecastHandoffPayload>;
    if (!parsed || parsed.version !== 1 || typeof parsed.ticker !== "string" || !Array.isArray(parsed.metrics)) {
      return null;
    }

    const metrics = parsed.metrics
      .map((metric): ForecastHandoffMetric | null => {
        if (!metric || typeof metric !== "object") {
          return null;
        }
        const candidate = metric as Partial<ForecastHandoffMetric>;
        if (typeof candidate.key !== "string" || typeof candidate.label !== "string" || typeof candidate.unit !== "string") {
          return null;
        }

        return {
          key: candidate.key,
          label: candidate.label,
          unit: candidate.unit,
          base: normalizeNumber(candidate.base),
          scenario: normalizeNumber(candidate.scenario),
        };
      })
      .filter((metric): metric is ForecastHandoffMetric => metric !== null);

    if (!metrics.length) {
      return null;
    }

    return {
      version: 1,
      ticker: parsed.ticker,
      asOf: typeof parsed.asOf === "string" ? parsed.asOf : null,
      forecastYear: typeof parsed.forecastYear === "number" && Number.isFinite(parsed.forecastYear) ? parsed.forecastYear : null,
      source: parsed.source === "user_scenario" ? "user_scenario" : "sec_base_forecast",
      scenarioName: typeof parsed.scenarioName === "string" ? parsed.scenarioName : null,
      overrideCount: typeof parsed.overrideCount === "number" && Number.isFinite(parsed.overrideCount) ? parsed.overrideCount : 0,
      metrics,
      createdAt: typeof parsed.createdAt === "string" ? parsed.createdAt : new Date(0).toISOString(),
    };
  } catch {
    return null;
  }
}

function normalizeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

import { buildCompanyChartsSpecFromPayload, getCompanyChartsOutlookSpec, getCompanyChartsStudioSpec, getOrderedOutlookComparisonCards, getOrderedOutlookMetricCards } from "@/lib/chart-spec";
import type {
  CompanyChartsCardPayload,
  CompanyChartsDashboardResponse,
  CompanyChartsLegendItemPayload,
  CompanyChartsProjectedRowPayload,
  CompanyChartsShareSnapshotChartPayload,
  CompanyChartsShareSnapshotMetricPayload,
  CompanyChartsShareSnapshotPayload,
  CompanyChartsShareSnapshotStudioRowPayload,
  CompanyChartsUnit,
} from "@/lib/types";

export const COMPANY_CHART_SHARE_SNAPSHOT_SCHEMA_VERSION = "company_chart_share_snapshot_v1";

export const CHART_SHARE_LAYOUTS = {
  square: { label: "1:1", width: 1200, height: 1200 },
  portrait: { label: "4:5", width: 1200, height: 1500 },
  landscape: { label: "16:9", width: 1200, height: 675 },
} as const;

export type ChartShareLayout = keyof typeof CHART_SHARE_LAYOUTS;

export function normalizeChartShareLayout(value: string | null | undefined): ChartShareLayout {
  if (value === "square" || value === "portrait" || value === "landscape") {
    return value;
  }
  return "landscape";
}

export function buildCompanyChartsShareImagePath(sharePath: string, layout: ChartShareLayout): string {
  return `${sharePath}/image?layout=${encodeURIComponent(layout)}`;
}

export function buildCompanyChartsShareImageUrl(sharePath: string, layout: ChartShareLayout, origin: string): string {
  return new URL(buildCompanyChartsShareImagePath(sharePath, layout), origin).toString();
}

export function buildOutlookChartShareSnapshot(
  payload: CompanyChartsDashboardResponse,
  options?: { sourcePath?: string | null }
): CompanyChartsShareSnapshotPayload {
  const chartSpec = buildCompanyChartsSpecFromPayload(payload);
  const outlook = getCompanyChartsOutlookSpec(payload);
  const legend = outlook.legend.items;
  const actualLabel = resolveLegendLabel(legend, "actual", "Reported");
  const forecastLabel = resolveLegendLabel(legend, "forecast", "Forecast");
  const primaryCard = getOrderedOutlookMetricCards(outlook, "primary").find((card) => card.key === "revenue") ?? outlook.cards.revenue;
  const comparisonCard = getOrderedOutlookComparisonCards(outlook)[0] ?? payload.cards.growth_summary;
  const phaseSummary = buildChartPhaseSummary(primaryCard);

  return {
    schema_version: COMPANY_CHART_SHARE_SNAPSHOT_SCHEMA_VERSION,
    mode: "outlook",
    ticker: payload.company?.ticker ?? "",
    company_name: payload.company?.name ?? null,
    title: outlook.title,
    as_of: payload.as_of,
    source_badge: outlook.summary.source_badges[0] ?? "Official filings",
    provenance_badge: payload.source_mix.official_only ? "SEC-derived" : "Mixed sources",
    trust_label: outlook.methodology.confidence_label ?? null,
    actual_label: actualLabel,
    forecast_label: forecastLabel,
    source_path: options?.sourcePath ?? buildChartsSourcePath(payload.company?.ticker ?? "", "outlook"),
    chart_spec: chartSpec,
    outlook: {
      headline: outlook.summary.headline,
      thesis: outlook.summary.thesis,
      primary_score: outlook.summary.primary_score,
      secondary_scores: outlook.summary.secondary_badges.slice(0, 3),
      summary_metrics: [
        buildShareMetric("reported", actualLabel, phaseSummary.reportedThrough ?? "Pending"),
        buildShareMetric("projected", forecastLabel, phaseSummary.projectedFrom ?? "Pending"),
        buildShareMetric(
          "growth_summary",
          comparisonCard?.title ?? "Growth Summary",
          formatShareMetricValue(comparisonCard?.comparisons?.[0]?.company_value ?? null, comparisonCard?.comparisons?.[0]?.unit ?? "count")
        ),
      ],
      primary_chart: buildShareChart(primaryCard),
    },
    studio: null,
  };
}

export function buildStudioChartShareSnapshot(
  payload: CompanyChartsDashboardResponse,
  options?: { sourcePath?: string | null; scenarioName?: string | null; overrideCount?: number }
): CompanyChartsShareSnapshotPayload {
  const chartSpec = buildCompanyChartsSpecFromPayload(payload);
  const studioSpec = getCompanyChartsStudioSpec(payload);
  const legend = chartSpec.outlook.legend.items;
  const actualLabel = resolveLegendLabel(legend, "actual", "Reported");
  const forecastLabel = resolveLegendLabel(legend, "forecast", "Forecast");
  const projectionStudio = studioSpec?.projection_studio ?? payload.projection_studio;
  const forecastYear = studioSpec?.what_if?.impact_summary?.forecast_year ?? findFirstProjectedYear(projectionStudio?.schedule_sections ?? []);

  return {
    schema_version: COMPANY_CHART_SHARE_SNAPSHOT_SCHEMA_VERSION,
    mode: "studio",
    ticker: payload.company?.ticker ?? "",
    company_name: payload.company?.name ?? null,
    title: studioSpec?.title ?? "Projection Studio",
    as_of: payload.as_of,
    source_badge: chartSpec.outlook.summary.source_badges[0] ?? "Official filings",
    provenance_badge: payload.source_mix.official_only ? "SEC-derived" : "Mixed sources",
    trust_label: payload.forecast_methodology.confidence_label ?? null,
    actual_label: actualLabel,
    forecast_label: forecastLabel,
    source_path: options?.sourcePath ?? buildChartsSourcePath(payload.company?.ticker ?? "", "studio"),
    chart_spec: chartSpec,
    outlook: null,
    studio: {
      headline: studioSpec?.title ?? "Projection Studio",
      summary: studioSpec?.summary ?? "Inspection of projected values, sensitivities, waterfall bridges, and traceable formulas.",
      scenario_name: options?.scenarioName ?? null,
      override_count: Math.max(0, options?.overrideCount ?? studioSpec?.what_if?.overrides_applied?.length ?? 0),
      forecast_year: forecastYear,
      metrics: collectStudioMetrics(projectionStudio?.schedule_sections ?? [], forecastYear),
      scenario_rows: (projectionStudio?.scenarios_comparison ?? []).slice(0, 4).map((row) => buildStudioScenarioRow(row)),
    },
  };
}

export function formatShareMetricValue(value: number | null | undefined, unit: CompanyChartsUnit | string): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  if (unit === "percent") {
    return `${(value * 100).toFixed(Math.abs(value) >= 0.1 ? 0 : 1)}%`;
  }
  if (unit === "usd") {
    return `$${formatCompactMetric(value)}`;
  }
  if (unit === "usd_per_share") {
    return `$${value.toFixed(Math.abs(value) >= 100 ? 0 : 2)}`;
  }
  if (unit === "ratio") {
    return `${value.toFixed(2)}x`;
  }
  return formatCompactMetric(value);
}

export function buildChartsSourcePath(ticker: string, mode: "outlook" | "studio"): string {
  const params = new URLSearchParams();
  params.set("mode", mode);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/company/${encodeURIComponent(ticker)}/charts${suffix}`;
}

function buildShareMetric(key: string, label: string, value: string, detail: string | null = null): CompanyChartsShareSnapshotMetricPayload {
  return { key, label, value, detail, tone: "neutral" };
}

function resolveLegendLabel(items: CompanyChartsLegendItemPayload[], tone: "actual" | "forecast", fallback: string): string {
  return items.find((item) => item.tone === tone)?.label ?? fallback;
}

function buildShareChart(card: CompanyChartsCardPayload | null | undefined): CompanyChartsShareSnapshotChartPayload | null {
  if (!card) {
    return null;
  }

  const actualSeries = card.series.filter((series) => series.series_kind === "actual");
  const forecastSeries = card.series.filter((series) => series.series_kind === "forecast");
  const actualPoints = actualSeries.flatMap((series) =>
    series.points.map((point) => ({
      label: point.period_label,
      value: point.value,
      kind: "actual" as const,
    }))
  );
  const forecastPoints = forecastSeries.flatMap((series) =>
    series.points.map((point) => ({
      label: point.period_label,
      value: point.value,
      kind: "forecast" as const,
    }))
  );

  if (!actualPoints.length && !forecastPoints.length) {
    return null;
  }

  return {
    title: card.title,
    unit: card.series[0]?.unit ?? "count",
    actual_points: actualPoints,
    forecast_points: forecastPoints,
  };
}

function buildChartPhaseSummary(card: CompanyChartsCardPayload | null | undefined): { reportedThrough: string | null; projectedFrom: string | null } {
  const rows = (card?.series ?? []).flatMap((series) =>
    series.points.map((point) => ({
      label: point.period_label,
      kind: point.series_kind,
    }))
  );

  return {
    reportedThrough: [...rows].reverse().find((row) => row.kind === "actual")?.label ?? null,
    projectedFrom: rows.find((row) => row.kind === "forecast")?.label ?? null,
  };
}

function collectStudioMetrics(
  scheduleSections: Array<{ rows: CompanyChartsProjectedRowPayload[] }>,
  forecastYear: number | null
): CompanyChartsShareSnapshotMetricPayload[] {
  if (forecastYear == null) {
    return [buildShareMetric("forecast_year", "Forecast Year", "Pending")];
  }

  const rows = [
    findProjectedRow(scheduleSections, "revenue"),
    findProjectedRow(scheduleSections, "operating_income"),
    findProjectedRow(scheduleSections, "free_cash_flow"),
    findProjectedRow(scheduleSections, "eps"),
  ].filter((row): row is CompanyChartsProjectedRowPayload => row !== null);

  const metrics = rows.slice(0, 3).map((row) =>
    buildShareMetric(row.key, row.label, formatShareMetricValue(row.projected_values[forecastYear], row.unit))
  );
  return [buildShareMetric("forecast_year", "Forecast Year", `FY${forecastYear}`), ...metrics];
}

function buildStudioScenarioRow(row: CompanyChartsProjectedRowPayload): CompanyChartsShareSnapshotStudioRowPayload {
  return {
    key: row.key,
    label: row.label,
    unit: row.unit,
    base_value: row.scenario_values.base ?? null,
    bull_value: row.scenario_values.bull ?? null,
    bear_value: row.scenario_values.bear ?? null,
  };
}

function findProjectedRow(
  sections: Array<{ rows: CompanyChartsProjectedRowPayload[] }>,
  rowKey: string
): CompanyChartsProjectedRowPayload | null {
  for (const section of sections) {
    const row = section.rows.find((candidate) => candidate.key === rowKey);
    if (row) {
      return row;
    }
  }
  return null;
}

function findFirstProjectedYear(sections: Array<{ rows: CompanyChartsProjectedRowPayload[] }>): number | null {
  const years = sections.flatMap((section) =>
    section.rows.flatMap((row) => Object.keys(row.projected_values).map((year) => Number(year)))
  );
  const validYears = years.filter((year) => Number.isFinite(year));
  return validYears.length ? Math.min(...validYears) : null;
}

function formatCompactMetric(value: number): string {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000_000) {
    return `${(value / 1_000_000_000_000).toFixed(1)}T`;
  }
  if (absolute >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(1)}B`;
  }
  if (absolute >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (absolute >= 1_000) {
    return `${(value / 1_000).toFixed(1)}K`;
  }
  return value.toFixed(Math.abs(value) >= 100 ? 0 : 1);
}

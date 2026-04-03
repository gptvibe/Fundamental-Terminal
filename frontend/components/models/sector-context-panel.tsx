"use client";

import { ChartStateBlock } from "@/components/charts/chart-framework";
import { MetricLabel } from "@/components/ui/metric-label";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanySectorContextResponse,
  SectorChartPayload,
  SectorDetailRowPayload,
  SectorMetricPayload,
  SectorPluginPayload,
} from "@/lib/types";

interface SectorContextPanelProps {
  context: CompanySectorContextResponse | null;
}

const CHART_COLORS = ["#1e90ff", "#ff8c00", "#00a86b", "#d14d72"];

export function SectorContextPanel({ context }: SectorContextPanelProps) {
  if (!context) {
    return <div className="text-muted">Sector context is loading...</div>;
  }

  if (!context.plugins.length) {
    return (
      <div style={{ display: "grid", gap: 14 }}>
        <SourceFreshnessSummary
          provenance={context.provenance}
          asOf={context.as_of}
          lastRefreshedAt={context.last_refreshed_at}
          sourceMix={context.source_mix}
          confidenceFlags={context.confidence_flags}
        />
        <ChartStateBlock
          title="Sector plug-ins"
          subtitle={context.status === "not_applicable" ? "No sector plug-ins matched this company" : "Sector context is unavailable"}
          detail={context.status === "not_applicable" ? "This company does not currently match the new official sector plug-ins." : "The official sector sources did not return usable data for this company yet."}
        />
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <SourceFreshnessSummary
        provenance={context.provenance}
        asOf={context.as_of}
        lastRefreshedAt={context.last_refreshed_at}
        sourceMix={context.source_mix}
        confidenceFlags={context.confidence_flags}
      />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">Status: {normalizeStatus(context.status)}</span>
        <span className="pill">Matched plug-ins: {context.matched_plugin_ids.length}</span>
        <span className="pill">Fetched: {formatDate(context.fetched_at)}</span>
      </div>

      <div style={{ display: "grid", gap: 12 }}>
        {context.plugins.map((plugin) => (
          <PluginCard key={plugin.plugin_id} plugin={plugin} />
        ))}
      </div>
    </div>
  );
}

function PluginCard({ plugin }: { plugin: SectorPluginPayload }) {
  return (
    <div className="filing-link-card" style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "start" }}>
        <div style={{ display: "grid", gap: 6 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <strong>{plugin.title}</strong>
            <span className="pill">{normalizeStatus(plugin.status)}</span>
          </div>
          <div className="text-muted">{plugin.description}</div>
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="pill">{plugin.refresh_policy.cadence_label}</span>
          <span className="pill">TTL {formatTtl(plugin.refresh_policy.ttl_seconds)}</span>
          {plugin.as_of ? <span className="pill">As of {plugin.as_of}</span> : null}
        </div>
      </div>

      {plugin.relevance_reasons.length ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {plugin.relevance_reasons.map((reason) => (
            <span key={reason} className="pill">{reason}</span>
          ))}
        </div>
      ) : null}

      {plugin.summary_metrics.length ? (
        <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          {plugin.summary_metrics.map((metric) => (
            <div key={metric.metric_id} className="metric-card">
              <div className="metric-label">
                <MetricLabel label={metric.label} />
              </div>
              <div className="metric-value">{formatUnitValue(metric.value, metric.unit)}</div>
              <div className="text-muted" style={{ fontSize: 12 }}>
                {metric.change_percent != null ? `${formatUnitChange(metric.change_percent, metric.unit)} vs prior` : metric.as_of ?? "No prior comparison"}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {plugin.charts.length ? (
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
          {plugin.charts.map((chart) => (
            <MiniLineChart key={chart.chart_id} chart={chart} />
          ))}
        </div>
      ) : null}

      <details className="subtle-details">
        <summary>
          {plugin.detail_view.title}
          <span className="pill">Rows {plugin.detail_view.rows.length}</span>
        </summary>
        <div className="subtle-details-body" style={{ display: "grid", gap: 8 }}>
          {plugin.detail_view.rows.map((row) => (
            <DetailRowCard key={`${plugin.plugin_id}-${row.label}`} row={row} />
          ))}
        </div>
      </details>
    </div>
  );
}

function DetailRowCard({ row }: { row: SectorDetailRowPayload }) {
  return (
    <div className="metric-card" style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <strong>{row.label}</strong>
        <span className="pill">{formatUnitValue(row.current_value, row.unit)}</span>
      </div>
      <div className="text-muted">
        {row.prior_value != null ? `Prior ${formatUnitValue(row.prior_value, row.unit)}` : "No prior value"}
        {row.change_percent != null ? ` | ${formatUnitChange(row.change_percent, row.unit)} vs prior` : ""}
        {row.as_of ? ` | ${row.as_of}` : ""}
      </div>
      {row.note ? <div className="text-muted" style={{ fontSize: 12 }}>{row.note}</div> : null}
    </div>
  );
}

function MiniLineChart({ chart }: { chart: SectorChartPayload }) {
  const validSeries = chart.series.map((series) => ({
    ...series,
    points: series.points.filter((point) => typeof point.value === "number" && Number.isFinite(point.value)),
  })).filter((series) => series.points.length > 0);

  if (!validSeries.length) {
    return (
      <div className="metric-card" style={{ display: "grid", gap: 8, minHeight: 180 }}>
        <div>
          <div style={{ fontWeight: 600 }}>{chart.title}</div>
          {chart.subtitle ? <div className="text-muted">{chart.subtitle}</div> : null}
        </div>
        <div className="text-muted">No chart points are available for this plugin yet.</div>
      </div>
    );
  }

  const allValues = validSeries.flatMap((series) => series.points.map((point) => point.value as number));
  const minValue = Math.min(...allValues);
  const maxValue = Math.max(...allValues);
  const valueRange = maxValue - minValue || 1;
  const width = 240;
  const height = 92;

  return (
    <div className="metric-card" style={{ display: "grid", gap: 8 }}>
      <div>
        <div style={{ fontWeight: 600 }}>{chart.title}</div>
        {chart.subtitle ? <div className="text-muted">{chart.subtitle}</div> : null}
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="92" aria-label={chart.title}>
        {validSeries.map((series, index) => (
          <polyline
            key={series.series_key}
            fill="none"
            stroke={CHART_COLORS[index % CHART_COLORS.length]}
            strokeWidth="2.5"
            points={series.points.map((point, pointIndex) => {
              const x = series.points.length === 1 ? width / 2 : (pointIndex / (series.points.length - 1)) * width;
              const y = height - (((point.value as number) - minValue) / valueRange) * (height - 8) - 4;
              return `${x},${y}`;
            }).join(" ")}
          />
        ))}
      </svg>

      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <span className="text-muted">{validSeries[0]?.points[0]?.label ?? ""}</span>
        <span className="text-muted">{validSeries[0]?.points[validSeries[0].points.length - 1]?.label ?? ""}</span>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {validSeries.map((series, index) => (
          <span key={series.series_key} className="pill" style={{ borderColor: CHART_COLORS[index % CHART_COLORS.length] }}>
            {series.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function formatUnitValue(value: number | null | undefined, unit: string): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  switch (unit) {
    case "percent":
    case "ratio":
      return formatPercent(value);
    case "usd":
      return `$${formatCompactNumber(value)}`;
    case "usd_per_bushel":
      return `$${value.toFixed(2)}/bu`;
    case "cents_per_kwh":
      return `${value.toFixed(2)} c/kWh`;
    case "index":
      return value.toFixed(2);
    case "million_bushels":
      return `${value.toFixed(1)}m bu`;
    case "million_kwh":
      return `${formatCompactNumber(value)} m kWh`;
    case "passengers":
    case "lbs":
      return formatCompactNumber(value);
    default:
      return formatCompactNumber(value);
  }
}

function formatUnitChange(value: number | null | undefined, unit: string): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  if (unit === "percent") {
    return formatPercent(value / 100);
  }
  return formatPercent(value);
}

function normalizeStatus(status: string): string {
  return status
    .split("_")
    .filter(Boolean)
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function formatTtl(ttlSeconds: number): string {
  if (ttlSeconds % 86_400 === 0) {
    return `${ttlSeconds / 86_400}d`;
  }
  if (ttlSeconds % 3_600 === 0) {
    return `${ttlSeconds / 3_600}h`;
  }
  return `${Math.round(ttlSeconds / 60)}m`;
}
"use client";

import type { CSSProperties } from "react";
import { useMemo } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyChartsAssumptionsCardPayload,
  CompanyChartsCardPayload,
  CompanyChartsComparisonCardPayload,
  CompanyChartsDashboardResponse,
  CompanyChartsFactorValuePayload,
  CompanyChartsLegendItemPayload,
  CompanyChartsScoreBadgePayload,
  CompanyChartsSeriesPayload,
  CompanyChartsTone,
  CompanyChartsUnit,
} from "@/lib/types";

type ChartRow = {
  periodLabel: string;
  forecastZone: boolean;
  values: Record<string, number | null>;
  pointMeta: Record<string, { annotation: string | null; seriesKind: string }>;
} & Record<string, number | boolean | string | null | Record<string, { annotation: string | null; seriesKind: string }> | Record<string, number | null>>;

const CARD_PALETTES: Record<string, string[]> = {
  revenue: ["#f2efe6", "#7be0a7"],
  revenue_growth: ["#79e08d", "#45674f"],
  profit_metric: ["#ffb15f", "#ffd56c", "#77d3ff"],
  cash_flow_metric: ["#7a88ff", "#d87dff", "#9ba6b2"],
  eps: ["#d6a04a", "#8f6f33"],
};

export function CompanyChartsDashboard({ payload }: { payload: CompanyChartsDashboardResponse }) {
  const company = payload.company;
  const factorItems = useMemo(
    () => [payload.factors.primary, ...payload.factors.supporting].filter((item): item is CompanyChartsFactorValuePayload => Boolean(item)),
    [payload.factors.primary, payload.factors.supporting]
  );

  return (
    <div className="charts-page-shell">
      <header className="charts-page-hero">
        <div className="charts-page-hero-copy">
          <div className="charts-page-kicker-row">
            <span className="charts-page-chip">Charts</span>
            <span className="charts-page-chip charts-page-chip-subtle">{payload.build_state === "ready" ? "Snapshot ready" : payload.build_status}</span>
          </div>
          <h1 className="charts-page-title">{company?.name ?? company?.ticker ?? "Company Charts"}</h1>
          <div className="charts-page-meta-row">
            <span className="charts-page-meta-pill">{company?.ticker ?? "Ticker pending"}</span>
            {company?.market_sector ? <span className="charts-page-meta-pill">{company.market_sector}</span> : null}
            {payload.forecast_methodology.confidence_label ? (
              <span className="charts-page-meta-pill">{payload.forecast_methodology.confidence_label}</span>
            ) : null}
          </div>
        </div>
        <div className="charts-page-hero-side">
          <div className="charts-page-hero-label">{payload.title}</div>
          <p className="charts-page-hero-status">{payload.build_status}</p>
        </div>
      </header>

      <div className="charts-dashboard-layout">
        <aside className="charts-summary-panel" aria-label="Growth outlook summary">
          <section className="charts-summary-block charts-summary-score-block">
            <div className="charts-summary-heading">
              <span className="charts-summary-eyebrow">{payload.summary.headline}</span>
              <PrimaryScoreBadge badge={payload.summary.primary_score} />
            </div>
            <div className="charts-summary-badge-grid">
              {payload.summary.secondary_badges.map((badge) => (
                <ScoreBadge key={badge.key} badge={badge} compact />
              ))}
            </div>
            <p className="charts-summary-thesis">{payload.summary.thesis ?? "Forecast values stay clearly labeled and separated from reported results."}</p>
          </section>

          <section className="charts-summary-block">
            <div className="charts-summary-section-title">Factor Profile</div>
            <div className="charts-factor-stack">
              {factorItems.map((factor) => (
                <FactorBar key={factor.key} factor={factor} />
              ))}
            </div>
          </section>

          <section className="charts-summary-block charts-summary-legend-block">
            <div className="charts-summary-section-title">{payload.legend.title}</div>
            <div className="charts-legend-stack">
              {payload.legend.items.map((item) => (
                <LegendItem key={item.key} item={item} />
              ))}
            </div>
          </section>

          {payload.summary.unavailable_notes.length ? (
            <section className="charts-summary-block">
              <div className="charts-summary-section-title">Notes</div>
              <div className="charts-note-list">
                {payload.summary.unavailable_notes.map((note) => (
                  <div key={note} className="charts-note-pill">
                    {note}
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section className="charts-summary-block charts-summary-footer-block">
            <div className="charts-summary-section-title">Freshness</div>
            <div className="charts-note-list">
              {payload.summary.freshness_badges.map((badge) => (
                <div key={badge} className="charts-note-pill charts-note-pill-muted">
                  {badge}
                </div>
              ))}
            </div>
            <div className="charts-summary-section-title">Sources</div>
            <div className="charts-note-list">
              {payload.summary.source_badges.map((badge) => (
                <div key={badge} className="charts-note-pill charts-note-pill-muted">
                  {badge}
                </div>
              ))}
            </div>
            <div className="charts-methodology-copy">
              <div className="charts-methodology-label">{payload.forecast_methodology.label}</div>
              <p>{payload.forecast_methodology.summary}</p>
              <p>{payload.forecast_methodology.disclaimer}</p>
            </div>
          </section>
        </aside>

        <section className="charts-card-grid" aria-label="Growth outlook charts">
          <MetricChartCard card={payload.cards.revenue} palette={CARD_PALETTES.revenue} />
          <MetricChartCard card={payload.cards.revenue_growth} palette={CARD_PALETTES.revenue_growth} />
          <MetricChartCard card={payload.cards.profit_metric} palette={CARD_PALETTES.profit_metric} />
          <MetricChartCard card={payload.cards.cash_flow_metric} palette={CARD_PALETTES.cash_flow_metric} />
          <MetricChartCard card={payload.cards.eps} palette={CARD_PALETTES.eps} />
          <GrowthSummaryCard card={payload.cards.growth_summary} />
          {payload.cards.forecast_assumptions ? <ForecastAssumptionsCard card={payload.cards.forecast_assumptions} /> : null}
          {payload.cards.forecast_calculations ? <ForecastAssumptionsCard card={payload.cards.forecast_calculations} /> : null}
        </section>
      </div>
    </div>
  );
}

function PrimaryScoreBadge({ badge }: { badge: CompanyChartsScoreBadgePayload }) {
  return (
    <div className={`charts-primary-score charts-tone-${badge.tone}`}>
      <div className="charts-primary-score-label">{badge.label}</div>
      <div className="charts-primary-score-value">{badge.score == null ? "—" : Math.round(badge.score)}</div>
    </div>
  );
}

function ScoreBadge({ badge, compact = false }: { badge: CompanyChartsScoreBadgePayload; compact?: boolean }) {
  return (
    <div className={`charts-score-badge charts-tone-${badge.tone} ${compact ? "is-compact" : ""}`}>
      <div className="charts-score-badge-label">{badge.label}</div>
      <div className="charts-score-badge-value">{badge.score == null ? "—" : Math.round(badge.score)}</div>
    </div>
  );
}

function FactorBar({ factor }: { factor: CompanyChartsFactorValuePayload }) {
  const width = Math.max(0, Math.min(100, Math.round((factor.normalized_score ?? 0) * 100)));
  return (
    <div className="charts-factor-row">
      <div className="charts-factor-copy">
        <div className="charts-factor-label">{factor.label}</div>
        <div className="charts-factor-detail">{factor.unavailable_reason ?? factor.detail ?? "Unavailable"}</div>
      </div>
      <div className="charts-factor-meter">
        <div className="charts-factor-meter-track">
          <div className={`charts-factor-meter-fill charts-tone-${factor.tone}`} style={{ width: `${width}%` }} />
        </div>
        <div className="charts-factor-score">{factor.score == null ? "—" : Math.round(factor.score)}</div>
      </div>
    </div>
  );
}

function LegendItem({ item }: { item: CompanyChartsLegendItemPayload }) {
  return (
    <div className="charts-legend-item">
      <span className={`charts-legend-swatch charts-legend-tone-${item.tone} charts-legend-style-${item.style}`} aria-hidden="true" />
      <div className="charts-legend-copy">
        <div className="charts-legend-label">{item.label}</div>
        {item.description ? <div className="charts-legend-detail">{item.description}</div> : null}
      </div>
    </div>
  );
}

function MetricChartCard({ card, palette }: { card: CompanyChartsCardPayload; palette: string[] }) {
  const rows = useMemo(() => buildChartRows(card.series), [card.series]);
  const forecastStart = rows.find((row) => row.forecastZone)?.periodLabel ?? null;

  return (
    <section className="charts-card">
      <div className="charts-card-header">
        <div>
          <h2 className="charts-card-title">{card.title}</h2>
          {card.subtitle ? <p className="charts-card-subtitle">{card.subtitle}</p> : null}
        </div>
        <div className="charts-card-series-pills">
          {card.series.map((series, index) => (
            <span key={series.key} className="charts-card-series-pill">
              <span
                className={`charts-card-series-marker ${series.stroke_style === "dashed" ? "is-dashed" : ""}`}
                style={{ "--marker-color": resolveSeriesColor(series, index, palette) } as CSSProperties}
              />
              {series.label}
            </span>
          ))}
        </div>
      </div>

      {rows.length ? (
        <div className="charts-card-plot">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              {forecastStart ? <ReferenceArea x1={forecastStart} x2={rows.at(-1)?.periodLabel} fill="rgba(123, 224, 167, 0.08)" strokeOpacity={0} /> : null}
              <XAxis dataKey="periodLabel" tick={chartTick(10)} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(value: number) => formatAxisValue(value, card.series[0]?.unit ?? "count")} tick={chartTick(10)} axisLine={false} tickLine={false} width={52} />
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                formatter={(value: unknown, name: unknown) => {
                  const dataKey = typeof name === "string" ? name : String(name ?? "");
                  const normalizedValue = Array.isArray(value) ? value[0] : value;
                  const series = card.series.find((item) => item.key === dataKey);
                  return [
                    formatMetricValue(typeof normalizedValue === "number" ? normalizedValue : null, series?.unit ?? "count"),
                    series?.label ?? dataKey,
                  ];
                }}
                labelFormatter={(label: string) => label}
              />
              {card.series.map((series, index) => {
                const color = resolveSeriesColor(series, index, palette);
                const commonProps = {
                  dataKey: series.key,
                  name: series.label,
                  stroke: color,
                  isAnimationActive: false,
                };

                if (series.chart_type === "bar") {
                  return (
                    <Bar
                      key={series.key}
                      {...commonProps}
                      fill={color}
                      stroke={color}
                      radius={[6, 6, 0, 0]}
                      fillOpacity={series.series_kind === "forecast" ? 0.42 : 0.92}
                      barSize={18}
                    />
                  );
                }

                if (series.chart_type === "area") {
                  return (
                    <Area
                      key={series.key}
                      {...commonProps}
                      fill={color}
                      fillOpacity={series.series_kind === "forecast" ? 0.12 : 0.18}
                      strokeWidth={series.series_kind === "forecast" ? 2 : 2.4}
                      strokeDasharray={series.stroke_style === "dashed" ? "5 5" : undefined}
                      dot={false}
                      activeDot={{ r: 4 }}
                      type="monotone"
                    />
                  );
                }

                return (
                  <Line
                    key={series.key}
                    {...commonProps}
                    strokeWidth={series.series_kind === "forecast" ? 2 : 2.4}
                    strokeDasharray={series.stroke_style === "dashed" ? "5 5" : undefined}
                    dot={false}
                    activeDot={{ r: 4 }}
                    type="monotone"
                  />
                );
              })}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="charts-card-empty">{card.empty_state ?? "Historical and forecast data are still warming up."}</div>
      )}

      {card.highlights.length ? (
        <div className="charts-card-highlights">
          {card.highlights.map((highlight) => (
            <span key={highlight} className="charts-card-highlight">
              {highlight}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function GrowthSummaryCard({ card }: { card: CompanyChartsComparisonCardPayload }) {
  return (
    <section className="charts-card charts-card-summary">
      <div className="charts-card-header">
        <div>
          <h2 className="charts-card-title">{card.title}</h2>
          {card.subtitle ? <p className="charts-card-subtitle">{card.subtitle}</p> : null}
        </div>
      </div>
      {card.comparisons.length ? (
        <div className="charts-summary-comparison-grid">
          {card.comparisons.map((comparison) => (
            <div key={comparison.key} className="charts-summary-comparison-card">
              <div className="charts-summary-comparison-label">{comparison.label}</div>
              <div className="charts-summary-comparison-value">
                {formatMetricValue(comparison.company_value, comparison.unit)}
              </div>
              <div className="charts-summary-comparison-company">{comparison.company_label ?? "Company"}</div>
              <div className="charts-summary-comparison-benchmark">
                {comparison.benchmark_available
                  ? `${comparison.benchmark_label ?? "Benchmark"} ${formatMetricValue(comparison.benchmark_value, comparison.unit)}`
                  : "Benchmark hidden until a trustworthy comparator is available"}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="charts-card-empty">{card.empty_state ?? "Growth comparison will appear when enough benchmark context is available."}</div>
      )}
    </section>
  );
}

function ForecastAssumptionsCard({ card }: { card: CompanyChartsAssumptionsCardPayload }) {
  return (
    <section className="charts-card charts-card-assumptions">
      <div className="charts-card-header">
        <div>
          <h2 className="charts-card-title">{card.title}</h2>
        </div>
      </div>
      {card.items.length ? (
        <div className="charts-assumptions-list">
          {card.items.map((item) => (
            <div key={item.key} className="charts-assumption-row">
              <div>
                <div className="charts-assumption-label">{item.label}</div>
                {item.detail ? <div className="charts-assumption-detail">{item.detail}</div> : null}
              </div>
              <div className="charts-assumption-value">{item.value}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="charts-card-empty">{card.empty_state ?? "Assumption details will appear when the forecast layer is available."}</div>
      )}
    </section>
  );
}

function buildChartRows(seriesList: CompanyChartsSeriesPayload[]): ChartRow[] {
  const byPeriod = new Map<string, ChartRow>();

  for (const series of seriesList) {
    for (const point of series.points) {
      const existing: ChartRow =
        byPeriod.get(point.period_label) ??
        {
          periodLabel: point.period_label,
          forecastZone: false,
          values: {},
          pointMeta: {},
        };

      existing.values[series.key] = point.value;
      existing[series.key] = point.value;
      existing.pointMeta[series.key] = {
        annotation: point.annotation,
        seriesKind: point.series_kind,
      };
      if (point.series_kind === "forecast") {
        existing.forecastZone = true;
      }

      byPeriod.set(point.period_label, existing);
    }
  }

  return Array.from(byPeriod.values());
}

function resolveSeriesColor(series: CompanyChartsSeriesPayload, index: number, palette: string[]): string {
  const explicit = palette[index % palette.length];
  if (series.series_kind === "comparison") {
    return "#7f8a96";
  }
  if (series.series_kind === "forecast" && series.chart_type !== "bar") {
    return explicit;
  }
  return explicit;
}

function formatAxisValue(value: number | null | undefined, unit: CompanyChartsUnit): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  switch (unit) {
    case "usd":
      return `$${formatCompactNumber(value)}`;
    case "usd_per_share":
      return `$${value.toFixed(value >= 100 ? 0 : 1)}`;
    case "percent":
      return formatPercent(value);
    case "shares":
      return formatCompactNumber(value);
    case "ratio":
      return `${value.toFixed(1)}x`;
    default:
      return formatCompactNumber(value);
  }
}

function formatMetricValue(value: number | null | undefined, unit: CompanyChartsUnit): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  switch (unit) {
    case "usd":
      return `$${formatCompactNumber(value)}`;
    case "usd_per_share":
      return `$${value.toFixed(value >= 100 ? 0 : 2)}`;
    case "percent":
      return formatPercent(value);
    case "shares":
      return formatCompactNumber(value);
    case "ratio":
      return `${value.toFixed(2)}x`;
    default:
      return formatCompactNumber(value);
  }
}

export function buildChartsFreshnessLine(payload: CompanyChartsDashboardResponse): string {
  if (payload.last_refreshed_at) {
    return `Refreshed ${formatDate(payload.last_refreshed_at)}`;
  }
  if (payload.company?.last_checked) {
    return `Checked ${formatDate(payload.company.last_checked)}`;
  }
  return "Freshness pending";
}

export function toneClassName(tone: CompanyChartsTone): string {
  return `charts-tone-${tone}`;
}

"use client";

import { useMemo } from "react";
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  LabelList,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartsModeSwitch } from "@/components/company/charts-mode-switch";
import { ForecastTrustCue } from "@/components/ui/forecast-trust-cue";
import { useForecastAccuracy } from "@/hooks/use-forecast-accuracy";
import { resolveChartsForecastSourceState } from "@/lib/forecast-source-state";
import { CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyChartsAssumptionsCardPayload,
  CompanyChartsCardPayload,
  CompanyChartsComparisonCardPayload,
  CompanyChartsDashboardResponse,
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

type MetricChartTooltipEntry = {
  dataKey?: string | number;
  name?: string | number;
  color?: string;
  value?: number | string | Array<number | string>;
  payload?: ChartRow;
};

const CARD_PALETTES: Record<string, string[]> = {
  revenue: ["#f2efe6", "#7be0a7"],
  revenue_outlook_bridge: ["#f2efe6", "#7be0a7", "#8ebbe2", "#e9c85d", "#f0877f", "#c7d0d9"],
  revenue_growth: ["#79e08d", "#45674f"],
  profit_metric: ["#ffb15f", "#ffd56c", "#77d3ff"],
  margin_path: ["#f2efe6", "#ffb15f", "#7be0a7", "#c7d0d9", "#ffd56c", "#8ebbe2"],
  cash_flow_metric: ["#7a88ff", "#d87dff", "#9ba6b2"],
  fcf_outlook: ["#f2efe6", "#77d3ff", "#7be0a7", "#d87dff", "#7a88ff", "#ffb15f", "#c7d0d9"],
  eps: ["#d6a04a", "#8f6f33"],
};

export function CompanyChartsDashboard({
  payload,
  activeMode = "outlook",
  studioEnabled = Boolean(payload.projection_studio),
  requestedAsOf = null,
}: {
  payload: CompanyChartsDashboardResponse;
  activeMode?: "outlook" | "studio";
  studioEnabled?: boolean;
  requestedAsOf?: string | null;
}) {
  const company = payload.company;
  const sourceState = useMemo(() => resolveChartsForecastSourceState(payload), [payload]);
  const forecastAccuracy = useForecastAccuracy(company?.ticker ?? "", {
    asOf: requestedAsOf,
    enabled: Boolean(company?.ticker),
  });
  const revenuePhaseSummary = useMemo(() => buildChartPhaseSummary(buildChartRows(payload.cards.revenue.series)), [payload.cards.revenue.series]);
  const summaryBadges = useMemo(() => payload.summary.secondary_badges.slice(0, 4), [payload.summary.secondary_badges]);
  const freshnessLine = useMemo(() => buildChartsFreshnessLine(payload), [payload]);
  const sourceLine = useMemo(() => payload.summary.source_badges.slice(0, 2).join(" · "), [payload.summary.source_badges]);
  const hasSecondaryOutlookCards = Boolean(payload.cards.revenue_outlook_bridge || payload.cards.margin_path || payload.cards.fcf_outlook);

  return (
    <div className="charts-page-shell">
      <header className="charts-page-hero">
        <div className="charts-page-hero-copy">
          <div className="charts-page-kicker-row">
            <span className="charts-page-chip">Charts</span>
            <span className="charts-page-chip charts-page-chip-subtle">{payload.build_state === "ready" ? "Snapshot ready" : payload.build_status}</span>
          </div>
          <ChartsModeSwitch activeMode={activeMode} studioEnabled={studioEnabled} />
          <h1 className="charts-page-title">{company?.name ?? company?.ticker ?? "Company Charts"}</h1>
          <div className="charts-page-meta-row">
            <span className="charts-page-meta-pill">{company?.ticker ?? "Ticker pending"}</span>
            {company?.market_sector ? <span className="charts-page-meta-pill">{company.market_sector}</span> : null}
            {payload.forecast_methodology.confidence_label ? (
              <span className="charts-page-meta-pill">{payload.forecast_methodology.confidence_label}</span>
            ) : null}
          </div>
          <p className="charts-page-hero-thesis">{payload.summary.thesis ?? "Forecast values stay clearly labeled and visually separated from reported results."}</p>
        </div>
        <div className="charts-page-hero-side charts-page-hero-summary-card">
          <div className="charts-page-hero-label">{payload.title}</div>
          <p className="charts-page-hero-status">{payload.build_status}</p>
          <div className="charts-page-hero-summary-grid">
            <HeroSummaryStat label="Reported" value={revenuePhaseSummary.reportedThrough ?? "Pending"} />
            <HeroSummaryStat label="Projected" value={revenuePhaseSummary.projectedFrom ?? "Pending"} />
            <HeroSummaryStat label={payload.summary.primary_score.label} value={payload.summary.primary_score.score == null ? "—" : String(Math.round(payload.summary.primary_score.score))} />
          </div>
          <div className="charts-page-hero-caption">{freshnessLine}</div>
        </div>
      </header>

      <KeyAssumptionsStrip card={payload.cards.forecast_assumptions} />

      <section className="charts-dashboard-matrix" aria-label="Growth outlook dashboard">
        <aside className="charts-summary-panel" aria-label="Growth outlook summary">
          <div className="charts-summary-head">
            <span className="charts-summary-eyebrow">{payload.summary.headline}</span>
            <PrimaryScoreBadge badge={payload.summary.primary_score} />
          </div>
          <div className="charts-summary-score-grid">
            {summaryBadges.map((badge) => (
              <ScoreBadge key={badge.key} badge={badge} compact />
            ))}
          </div>
          <div className="charts-summary-read-guide">
            <div className="charts-summary-section-title">{payload.legend.title}</div>
            <div className="charts-legend-inline" aria-label="Actual versus forecast legend">
              {payload.legend.items.map((item) => (
                <LegendInlineItem key={item.key} item={item} />
              ))}
            </div>
            <div className="charts-legend-footnote">Projected periods begin at the divider and use a soft shaded region inside each chart.</div>
          </div>
          <div className="charts-summary-data-lines">
            <SummaryDataLine label="Freshness" value={payload.summary.freshness_badges.join(" · ") || freshnessLine} />
            <SummaryDataLine label="Sources" value={sourceLine || "Official filings"} />
          </div>
          <div className="charts-summary-trust-block">
            <div className="charts-summary-section-title">Forecast Trust</div>
            <ForecastTrustCue
              sourceState={sourceState}
              accuracy={forecastAccuracy.data}
              loading={forecastAccuracy.loading}
              error={forecastAccuracy.error}
            />
          </div>
          <div className="charts-methodology-copy charts-methodology-copy-compact">
            <div className="charts-methodology-heading">SEC-Derived Outlook</div>
            <div className="charts-methodology-points" aria-label="Charts methodology standards">
              <div className="charts-methodology-point">SEC EDGAR filings only</div>
              <div className="charts-methodology-point">No third-party consensus or price prediction content</div>
              <div className="charts-methodology-point">Point-in-time inputs only</div>
              <div className="charts-methodology-point">Guarded fallback when disclosures are thin</div>
            </div>
            <div className="charts-methodology-label">{payload.forecast_methodology.label}</div>
            <p>{payload.forecast_methodology.summary}</p>
          </div>
          {payload.summary.unavailable_notes.length ? (
            <div className="charts-summary-note-list">
              {payload.summary.unavailable_notes.slice(0, 2).map((note) => (
                <div key={note} className="charts-summary-note-item">
                  {note}
                </div>
              ))}
            </div>
          ) : null}
        </aside>

        <MetricChartCard card={payload.cards.revenue} palette={CARD_PALETTES.revenue} className="charts-card-matrix" />
        <MetricChartCard card={payload.cards.revenue_growth} palette={CARD_PALETTES.revenue_growth} className="charts-card-matrix" />
        <MetricChartCard card={payload.cards.profit_metric} palette={CARD_PALETTES.profit_metric} className="charts-card-matrix" />
        <MetricChartCard card={payload.cards.cash_flow_metric} palette={CARD_PALETTES.cash_flow_metric} className="charts-card-matrix" />
        <MetricChartCard card={payload.cards.eps} palette={CARD_PALETTES.eps} className="charts-card-matrix" />
        <GrowthSummaryCard card={payload.cards.growth_summary} className="charts-card-matrix" />
      </section>

      {hasSecondaryOutlookCards ? (
        <section className="charts-card-grid charts-card-grid-secondary" aria-label="Growth outlook details">
          {payload.cards.revenue_outlook_bridge ? <MetricChartCard card={payload.cards.revenue_outlook_bridge} palette={CARD_PALETTES.revenue_outlook_bridge} className="charts-card-wide" /> : null}
          {payload.cards.margin_path ? <MetricChartCard card={payload.cards.margin_path} palette={CARD_PALETTES.margin_path} /> : null}
          {payload.cards.fcf_outlook ? <MetricChartCard card={payload.cards.fcf_outlook} palette={CARD_PALETTES.fcf_outlook} /> : null}
        </section>
      ) : null}

      {payload.cards.forecast_assumptions || payload.cards.forecast_calculations ? (
        <section className="charts-detail-grid" aria-label="Forecast details">
          {payload.cards.forecast_assumptions ? <ForecastAssumptionsCard card={payload.cards.forecast_assumptions} /> : null}
          {payload.cards.forecast_calculations ? <ForecastAssumptionsCard card={payload.cards.forecast_calculations} /> : null}
        </section>
      ) : null}
    </div>
  );
}

function HeroSummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="charts-page-hero-stat">
      <div className="charts-page-hero-stat-label">{label}</div>
      <div className="charts-page-hero-stat-value">{value}</div>
    </div>
  );
}

function KeyAssumptionsStrip({ card }: { card: CompanyChartsAssumptionsCardPayload | null }) {
  const summaryItems = useMemo(
    () =>
      (card?.items ?? [])
        .filter((item) => Boolean(item.label.trim() || item.value.trim()))
        .slice(0, 6),
    [card]
  );

  if (!summaryItems.length) {
    return null;
  }

  return (
    <section className="charts-assumption-strip" aria-label="Key assumptions">
      <div className="charts-assumption-strip-heading">Key Assumptions</div>
      <div className="charts-assumption-strip-grid">
        {summaryItems.map((item) => {
          const showWarning = assumptionNeedsAttention(item.detail) || assumptionNeedsAttention(item.value);
          return (
            <div key={item.key} className={`charts-assumption-summary-pill ${showWarning ? "is-warning" : ""}`}>
              <div className="charts-assumption-summary-topline">
                <span className="charts-assumption-summary-label">{item.label || "Assumption"}</span>
                {showWarning ? <span className="charts-assumption-summary-warning">Fallback</span> : null}
              </div>
              <div className="charts-assumption-summary-value">{item.value || "Pending"}</div>
              {item.detail ? <div className="charts-assumption-summary-detail">{item.detail}</div> : null}
            </div>
          );
        })}
      </div>
    </section>
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

function SummaryDataLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="charts-summary-data-line">
      <span className="charts-summary-data-line-label">{label}</span>
      <span className="charts-summary-data-line-value">{value}</span>
    </div>
  );
}

function LegendInlineItem({ item }: { item: CompanyChartsLegendItemPayload }) {
  return (
    <div className="charts-legend-inline-item">
      <span className={`charts-legend-swatch charts-legend-tone-${item.tone} charts-legend-style-${item.style}`} aria-hidden="true" />
      <span className="charts-legend-inline-label">{item.label}</span>
    </div>
  );
}

function MetricChartCard({ card, palette, className }: { card: CompanyChartsCardPayload; palette: string[]; className?: string }) {
  const rows = useMemo(() => buildChartRows(card.series), [card.series]);
  const phaseSummary = useMemo(() => buildChartPhaseSummary(rows), [rows]);
  const showSeriesEndLabels = useMemo(() => shouldShowSeriesEndLabels(card.series), [card.series]);
  const phaseContext = buildPhaseContextText(phaseSummary);
  const hasInlineLegend = card.series.length > 1 && !showSeriesEndLabels;

  return (
    <section className={`charts-card charts-card-metric ${phaseSummary.projectedFrom ? "has-forecast-boundary" : ""} ${className ?? ""}`.trim()}>
      <div className="charts-card-header">
        <div className="charts-card-copy">
          <h2 className="charts-card-title">{card.title}</h2>
          {card.subtitle ? <p className="charts-card-subtitle">{card.subtitle}</p> : null}
          {phaseContext ? <div className="charts-card-phase-line">{phaseContext}</div> : null}
        </div>
        {hasInlineLegend ? (
          <div className="charts-card-series-inline" aria-label={`${card.title} series`}>
            {card.series.map((series, index) => (
              <span key={series.key} className="charts-card-series-inline-item">
                <SeriesMarker color={resolveSeriesColor(series, index, palette)} dashed={series.stroke_style === "dashed"} />
                <span>{series.label}</span>
              </span>
            ))}
          </div>
        ) : null}
      </div>

      {rows.length ? (
        <div className="charts-card-plot">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              {phaseSummary.projectedFrom ? (
                <ReferenceArea x1={phaseSummary.projectedFrom} x2={rows.at(-1)?.periodLabel} fill="rgba(123, 224, 167, 0.09)" strokeOpacity={0} />
              ) : null}
              {phaseSummary.projectedFrom ? (
                <ReferenceLine x={phaseSummary.projectedFrom} stroke="rgba(242, 239, 230, 0.5)" strokeWidth={1.1} strokeDasharray="4 4" ifOverflow="extendDomain" />
              ) : null}
              <XAxis dataKey="periodLabel" tick={chartTick(11)} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(value: number) => formatAxisValue(value, card.series[0]?.unit ?? "count")} tick={chartTick(11)} axisLine={false} tickLine={false} width={56} />
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                cursor={{ stroke: "rgba(242, 239, 230, 0.28)", strokeWidth: 1 }}
                content={({ active, payload, label }) => (
                  <MetricChartTooltipContent
                    active={active}
                    label={label}
                    payload={payload as MetricChartTooltipEntry[] | undefined}
                    seriesList={card.series}
                  />
                )}
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
                      fillOpacity={series.series_kind === "forecast" ? 0.08 : 0.14}
                      strokeWidth={series.series_kind === "forecast" ? 2.4 : 2.8}
                      strokeDasharray={series.stroke_style === "dashed" ? "5 5" : undefined}
                      dot={false}
                      activeDot={{ r: 4.5 }}
                      type="monotone"
                    >
                      {showSeriesEndLabels ? <LabelList dataKey={`${series.key}__endLabel`} position="right" offset={8} className="charts-end-label" /> : null}
                    </Area>
                  );
                }

                return (
                  <Line
                    key={series.key}
                    {...commonProps}
                    strokeWidth={series.series_kind === "forecast" ? 2.4 : 2.8}
                    strokeDasharray={series.stroke_style === "dashed" ? "5 5" : undefined}
                    dot={false}
                    activeDot={{ r: 4.5 }}
                    type="monotone"
                  >
                    {showSeriesEndLabels ? <LabelList dataKey={`${series.key}__endLabel`} position="right" offset={8} className="charts-end-label" /> : null}
                  </Line>
                );
              })}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="charts-card-empty">{card.empty_state ?? "Historical and forecast data are still warming up."}</div>
      )}

      {card.highlights.length ? (
        <div className="charts-card-highlights charts-card-highlights-quiet">
          {card.highlights.slice(0, 2).map((highlight) => (
            <span key={highlight} className="charts-card-highlight">
              {highlight}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function SeriesMarker({ color, dashed }: { color: string; dashed: boolean }) {
  return (
    <svg className={`charts-card-series-marker ${dashed ? "is-dashed" : ""}`} viewBox="0 0 18 10" aria-hidden="true">
      <line className="charts-card-series-marker-line" x1="1" y1="5" x2="17" y2="5" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function MetricChartTooltipContent({
  active,
  label,
  payload,
  seriesList,
}: {
  active?: boolean;
  label?: string | number;
  payload?: MetricChartTooltipEntry[];
  seriesList: CompanyChartsSeriesPayload[];
}) {
  const activeRow = payload?.find((entry) => entry?.payload)?.payload;
  const visibleEntries = (payload ?? []).filter((entry) => entry && entry.value != null);

  if (!active || !activeRow || !visibleEntries.length) {
    return null;
  }

  const phaseLabel = activeRow.forecastZone ? "Projected period" : "Reported period";
  const formattedLabel = typeof label === "string" || typeof label === "number" ? String(label) : activeRow.periodLabel;

  return (
    <div className="charts-tooltip-card">
      <div className="charts-tooltip-header">
        <div className="charts-tooltip-period">{formattedLabel}</div>
        <div className={`charts-tooltip-phase ${activeRow.forecastZone ? "is-forecast" : "is-reported"}`}>{phaseLabel}</div>
      </div>
      <div className="charts-tooltip-series-list">
        {visibleEntries.map((entry) => {
          const dataKey = typeof entry.dataKey === "string" ? entry.dataKey : String(entry.dataKey ?? "");
          const normalizedValue = Array.isArray(entry.value) ? entry.value[0] : entry.value;
          const series = seriesList.find((item) => item.key === dataKey);
          const pointMeta = activeRow.pointMeta[dataKey];
          const kindLabel = pointMeta?.seriesKind === "forecast" ? "Projected" : pointMeta?.seriesKind === "actual" ? "Reported" : "Context";
          const annotation = pointMeta?.annotation ?? null;
          return (
            <div key={dataKey} className="charts-tooltip-series-row">
              <div className="charts-tooltip-series-labels">
                <span className="charts-tooltip-series-name">{series?.label ?? String(entry.name ?? dataKey)}</span>
                <span className={`charts-tooltip-series-kind ${pointMeta?.seriesKind === "forecast" ? "is-forecast" : "is-reported"}`}>{kindLabel}</span>
              </div>
              <div className="charts-tooltip-series-value">{formatMetricValue(typeof normalizedValue === "number" ? normalizedValue : null, series?.unit ?? "count")}</div>
              {annotation ? <div className="charts-tooltip-series-note">{annotation}</div> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GrowthSummaryCard({ card, className }: { card: CompanyChartsComparisonCardPayload; className?: string }) {
  return (
    <section className={`charts-card charts-card-summary ${className ?? ""}`.trim()}>
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

  for (const series of seriesList) {
    const lastPoint = [...series.points].reverse().find((point) => point.value != null);
    if (!lastPoint) {
      continue;
    }
    const row = byPeriod.get(lastPoint.period_label);
    if (!row) {
      continue;
    }
    row[`${series.key}__endLabel`] = series.label;
  }

  return Array.from(byPeriod.values());
}

function buildChartPhaseSummary(rows: ChartRow[]): { reportedThrough: string | null; projectedFrom: string | null } {
  const projectedFrom = rows.find((row) => row.forecastZone)?.periodLabel ?? null;
  const reportedThrough = [...rows].reverse().find((row) => !row.forecastZone)?.periodLabel ?? null;
  return {
    reportedThrough,
    projectedFrom,
  };
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

function shouldShowSeriesEndLabels(seriesList: CompanyChartsSeriesPayload[]): boolean {
  return seriesList.length > 0 && seriesList.length <= 2 && seriesList.every((series) => series.chart_type !== "bar");
}

function buildPhaseContextText(summary: { reportedThrough: string | null; projectedFrom: string | null }): string | null {
  if (summary.reportedThrough && summary.projectedFrom) {
    return `Reported through ${summary.reportedThrough} · Projected from ${summary.projectedFrom}`;
  }
  if (summary.reportedThrough) {
    return `Reported through ${summary.reportedThrough}`;
  }
  if (summary.projectedFrom) {
    return `Projected from ${summary.projectedFrom}`;
  }
  return null;
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

function assumptionNeedsAttention(value: string | null | undefined): boolean {
  if (!value) {
    return false;
  }
  return /(fallback|default|proxy|heuristic|bypass)/i.test(value);
}

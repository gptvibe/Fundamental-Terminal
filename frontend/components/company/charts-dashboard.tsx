"use client";

import { memo, useEffect, useMemo, useState } from "react";
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
import { ChartShareActions } from "@/components/company/chart-share-actions";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { Dialog } from "@/components/ui/dialog";
import { ForecastTrustCue } from "@/components/ui/forecast-trust-cue";
import { useForecastAccuracy } from "@/hooks/use-forecast-accuracy";
import { buildOutlookChartShareSnapshot } from "@/lib/chart-share";
import { getCompanyChartsOutlookSpec, getOrderedOutlookComparisonCards, getOrderedOutlookDetailCards, getOrderedOutlookMetricCards } from "@/lib/chart-spec";
import { resolveChartsForecastSourceState } from "@/lib/forecast-source-state";
import { CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyChartsAssumptionsCardPayload,
  CompanyChartsCardPayload,
  CompanyChartsComparisonCardPayload,
  CompanyChartsDashboardResponse,
  CompanyChartsLegendItemPayload,
  CompanyChartsMetricDiffPayload,
  CompanyChartsEventOverlayPayload,
  CompanyChartsEventPayload,
  CompanyChartsQuarterChangePayload,
  CompanyChartsScoreBadgePayload,
  CompanyChartsSeriesPayload,
  CompanyChartsTone,
  CompanyChartsUnit,
} from "@/lib/types";

type ChartRow = {
  periodLabel: string;
  forecastZone: boolean;
  events: CompanyChartsEventPayload[];
  values: Record<string, number | null>;
  pointMeta: Record<string, { annotation: string | null; seriesKind: string }>;
} & Record<string, number | boolean | string | null | CompanyChartsEventPayload[] | Record<string, { annotation: string | null; seriesKind: string }> | Record<string, number | null>>;

type MetricChartTooltipEntry = {
  dataKey?: string | number;
  name?: string | number;
  color?: string;
  value?: number | string | Array<number | string>;
  payload?: ChartRow;
};

const CARD_PALETTES: Record<string, string[]> = {
  revenue: ["var(--charts-series-reported)", "var(--charts-series-forecast)"],
  revenue_outlook_bridge: [
    "var(--charts-series-reported)",
    "var(--charts-series-forecast)",
    "var(--charts-series-context)",
    "var(--charts-series-warning)",
    "var(--charts-series-alert)",
    "var(--charts-series-muted)",
  ],
  revenue_growth: ["var(--charts-series-growth)", "var(--charts-series-growth-context)"],
  profit_metric: ["var(--charts-series-profit-1)", "var(--charts-series-profit-2)", "var(--charts-series-profit-3)"],
  margin_path: [
    "var(--charts-series-reported)",
    "var(--charts-series-profit-1)",
    "var(--charts-series-forecast)",
    "var(--charts-series-muted)",
    "var(--charts-series-profit-2)",
    "var(--charts-series-context)",
  ],
  cash_flow_metric: ["var(--charts-series-cash-1)", "var(--charts-series-cash-2)", "var(--charts-series-cash-3)"],
  fcf_outlook: [
    "var(--charts-series-reported)",
    "var(--charts-series-profit-3)",
    "var(--charts-series-forecast)",
    "var(--charts-series-cash-2)",
    "var(--charts-series-cash-1)",
    "var(--charts-series-profit-1)",
    "var(--charts-series-muted)",
  ],
  eps: ["var(--charts-series-eps-1)", "var(--charts-series-eps-2)"],
};

const EMPTY_EVENT_OVERLAY: CompanyChartsEventOverlayPayload = {
  title: "Event overlays",
  available_event_types: [],
  default_enabled_event_types: [],
  events: [],
  sparse_data_note: null,
};

const EMPTY_QUARTER_CHANGE: CompanyChartsQuarterChangePayload = {
  title: "What changed since last quarter?",
  latest_period_label: null,
  prior_period_label: null,
  summary: null,
  items: [],
  empty_state: "Not enough period history for a change summary yet.",
};

const ABOVE_FOLD_PRIMARY_CARD_COUNT = 1;
const ABOVE_FOLD_SECONDARY_CARD_COUNT = 1;

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
  const outlookSpec = useMemo(() => getCompanyChartsOutlookSpec(payload), [payload]);
  const primaryCards = useMemo(() => getOrderedOutlookMetricCards(outlookSpec, "primary"), [outlookSpec]);
  const secondaryCards = useMemo(() => getOrderedOutlookMetricCards(outlookSpec, "secondary"), [outlookSpec]);
  const comparisonCards = useMemo(() => getOrderedOutlookComparisonCards(outlookSpec), [outlookSpec]);
  const detailCards = useMemo(() => getOrderedOutlookDetailCards(outlookSpec), [outlookSpec]);
  const revenueCard = useMemo(
    () => primaryCards.find((card) => card.key === "revenue") ?? outlookSpec.cards.revenue,
    [outlookSpec.cards.revenue, primaryCards]
  );
  const primaryComparisonCard = comparisonCards[0] ?? outlookSpec.cards.growth_summary;
  const sourceState = useMemo(() => resolveChartsForecastSourceState(payload), [payload]);
  const forecastAccuracy = useForecastAccuracy(company?.ticker ?? "", {
    asOf: requestedAsOf,
    enabled: Boolean(company?.ticker),
  });
  const revenuePhaseSummary = useMemo(() => buildChartPhaseSummary(buildChartRows(revenueCard.series)), [revenueCard.series]);
  const summaryBadges = useMemo(() => outlookSpec.summary.secondary_badges.slice(0, 4), [outlookSpec.summary.secondary_badges]);
  const freshnessLine = useMemo(() => buildChartsFreshnessLine(payload), [payload]);
  const sourceLine = useMemo(() => outlookSpec.summary.source_badges.slice(0, 2).join(" · "), [outlookSpec.summary.source_badges]);
  const hasSecondaryOutlookCards = secondaryCards.length > 0;
  const initialPrimaryCards = useMemo(() => primaryCards.slice(0, ABOVE_FOLD_PRIMARY_CARD_COUNT), [primaryCards]);
  const deferredPrimaryCards = useMemo(() => primaryCards.slice(ABOVE_FOLD_PRIMARY_CARD_COUNT), [primaryCards]);
  const initialSecondaryCards = useMemo(() => secondaryCards.slice(0, ABOVE_FOLD_SECONDARY_CARD_COUNT), [secondaryCards]);
  const deferredSecondaryCards = useMemo(() => secondaryCards.slice(ABOVE_FOLD_SECONDARY_CARD_COUNT), [secondaryCards]);
  const shareSnapshot = useMemo(() => buildOutlookChartShareSnapshot(payload), [payload]);
  const eventOverlay = outlookSpec.event_overlay ?? payload.event_overlay ?? EMPTY_EVENT_OVERLAY;
  const quarterChange = outlookSpec.quarter_change ?? payload.quarter_change ?? EMPTY_QUARTER_CHANGE;
  const metricDiffByCard = useMemo(() => buildMetricDiffByCard(quarterChange), [quarterChange]);
  const defaultEnabledEventTypes = useMemo(
    () => eventOverlay.default_enabled_event_types.filter((eventType) => eventOverlay.available_event_types.includes(eventType)),
    [eventOverlay.available_event_types, eventOverlay.default_enabled_event_types]
  );
  const [enabledEventTypes, setEnabledEventTypes] = useState<Set<string>>(() => new Set(defaultEnabledEventTypes));
  const [selectedMetricDiff, setSelectedMetricDiff] = useState<CompanyChartsMetricDiffPayload | null>(null);

  useEffect(() => {
    setEnabledEventTypes(new Set(defaultEnabledEventTypes));
  }, [defaultEnabledEventTypes]);

  const enabledEventTypeList = useMemo(() => Array.from(enabledEventTypes), [enabledEventTypes]);

  const toggleEventType = (eventType: string) => {
    setEnabledEventTypes((prev) => {
      const next = new Set(prev);
      if (next.has(eventType)) {
        next.delete(eventType);
      } else {
        next.add(eventType);
      }
      return next;
    });
  };

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
            {outlookSpec.methodology.confidence_label ? (
              <span className="charts-page-meta-pill">{outlookSpec.methodology.confidence_label}</span>
            ) : null}
          </div>
          <p className="charts-page-hero-thesis">{outlookSpec.summary.thesis ?? "Forecast values stay clearly labeled and visually separated from reported results."}</p>
        </div>
        <div className="charts-page-hero-side charts-page-hero-summary-card">
          <div className="charts-page-hero-label">{outlookSpec.title}</div>
          <p className="charts-page-hero-status">{payload.build_status}</p>
          <div className="charts-page-hero-summary-grid">
            <HeroSummaryStat label="Reported" value={revenuePhaseSummary.reportedThrough ?? "Pending"} />
            <HeroSummaryStat label="Projected" value={revenuePhaseSummary.projectedFrom ?? "Pending"} />
            <HeroSummaryStat label={outlookSpec.summary.primary_score.label} value={outlookSpec.summary.primary_score.score == null ? "—" : String(Math.round(outlookSpec.summary.primary_score.score))} />
          </div>
          <div className="charts-page-hero-caption">{freshnessLine}</div>
          {company?.ticker ? <ChartShareActions ticker={company.ticker} snapshot={shareSnapshot} fileStem={`${company.ticker.toLowerCase()}-growth-outlook`} /> : null}
        </div>
      </header>

      <KeyAssumptionsStrip card={detailCards.find((card) => card.key === "forecast_assumptions") ?? null} />
      <DeferredClientSection placeholder={<LightweightPanelPlaceholder title="Event overlays" />}>
        <EventOverlayPanel overlay={eventOverlay} enabledEventTypes={enabledEventTypeList} onToggleEventType={toggleEventType} />
      </DeferredClientSection>
      <DeferredClientSection placeholder={<LightweightPanelPlaceholder title="What changed since last quarter?" />}>
        <QuarterChangePanel panel={quarterChange} />
      </DeferredClientSection>

      <section className="charts-dashboard-matrix" aria-label="Growth outlook dashboard">
        <aside className="charts-summary-panel" aria-label="Growth outlook summary">
          <div className="charts-summary-head">
            <span className="charts-summary-eyebrow">{outlookSpec.summary.headline}</span>
            <PrimaryScoreBadge badge={outlookSpec.summary.primary_score} />
          </div>
          <div className="charts-summary-score-grid">
            {summaryBadges.map((badge) => (
              <ScoreBadge key={badge.key} badge={badge} compact />
            ))}
          </div>
          <div className="charts-summary-read-guide">
            <div className="charts-summary-section-title">{outlookSpec.legend.title}</div>
            <div className="charts-legend-inline" aria-label="Actual versus forecast legend">
              {outlookSpec.legend.items.map((item) => (
                <LegendInlineItem key={item.key} item={item} />
              ))}
            </div>
            <div className="charts-legend-footnote">Projected periods begin at the divider and use a soft shaded region inside each chart.</div>
          </div>
          <div className="charts-summary-data-lines">
            <SummaryDataLine label="Freshness" value={outlookSpec.summary.freshness_badges.join(" · ") || freshnessLine} />
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
            <div className="charts-methodology-label">{outlookSpec.methodology.label}</div>
            <p>{outlookSpec.methodology.summary}</p>
          </div>
          {outlookSpec.summary.unavailable_notes.length ? (
            <div className="charts-summary-note-list">
              {outlookSpec.summary.unavailable_notes.slice(0, 2).map((note) => (
                <div key={note} className="charts-summary-note-item">
                  {note}
                </div>
              ))}
            </div>
          ) : null}
        </aside>

        {initialPrimaryCards.map((card) => (
          <MetricChartCard
            key={card.key}
            card={card}
            palette={CARD_PALETTES[card.key] ?? CARD_PALETTES.revenue}
            className="charts-card-matrix"
            overlayEvents={eventOverlay.events}
            enabledEventTypes={enabledEventTypeList}
            metricDiff={metricDiffByCard.get(card.key) ?? null}
            onOpenMetricDiff={setSelectedMetricDiff}
          />
        ))}
        <GrowthSummaryCard card={primaryComparisonCard} className="charts-card-matrix" />
      </section>

      {deferredPrimaryCards.length ? (
        <section className="charts-card-grid charts-card-grid-secondary" aria-label="Growth outlook extended metrics">
          {deferredPrimaryCards.map((card) => (
            <DeferredClientSection
              key={card.key}
              placeholder={<MetricChartCardPlaceholder title={card.title} />}
            >
              <MetricChartCard
                card={card}
                palette={CARD_PALETTES[card.key] ?? CARD_PALETTES.revenue}
                overlayEvents={eventOverlay.events}
                enabledEventTypes={enabledEventTypeList}
                metricDiff={metricDiffByCard.get(card.key) ?? null}
                onOpenMetricDiff={setSelectedMetricDiff}
              />
            </DeferredClientSection>
          ))}
        </section>
      ) : null}

      {hasSecondaryOutlookCards ? (
        <section className="charts-card-grid charts-card-grid-secondary" aria-label="Growth outlook details">
          {initialSecondaryCards.map((card, index) => (
            <DeferredClientSection
              key={card.key}
              forceVisible
              placeholder={<MetricChartCardPlaceholder title={card.title} />}
            >
              <MetricChartCard
                card={card}
                palette={CARD_PALETTES[card.key] ?? CARD_PALETTES.revenue}
                className={index === 0 ? "charts-card-wide" : undefined}
                overlayEvents={eventOverlay.events}
                enabledEventTypes={enabledEventTypeList}
                metricDiff={metricDiffByCard.get(card.key) ?? null}
                onOpenMetricDiff={setSelectedMetricDiff}
              />
            </DeferredClientSection>
          ))}
          {deferredSecondaryCards.map((card) => (
            <DeferredClientSection
              key={card.key}
              placeholder={<MetricChartCardPlaceholder title={card.title} />}
            >
              <MetricChartCard
                card={card}
                palette={CARD_PALETTES[card.key] ?? CARD_PALETTES.revenue}
                overlayEvents={eventOverlay.events}
                enabledEventTypes={enabledEventTypeList}
                metricDiff={metricDiffByCard.get(card.key) ?? null}
                onOpenMetricDiff={setSelectedMetricDiff}
              />
            </DeferredClientSection>
          ))}
        </section>
      ) : null}

      {detailCards.length ? (
        <section className="charts-detail-grid" aria-label="Forecast details">
          {detailCards.map((card) => (
            <DeferredClientSection
              key={card.key}
              placeholder={<AssumptionsCardPlaceholder title={card.title} />}
            >
              <ForecastAssumptionsCard card={card} />
            </DeferredClientSection>
          ))}
        </section>
      ) : null}

      <MetricDiffDialog diff={selectedMetricDiff} onClose={() => setSelectedMetricDiff(null)} />
    </div>
  );
}

function LightweightPanelPlaceholder({ title }: { title: string }) {
  return (
    <section className="charts-quarter-change-panel" aria-label={title}>
      <div className="charts-quarter-change-title">{title}</div>
      <div className="charts-card-empty">Loading cached context for this section...</div>
    </section>
  );
}

function MetricChartCardPlaceholder({ title }: { title: string }) {
  return (
    <section className="charts-card charts-card-metric">
      <div className="charts-card-header">
        <div className="charts-card-copy">
          <h2 className="charts-card-title">{title}</h2>
          <p className="charts-card-subtitle">Preparing chart view from cached series.</p>
        </div>
      </div>
      <div className="charts-card-empty">Loading chart panel...</div>
    </section>
  );
}

function AssumptionsCardPlaceholder({ title }: { title: string }) {
  return (
    <section className="charts-card charts-card-assumptions">
      <div className="charts-card-header">
        <div>
          <h2 className="charts-card-title">{title}</h2>
        </div>
      </div>
      <div className="charts-card-empty">Loading assumptions...</div>
    </section>
  );
}

const HeroSummaryStat = memo(function HeroSummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="charts-page-hero-stat">
      <div className="charts-page-hero-stat-label">{label}</div>
      <div className="charts-page-hero-stat-value">{value}</div>
    </div>
  );
});

const KeyAssumptionsStrip = memo(function KeyAssumptionsStrip({ card }: { card: CompanyChartsAssumptionsCardPayload | null }) {
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
});

const PrimaryScoreBadge = memo(function PrimaryScoreBadge({ badge }: { badge: CompanyChartsScoreBadgePayload }) {
  return (
    <div className={`charts-primary-score charts-tone-${badge.tone}`}>
      <div className="charts-primary-score-label">{badge.label}</div>
      <div className="charts-primary-score-value">{badge.score == null ? "—" : Math.round(badge.score)}</div>
    </div>
  );
});

const ScoreBadge = memo(function ScoreBadge({ badge, compact = false }: { badge: CompanyChartsScoreBadgePayload; compact?: boolean }) {
  return (
    <div className={`charts-score-badge charts-tone-${badge.tone} ${compact ? "is-compact" : ""}`}>
      <div className="charts-score-badge-label">{badge.label}</div>
      <div className="charts-score-badge-value">{badge.score == null ? "—" : Math.round(badge.score)}</div>
    </div>
  );
});

const SummaryDataLine = memo(function SummaryDataLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="charts-summary-data-line">
      <span className="charts-summary-data-line-label">{label}</span>
      <span className="charts-summary-data-line-value">{value}</span>
    </div>
  );
});

const LegendInlineItem = memo(function LegendInlineItem({ item }: { item: CompanyChartsLegendItemPayload }) {
  return (
    <div className="charts-legend-inline-item">
      <span className={`charts-legend-swatch charts-legend-tone-${item.tone} charts-legend-style-${item.style}`} aria-hidden="true" />
      <span className="charts-legend-inline-label">{item.label}</span>
    </div>
  );
});

const EventOverlayPanel = memo(function EventOverlayPanel({
  overlay,
  enabledEventTypes,
  onToggleEventType,
}: {
  overlay: CompanyChartsEventOverlayPayload;
  enabledEventTypes: string[];
  onToggleEventType: (eventType: string) => void;
}) {
  const visibleEvents = useMemo(() => overlay.events.filter((event) => enabledEventTypes.includes(event.event_type)).slice(0, 8), [enabledEventTypes, overlay.events]);

  return (
    <section className="charts-event-panel" aria-label="Event overlays">
      <div className="charts-event-panel-header">
        <h2 className="charts-card-title">{overlay.title}</h2>
        <div className="charts-event-toggle-row" role="group" aria-label="Event overlay toggles">
          {overlay.available_event_types.map((eventType) => {
            const enabled = enabledEventTypes.includes(eventType);
            return (
              <button key={eventType} type="button" className={`charts-event-toggle ${enabled ? "is-active" : ""}`} onClick={() => onToggleEventType(eventType)}>
                {eventType.replace(/_/g, " ")}
              </button>
            );
          })}
        </div>
      </div>
      {overlay.sparse_data_note ? <p className="charts-event-sparse-note">{overlay.sparse_data_note}</p> : null}
      <div className="charts-event-list" aria-label="Recent chart events">
        {visibleEvents.length ? (
          visibleEvents.map((event) => (
            <article key={event.key} className={`charts-event-item charts-event-type-${event.event_type}`}>
              <div className="charts-event-item-meta">
                <span>{formatDate(event.event_date)}</span>
                <span>{event.source_label}</span>
              </div>
              <div className="charts-event-item-title">{event.label}</div>
              {event.detail ? <div className="charts-event-item-detail">{event.detail}</div> : null}
            </article>
          ))
        ) : (
          <div className="charts-card-empty">No events in the selected categories for this snapshot.</div>
        )}
      </div>
    </section>
  );
});

const QuarterChangePanel = memo(function QuarterChangePanel({ panel }: { panel: CompanyChartsQuarterChangePayload }) {
  if (panel.empty_state) {
    return (
      <section className="charts-quarter-change-panel" aria-label="What changed since last quarter">
        <h2 className="charts-card-title">{panel.title}</h2>
        <div className="charts-card-empty">{panel.empty_state}</div>
      </section>
    );
  }

  return (
    <section className="charts-quarter-change-panel" aria-label="What changed since last quarter">
      <div className="charts-quarter-change-header">
        <h2 className="charts-card-title">{panel.title}</h2>
        {panel.latest_period_label && panel.prior_period_label ? <div className="charts-quarter-change-periods">{panel.latest_period_label} vs {panel.prior_period_label}</div> : null}
      </div>
      {panel.summary ? <p className="charts-quarter-change-summary">{panel.summary}</p> : null}
      <div className="charts-quarter-change-grid">
        {panel.items.map((item) => (
          <div key={item.key} className="charts-quarter-change-item">
            <div className="charts-quarter-change-label">{item.label}</div>
            <div className="charts-quarter-change-value">{item.value}</div>
            {item.detail ? <div className="charts-quarter-change-detail">{item.detail}</div> : null}
          </div>
        ))}
      </div>
    </section>
  );
});

const MetricDiffDialog = memo(function MetricDiffDialog({ diff, onClose }: { diff: CompanyChartsMetricDiffPayload | null; onClose: () => void }) {
  if (!diff) {
    return null;
  }

  const changeSummary = diff.absolute_change == null ? "No prior comparable value" : formatSignedValue(diff.absolute_change);
  const percentSummary = diff.percentage_change == null ? "N/A" : formatPercent(diff.percentage_change);

  return (
    <Dialog open={Boolean(diff)} onClose={onClose} labelledBy="metric-diff-title" contentClassName="charts-metric-diff-dialog">
      <div className="charts-metric-diff-header">
        <h2 id="metric-diff-title" className="charts-card-title">Why {diff.metric_label} changed</h2>
        <button type="button" className="charts-metric-diff-close" onClick={onClose} aria-label="Close metric change details">Close</button>
      </div>
      <div className="charts-metric-diff-grid">
        <MetricDiffCell label="Old value" value={formatNullableValue(diff.previous_value)} />
        <MetricDiffCell label="New value" value={formatNullableValue(diff.current_value)} />
        <MetricDiffCell label="Absolute change" value={changeSummary} />
        <MetricDiffCell label="Percentage change" value={percentSummary} />
      </div>
      <div className="charts-metric-diff-section">
        <div className="charts-summary-section-title">Changed input fields</div>
        <div className="charts-metric-diff-tags">
          {diff.changed_input_fields.length ? diff.changed_input_fields.map((field) => <span key={field} className="charts-metric-diff-tag">{field}</span>) : <span className="charts-metric-diff-empty">No input field changes were detected.</span>}
        </div>
      </div>
      <div className="charts-metric-diff-section">
        <div className="charts-summary-section-title">Filing / source</div>
        <div className="charts-metric-diff-source">{diff.source?.source_label ?? "Source unavailable"}</div>
        {diff.source?.filing_type ? <div className="charts-metric-diff-source-detail">Type: {diff.source.filing_type}</div> : null}
        {diff.source?.filing_date ? <div className="charts-metric-diff-source-detail">Date: {formatDate(diff.source.filing_date)}</div> : null}
        {diff.source?.detail ? <div className="charts-metric-diff-source-detail">{diff.source.detail}</div> : null}
      </div>
      {diff.previous_value_missing ? <div className="charts-metric-diff-note">Previous value is missing, so absolute and percentage deltas are unavailable.</div> : null}
      {diff.stale_cache ? <div className="charts-metric-diff-note">Snapshot cache is stale, so this explanation may lag newly filed updates.</div> : null}
    </Dialog>
  );
});

const MetricDiffCell = memo(function MetricDiffCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="charts-metric-diff-cell">
      <div className="charts-metric-diff-label">{label}</div>
      <div className="charts-metric-diff-value">{value}</div>
    </div>
  );
});

const MetricChartCard = memo(function MetricChartCard({
  card,
  palette,
  className,
  overlayEvents,
  enabledEventTypes,
  metricDiff,
  onOpenMetricDiff,
}: {
  card: CompanyChartsCardPayload;
  palette: string[];
  className?: string;
  overlayEvents: CompanyChartsEventPayload[];
  enabledEventTypes: string[];
  metricDiff: CompanyChartsMetricDiffPayload | null;
  onOpenMetricDiff: (diff: CompanyChartsMetricDiffPayload) => void;
}) {
  const rows = useMemo(
    () => buildChartRows(card.series, overlayEvents, enabledEventTypes),
    [card.series, enabledEventTypes, overlayEvents]
  );
  const phaseSummary = useMemo(() => buildChartPhaseSummary(rows), [rows]);
  const showSeriesEndLabels = useMemo(() => shouldShowSeriesEndLabels(card.series), [card.series]);
  const phaseContext = buildPhaseContextText(phaseSummary);
  const hasInlineLegend = card.series.length > 1 && !showSeriesEndLabels;
  const markerRows = useMemo(() => rows.filter((row) => row.events.length > 0), [rows]);

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
        {metricDiff ? (
          <button
            type="button"
            className="charts-why-changed-button"
            onClick={() => onOpenMetricDiff(metricDiff)}
            aria-label={`Why changed ${card.title}`}
          >
            Why changed?
          </button>
        ) : null}
      </div>

      {rows.length ? (
        <div className="charts-card-plot">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              {phaseSummary.projectedFrom ? (
                <ReferenceArea x1={phaseSummary.projectedFrom} x2={rows.at(-1)?.periodLabel} fill="var(--charts-forecast-region)" strokeOpacity={0} />
              ) : null}
              {phaseSummary.projectedFrom ? (
                <ReferenceLine x={phaseSummary.projectedFrom} stroke="var(--charts-forecast-divider)" strokeWidth={1.1} strokeDasharray="4 4" ifOverflow="extendDomain" />
              ) : null}
              <XAxis dataKey="periodLabel" tick={chartTick(11)} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(value: number) => formatAxisValue(value, card.series[0]?.unit ?? "count")} tick={chartTick(11)} axisLine={false} tickLine={false} width={56} />
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                cursor={{ stroke: "var(--charts-chart-cursor)", strokeWidth: 1 }}
                content={({ active, payload, label }) => (
                  <MetricChartTooltipContent
                    active={active}
                    label={label}
                    payload={payload as MetricChartTooltipEntry[] | undefined}
                    seriesList={card.series}
                  />
                )}
              />
              {markerRows.map((row) => (
                <ReferenceLine key={`${card.key}-${row.periodLabel}-events`} x={row.periodLabel} stroke="var(--charts-event-marker)" strokeWidth={1} strokeDasharray="2 6" ifOverflow="extendDomain" />
              ))}
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

      {markerRows.length ? (
        <div className="charts-event-rail" aria-label={`${card.title} events`}>
          {markerRows.slice(0, 4).map((row) => (
            <div key={`${card.key}-${row.periodLabel}-event-pill`} className="charts-event-rail-pill">
              <span className="charts-event-rail-period">{row.periodLabel}</span>
              <span className="charts-event-rail-count">{row.events.length} events</span>
            </div>
          ))}
        </div>
      ) : null}

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
});

const SeriesMarker = memo(function SeriesMarker({ color, dashed }: { color: string; dashed: boolean }) {
  return (
    <svg className={`charts-card-series-marker ${dashed ? "is-dashed" : ""}`} viewBox="0 0 18 10" aria-hidden="true">
      <line className="charts-card-series-marker-line" x1="1" y1="5" x2="17" y2="5" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
});

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

  const seriesByKey = new Map(seriesList.map((item) => [item.key, item]));

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
          const series = seriesByKey.get(dataKey);
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
      {activeRow.events.length ? (
        <div className="charts-tooltip-event-list">
          {activeRow.events.slice(0, 3).map((event) => (
            <div key={event.key} className="charts-tooltip-event-row">
              <span className="charts-tooltip-event-label">{event.label}</span>
              <span className="charts-tooltip-event-meta">{formatDate(event.event_date)} · {event.source_label}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const GrowthSummaryCard = memo(function GrowthSummaryCard({ card, className }: { card: CompanyChartsComparisonCardPayload; className?: string }) {
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
});

const ForecastAssumptionsCard = memo(function ForecastAssumptionsCard({ card }: { card: CompanyChartsAssumptionsCardPayload }) {
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
});

function buildMetricDiffByCard(panel: CompanyChartsQuarterChangePayload): Map<string, CompanyChartsMetricDiffPayload> {
  const map = new Map<string, CompanyChartsMetricDiffPayload>();
  for (const item of panel.items) {
    const diff = item.metric_diff;
    if (!diff) {
      continue;
    }
    const cardKeys = CARD_KEYS_BY_METRIC_DIFF[item.key] ?? [];
    for (const cardKey of cardKeys) {
      map.set(cardKey, diff);
    }
  }
  return map;
}

function formatNullableValue(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "N/A";
  }
  return formatCompactNumber(value);
}

function formatSignedValue(value: number): string {
  if (!Number.isFinite(value)) {
    return "N/A";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCompactNumber(value)}`;
}

const CARD_KEYS_BY_METRIC_DIFF: Record<string, string[]> = {
  revenue_delta: ["revenue", "revenue_growth", "revenue_outlook_bridge"],
  eps_delta: ["eps", "profit_metric", "margin_path"],
  fcf_delta: ["cash_flow_metric", "fcf_outlook"],
};

function buildChartRows(
  seriesList: CompanyChartsSeriesPayload[],
  overlayEvents: CompanyChartsEventPayload[] = [],
  enabledEventTypes: string[] = []
): ChartRow[] {
  const byPeriod = new Map<string, ChartRow>();
  const enabledEventTypeSet = enabledEventTypes.length ? new Set(enabledEventTypes) : null;

  for (const series of seriesList) {
    for (const point of series.points) {
      const existing: ChartRow =
        byPeriod.get(point.period_label) ??
        {
          periodLabel: point.period_label,
          forecastZone: false,
          events: [],
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
    let lastPoint = null as CompanyChartsSeriesPayload["points"][number] | null;
    for (let index = series.points.length - 1; index >= 0; index -= 1) {
      const point = series.points[index];
      if (point.value != null) {
        lastPoint = point;
        break;
      }
    }
    if (!lastPoint) {
      continue;
    }
    const row = byPeriod.get(lastPoint.period_label);
    if (!row) {
      continue;
    }
    row[`${series.key}__endLabel`] = series.label;
  }

  const rows = Array.from(byPeriod.values());
  if (!rows.length || !overlayEvents.length || !enabledEventTypeSet) {
    return rows;
  }

  const rowByLabel = new Map(rows.map((row) => [row.periodLabel, row]));
  for (const event of overlayEvents) {
    if (!enabledEventTypeSet.has(event.event_type)) {
      continue;
    }
    const direct = event.period_label ? rowByLabel.get(event.period_label) : null;
    if (direct) {
      direct.events.push(event);
      continue;
    }
    const year = Number.parseInt(event.event_date.slice(0, 4), 10);
    if (Number.isNaN(year)) {
      continue;
    }
    const inferred = rowByLabel.get(`FY${year}`) ?? rowByLabel.get(`FY${year}E`);
    if (inferred) {
      inferred.events.push(event);
    }
  }
  return rows;
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
    return "var(--charts-comparison-series)";
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

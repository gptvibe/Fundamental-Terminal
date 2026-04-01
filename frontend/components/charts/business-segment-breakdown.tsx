"use client";

import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import type { ChartInspectorControlState } from "@/components/charts/chart-inspector";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import { getCompanySegmentHistory } from "@/lib/api";
import { getDefaultChartType, type ChartType } from "@/lib/chart-capabilities";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem, type ExportRow } from "@/lib/export";
import { buildFinancialPeriodKey, type FinancialCadence } from "@/hooks/use-period-selection";
import type { SharedFinancialChartState } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import {
  dedupeSnapshotSurfaceWarnings,
  resolveSnapshotSurfaceMode,
  type SnapshotSurfaceCapabilities,
  type SnapshotSurfaceWarning,
} from "@/lib/snapshot-surface";
import type {
  FinancialPayload,
  FinancialSegmentPayload,
  SegmentAnalysisPayload,
  SegmentComparabilityFlagsPayload,
  SegmentDisclosurePayload,
  SegmentHistoryPeriodPayload,
  SegmentLensPayload,
} from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const SEGMENT_COLORS = ["var(--positive)", "var(--accent)", "var(--warning)", "var(--negative)", "#A855F7", "#64D2FF", "#0EA5E9"];
const SEGMENT_COMPOSITION_CHART_TYPE_OPTIONS = ["donut", "pie", "stacked_bar"] as const satisfies readonly ChartType[];
const DEFAULT_SEGMENT_COMPOSITION_CHART_TYPE: SegmentCompositionChartType = "donut";
const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

type SegmentKind = "business" | "geographic";

type TooltipEntry = {
  payload?: SegmentPoint;
};

type SegmentPoint = {
  id: string;
  name: string;
  axisLabel: string | null;
  kind: SegmentKind;
  revenue: number;
  share: number | null;
  operatingIncome: number | null;
  operatingMargin: number | null;
  growth: number | null;
  shareDelta: number | null;
  operatingMarginDelta: number | null;
  comparisonRevenue: number | null;
  comparisonShare: number | null;
  comparisonOperatingMargin: number | null;
  color: string;
};

type SegmentPeriod = {
  key: string;
  periodEnd: string;
  filingType: string | null;
  label: string;
  cadence: FinancialCadence | "reported";
  comparabilityFlags: SegmentComparabilityFlagsPayload;
  segments: Array<{
    id: string;
    name: string;
    axisLabel: string | null;
    kind: SegmentKind;
    revenue: number;
    share: number | null;
    operatingIncome: number | null;
    operatingMargin: number | null;
  }>;
};

interface BusinessSegmentBreakdownProps {
  financials: FinancialPayload[];
  segmentAnalysis?: SegmentAnalysisPayload | null;
  chartState?: SharedFinancialChartState;
  ticker?: string;
  reloadKey?: string | null;
}

export function BusinessSegmentBreakdown({
  financials,
  segmentAnalysis = null,
  chartState,
  ticker,
  reloadKey = null,
}: BusinessSegmentBreakdownProps) {
  const params = useParams<{ ticker?: string }>();
  const resolvedTicker = (ticker ?? params?.ticker ?? "").trim().toUpperCase();
  const noFinancials = financials.length === 0;
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);
  const [historyPeriods, setHistoryPeriods] = useState<SegmentHistoryPeriodPayload[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const { chartType: segmentCompositionChartType, setChartType: setSegmentCompositionChartType } = useChartPreferences({
    chartFamily: "segment-breakdown-composition",
    defaultChartType: DEFAULT_SEGMENT_COMPOSITION_CHART_TYPE,
    allowedChartTypes: SEGMENT_COMPOSITION_CHART_TYPE_OPTIONS,
  });

  const availableKinds = useMemo(() => {
    const kinds = new Set<SegmentKind>();
    for (const statement of financials) {
      for (const segment of statement.segment_breakdown) {
        if ((segment.kind === "business" || segment.kind === "geographic") && typeof segment.revenue === "number" && segment.revenue > 0) {
          kinds.add(segment.kind);
        }
      }
    }
    if (segmentAnalysis?.business) {
      kinds.add("business");
    }
    if (segmentAnalysis?.geographic) {
      kinds.add("geographic");
    }
    return kinds;
  }, [financials, segmentAnalysis]);

  const preferredKind: SegmentKind = availableKinds.has("business") ? "business" : "geographic";
  const [activeKind, setActiveKind] = useState<SegmentKind>(preferredKind);

  useEffect(() => {
    if (!availableKinds.has(activeKind)) {
      setActiveKind(preferredKind);
    }
  }, [activeKind, availableKinds, preferredKind]);

  const localPeriods = useMemo(
    () => buildLocalPeriods(financials, activeKind, chartState?.effectiveCadence ?? chartState?.cadence),
    [activeKind, chartState?.cadence, chartState?.effectiveCadence, financials]
  );
  const requestedYears = useMemo(() => Math.max(chartState?.visiblePeriodCount ?? localPeriods.length, 2), [chartState?.visiblePeriodCount, localPeriods.length]);
  const useAnnualHistory = (chartState?.effectiveCadence ?? chartState?.cadence ?? "annual") === "annual";

  useEffect(() => {
    if (!resolvedTicker || !useAnnualHistory) {
      setHistoryPeriods([]);
      setHistoryError(null);
      return;
    }

    const controller = new AbortController();
    setHistoryError(null);

    getCompanySegmentHistory(resolvedTicker, {
      kind: activeKind,
      years: requestedYears,
      signal: controller.signal,
    })
      .then((payload) => {
        setHistoryPeriods(payload.periods ?? []);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setHistoryPeriods([]);
        setHistoryError(error instanceof Error ? error.message : "Segment history is unavailable right now.");
      });

    return () => controller.abort();
  }, [activeKind, reloadKey, requestedYears, resolvedTicker, useAnnualHistory]);

  const mergedPeriods = useMemo(() => mergePeriods(localPeriods, buildHistoryPeriods(historyPeriods)), [historyPeriods, localPeriods]);
  const currentPeriod = useMemo(() => resolveDisplayPeriod(mergedPeriods, chartState?.selectedFinancial ?? null), [chartState?.selectedFinancial, mergedPeriods]);
  const explicitComparisonPeriod = useMemo(() => resolveDisplayPeriod(mergedPeriods, chartState?.comparisonFinancial ?? null), [chartState?.comparisonFinancial, mergedPeriods]);
  const implicitComparisonPeriod = useMemo(() => resolveImplicitComparisonPeriod(mergedPeriods, currentPeriod), [currentPeriod, mergedPeriods]);
  const comparisonPeriod = explicitComparisonPeriod ?? implicitComparisonPeriod;
  const comparisonIsExplicit = explicitComparisonPeriod !== null;
  const activeLens = activeKind === "business" ? segmentAnalysis?.business ?? null : segmentAnalysis?.geographic ?? null;

  const segmentPoints = useMemo(() => buildSegmentPoints(currentPeriod, comparisonPeriod), [comparisonPeriod, currentPeriod]);

  useEffect(() => {
    if (selectedSegmentId && !segmentPoints.some((segment) => segment.id === selectedSegmentId)) {
      setSelectedSegmentId(null);
    }
  }, [selectedSegmentId, segmentPoints]);

  const selectedSegment = useMemo(() => segmentPoints.find((segment) => segment.id === selectedSegmentId) ?? null, [segmentPoints, selectedSegmentId]);
  const pieChartData = useMemo(() => buildPieChartData(segmentPoints, selectedSegment), [segmentPoints, selectedSegment]);
  const selectedCompositionChartType: SegmentCompositionChartType = isSegmentCompositionChartType(segmentCompositionChartType)
    ? segmentCompositionChartType
    : DEFAULT_SEGMENT_COMPOSITION_CHART_TYPE;
  const compositionControlState = useMemo<ChartInspectorControlState>(
    () => ({
      datasetKind: "segment_mix",
      chartType: selectedCompositionChartType,
      chartTypeOptions: SEGMENT_COMPOSITION_CHART_TYPE_OPTIONS,
      onChartTypeChange: setSegmentCompositionChartType,
    }),
    [selectedCompositionChartType, setSegmentCompositionChartType]
  );
  const resetSegmentView = () => {
    setActiveKind(preferredKind);
    setSelectedSegmentId(null);
    setSegmentCompositionChartType(DEFAULT_SEGMENT_COMPOSITION_CHART_TYPE);
  };
  const resetSegmentViewDisabled =
    activeKind === preferredKind && selectedSegmentId === null && selectedCompositionChartType === DEFAULT_SEGMENT_COMPOSITION_CHART_TYPE;
  const revenueComparisonRows = useMemo(() => (selectedSegment ? [selectedSegment] : segmentPoints), [segmentPoints, selectedSegment]);
  const marginComparisonRows = useMemo(() => revenueComparisonRows.filter((segment) => segment.operatingMargin !== null), [revenueComparisonRows]);
  const marginDeltaRows = useMemo(() => marginComparisonRows.filter((segment) => segment.comparisonOperatingMargin !== null), [marginComparisonRows]);
  const trendPeriods = useMemo(() => mergedPeriods.filter((period) => period.segments.length > 0), [mergedPeriods]);
  const trendFocusSegments = useMemo(() => selectedSegment ? [selectedSegment] : segmentPoints.slice(0, Math.min(3, segmentPoints.length)), [segmentPoints, selectedSegment]);
  const revenueTrendData = useMemo(() => buildTrendData(trendPeriods, trendFocusSegments, "revenue"), [trendFocusSegments, trendPeriods]);
  const marginTrendData = useMemo(() => buildTrendData(trendPeriods, trendFocusSegments, "operatingMargin").filter((row) => trendFocusSegments.some((segment) => row[segment.id] != null)), [trendFocusSegments, trendPeriods]);

  const warnings = useMemo(() => buildWarnings({
    currentPeriod,
    comparisonPeriod: comparisonIsExplicit ? explicitComparisonPeriod : null,
    comparisonRequested: Boolean(chartState?.comparisonFinancial),
    chartState,
    historyError,
    trendPeriodCount: trendPeriods.length,
    activeKind,
  }), [activeKind, chartState, comparisonIsExplicit, currentPeriod, explicitComparisonPeriod, historyError, trendPeriods.length]);

  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: Boolean(chartState?.comparisonFinancial && explicitComparisonPeriod),
    trendAvailable: trendPeriods.length > 1,
    capabilities: CAPABILITIES,
  });

  const exportStem = useMemo(
    () => normalizeExportFileStem(resolvedTicker ? `${resolvedTicker}-${activeKind}` : `${activeKind}-segments`, "segments"),
    [activeKind, resolvedTicker]
  );

  const segmentSnapshotRows = useMemo(
    () =>
      segmentPoints.map((segment) => ({
        segment: segment.name,
        kind: segment.kind,
        revenue: segment.revenue,
        share: segment.share,
        operating_income: segment.operatingIncome,
        operating_margin: segment.operatingMargin,
        revenue_growth: segment.growth,
        share_delta: segment.shareDelta,
        operating_margin_delta: segment.operatingMarginDelta,
      })),
    [segmentPoints]
  );

  const revenueComparisonExportRows = useMemo(
    () =>
      revenueComparisonRows.map((segment) => ({
        segment: segment.name,
        current_revenue: segment.revenue,
        compare_revenue: segment.comparisonRevenue,
        revenue_growth: segment.growth,
        current_share: segment.share,
        compare_share: segment.comparisonShare,
      })),
    [revenueComparisonRows]
  );

  const marginComparisonExportRows = useMemo(
    () =>
      marginComparisonRows.map((segment) => ({
        segment: segment.name,
        current_operating_margin: segment.operatingMargin,
        compare_operating_margin: segment.comparisonOperatingMargin,
        margin_delta: segment.operatingMarginDelta,
      })),
    [marginComparisonRows]
  );

  const revenueTrendExportRows = useMemo(() => buildTrendExportRows(revenueTrendData, trendFocusSegments), [revenueTrendData, trendFocusSegments]);
  const marginTrendExportRows = useMemo(() => buildTrendExportRows(marginTrendData, trendFocusSegments), [marginTrendData, trendFocusSegments]);
  const currentPeriodLabel = currentPeriod?.label ?? "Reported segments";
  const currentPeriodAsOf = activeLens?.as_of ?? currentPeriod?.periodEnd ?? null;
  const segmentFooter = (
    <div className="chart-inspector-footer-stack">
      <div className="chart-inspector-footer-pill-row">
        <span className="pill">Kind: {activeKind === "business" ? "Business" : "Geography"}</span>
        <span className="pill">Focus: {currentPeriodLabel}</span>
        <span className="pill">As of {formatDate(currentPeriodAsOf)}</span>
        <span className="pill">Sources: {(activeLens?.provenance_sources.length ?? 0) || 1}</span>
      </div>
      <div className="chart-inspector-footer-copy">
        Provenance reflects cached SEC segment disclosures{activeLens?.last_refreshed_at ? `, refreshed ${formatDate(activeLens.last_refreshed_at)}` : ""}.
      </div>
    </div>
  );
  const segmentAnnotations = [
    { label: activeKind === "business" ? "Business segments" : "Geography segments", tone: "accent" as const },
    { label: selectedSegment?.name ?? "All segments", color: selectedSegment?.color ?? "var(--accent)" },
  ];

  function toggleSegment(segmentId: string) {
    setSelectedSegmentId((current) => (current === segmentId ? null : segmentId));
  }

  function renderSegmentBadgeArea() {
    const sourceValue = activeLens?.provenance_sources.length
      ? activeLens.provenance_sources.join(", ")
      : formatSourceLabel(financials[0]?.source ?? "reported filings");

    return (
      <ChartSourceBadges
        badges={[
          { label: "Focus", value: currentPeriodLabel },
          { label: chartState?.comparisonFinancial && explicitComparisonPeriod ? "Compare" : "Baseline", value: comparisonPeriod?.label ?? "None" },
          { label: "Segment", value: selectedSegment?.name ?? "All segments" },
          { label: "As of", value: formatDate(currentPeriodAsOf) },
          { label: "Source", value: sourceValue },
        ]}
      />
    );
  }

  function renderSegmentInspectorControls() {
    return (
      <div className="chart-inspector-control-stack">
        <div className="segment-filter-row">
          {[...availableKinds].map((kind) => (
            <button
              key={`inspector-kind-${kind}`}
              type="button"
              className={`chart-chip ${activeKind === kind ? "chart-chip-active" : ""}`}
              onClick={() => {
                setActiveKind(kind);
                setSelectedSegmentId(null);
              }}
            >
              {kind === "business" ? "Business" : "Geography"}
            </button>
          ))}
        </div>

        <div className="segment-filter-row">
          <button
            type="button"
            className={`chart-chip ${selectedSegmentId === null ? "chart-chip-active" : ""}`}
            onClick={() => setSelectedSegmentId(null)}
          >
            All Segments
          </button>
          {segmentPoints.map((segment) => (
            <button
              key={`inspector-segment-${segment.id}`}
              type="button"
              className={`chart-chip ${selectedSegmentId === segment.id ? "chart-chip-active" : ""}`}
              onClick={() => toggleSegment(segment.id)}
              style={{ borderColor: `${segment.color}55`, color: selectedSegmentId === segment.id ? "var(--bg)" : segment.color }}
            >
              {segment.name}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (noFinancials) {
    return (
      <div className="sparkline-note">
        No business segment breakdowns are reported for this company. If segments become available in SEC filings, they will appear here automatically.
      </div>
    );
  }

  if (!segmentPoints.length || !currentPeriod) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 320 }}>
        <div className="grid-empty-kicker">Reported segments</div>
        <div className="grid-empty-title">No cached segment breakdown yet</div>
        <div className="grid-empty-copy">
          Refresh the cache to backfill reported segment revenue from SEC filings. Some issuers may only disclose limited or geographic breakdowns.
        </div>
      </div>
    );
  }

  return (
    <div className="segment-breakdown-shell">
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div className="segment-breakdown-toolbar" style={{ gap: 14 }}>
        <div className="segment-filter-row">
          {[...availableKinds].map((kind) => (
            <button
              key={kind}
              type="button"
              className={`chart-chip ${activeKind === kind ? "chart-chip-active" : ""}`}
              onClick={() => {
                setActiveKind(kind);
                setSelectedSegmentId(null);
              }}
            >
              {kind === "business" ? "Business" : "Geography"}
            </button>
          ))}
        </div>

        <div className="segment-filter-row">
          <button
            type="button"
            className={`chart-chip ${selectedSegmentId === null ? "chart-chip-active" : ""}`}
            onClick={() => setSelectedSegmentId(null)}
          >
            All Segments
          </button>
          {segmentPoints.map((segment) => (
            <button
              key={segment.id}
              type="button"
              className={`chart-chip ${selectedSegmentId === segment.id ? "chart-chip-active" : ""}`}
              onClick={() => toggleSegment(segment.id)}
              style={{ borderColor: `${segment.color}55`, color: selectedSegmentId === segment.id ? "var(--bg)" : segment.color }}
            >
              {segment.name}
            </button>
          ))}
        </div>

        <div className="segment-meta-row">
          <span className="pill tone-cyan">Focus {currentPeriod.label}</span>
          {chartState?.comparisonFinancial && explicitComparisonPeriod ? <span className="pill tone-gold">Compare {explicitComparisonPeriod.label}</span> : null}
          {!chartState?.comparisonFinancial && comparisonPeriod ? <span className="pill">Baseline {comparisonPeriod.label}</span> : null}
          <span className="pill">Axis: {activeLens?.axis_label ?? segmentPoints[0]?.axisLabel ?? "Reported segments"}</span>
          <span className="pill">Focus Segment: {selectedSegment?.name ?? "All segments"}</span>
        </div>
      </div>

      {activeLens ? <LensSummary lens={activeLens} /> : null}

      <div className="segment-breakdown-top-grid">
        <SegmentChartFrame
          title="Revenue Treemap"
          subtitle="Selected period revenue mix. Click a tile to focus the compare and trend views."
          badgeArea={renderSegmentBadgeArea()}
          controls={renderSegmentInspectorControls()}
          annotations={segmentAnnotations}
          footer={segmentFooter}
          resetState={{ onReset: resetSegmentView, disabled: resetSegmentViewDisabled }}
          exportFileName={`${exportStem}-treemap.csv`}
          exportRows={segmentSnapshotRows}
          renderChart={({ expanded }) => (
            <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-treemap" style={expanded ? { height: 460 } : undefined}>
              <ResponsiveContainer>
                <Treemap
                  data={segmentPoints}
                  dataKey="revenue"
                  stroke="var(--panel-border)"
                  isAnimationActive
                  content={<SegmentTreemapNode selectedSegmentId={selectedSegmentId} onSelect={toggleSegment} />}
                >
                  <Tooltip content={<SegmentTooltip />} />
                </Treemap>
              </ResponsiveContainer>
            </div>
          )}
        />

        <SegmentChartFrame
          title="Revenue Share"
          subtitle="Selected period share of revenue, with compare deltas surfaced in the detail bars below."
          badgeArea={renderSegmentBadgeArea()}
          controls={renderSegmentInspectorControls()}
          controlState={compositionControlState}
          annotations={segmentAnnotations}
          footer={segmentFooter}
          resetState={{ onReset: resetSegmentView, disabled: resetSegmentViewDisabled }}
          stageState={
            pieChartData.length
              ? undefined
              : {
                  kind: "empty",
                  kicker: "Revenue share",
                  title: "No segment composition in view",
                  message: "Select a different segment set or period once the company exposes comparable segment revenue.",
                }
          }
          exportFileName={`${exportStem}-revenue-share.csv`}
          exportRows={segmentSnapshotRows}
          renderChart={({ expanded }) =>
            renderSegmentCompositionChart({
              chartType: expanded ? selectedCompositionChartType : "donut",
              data: pieChartData,
              currentPeriodLabel: currentPeriod.label,
              expanded,
              selectedSegmentId,
              onSelectSegment: toggleSegment,
            })
          }
        />
      </div>

      <SegmentChartFrame
        title={comparisonPeriod ? `${titleCase(activeKind)} Revenue Change` : `${titleCase(activeKind)} Revenue By Segment`}
        subtitle={comparisonPeriod
          ? `${currentPeriod.label} versus ${comparisonPeriod.label}.`
          : `Only one comparable ${activeKind} disclosure is visible, so this view falls back to the selected-period revenue mix.`}
        badgeArea={renderSegmentBadgeArea()}
        controls={renderSegmentInspectorControls()}
        annotations={segmentAnnotations}
        footer={segmentFooter}
        resetState={{ onReset: resetSegmentView, disabled: resetSegmentViewDisabled }}
        exportFileName={`${exportStem}-revenue-comparison.csv`}
        exportRows={revenueComparisonExportRows}
        renderChart={({ expanded }) => (
          <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-bar" style={expanded ? { height: 440 } : undefined}>
            <ResponsiveContainer>
              <BarChart data={revenueComparisonRows} margin={{ top: 12, right: expanded ? 24 : 18, left: 6, bottom: 4 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis
                  dataKey="name"
                  stroke={CHART_AXIS_COLOR}
                  tick={chartTick(expanded ? 11 : 10)}
                  interval={0}
                  angle={revenueComparisonRows.length > 3 ? -12 : 0}
                  textAnchor={revenueComparisonRows.length > 3 ? "end" : "middle"}
                  height={revenueComparisonRows.length > 3 ? 56 : 32}
                />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => comparisonPeriod ? formatPercent(Number(value)) : formatCompactNumber(Number(value))} />
                <Tooltip content={<SegmentTooltip />} />
                <Bar dataKey={comparisonPeriod ? "growth" : "revenue"} radius={[2, 2, 0, 0]} onClick={(entry) => entry?.id && toggleSegment(String(entry.id))}>
                  {revenueComparisonRows.map((segment) => (
                    <Cell key={segment.id} fill={comparisonPeriod && segment.growth != null && segment.growth < 0 ? "var(--negative)" : segment.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      />

      {marginComparisonRows.length ? (
        <div>
          <SegmentChartFrame
            title={`${titleCase(activeKind)} Operating Margin`}
            subtitle="Selected-period margin is always shown. Compare deltas appear whenever the baseline period reports operating income for the same segments."
            badgeArea={renderSegmentBadgeArea()}
            controls={renderSegmentInspectorControls()}
            annotations={segmentAnnotations}
            footer={segmentFooter}
            resetState={{ onReset: resetSegmentView, disabled: resetSegmentViewDisabled }}
            exportFileName={`${exportStem}-margin-comparison.csv`}
            exportRows={marginComparisonExportRows}
            renderChart={({ expanded }) => (
              <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-bar" style={expanded ? { height: 440 } : undefined}>
                <ResponsiveContainer>
                  <BarChart data={marginComparisonRows} margin={{ top: 12, right: expanded ? 24 : 18, left: 6, bottom: 4 }}>
                    <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                    <XAxis
                      dataKey="name"
                      stroke={CHART_AXIS_COLOR}
                      tick={chartTick(expanded ? 11 : 10)}
                      interval={0}
                      angle={marginComparisonRows.length > 3 ? -12 : 0}
                      textAnchor={marginComparisonRows.length > 3 ? "end" : "middle"}
                      height={marginComparisonRows.length > 3 ? 56 : 32}
                    />
                    <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatPercent(Number(value))} />
                    <Tooltip content={<SegmentTooltip />} />
                    <Bar dataKey="operatingMargin" name="Op. Margin" radius={[2, 2, 0, 0]} onClick={(entry) => entry?.id && toggleSegment(String(entry.id))}>
                      {marginComparisonRows.map((segment) => (
                        <Cell key={segment.id} fill={segment.operatingMargin != null && segment.operatingMargin < 0 ? "var(--negative)" : segment.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          />

          {marginDeltaRows.length ? (
            <div className="segment-table-shell">
              <table className="company-data-table" style={{ minWidth: 620 }}>
                <thead>
                  <tr>
                    <th align="left">Segment</th>
                    <th align="right">Selected Margin</th>
                    <th align="right">Compare Margin</th>
                    <th align="right">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {marginDeltaRows.map((row) => (
                    <tr key={`${row.id}:margin-delta`}>
                      <td>{row.name}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.operatingMargin)}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.comparisonOperatingMargin)}</td>
                      <td style={{ textAlign: "right", color: (row.operatingMarginDelta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedPoints(row.operatingMarginDelta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {revenueTrendData.length > 1 ? (
        <SegmentChartFrame
          title={`${titleCase(activeKind)} Revenue Trend`}
          subtitle={selectedSegment ? `${selectedSegment.name} across visible periods.` : "Top segments across the visible history window."}
          badgeArea={renderSegmentBadgeArea()}
          controls={renderSegmentInspectorControls()}
          annotations={segmentAnnotations}
          footer={segmentFooter}
          resetState={{ onReset: resetSegmentView, disabled: resetSegmentViewDisabled }}
          exportFileName={`${exportStem}-revenue-trend.csv`}
          exportRows={revenueTrendExportRows}
          renderChart={({ expanded }) => (
            <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-bar" style={expanded ? { height: 440 } : undefined}>
              <ResponsiveContainer>
                <BarChart data={revenueTrendData} margin={{ top: 12, right: expanded ? 24 : 18, left: 6, bottom: 4 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} interval={0} angle={-12} textAnchor="end" height={56} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatCompactNumber(Number(value))} />
                  <Tooltip />
                  {trendFocusSegments.map((segment) => (
                    <Bar key={segment.id} dataKey={segment.id} name={segment.name} fill={segment.color} radius={[2, 2, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        />
      ) : null}

      {marginTrendData.length > 1 ? (
        <SegmentChartFrame
          title={`${titleCase(activeKind)} Margin Trend`}
          subtitle={selectedSegment ? `${selectedSegment.name} operating margin across visible periods.` : "Operating margin trend for the current focus set."}
          badgeArea={renderSegmentBadgeArea()}
          controls={renderSegmentInspectorControls()}
          annotations={segmentAnnotations}
          footer={segmentFooter}
          resetState={{ onReset: resetSegmentView, disabled: resetSegmentViewDisabled }}
          exportFileName={`${exportStem}-margin-trend.csv`}
          exportRows={marginTrendExportRows}
          renderChart={({ expanded }) => (
            <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-bar" style={expanded ? { height: 440 } : undefined}>
              <ResponsiveContainer>
                <BarChart data={marginTrendData} margin={{ top: 12, right: expanded ? 24 : 18, left: 6, bottom: 4 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} interval={0} angle={-12} textAnchor="end" height={56} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatPercent(Number(value))} />
                  <Tooltip />
                  {trendFocusSegments.map((segment) => (
                    <Bar key={segment.id} dataKey={segment.id} name={segment.name} fill={segment.color} radius={[2, 2, 0, 0]} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        />
      ) : null}
    </div>
  );
}

function LensSummary({ lens }: { lens: SegmentLensPayload }) {
  return (
      <div style={{ display: "grid", gap: 12, marginBottom: 12 }}>
      <div className="segment-chart-card" style={{ display: "grid", gap: 12 }}>
        <div className="segment-card-header">
          <div className="segment-card-heading">
            <div className="segment-section-title">What Moved The {titleCase(lens.kind)} Mix</div>
            <div className="segment-section-subtitle">{lens.summary ?? "Recent disclosures are available, but there is not enough comparable history to explain the mix shift yet."}</div>
          </div>
          <div className="segment-card-meta">
            <span className="pill">As of {formatDate(lens.as_of)}</span>
            <span className="pill">Refreshed {formatDate(lens.last_refreshed_at)}</span>
            <span className="pill">Confidence {formatPercent(lens.confidence_score)}</span>
          </div>
        </div>

        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <MetricCard
            label="Top Line"
            value={lens.concentration.top_segment_name ? `${lens.concentration.top_segment_name} (${formatPercent(lens.concentration.top_segment_share)})` : "-"}
          />
          <MetricCard label="Top Two Share" value={formatPercent(lens.concentration.top_two_share)} />
          <MetricCard label="HHI" value={formatHhi(lens.concentration.hhi)} />
          <MetricCard label="Sources" value={lens.provenance_sources.join(", ") || "-"} />
        </div>

        {lens.top_mix_movers.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="segment-section-title" style={{ fontSize: 15 }}>Top Mix Movers</div>
            <div className="segment-table-shell">
              <table className="company-data-table" style={{ minWidth: 620 }}>
                <thead>
                  <tr>
                    <th align="left">Segment</th>
                    <th align="right">Share Delta</th>
                    <th align="right">Revenue Delta</th>
                    <th align="right">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lens.top_mix_movers.map((row) => (
                    <tr key={`${row.segment_id}:${row.status}`}>
                      <td>{row.segment_name}</td>
                      <td style={{ textAlign: "right", color: (row.share_delta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedPoints(row.share_delta)}
                      </td>
                      <td style={{ textAlign: "right", color: (row.revenue_delta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedCompactNumber(row.revenue_delta)}
                      </td>
                      <td style={{ textAlign: "right" }}>{titleCase(row.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {lens.top_margin_contributors.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="segment-section-title" style={{ fontSize: 15 }}>Margin Contribution</div>
            <div className="segment-table-shell">
              <table className="company-data-table" style={{ minWidth: 620 }}>
                <thead>
                  <tr>
                    <th align="left">Segment</th>
                    <th align="right">Op. Income Share</th>
                    <th align="right">Op. Margin</th>
                    <th align="right">Margin Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {lens.top_margin_contributors.map((row) => (
                    <tr key={`${row.segment_id}:margin`}>
                      <td>{row.segment_name}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.share_of_operating_income)}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.operating_margin)}</td>
                      <td style={{ textAlign: "right", color: (row.operating_margin_delta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedPoints(row.operating_margin_delta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {lens.unusual_disclosures.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="segment-section-title" style={{ fontSize: 15 }}>Unusual Disclosures</div>
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              {lens.unusual_disclosures.map((disclosure) => (
                <DisclosureCard key={disclosure.code} disclosure={disclosure} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SegmentChartFrame({
  title,
  subtitle,
  badgeArea,
  controls,
  controlState,
  annotations,
  footer,
  resetState,
  stageState,
  exportFileName,
  exportRows,
  renderChart,
}: {
  title: string;
  subtitle: string;
  badgeArea: ReactNode;
  controls: ReactNode;
  controlState?: ChartInspectorControlState;
  annotations?: Array<{ label: string; tone?: "neutral" | "accent" | "positive" | "warning"; color?: string }>;
  footer?: ReactNode;
  resetState?: { onReset: () => void; disabled?: boolean };
  stageState?: { kind: "ready" | "loading" | "empty" | "error"; kicker?: string; title?: string; message: string; actionLabel?: string; onAction?: () => void };
  exportFileName: string;
  exportRows: ExportRow[];
  renderChart: (context: { expanded: boolean }) => ReactNode;
}) {
  return (
    <InteractiveChartFrame
      title={title}
      subtitle={subtitle}
      className="segment-chart-card"
      headerClassName="segment-card-heading"
      titleClassName="segment-section-title"
      subtitleClassName="segment-section-subtitle"
      badgeArea={badgeArea}
      controls={controls}
      controlState={controlState}
      annotations={annotations}
      footer={footer}
      resetState={resetState}
      stageState={stageState}
      exportState={{
        pngFileName: exportFileName.replace(/\.csv$/i, ".png"),
        csvFileName: exportFileName,
        csvRows: exportRows,
      }}
      renderChart={renderChart}
    />
  );
}

function buildLocalPeriods(financials: FinancialPayload[], kind: SegmentKind, cadence: FinancialCadence | "reported" | undefined): SegmentPeriod[] {
  const source = selectSegmentStatements(financials, kind, cadence);
  return source.map((statement) => ({
    key: buildFinancialPeriodKey(statement),
    periodEnd: statement.period_end,
    filingType: statement.filing_type,
    label: `${statement.filing_type} ${formatDate(statement.period_end)}`,
    cadence: cadence ?? inferCadence(statement.filing_type),
    comparabilityFlags: emptyComparabilityFlags(),
    segments: normalizeSegments(
      statement.segment_breakdown.filter((segment) => segment.kind === kind && typeof segment.revenue === "number" && segment.revenue > 0),
      kind,
      statement.revenue
    ),
  }));
}

function buildHistoryPeriods(periods: SegmentHistoryPeriodPayload[]): SegmentPeriod[] {
  return periods.map((period) => ({
    key: period.period_end,
    periodEnd: period.period_end,
    filingType: null,
    label: period.fiscal_year != null ? `FY ${period.fiscal_year}` : formatDate(period.period_end),
    cadence: "annual",
    comparabilityFlags: period.comparability_flags,
    segments: normalizeHistorySegments(period),
  }));
}

function mergePeriods(localPeriods: SegmentPeriod[], historyPeriods: SegmentPeriod[]): SegmentPeriod[] {
  const historyByPeriodEnd = new Map(historyPeriods.map((period) => [period.periodEnd, period]));
  const merged = localPeriods.map((period) => {
    const history = historyByPeriodEnd.get(period.periodEnd);
    if (!history) {
      return period;
    }
    return {
      ...period,
      comparabilityFlags: history.comparabilityFlags,
      segments: period.segments.length ? period.segments : history.segments,
    };
  });
  for (const history of historyPeriods) {
    if (!merged.some((period) => period.periodEnd === history.periodEnd)) {
      merged.push(history);
    }
  }
  return merged.sort((left, right) => Date.parse(right.periodEnd) - Date.parse(left.periodEnd));
}

function resolveDisplayPeriod(periods: SegmentPeriod[], statement: FinancialPayload | null): SegmentPeriod | null {
  if (!periods.length) {
    return null;
  }
  if (!statement) {
    return periods[0] ?? null;
  }
  const key = buildFinancialPeriodKey(statement);
  return periods.find((period) => period.key === key || period.periodEnd === statement.period_end) ?? periods[0] ?? null;
}

function resolveImplicitComparisonPeriod(periods: SegmentPeriod[], currentPeriod: SegmentPeriod | null): SegmentPeriod | null {
  if (!currentPeriod) {
    return null;
  }
  const currentIndex = periods.findIndex((period) => period.key === currentPeriod.key);
  if (currentIndex < 0) {
    return periods[1] ?? null;
  }
  return periods[currentIndex + 1] ?? null;
}

function buildSegmentPoints(currentPeriod: SegmentPeriod | null, comparisonPeriod: SegmentPeriod | null): SegmentPoint[] {
  if (!currentPeriod) {
    return [];
  }
  const comparisonMap = new Map((comparisonPeriod?.segments ?? []).map((segment) => [segment.id, segment]));
  return currentPeriod.segments
    .map((segment, index) => {
      const comparison = comparisonMap.get(segment.id) ?? null;
      return {
        id: segment.id,
        name: segment.name,
        axisLabel: segment.axisLabel,
        kind: segment.kind,
        revenue: segment.revenue,
        share: segment.share,
        operatingIncome: segment.operatingIncome,
        operatingMargin: segment.operatingMargin,
        growth: calculateRelativeChange(segment.revenue, comparison?.revenue ?? null),
        shareDelta: calculateDelta(segment.share, comparison?.share ?? null),
        operatingMarginDelta: calculateDelta(segment.operatingMargin, comparison?.operatingMargin ?? null),
        comparisonRevenue: comparison?.revenue ?? null,
        comparisonShare: comparison?.share ?? null,
        comparisonOperatingMargin: comparison?.operatingMargin ?? null,
        color: SEGMENT_COLORS[index % SEGMENT_COLORS.length],
      } satisfies SegmentPoint;
    })
    .sort((left, right) => right.revenue - left.revenue);
}

function buildPieChartData(segmentPoints: SegmentPoint[], selectedSegment: SegmentPoint | null): SegmentPoint[] {
  if (!selectedSegment) {
    return segmentPoints;
  }
  const otherRevenue = segmentPoints.reduce((sum, segment) => segment.id === selectedSegment.id ? sum : sum + segment.revenue, 0);
  return [
    selectedSegment,
    ...(otherRevenue > 0 ? [{
      id: "other",
      name: "Other Segments",
      axisLabel: selectedSegment.axisLabel,
      kind: selectedSegment.kind,
      revenue: otherRevenue,
      share: otherRevenue / (otherRevenue + selectedSegment.revenue),
      operatingIncome: null,
      operatingMargin: null,
      growth: null,
      shareDelta: null,
      operatingMarginDelta: null,
      comparisonRevenue: null,
      comparisonShare: null,
      comparisonOperatingMargin: null,
      color: "var(--text-muted)",
    } satisfies SegmentPoint] : []),
  ];
}

function buildStackedCompositionRow(periodLabel: string, segmentPoints: SegmentPoint[]): Record<string, number | string> {
  const row: Record<string, number | string> = { period: periodLabel };
  for (const segment of segmentPoints) {
    row[segment.id] = segment.share ?? 0;
  }
  return row;
}

function buildTrendData(periods: SegmentPeriod[], focusSegments: SegmentPoint[], metric: "revenue" | "operatingMargin"): Array<Record<string, number | string | null>> {
  return [...periods].reverse().map((period) => {
    const row: Record<string, number | string | null> = { period: period.label };
    for (const segment of focusSegments) {
      const matching = period.segments.find((item) => item.id === segment.id) ?? null;
      row[segment.id] = metric === "revenue" ? matching?.revenue ?? null : matching?.operatingMargin ?? null;
    }
    return row;
  });
}

function buildTrendExportRows(rows: Array<Record<string, number | string | null>>, focusSegments: SegmentPoint[]): ExportRow[] {
  return rows.map((row) => {
    const exportRow: ExportRow = { period: row.period as string | number | null | undefined };
    for (const segment of focusSegments) {
      exportRow[segment.name] = row[segment.id] as string | number | null | undefined;
    }
    return exportRow;
  });
}

function buildWarnings({
  currentPeriod,
  comparisonPeriod,
  comparisonRequested,
  chartState,
  historyError,
  trendPeriodCount,
  activeKind,
}: {
  currentPeriod: SegmentPeriod | null;
  comparisonPeriod: SegmentPeriod | null;
  comparisonRequested: boolean;
  chartState?: SharedFinancialChartState;
  historyError: string | null;
  trendPeriodCount: number;
  activeKind: SegmentKind;
}): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];
  const flags = currentPeriod?.comparabilityFlags ?? emptyComparabilityFlags();
  if (chartState?.requestedCadence && chartState.requestedCadence !== "annual") {
    warnings.push({
      code: "segment_history_annual_only",
      label: "Server-backed segment history is annual-only",
      detail: "Quarterly and TTM selections keep the selected-period composition and reported-period trend views in sync, but the extended segment history service only runs on annual ranges.",
      tone: "info",
    });
  }
  if (comparisonRequested && !comparisonPeriod) {
    warnings.push({
      code: "comparison_period_missing",
      label: "Comparison period unavailable",
      detail: `The selected comparison period does not expose comparable ${activeKind} disclosure in the current view.`,
      tone: "warning",
    });
  }
  if (trendPeriodCount < 2) {
    warnings.push({
      code: "single_period_visible",
      label: "Sparse visible history",
      detail: `Only one ${activeKind} disclosure period is available, so the trend view falls back to the selected period snapshot.`,
      tone: "info",
    });
  }
  if (flags.no_prior_comparable_disclosure) {
    warnings.push({
      code: "no_prior_comparable_disclosure",
      label: "No prior comparable disclosure",
      detail: `The selected ${activeKind} period has no prior comparable disclosure, so growth and delta views are limited.`,
      tone: "warning",
    });
  }
  if (flags.segment_axis_changed) {
    warnings.push({
      code: "segment_axis_changed",
      label: "Segment axis changed",
      detail: `Management changed the reported ${activeKind} axis, so period-over-period comparisons may not be apples to apples.`,
      tone: "danger",
    });
  }
  if (flags.partial_operating_income_disclosure) {
    warnings.push({
      code: "partial_operating_income_disclosure",
      label: "Partial operating income disclosure",
      detail: "Business operating margin is shown only for the segments that reported operating income in the filing.",
      tone: "warning",
    });
  }
  if (flags.new_or_removed_segments) {
    warnings.push({
      code: "new_or_removed_segments",
      label: "Segment roster changed",
      detail: `At least one ${activeKind} segment was added or removed between the compared periods.`,
      tone: "warning",
    });
  }
  if (historyError) {
    warnings.push({
      code: "segment_history_fetch_failed",
      label: "History service unavailable",
      detail: `${historyError} The component is falling back to statement-level segment disclosures already loaded on the page.`,
      tone: "info",
    });
  }
  return dedupeSnapshotSurfaceWarnings(warnings);
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid var(--panel-border)", borderRadius: 6, padding: 12, background: "var(--panel)", display: "grid", gap: 4 }}>
      <div className="text-muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontWeight: 700, wordBreak: "break-word", color: "var(--surface-strong-text)" }}>{value}</div>
    </div>
  );
}

function DisclosureCard({ disclosure }: { disclosure: SegmentDisclosurePayload }) {
  const palette = disclosure.severity === "high"
    ? { border: "color-mix(in srgb, var(--negative) 40%, var(--panel-border))", background: "color-mix(in srgb, var(--negative) 10%, var(--panel))", text: "var(--negative)" }
    : disclosure.severity === "medium"
      ? { border: "color-mix(in srgb, var(--warning) 40%, var(--panel-border))", background: "color-mix(in srgb, var(--warning) 10%, var(--panel))", text: "var(--warning)" }
      : { border: "var(--panel-border)", background: "var(--panel)", text: "var(--text-muted)" };

  return (
    <div style={{ border: `1px solid ${palette.border}`, background: palette.background, borderRadius: 6, padding: 12, display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <div style={{ fontWeight: 700 }}>{disclosure.label}</div>
        <span style={{ color: palette.text, fontSize: 12, fontWeight: 700 }}>{titleCase(disclosure.severity)}</span>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>{disclosure.detail}</div>
    </div>
  );
}

function SegmentTreemapNode(
  props: {
    selectedSegmentId: string | null;
    onSelect: (segmentId: string) => void;
  } & Record<string, unknown>
) {
  const { selectedSegmentId, onSelect, depth, x, y, width, height } = props;
  const payloadCandidate =
    props.payload && typeof props.payload === "object"
      ? (((props.payload as { payload?: Partial<SegmentPoint> }).payload ?? props.payload) as Partial<SegmentPoint>)
      : null;
  const point = (payloadCandidate ?? (props as Partial<SegmentPoint>)) as Partial<SegmentPoint>;

  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    typeof height !== "number" ||
    typeof point.id !== "string" ||
    typeof point.name !== "string" ||
    typeof point.color !== "string" ||
    typeof point.revenue !== "number"
  ) {
    return null;
  }

  if ((typeof depth === "number" && depth !== 1) || width < 32 || height < 24) {
    return null;
  }

  const segmentPoint = point as SegmentPoint;
  const active = selectedSegmentId === null || selectedSegmentId === point.id;
  const focused = selectedSegmentId === point.id;

  return (
    <g onClick={() => onSelect(segmentPoint.id)} style={{ cursor: "pointer" }}>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={12}
        ry={12}
        fill={segmentPoint.color}
        opacity={active ? 0.96 : 0.38}
        stroke={focused ? "var(--warning)" : "var(--panel-border)"}
        strokeWidth={focused ? 2.2 : 1}
      />
      {width > 88 && height > 56 ? (
        <>
          <text x={x + 10} y={y + 20} fill="var(--bg)" fontSize={12} fontWeight={700}>
            {trimLabel(segmentPoint.name, width > 120 ? 18 : 12)}
          </text>
          <text x={x + 10} y={y + 38} fill="var(--bg)" fontSize={11} opacity={0.78}>
            {formatCompactNumber(segmentPoint.revenue)}
          </text>
        </>
      ) : null}
    </g>
  );
}

function SegmentTooltip({ active, payload }: { active?: boolean; payload?: TooltipEntry[] }) {
  const point = payload?.find((entry) => entry?.payload)?.payload;
  if (!active || !point) {
    return null;
  }

  return (
    <div className="segment-tooltip-card">
      <div className="segment-tooltip-title">{point.name}</div>
      <div className="segment-tooltip-row">
        <span>Revenue</span>
        <strong>{formatCompactNumber(point.revenue)}</strong>
      </div>
      <div className="segment-tooltip-row">
        <span>Share</span>
        <strong>{formatPercent(point.share)}</strong>
      </div>
      {point.comparisonRevenue !== null ? (
        <div className="segment-tooltip-row">
          <span>Compare Revenue</span>
          <strong>{formatCompactNumber(point.comparisonRevenue)}</strong>
        </div>
      ) : null}
      {point.operatingIncome !== null ? (
        <div className="segment-tooltip-row">
          <span>Op. Income</span>
          <strong>{formatCompactNumber(point.operatingIncome)}</strong>
        </div>
      ) : null}
      {point.operatingMargin !== null ? (
        <div className="segment-tooltip-row">
          <span>Op. Margin</span>
          <strong>{formatPercent(point.operatingMargin)}</strong>
        </div>
      ) : null}
      {point.operatingMarginDelta !== null ? (
        <div className="segment-tooltip-row">
          <span>Margin Delta</span>
          <strong>{formatSignedPoints(point.operatingMarginDelta)}</strong>
        </div>
      ) : null}
      <div className="segment-tooltip-row">
        <span>Growth</span>
        <strong>{formatPercent(point.growth)}</strong>
      </div>
      <div className="segment-tooltip-footnote">{point.axisLabel ?? "Reported segments"}</div>
    </div>
  );
}

function SegmentCompositionTooltip({
  active,
  payload,
  segments,
}: {
  active?: boolean;
  payload?: Array<{ dataKey?: string | number; value?: number | string | null }>;
  segments: SegmentPoint[];
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const segmentMap = new Map(segments.map((segment) => [segment.id, segment]));
  const visibleRows = payload
    .map((entry) => {
      const segmentId = typeof entry.dataKey === "string" ? entry.dataKey : null;
      const segment = segmentId ? segmentMap.get(segmentId) ?? null : null;
      if (!segment) {
        return null;
      }
      return {
        segment,
        share: typeof entry.value === "number" ? entry.value : segment.share,
      };
    })
    .filter((entry): entry is { segment: SegmentPoint; share: number | null } => entry !== null)
    .sort((left, right) => (right.share ?? 0) - (left.share ?? 0));

  if (!visibleRows.length) {
    return null;
  }

  return (
    <div className="segment-tooltip-card">
      <div className="segment-tooltip-title">Revenue mix</div>
      {visibleRows.map(({ segment, share }) => (
        <div key={segment.id} className="segment-tooltip-row">
          <span>{segment.name}</span>
          <strong>{formatPercent(share)} | {formatCompactNumber(segment.revenue)}</strong>
        </div>
      ))}
      <div className="segment-tooltip-footnote">Selected period composition</div>
    </div>
  );
}

function renderSegmentCompositionChart({
  chartType,
  data,
  currentPeriodLabel,
  expanded,
  selectedSegmentId,
  onSelectSegment,
}: {
  chartType: SegmentCompositionChartType;
  data: SegmentPoint[];
  currentPeriodLabel: string;
  expanded: boolean;
  selectedSegmentId: string | null;
  onSelectSegment: (segmentId: string) => void;
}) {
  if (chartType === "stacked_bar") {
    const stackedRow = buildStackedCompositionRow(currentPeriodLabel, data);

    return (
      <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-bar" style={expanded ? { height: 420 } : undefined}>
        <ResponsiveContainer>
          <BarChart data={[stackedRow]} layout="vertical" margin={{ top: 16, right: expanded ? 30 : 18, left: 18, bottom: 12 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis type="number" domain={[0, 1]} stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatPercent(Number(value))} />
            <YAxis type="category" dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} width={expanded ? 120 : 96} />
            <Tooltip content={<SegmentCompositionTooltip segments={data} />} />
            {data.map((segment, index) => (
              <Bar
                key={segment.id}
                dataKey={segment.id}
                stackId="share"
                fill={segment.color}
                radius={index === data.length - 1 ? [0, 4, 4, 0] : index === 0 ? [4, 0, 0, 4] : [0, 0, 0, 0]}
                onClick={() => segment.id !== "other" && onSelectSegment(segment.id)}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return (
    <div data-chart-frame-ignore-open className="segment-chart-shell segment-chart-shell-pie" style={expanded ? { height: 460 } : undefined}>
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            dataKey="revenue"
            nameKey="name"
            innerRadius={chartType === "donut" ? "48%" : 0}
            outerRadius={expanded ? "84%" : "82%"}
            paddingAngle={2}
            stroke="var(--panel)"
            strokeWidth={2}
            onClick={(entry) => {
              if (entry && typeof entry === "object" && "id" in entry && typeof entry.id === "string" && entry.id !== "other") {
                onSelectSegment(entry.id);
              }
            }}
          >
            {data.map((segment) => (
              <Cell key={segment.id} fill={segment.color} opacity={selectedSegmentId && selectedSegmentId !== segment.id ? 0.55 : 1} />
            ))}
          </Pie>
          <Tooltip content={<SegmentTooltip />} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function normalizeSegments(segments: FinancialSegmentPayload[], kind: SegmentKind, statementRevenue: number | null): SegmentPeriod["segments"] {
  const totalRevenue = statementRevenue ?? segments.reduce((sum, segment) => sum + (segment.revenue ?? 0), 0);
  return [...segments]
    .sort((left, right) => (right.revenue ?? 0) - (left.revenue ?? 0))
    .map((segment) => {
      const revenue = segment.revenue ?? 0;
      const operatingIncome = segment.operating_income ?? null;
      return {
        id: segment.segment_id || slugifySegmentName(segment.segment_name),
        name: segment.segment_name,
        axisLabel: segment.axis_label,
        kind,
        revenue,
        share: segment.share_of_revenue ?? (totalRevenue ? revenue / Math.abs(totalRevenue) : null),
        operatingIncome,
        operatingMargin: operatingIncome != null && revenue !== 0 ? operatingIncome / revenue : null,
      };
    });
}

function normalizeHistorySegments(period: SegmentHistoryPeriodPayload): SegmentPeriod["segments"] {
  return [...period.segments]
    .filter((segment) => typeof segment.revenue === "number" && segment.revenue > 0)
    .sort((left, right) => (right.revenue ?? 0) - (left.revenue ?? 0))
    .map((segment) => ({
      id: slugifySegmentName(segment.name),
      name: segment.name,
      axisLabel: null,
      kind: period.kind,
      revenue: segment.revenue ?? 0,
      share: segment.share_of_revenue,
      operatingIncome: segment.operating_income,
      operatingMargin: segment.operating_margin,
    }));
}

function selectSegmentStatements(financials: FinancialPayload[], kind: SegmentKind, cadence: FinancialCadence | "reported" | undefined): FinancialPayload[] {
  const statementsWithKind = financials.filter((statement) => hasKindSegments(statement, kind));
  if (cadence === "annual") {
    const annual = statementsWithKind.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
    return annual.length ? annual : statementsWithKind;
  }
  return statementsWithKind;
}

function hasKindSegments(statement: FinancialPayload, kind: SegmentKind): boolean {
  return statement.segment_breakdown.some((segment) => segment.kind === kind && typeof segment.revenue === "number" && segment.revenue > 0);
}

function inferCadence(filingType: string | null): FinancialCadence | "reported" {
  if (filingType && ANNUAL_FORMS.has(filingType)) {
    return "annual";
  }
  if (filingType === "10-Q" || filingType === "6-K") {
    return "quarterly";
  }
  return "reported";
}

function calculateRelativeChange(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function calculateDelta(current: number | null, previous: number | null): number | null {
  if (current == null || previous == null) {
    return null;
  }
  return current - previous;
}

function emptyComparabilityFlags(): SegmentComparabilityFlagsPayload {
  return {
    no_prior_comparable_disclosure: false,
    segment_axis_changed: false,
    partial_operating_income_disclosure: false,
    new_or_removed_segments: false,
  };
}

function slugifySegmentName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || value;
}

function formatSignedPoints(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)} pts`;
}

function formatSignedCompactNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCompactNumber(value)}`;
}

function formatSourceLabel(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

function formatHhi(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(2);
}

type SegmentCompositionChartType = (typeof SEGMENT_COMPOSITION_CHART_TYPE_OPTIONS)[number];

function isSegmentCompositionChartType(value: ChartType | null | undefined): value is SegmentCompositionChartType {
  return value != null && SEGMENT_COMPOSITION_CHART_TYPE_OPTIONS.includes(value as SegmentCompositionChartType);
}

function trimLabel(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
}

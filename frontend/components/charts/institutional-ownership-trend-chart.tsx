"use client";

import { useMemo } from "react";
import {
  Area,
  Brush,
  ComposedChart,
  Bar,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import { formatChartTimeframeLabel, getDefaultChartType, type ChartType } from "@/lib/chart-capabilities";
import { RANGE_TIMEFRAME_OPTIONS, TIME_SERIES_CHART_TYPE_OPTIONS } from "@/lib/chart-expansion-presets";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartLegendStyle, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { formatDate, formatPercent } from "@/lib/format";
import { buildWindowedSeries } from "@/lib/chart-windowing";
import type { FinancialPayload, InstitutionalHoldingPayload } from "@/lib/types";

type OwnershipTrendDatum = {
  quarterKey: string;
  quarterLabel: string;
  quarterDate: string;
  totalSharesHeld: number;
  top10SharesHeld: number;
  trackedOwnershipPercent: number | null;
  fundCount: number;
};

type TooltipPayloadEntry = {
  color?: string;
  dataKey?: string | number;
  name?: string;
  payload?: OwnershipTrendDatum;
  value?: number;
};

interface InstitutionalOwnershipTrendChartProps {
  holdings: InstitutionalHoldingPayload[];
  financials: FinancialPayload[];
}

export function InstitutionalOwnershipTrendChart({ holdings, financials }: InstitutionalOwnershipTrendChartProps) {
  const { chartType, timeframeMode, setChartType, setTimeframeMode } = useChartPreferences({
    chartFamily: "institutional-ownership-trend",
    defaultChartType: getDefaultChartType("time_series"),
    defaultTimeframeMode: "max",
    allowedChartTypes: TIME_SERIES_CHART_TYPE_OPTIONS,
    allowedTimeframeModes: RANGE_TIMEFRAME_OPTIONS,
  });
  const selectedChartType = chartType ?? getDefaultChartType("time_series");
  const selectedTimeframeMode = timeframeMode ?? "max";
  const ownershipTrend = useMemo(() => buildOwnershipTrend(holdings, financials), [holdings, financials]);
  const data = useMemo(
    () =>
      buildWindowedSeries(ownershipTrend, {
        timeframeMode: selectedTimeframeMode,
        getDate: (point) => point.quarterDate,
      }),
    [ownershipTrend, selectedTimeframeMode]
  );
  const peakShares = data.reduce((max, item) => Math.max(max, item.totalSharesHeld), 0);
  const peakOwnership = data.reduce((max, item) => Math.max(max, item.trackedOwnershipPercent ?? 0), 0);
  const exportRows = useMemo(
    () =>
      data.map((row) => ({
        quarter: row.quarterLabel,
        quarter_date: row.quarterDate,
        total_shares_held: row.totalSharesHeld,
        top10_shares_held: row.top10SharesHeld,
        tracked_ownership_percent: row.trackedOwnershipPercent,
        fund_count: row.fundCount,
      })),
    [data]
  );
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Quarters", value: String(data.length) },
        { label: "Window", value: formatChartTimeframeLabel(selectedTimeframeMode) },
        { label: "Peak tracked ownership", value: formatPercent(peakOwnership) },
        { label: "Source", value: "Cached 13F positions" },
      ]}
    />
  ) : null;
  const resetDisabled = selectedChartType === getDefaultChartType("time_series") && selectedTimeframeMode === "max";

  return (
    <InteractiveChartFrame
      title="Institutional ownership trend"
      subtitle={data.length ? `${data.length} quarters of tracked 13F ownership history.` : "Awaiting quarterly ownership history"}
      inspectorTitle="Institutional ownership trend"
      inspectorSubtitle="Tracked institutional shares, top-ten concentration, and estimated tracked ownership across cached 13F quarters."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{
        datasetKind: "time_series",
        chartType: selectedChartType,
        chartTypeOptions: TIME_SERIES_CHART_TYPE_OPTIONS,
        onChartTypeChange: setChartType,
        timeframeMode: selectedTimeframeMode,
        timeframeModeOptions: RANGE_TIMEFRAME_OPTIONS,
        onTimeframeModeChange: setTimeframeMode,
      }}
      annotations={[
        { label: "Tracked Institutional Shares", color: "var(--positive)" },
        { label: "Top 10 Funds Combined", color: "var(--warning)" },
        { label: "Tracked Ownership %", color: "var(--accent)" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Window {formatChartTimeframeLabel(selectedTimeframeMode)}</span>
            <span className="pill">Source: cached 13F positions</span>
            <span className="pill">Peak tracked shares {formatShareCompact(peakShares)}</span>
            <span className="pill">Peak tracked ownership {formatPercent(peakOwnership)}</span>
          </div>
          <div className="chart-inspector-footer-copy">
            Total ownership percent uses cached shares outstanding when available and reflects tracked 13F funds in the current cache.
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Institutional trend",
              title: "No quarterly ownership history yet",
              message: "This chart appears when cached 13F filings contain at least one reported quarter of institutional positions.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("institutional-ownership-trend", "ownership")}.png`,
        csvFileName: `${normalizeExportFileStem("institutional-ownership-trend", "ownership")}.csv`,
        csvRows: exportRows,
      }}
      resetState={{
        onReset: () => {
          setChartType(getDefaultChartType("time_series"));
          setTimeframeMode("max");
        },
        disabled: resetDisabled,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div className="institutional-trend-shell">
            <div className="institutional-trend-meta">
              <span>{data.length} quarters</span>
              <span>{formatShareCompact(peakShares)} peak tracked shares</span>
              <span>{formatPercent(peakOwnership)} peak tracked ownership</span>
              <span>Window {formatChartTimeframeLabel(selectedTimeframeMode)}</span>
            </div>

            {renderInstitutionalTrendChart({ chartType: selectedChartType, data, expanded })}
          </div>
        ) : (
                  <div className="grid-empty-state grid-empty-state-tall">
            <div className="grid-empty-kicker">Institutional trend</div>
            <div className="grid-empty-title">No quarterly ownership history yet</div>
            <div className="grid-empty-copy">This chart appears when cached 13F filings contain at least one reported quarter of institutional positions.</div>
          </div>
        )
      }
    />
  );
}

function renderInstitutionalTrendChart({
  chartType,
  data,
  expanded,
}: {
  chartType: ChartType;
  data: OwnershipTrendDatum[];
  expanded: boolean;
}) {
  const margin = { top: 8, right: expanded ? 24 : 16, left: 4, bottom: 12 };
  const lineStroke = expanded ? 2.8 : 2.6;
  const percentStroke = expanded ? 2.4 : 2.2;
  const shouldShowBrush = data.length > (expanded ? 8 : 12);
  const chartShellClassName = expanded ? "institutional-trend-chart-shell is-expanded" : "institutional-trend-chart-shell";

  return (
    <div className={chartShellClassName}>
      <ResponsiveContainer>
        {chartType === "line" ? (
          <LineChart data={data} margin={margin}>
            <SharedInstitutionalTrendChrome expanded={expanded} />
            <Line
              yAxisId="shares"
              type="monotone"
              dataKey="totalSharesHeld"
              name="Tracked Institutional Shares"
              stroke="var(--positive)"
              strokeWidth={lineStroke}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--positive)" }}
            />
            <Line
              yAxisId="shares"
              type="monotone"
              dataKey="top10SharesHeld"
              name="Top 10 Funds Combined"
              stroke="var(--warning)"
              strokeWidth={percentStroke}
              strokeDasharray="7 4"
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--warning)" }}
            />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="trackedOwnershipPercent"
              name="Tracked Ownership %"
              stroke="var(--accent)"
              strokeWidth={percentStroke}
              dot={false}
              connectNulls
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
            />
            {shouldShowBrush ? <SharedInstitutionalTrendBrush /> : null}
          </LineChart>
        ) : chartType === "area" ? (
          <ComposedChart data={data} margin={margin}>
            <SharedInstitutionalTrendChrome expanded={expanded} />
            <Area
              yAxisId="shares"
              type="monotone"
              dataKey="totalSharesHeld"
              name="Tracked Institutional Shares"
              stroke="var(--positive)"
              fill="color-mix(in srgb, var(--positive) 18%, transparent)"
              strokeWidth={lineStroke}
              isAnimationActive={false}
            />
            <Area
              yAxisId="shares"
              type="monotone"
              dataKey="top10SharesHeld"
              name="Top 10 Funds Combined"
              stroke="var(--warning)"
              fill="color-mix(in srgb, var(--warning) 14%, transparent)"
              strokeWidth={percentStroke}
              isAnimationActive={false}
            />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="trackedOwnershipPercent"
              name="Tracked Ownership %"
              stroke="var(--accent)"
              strokeWidth={percentStroke}
              dot={false}
              connectNulls
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
            />
            {shouldShowBrush ? <SharedInstitutionalTrendBrush /> : null}
          </ComposedChart>
        ) : chartType === "bar" ? (
          <ComposedChart data={data} margin={margin}>
            <SharedInstitutionalTrendChrome expanded={expanded} />
            <Bar yAxisId="shares" dataKey="totalSharesHeld" name="Tracked Institutional Shares" fill="var(--positive)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Bar yAxisId="shares" dataKey="top10SharesHeld" name="Top 10 Funds Combined" fill="var(--warning)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="trackedOwnershipPercent"
              name="Tracked Ownership %"
              stroke="var(--accent)"
              strokeWidth={percentStroke}
              dot={false}
              connectNulls
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
            />
            {shouldShowBrush ? <SharedInstitutionalTrendBrush /> : null}
          </ComposedChart>
        ) : (
          <ComposedChart data={data} margin={margin}>
            <SharedInstitutionalTrendChrome expanded={expanded} />
            <Area
              yAxisId="shares"
              type="monotone"
              dataKey="totalSharesHeld"
              name="Tracked Institutional Shares"
              stroke="var(--positive)"
              fill="color-mix(in srgb, var(--positive) 16%, transparent)"
              strokeWidth={lineStroke}
              isAnimationActive={false}
            />
            <Bar yAxisId="shares" dataKey="top10SharesHeld" name="Top 10 Funds Combined" fill="color-mix(in srgb, var(--warning) 78%, transparent)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="trackedOwnershipPercent"
              name="Tracked Ownership %"
              stroke="var(--accent)"
              strokeWidth={percentStroke}
              dot={false}
              connectNulls
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
            />
            {shouldShowBrush ? <SharedInstitutionalTrendBrush /> : null}
          </ComposedChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function SharedInstitutionalTrendChrome({ expanded }: { expanded: boolean }) {
  return (
    <>
      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
      <XAxis dataKey="quarterLabel" minTickGap={18} stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
      <YAxis
        yAxisId="shares"
        stroke={CHART_AXIS_COLOR}
        tick={chartTick(expanded ? 11 : 10)}
        tickFormatter={(value) => formatShareCompact(Number(value))}
      />
      <YAxis
        yAxisId="percent"
        orientation="right"
        stroke={CHART_AXIS_COLOR}
        tick={chartTick(expanded ? 11 : 10)}
        tickFormatter={(value) => formatPercent(Number(value))}
      />
      <Tooltip
        cursor={{ stroke: "var(--accent)", strokeWidth: 1 }}
        content={({ active, payload, label }) => (
          <InstitutionalOwnershipTooltip active={active} label={label} payload={payload as TooltipPayloadEntry[] | undefined} />
        )}
      />
      <Legend wrapperStyle={chartLegendStyle()} />
    </>
  );
}

function SharedInstitutionalTrendBrush() {
  return (
    <Brush
      dataKey="quarterLabel"
      height={24}
      stroke="var(--accent)"
      travellerWidth={10}
      fill="var(--accent)"
      tickFormatter={(value) => String(value)}
    />
  );
}

function InstitutionalOwnershipTooltip({
  active,
  label,
  payload
}: {
  active?: boolean;
  label?: string;
  payload?: TooltipPayloadEntry[];
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload;
  if (!point) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label ?? point.quarterLabel}</div>
      <TooltipRow label="Tracked Shares" value={formatShareCompact(point.totalSharesHeld)} tone="positive" />
      <TooltipRow label="Top 10 Combined" value={formatShareCompact(point.top10SharesHeld)} tone="warning" />
      <TooltipRow label="Tracked Ownership" value={point.trackedOwnershipPercent == null ? "—" : formatPercent(point.trackedOwnershipPercent)} tone="accent" />
      <TooltipRow label="Funds Reporting" value={formatInteger(point.fundCount)} tone="slate" />
      <TooltipRow label="Quarter End" value={formatDate(point.quarterDate)} tone="light" />
    </div>
  );
}

function TooltipRow({ label, value, tone }: { label: string; value: string; tone: "positive" | "warning" | "accent" | "slate" | "light" }) {
  return (
    <div className="chart-tooltip-row">
      <span className="chart-tooltip-key">
        <span className={`chart-tooltip-dot is-${tone}`} />
        {label}
      </span>
      <span className="chart-tooltip-value">{value}</span>
    </div>
  );
}

function buildOwnershipTrend(holdings: InstitutionalHoldingPayload[], financials: FinancialPayload[]): OwnershipTrendDatum[] {
  const grouped = new Map<string, InstitutionalHoldingPayload[]>();

  for (const holding of holdings) {
    const rows = grouped.get(holding.reporting_date) ?? [];
    rows.push(holding);
    grouped.set(holding.reporting_date, rows);
  }

  return Array.from(grouped.entries())
    .sort(([leftDate], [rightDate]) => Date.parse(leftDate) - Date.parse(rightDate))
    .map(([reportingDate, quarterHoldings]) => {
      const sortedByShares = [...quarterHoldings].sort((left, right) => (right.shares_held ?? 0) - (left.shares_held ?? 0));
      const totalSharesHeld = roundValue(quarterHoldings.reduce((sum, holding) => sum + (holding.shares_held ?? 0), 0));
      const top10SharesHeld = roundValue(sortedByShares.slice(0, 10).reduce((sum, holding) => sum + (holding.shares_held ?? 0), 0));
      const sharesOutstanding = resolveSharesOutstanding(reportingDate, financials);

      return {
        quarterKey: reportingDate,
        quarterLabel: formatQuarter(reportingDate),
        quarterDate: reportingDate,
        totalSharesHeld,
        top10SharesHeld,
        trackedOwnershipPercent: sharesOutstanding && sharesOutstanding > 0 ? roundValue(totalSharesHeld / sharesOutstanding) : null,
        fundCount: quarterHoldings.length
      };
    });
}

function resolveSharesOutstanding(reportingDate: string, financials: FinancialPayload[]) {
  const targetQuarter = quarterKey(reportingDate);

  const exactQuarter = financials.find(
    (statement) => statement.shares_outstanding != null && quarterKey(statement.period_end) === targetQuarter
  );
  if (exactQuarter?.shares_outstanding != null) {
    return exactQuarter.shares_outstanding;
  }

  const targetTime = Date.parse(reportingDate);
  const nearestPrior = financials.find(
    (statement) => statement.shares_outstanding != null && Date.parse(statement.period_end) <= targetTime
  );
  if (nearestPrior?.shares_outstanding != null) {
    return nearestPrior.shares_outstanding;
  }

  const nearestAny = financials.find((statement) => statement.shares_outstanding != null);
  return nearestAny?.shares_outstanding ?? null;
}

function formatQuarter(value: string) {
  const dateValue = new Date(value);
  const quarter = Math.floor(dateValue.getUTCMonth() / 3) + 1;
  return `Q${quarter} ${dateValue.getUTCFullYear()}`;
}

function quarterKey(value: string) {
  const dateValue = new Date(value);
  const quarter = Math.floor(dateValue.getUTCMonth() / 3) + 1;
  return `${dateValue.getUTCFullYear()}-Q${quarter}`;
}

function roundValue(value: number) {
  return Math.round(value * 100) / 100;
}

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatShareCompact(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2
  }).format(value);
}

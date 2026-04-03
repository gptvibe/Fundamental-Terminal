"use client";

import { useMemo } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { MetricLabel } from "@/components/ui/metric-label";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { EarningsReleasePayload } from "@/lib/types";

export type EarningsTrendDatum = {
  label: string;
  filingDate: string | null;
  reportedPeriodEnd: string | null;
  revenue: number | null;
  dilutedEps: number | null;
  parseState: string;
};

interface EarningsTrendChartProps {
  earnings?: EarningsReleasePayload[];
  points?: EarningsTrendDatum[];
  sourceLabel?: string;
}

export function EarningsTrendChart({ earnings = [], points, sourceLabel }: EarningsTrendChartProps) {
  const allRows = useMemo(() => (points ? points : buildTrendData(earnings)), [earnings, points]);
  const data = useMemo(() => allRows.filter((row) => row.revenue != null || row.dilutedEps != null), [allRows]);
  const latest = data.at(-1) ?? null;
  const omittedRows = allRows.length - data.length;
  const isFallbackSeries = points != null;
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Points", value: String(data.length) },
        { label: "Latest", value: latest?.label ?? "Unavailable" },
        { label: "Source", value: sourceLabel ?? (isFallbackSeries ? "Provided series" : "Cached earnings releases") },
      ]}
    />
  ) : null;
  const exportRows = useMemo(
    () =>
      data.map((row) => ({
        label: row.label,
        filing_date: row.filingDate,
        reported_period_end: row.reportedPeriodEnd,
        revenue: row.revenue,
        diluted_eps: row.dilutedEps,
        parse_state: row.parseState,
      })),
    [data]
  );

  return (
    <InteractiveChartFrame
      title="Earnings trend"
      subtitle={data.length ? `${data.length} releases with reported revenue or diluted EPS.` : "Awaiting parsed earnings releases"}
      inspectorTitle="Earnings trend"
      inspectorSubtitle="Reported revenue and diluted EPS by earnings release, using only rows with parsed numeric values."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{ datasetKind: "time_series" }}
      annotations={[
        { label: "Reported Revenue", color: "var(--positive)" },
        { label: "Diluted EPS", color: "var(--accent)" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Visible releases {data.length}</span>
            {sourceLabel ? <span className="pill">Source: {sourceLabel}</span> : null}
            {!isFallbackSeries && omittedRows > 0 ? <span className="pill">Metadata-only releases omitted {omittedRows}</span> : null}
            {latest?.parseState ? <span className="pill">Latest state {latest.parseState.replace(/_/g, " ")}</span> : null}
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Earnings trend",
              title: "No releases with reported revenue or diluted EPS yet",
              message: "This chart fills in once parsed releases include reported revenue or diluted EPS values.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("earnings-trend", "earnings")}.png`,
        csvFileName: `${normalizeExportFileStem("earnings-trend", "earnings")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span className="pill">{data.length} points plotted</span>
              {sourceLabel ? <span className="pill">Source: {sourceLabel}</span> : null}
              {!isFallbackSeries && omittedRows > 0 ? <span className="pill">{omittedRows} metadata-only releases omitted</span> : null}
              {latest?.label ? <span className="pill">Latest period {latest.label}</span> : null}
              {latest?.parseState ? <span className="pill">{latest.parseState.replace(/_/g, " ")}</span> : null}
            </div>

            <div style={{ width: "100%", height: expanded ? 420 : 340 }}>
              <ResponsiveContainer>
                <ComposedChart data={data} margin={{ top: 10, right: expanded ? 24 : 18, left: 4, bottom: 8 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                  <YAxis
                    yAxisId="revenue"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick(expanded ? 11 : 10)}
                    tickFormatter={(value) => formatCompactNumber(Number(value))}
                    width={72}
                  />
                  <YAxis
                    yAxisId="eps"
                    orientation="right"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick(expanded ? 11 : 10)}
                    tickFormatter={(value) => formatEps(Number(value))}
                    width={64}
                  />
                  <Tooltip content={<EarningsTooltip />} {...RECHARTS_TOOLTIP_PROPS} />
                  <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                  <Bar yAxisId="revenue" dataKey="revenue" name="Reported Revenue" fill="var(--positive)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
                  <Line
                    yAxisId="eps"
                    type="monotone"
                    dataKey="dilutedEps"
                    name="Diluted EPS"
                    stroke="var(--accent)"
                    strokeWidth={expanded ? 2.8 : 2.4}
                    dot={{ r: expanded ? 4 : 3 }}
                    activeDot={{ r: expanded ? 6 : 5 }}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <PanelEmptyState message="No releases with reported revenue or diluted EPS are available yet for this company." />
        )
      }
    />
  );
}

function buildTrendData(earnings: EarningsReleasePayload[]): EarningsTrendDatum[] {
  return [...earnings]
    .sort((left, right) => trendSortKey(left).localeCompare(trendSortKey(right)))
    .map((release) => ({
      label: release.reported_period_label ?? formatDate(release.reported_period_end ?? release.filing_date ?? release.report_date),
      filingDate: release.filing_date,
      reportedPeriodEnd: release.reported_period_end,
      revenue: release.revenue,
      dilutedEps: release.diluted_eps,
      parseState: release.parse_state
    }));
}

function trendSortKey(release: EarningsReleasePayload): string {
  return release.reported_period_end ?? release.filing_date ?? release.report_date ?? release.accession_number ?? release.primary_document ?? "";
}

function EarningsTooltip({
  active,
  payload,
  label
}: {
  active?: boolean;
  payload?: Array<{ dataKey?: string; value?: number | null; payload?: EarningsTrendDatum }>;
  label?: string;
}) {
  if (!active || !payload?.length || !payload[0]?.payload) {
    return null;
  }

  const row = payload[0].payload;

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      <TooltipRow label="Reported Revenue" value={formatCompactNumber(row.revenue)} color="var(--positive)" />
      <TooltipRow label="Diluted EPS" value={formatEps(row.dilutedEps)} color="var(--accent)" />
      <TooltipRow label="Filing Date" value={formatDate(row.filingDate)} color="var(--warning)" />
      <TooltipRow label="Source State" value={row.parseState.replace(/_/g, " ")} color="#8b949e" />
    </div>
  );
}

function TooltipRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="chart-tooltip-row">
      <span className="chart-tooltip-key">
        <span className="chart-tooltip-dot" style={{ background: color }} />
        {label}
      </span>
      <span className="chart-tooltip-value">{value}</span>
    </div>
  );
}

function formatEps(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "\u2014";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

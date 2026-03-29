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

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
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

  if (!data.length) {
    return <PanelEmptyState message="No releases with reported revenue or diluted EPS are available yet for this company." />;
  }

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">{data.length} points plotted</span>
        {sourceLabel ? <span className="pill">Source: {sourceLabel}</span> : null}
        {!isFallbackSeries && omittedRows > 0 ? <span className="pill">{omittedRows} metadata-only releases omitted</span> : null}
        {latest?.label ? <span className="pill">Latest period {latest.label}</span> : null}
        {latest?.parseState ? <span className="pill">{latest.parseState.replace(/_/g, " ")}</span> : null}
      </div>

      <div style={{ width: "100%", height: 340 }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 10, right: 18, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis
              yAxisId="revenue"
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatCompactNumber(Number(value))}
              width={72}
            />
            <YAxis
              yAxisId="eps"
              orientation="right"
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatEps(Number(value))}
              width={64}
            />
            <Tooltip content={<EarningsTooltip />} {...RECHARTS_TOOLTIP_PROPS} />
            <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
            <Bar yAxisId="revenue" dataKey="revenue" name="Reported Revenue" fill="var(--positive)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Line
              yAxisId="eps"
              type="monotone"
              dataKey="dilutedEps"
              name="Diluted EPS"
              stroke="var(--accent)"
              strokeWidth={2.4}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
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

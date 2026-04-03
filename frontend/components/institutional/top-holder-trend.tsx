"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { MetricLabel } from "@/components/ui/metric-label";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatDate } from "@/lib/format";
import type { InstitutionalHoldingPayload } from "@/lib/types";

const SERIES_COLORS = ["var(--positive)", "var(--accent)", "var(--warning)", "var(--negative)", "var(--positive)"];

export function TopHolderTrend({ holdings }: { holdings: InstitutionalHoldingPayload[] }) {
  const { data, series } = useMemo(() => buildTopHolderSeries(holdings), [holdings]);

  if (!data.length || !series.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Top holders</div>
        <div className="grid-empty-title">No top-holder trend yet</div>
        <div className="grid-empty-copy">This chart appears when cached 13F data includes multiple reporting quarters for the same tracked funds.</div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 8 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="quarterLabel" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatShares(Number(value))} width={72} />
          <Tooltip
            {...RECHARTS_TOOLTIP_PROPS}
            labelFormatter={(label, payload) => {
              const quarterDate = payload?.[0]?.payload?.quarterDate;
              return quarterDate ? `${label} (${formatDate(quarterDate)})` : String(label);
            }}
            formatter={(value: number) => formatShares(value)}
          />
          <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
          {series.map((fund, index) => (
            <Line
              key={fund}
              type="monotone"
              dataKey={fund}
              name={fund}
              stroke={SERIES_COLORS[index % SERIES_COLORS.length]}
              strokeWidth={2.2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function buildTopHolderSeries(holdings: InstitutionalHoldingPayload[]) {
  const byQuarter = new Map<string, InstitutionalHoldingPayload[]>();
  for (const holding of holdings) {
    const rows = byQuarter.get(holding.reporting_date) ?? [];
    rows.push(holding);
    byQuarter.set(holding.reporting_date, rows);
  }

  const orderedQuarters = [...byQuarter.keys()].sort((left, right) => Date.parse(left) - Date.parse(right));
  const latestQuarter = orderedQuarters.at(-1);
  if (!latestQuarter) {
    return { data: [], series: [] as string[] };
  }

  const topFunds = [...(byQuarter.get(latestQuarter) ?? [])]
    .sort((left, right) => (right.shares_held ?? 0) - (left.shares_held ?? 0))
    .slice(0, 5)
    .map((holding) => holding.fund_name);

  const data = orderedQuarters.map((quarter) => {
    const row: Record<string, string | number | null> = {
      quarterLabel: formatQuarter(quarter),
      quarterDate: quarter,
    };
    const quarterRows = byQuarter.get(quarter) ?? [];
    for (const fund of topFunds) {
      const holding = quarterRows.find((item) => item.fund_name === fund);
      row[fund] = holding?.shares_held ?? null;
    }
    return row;
  });

  return { data, series: topFunds };
}

function formatQuarter(value: string) {
  const dateValue = new Date(value);
  const quarter = Math.floor(dateValue.getUTCMonth() / 3) + 1;
  return `Q${quarter} ${dateValue.getUTCFullYear()}`;
}

function formatShares(value: number) {
  return new Intl.NumberFormat("en-US", {
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2,
  }).format(value);
}
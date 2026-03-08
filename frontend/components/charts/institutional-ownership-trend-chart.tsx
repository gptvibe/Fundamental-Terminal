"use client";

import { useMemo } from "react";
import {
  Brush,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartLegendStyle, chartTick } from "@/lib/chart-theme";
import { formatDate, formatPercent } from "@/lib/format";
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
  const data = useMemo(() => buildOwnershipTrend(holdings, financials), [holdings, financials]);

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Institutional trend</div>
        <div className="grid-empty-title">No quarterly ownership history yet</div>
        <div className="grid-empty-copy">This chart appears when cached 13F filings contain at least one reported quarter of institutional positions.</div>
      </div>
    );
  }

  const peakShares = data.reduce((max, item) => Math.max(max, item.totalSharesHeld), 0);
  const peakOwnership = data.reduce((max, item) => Math.max(max, item.trackedOwnershipPercent ?? 0), 0);

  return (
    <div className="institutional-trend-shell">
      <div className="institutional-trend-meta">
        <span>{data.length} quarters</span>
        <span>{formatShareCompact(peakShares)} peak tracked shares</span>
        <span>{formatPercent(peakOwnership)} peak tracked ownership</span>
        <span>Brush to zoom</span>
      </div>

      <div className="institutional-trend-chart-shell">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 12 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="quarterLabel" minTickGap={18} stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis
              yAxisId="shares"
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatShareCompact(Number(value))}
            />
            <YAxis
              yAxisId="percent"
              orientation="right"
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatPercent(Number(value))}
            />
            <Tooltip
              cursor={{ stroke: "rgba(0,229,255,0.28)", strokeWidth: 1 }}
              content={({ active, payload, label }) => (
                <InstitutionalOwnershipTooltip active={active} label={label} payload={payload as TooltipPayloadEntry[] | undefined} />
              )}
            />
            <Legend wrapperStyle={chartLegendStyle()} />
            <Line
              yAxisId="shares"
              type="monotone"
              dataKey="totalSharesHeld"
              name="Tracked Institutional Shares"
              stroke="#00FF41"
              strokeWidth={2.6}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "#00FF41" }}
            />
            <Line
              yAxisId="shares"
              type="monotone"
              dataKey="top10SharesHeld"
              name="Top 10 Funds Combined"
              stroke="#FFD700"
              strokeWidth={2.2}
              strokeDasharray="7 4"
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "#FFD700" }}
            />
            <Line
              yAxisId="percent"
              type="monotone"
              dataKey="trackedOwnershipPercent"
              name="Tracked Ownership %"
              stroke="#00E5FF"
              strokeWidth={2.2}
              dot={false}
              connectNulls
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "#00E5FF" }}
            />
            <Brush
              dataKey="quarterLabel"
              height={24}
              stroke="#00E5FF"
              travellerWidth={10}
              fill="rgba(0,229,255,0.08)"
              tickFormatter={(value) => String(value)}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="institutional-trend-note">
        Total ownership percent uses cached shares outstanding when available and reflects tracked 13F funds in the current cache.
      </div>
    </div>
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
      <TooltipRow label="Tracked Shares" value={formatShareCompact(point.totalSharesHeld)} color="#00FF41" />
      <TooltipRow label="Top 10 Combined" value={formatShareCompact(point.top10SharesHeld)} color="#FFD700" />
      <TooltipRow label="Tracked Ownership" value={point.trackedOwnershipPercent == null ? "—" : formatPercent(point.trackedOwnershipPercent)} color="#00E5FF" />
      <TooltipRow label="Funds Reporting" value={formatInteger(point.fundCount)} color="#94A3B8" />
      <TooltipRow label="Quarter End" value={formatDate(point.quarterDate)} color="#CBD5E1" />
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

"use client";

import { useMemo } from "react";
import {
  Bar,
  Brush,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartLegendStyle, chartTick } from "@/lib/chart-theme";
import { formatDate } from "@/lib/format";
import { buildSmartMoneyFlowTrend } from "@/lib/smart-money";
import type { InstitutionalHoldingPayload, RefreshState } from "@/lib/types";

type TooltipPayloadEntry = {
  color?: string;
  dataKey?: string | number;
  name?: string;
  payload?: ReturnType<typeof buildSmartMoneyFlowTrend>[number];
  value?: number;
};

interface SmartMoneyFlowChartProps {
  holdings: InstitutionalHoldingPayload[];
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

export function SmartMoneyFlowChart({ holdings, loading = false, error = null, refresh = null }: SmartMoneyFlowChartProps) {
  const data = useMemo(() => buildSmartMoneyFlowTrend(holdings), [holdings]);
  const totalBuy = data.reduce((sum, quarter) => sum + quarter.institutionalBuyValue, 0);
  const totalSell = data.reduce((sum, quarter) => sum + quarter.institutionalSellValue, 0);

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && !data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Smart money flow</div>
        <div className="grid-empty-title">Loading quarterly fund flow</div>
        <div className="grid-empty-copy">Reading cached 13F deltas and building institutional buy/sell flow by quarter.</div>
      </div>
    );
  }

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Smart money flow</div>
        <div className="grid-empty-title">No quarterly flow history available yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "The backend is refreshing cached 13F data now. This chart will populate when the run completes."
            : "This chart appears when cached 13F filings include enough quarter-over-quarter fund changes to compute flow."}
        </div>
      </div>
    );
  }

  return (
    <div className="institutional-trend-shell">
      <div className="institutional-trend-meta">
        <span>{data.length} quarters</span>
        <span>{formatCurrencyCompact(totalBuy)} buying</span>
        <span>{formatCurrencyCompact(totalSell)} selling</span>
        <span>Brush to zoom</span>
      </div>

      <div className="institutional-trend-chart-shell">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 16, left: 4, bottom: 12 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="quarterLabel" minTickGap={18} stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCurrencyCompact(Number(value))} />
            <Tooltip
              cursor={{ fill: "var(--ag-row-hover)" }}
              content={({ active, payload, label }) => (
                <SmartMoneyFlowTooltip active={active} payload={payload as TooltipPayloadEntry[] | undefined} label={label} />
              )}
            />
            <Legend wrapperStyle={chartLegendStyle()} />
            <Bar dataKey="institutionalBuyValue" name="Institutional Buying" stackId="smart-money-flow" fill="var(--positive)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="institutionalSellValue" name="Institutional Selling" stackId="smart-money-flow" fill="var(--negative)" radius={[4, 4, 0, 0]} />
            <Line
              type="monotone"
              dataKey="netSmartMoneyFlow"
              name="Net Smart Money Flow"
              stroke="var(--accent)"
              strokeWidth={2.4}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
            />
            <Brush
              dataKey="quarterLabel"
              height={24}
              stroke="var(--accent)"
              travellerWidth={10}
              fill="var(--accent)"
              tickFormatter={(value) => String(value)}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="institutional-trend-note">
        Institutional buying and selling values are derived from quarter-over-quarter share changes multiplied by the reported per-share value implied by cached 13F holdings.
      </div>
    </div>
  );
}

function SmartMoneyFlowTooltip({
  active,
  payload,
  label
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
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
      <TooltipRow label="Institutional Buying" value={formatCurrencyCompact(point.institutionalBuyValue)} color="var(--positive)" />
      <TooltipRow label="Institutional Selling" value={formatCurrencyCompact(point.institutionalSellValue)} color="var(--negative)" />
      <TooltipRow label="Net Flow" value={formatSignedCurrencyCompact(point.netSmartMoneyFlow)} color="var(--accent)" />
      <TooltipRow label="Funds Buying" value={formatInteger(point.fundsBuying)} color="var(--warning)" />
      <TooltipRow label="Funds Selling" value={formatInteger(point.fundsSelling)} color="#F97316" />
      <TooltipRow label="Total Value Traded" value={formatCurrencyCompact(point.totalValueTraded)} color="#94A3B8" />
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

function formatCurrencyCompact(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2
  }).format(value);
}

function formatSignedCurrencyCompact(value: number) {
  if (value > 0) {
    return `+${formatCurrencyCompact(value)}`;
  }
  if (value < 0) {
    return `-${formatCurrencyCompact(Math.abs(value))}`;
  }
  return formatCurrencyCompact(0);
}

function formatInteger(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

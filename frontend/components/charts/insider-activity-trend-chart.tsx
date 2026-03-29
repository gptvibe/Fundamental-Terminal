"use client";

import { useMemo } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import type { InsiderTradePayload } from "@/lib/types";

type InsiderTrendDatum = {
  monthKey: string;
  monthLabel: string;
  buys: number;
  sells: number;
  net: number;
  insiderCount: number;
  totalShares: number;
  buyShares: number;
  sellShares: number;
};

type TooltipPayloadEntry = {
  color?: string;
  dataKey?: string | number;
  name?: string;
  payload?: InsiderTrendDatum;
  value?: number;
};

interface InsiderActivityTrendChartProps {
  trades: InsiderTradePayload[];
}

export function InsiderActivityTrendChart({ trades }: InsiderActivityTrendChartProps) {
  const data = useMemo(() => buildMonthlyTrend(trades), [trades]);
  const activeMonths = data.filter((month) => month.buys !== 0 || month.sells !== 0).length;
  const totalBuys = data.reduce((sum, month) => sum + month.buys, 0);
  const totalSells = data.reduce((sum, month) => sum + Math.abs(month.sells), 0);

  if (!activeMonths) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 260 }}>
        <div className="grid-empty-kicker">Insider trend</div>
        <div className="grid-empty-title">No open-market insider activity in the last 12 months</div>
        <div className="grid-empty-copy">This chart tracks open-market Form 4 signals only, excluding grants and option exercises.</div>
      </div>
    );
  }

  return (
    <div className="insider-trend-shell">
      <div className="insider-trend-meta">
        <span>{activeMonths} active months</span>
        <span>{formatCurrencyCompact(totalBuys)} buys</span>
        <span>{formatCurrencyCompact(totalSells)} sells</span>
        <span>Open-market signal only</span>
      </div>

      <div className="insider-trend-chart-shell">
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="monthLabel"
              minTickGap={18}
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
            />
            <YAxis
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(value) => formatSignedAxisCurrency(Number(value))}
            />
            <Tooltip
              cursor={{ fill: "var(--ag-row-hover)" }}
              content={({ active, payload, label }) => (
                <InsiderTrendTooltip active={active} label={label} payload={payload as TooltipPayloadEntry[] | undefined} />
              )}
            />
            <ReferenceLine y={0} stroke="var(--panel-border)" />
            <Bar dataKey="buys" name="Insider Buys" stackId="insider-activity" fill="var(--positive)" radius={[4, 4, 0, 0]} />
            <Bar dataKey="sells" name="Insider Sells" stackId="insider-activity" fill="var(--negative)" radius={[4, 4, 0, 0]} />
            <Line
              type="monotone"
              dataKey="net"
              name="Net Insider Activity"
              stroke="var(--accent)"
              strokeWidth={2.4}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function InsiderTrendTooltip({
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
      <div className="chart-tooltip-label">{label ?? "Month"}</div>
      <TooltipRow label="Insider Buys" value={formatCurrencyCompact(point.buys)} color="var(--positive)" />
      <TooltipRow label="Insider Sells" value={formatCurrencyCompact(Math.abs(point.sells))} color="var(--negative)" />
      <TooltipRow label="Net Activity" value={formatSignedCurrencyCompact(point.net)} color="var(--accent)" />
      <TooltipRow label="Unique Insiders" value={formatInteger(point.insiderCount)} color="var(--warning)" />
      <TooltipRow label="Total Shares" value={formatShareCompact(point.totalShares)} color="#94A3B8" />
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

function buildMonthlyTrend(trades: InsiderTradePayload[]): InsiderTrendDatum[] {
  const end = startOfMonth(new Date());
  const months = Array.from({ length: 12 }, (_, index) => addMonths(end, index - 11));
  const buckets = new Map<string, { buys: number; sells: number; insiders: Set<string>; totalShares: number; buyShares: number; sellShares: number }>();

  for (const month of months) {
    buckets.set(monthKey(month), {
      buys: 0,
      sells: 0,
      insiders: new Set<string>(),
      totalShares: 0,
      buyShares: 0,
      sellShares: 0
    });
  }

  for (const trade of trades) {
    if (!trade.date) {
      continue;
    }

    const tradeDate = startOfMonth(new Date(trade.date));
    const key = monthKey(tradeDate);
    const bucket = buckets.get(key);
    if (!bucket) {
      continue;
    }

    const value = resolveTransactionValue(trade);
    const shares = Math.abs(trade.shares ?? 0);
    const normalizedName = trade.name.trim().toLowerCase();

    if (isSignalBuy(trade)) {
      bucket.buys += value;
      bucket.buyShares += shares;
      bucket.totalShares += shares;
      if (normalizedName) {
        bucket.insiders.add(normalizedName);
      }
      continue;
    }

    if (isSignalSell(trade)) {
      bucket.sells -= value;
      bucket.sellShares += shares;
      bucket.totalShares += shares;
      if (normalizedName) {
        bucket.insiders.add(normalizedName);
      }
    }
  }

  return months.map((month) => {
    const key = monthKey(month);
    const bucket = buckets.get(key) ?? {
      buys: 0,
      sells: 0,
      insiders: new Set<string>(),
      totalShares: 0,
      buyShares: 0,
      sellShares: 0
    };
    return {
      monthKey: key,
      monthLabel: new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" }).format(month),
      buys: roundValue(bucket.buys),
      sells: roundValue(bucket.sells),
      net: roundValue(bucket.buys + bucket.sells),
      insiderCount: bucket.insiders.size,
      totalShares: roundValue(bucket.totalShares),
      buyShares: roundValue(bucket.buyShares),
      sellShares: roundValue(bucket.sellShares)
    };
  });
}

function isSignalBuy(trade: InsiderTradePayload) {
  const code = (trade.transaction_code ?? "").trim().toUpperCase();
  if (code) {
    return code === "P";
  }
  return trade.action.trim().toLowerCase() === "buy";
}

function isSignalSell(trade: InsiderTradePayload) {
  const code = (trade.transaction_code ?? "").trim().toUpperCase();
  if (code) {
    return code === "S";
  }
  return trade.action.trim().toLowerCase() === "sell";
}

function resolveTransactionValue(trade: InsiderTradePayload) {
  if (typeof trade.value === "number" && Number.isFinite(trade.value)) {
    return Math.abs(trade.value);
  }
  if (typeof trade.shares === "number" && Number.isFinite(trade.shares) && typeof trade.price === "number" && Number.isFinite(trade.price)) {
    return Math.abs(trade.shares * trade.price);
  }
  return 0;
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addMonths(value: Date, delta: number) {
  return new Date(value.getFullYear(), value.getMonth() + delta, 1);
}

function monthKey(value: Date) {
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  return `${value.getFullYear()}-${month}`;
}

function roundValue(value: number) {
  return Math.round(value * 100) / 100;
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

function formatSignedAxisCurrency(value: number) {
  if (value === 0) {
    return "$0";
  }
  return value > 0 ? formatCurrencyCompact(value) : `-${formatCurrencyCompact(Math.abs(value))}`;
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

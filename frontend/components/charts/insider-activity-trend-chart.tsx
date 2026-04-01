"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import { formatChartTimeframeLabel, type ChartType } from "@/lib/chart-capabilities";
import { MIXED_TIME_SERIES_CHART_TYPE_OPTIONS, RANGE_TIMEFRAME_OPTIONS } from "@/lib/chart-expansion-presets";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { buildWindowedSeries } from "@/lib/chart-windowing";
import type { InsiderTradePayload } from "@/lib/types";

type InsiderTrendDatum = {
  monthStart: string;
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
  const { chartType, timeframeMode, setChartType, setTimeframeMode } = useChartPreferences({
    chartFamily: "insider-activity-trend",
    defaultChartType: "composed",
    defaultTimeframeMode: "1y",
    allowedChartTypes: MIXED_TIME_SERIES_CHART_TYPE_OPTIONS,
    allowedTimeframeModes: RANGE_TIMEFRAME_OPTIONS,
  });
  const selectedChartType = (chartType ?? "composed") as Extract<ChartType, "bar" | "composed">;
  const selectedTimeframeMode = timeframeMode ?? "1y";
  const insiderTrend = useMemo(() => buildMonthlyTrend(trades), [trades]);
  const data = useMemo(
    () =>
      buildWindowedSeries(insiderTrend, {
        timeframeMode: selectedTimeframeMode,
        getDate: (point) => point.monthStart,
      }),
    [insiderTrend, selectedTimeframeMode]
  );
  const activeMonths = data.filter((month) => month.buys !== 0 || month.sells !== 0).length;
  const totalBuys = data.reduce((sum, month) => sum + month.buys, 0);
  const totalSells = data.reduce((sum, month) => sum + Math.abs(month.sells), 0);
  const exportRows = useMemo(
    () =>
      data.map((row) => ({
        month: row.monthLabel,
        buys: row.buys,
        sells: row.sells,
        net: row.net,
        insider_count: row.insiderCount,
        total_shares: row.totalShares,
        buy_shares: row.buyShares,
        sell_shares: row.sellShares,
      })),
    [data]
  );
  const badgeArea = activeMonths ? (
    <ChartSourceBadges
      badges={[
        { label: "Window", value: formatChartTimeframeLabel(selectedTimeframeMode) },
        { label: "Active months", value: String(activeMonths) },
        { label: "Source", value: "Form 4 open-market signals" },
      ]}
    />
  ) : null;
  const resetDisabled = selectedChartType === "composed" && selectedTimeframeMode === "1y";

  return (
    <InteractiveChartFrame
      title="Insider activity trend"
      subtitle={activeMonths ? `${activeMonths} active months across the ${formatChartTimeframeLabel(selectedTimeframeMode).toLowerCase()} window.` : "Awaiting open-market insider activity"}
      inspectorTitle="Insider activity trend"
      inspectorSubtitle="Monthly insider buys, sells, and net open-market activity from Form 4 filings."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{
        datasetKind: "time_series",
        chartType: selectedChartType,
        chartTypeOptions: MIXED_TIME_SERIES_CHART_TYPE_OPTIONS,
        onChartTypeChange: (nextChartType) => setChartType(nextChartType as Extract<ChartType, "bar" | "composed">),
        timeframeMode: selectedTimeframeMode,
        timeframeModeOptions: RANGE_TIMEFRAME_OPTIONS,
        onTimeframeModeChange: setTimeframeMode,
      }}
      annotations={[
        { label: "Insider Buys", color: "var(--positive)" },
        { label: "Insider Sells", color: "var(--negative)" },
        { label: "Net Insider Activity", color: "var(--accent)" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Window: {formatChartTimeframeLabel(selectedTimeframeMode)}</span>
            <span className="pill">Open-market signal only</span>
            <span className="pill">Source: Form 4 filings</span>
          </div>
        </div>
      )}
      stageState={
        activeMonths
          ? undefined
          : {
              kind: "empty",
              kicker: "Insider trend",
              title: "No open-market insider activity in the selected window",
              message: "This chart tracks open-market Form 4 signals only, excluding grants and option exercises.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("insider-activity-trend", "insiders")}.png`,
        csvFileName: `${normalizeExportFileStem("insider-activity-trend", "insiders")}.csv`,
        csvRows: exportRows,
      }}
      resetState={{
        onReset: () => {
          setChartType("composed");
          setTimeframeMode("1y");
        },
        disabled: resetDisabled,
      }}
      renderChart={({ expanded }) =>
        activeMonths ? (
          <div className="insider-trend-shell">
            <div className="insider-trend-meta">
              <span>{activeMonths} active months</span>
              <span>{formatCurrencyCompact(totalBuys)} buys</span>
              <span>{formatCurrencyCompact(totalSells)} sells</span>
              <span>{formatChartTimeframeLabel(selectedTimeframeMode)} window</span>
            </div>

            {renderInsiderTrendChart({ chartType: selectedChartType, data, expanded })}
          </div>
        ) : (
          <div className="grid-empty-state grid-empty-state-tall">
            <div className="grid-empty-kicker">Insider trend</div>
            <div className="grid-empty-title">No open-market insider activity in the selected window</div>
            <div className="grid-empty-copy">This chart tracks open-market Form 4 signals only, excluding grants and option exercises.</div>
          </div>
        )
      }
    />
  );
}

function renderInsiderTrendChart({
  chartType,
  data,
  expanded,
}: {
  chartType: Extract<ChartType, "bar" | "composed">;
  data: InsiderTrendDatum[];
  expanded: boolean;
}) {
  const margin = { top: 8, right: expanded ? 20 : 12, left: 0, bottom: 0 };
  const shouldShowBrush = data.length > (expanded ? 10 : 14);
  const chartShellClassName = expanded ? "insider-trend-chart-shell is-expanded" : "insider-trend-chart-shell";

  return (
    <div className={chartShellClassName}>
      <ResponsiveContainer>
        {chartType === "bar" ? (
          <BarChart data={data} margin={margin}>
            <SharedInsiderTrendChrome expanded={expanded} />
            <Bar dataKey="buys" name="Insider Buys" fill="var(--positive)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="sells" name="Insider Sells" fill="var(--negative)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="net" name="Net Insider Activity" fill="var(--accent)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            {shouldShowBrush ? <SharedInsiderTrendBrush /> : null}
          </BarChart>
        ) : (
          <ComposedChart data={data} margin={margin}>
            <SharedInsiderTrendChrome expanded={expanded} />
            <Bar dataKey="buys" name="Insider Buys" stackId="insider-activity" fill="var(--positive)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Bar dataKey="sells" name="Insider Sells" stackId="insider-activity" fill="var(--negative)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            <Line
              type="monotone"
              dataKey="net"
              name="Net Insider Activity"
              stroke="var(--accent)"
              strokeWidth={expanded ? 2.8 : 2.4}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
              isAnimationActive={false}
            />
            {shouldShowBrush ? <SharedInsiderTrendBrush /> : null}
          </ComposedChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function SharedInsiderTrendChrome({ expanded }: { expanded: boolean }) {
  return (
    <>
      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
      <XAxis
        dataKey="monthLabel"
        minTickGap={18}
        stroke={CHART_AXIS_COLOR}
        tick={chartTick(expanded ? 11 : 10)}
      />
      <YAxis
        stroke={CHART_AXIS_COLOR}
        tick={chartTick(expanded ? 11 : 10)}
        tickFormatter={(value) => formatSignedAxisCurrency(Number(value))}
      />
      <Tooltip
        cursor={{ fill: "var(--ag-row-hover)" }}
        content={({ active, payload, label }) => (
          <InsiderTrendTooltip active={active} label={label} payload={payload as TooltipPayloadEntry[] | undefined} />
        )}
      />
      <ReferenceLine y={0} stroke="var(--panel-border)" />
    </>
  );
}

function SharedInsiderTrendBrush() {
  return <Brush dataKey="monthLabel" height={24} stroke="var(--accent)" travellerWidth={10} fill="var(--accent)" tickFormatter={(value) => String(value)} />;
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
      <TooltipRow label="Insider Buys" value={formatCurrencyCompact(point.buys)} tone="positive" />
      <TooltipRow label="Insider Sells" value={formatCurrencyCompact(Math.abs(point.sells))} tone="negative" />
      <TooltipRow label="Net Activity" value={formatSignedCurrencyCompact(point.net)} tone="accent" />
      <TooltipRow label="Unique Insiders" value={formatInteger(point.insiderCount)} tone="warning" />
      <TooltipRow label="Total Shares" value={formatShareCompact(point.totalShares)} tone="slate" />
    </div>
  );
}

function TooltipRow({ label, value, tone }: { label: string; value: string; tone: "positive" | "negative" | "accent" | "warning" | "slate" }) {
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

function buildMonthlyTrend(trades: InsiderTradePayload[]): InsiderTrendDatum[] {
  const end = startOfMonth(new Date());
  const signalTrades = trades.filter(isDatedSignalTrade);
  const earliestTradeMonth = signalTrades.reduce<Date | null>((earliest, trade) => {
    const current = startOfMonth(new Date(trade.date));
    if (!earliest || current < earliest) {
      return current;
    }
    return earliest;
  }, null);
  const start = earliestTradeMonth ?? addMonths(end, -11);
  const monthCount = Math.max(1, differenceInMonths(start, end) + 1);
  const months = Array.from({ length: monthCount }, (_, index) => addMonths(start, index));
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

  for (const trade of signalTrades) {
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
      monthStart: `${key}-01`,
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

function isDatedSignalTrade(trade: InsiderTradePayload): trade is InsiderTradePayload & { date: string } {
  return Boolean(trade.date) && (isSignalBuy(trade) || isSignalSell(trade));
}

function startOfMonth(value: Date) {
  return new Date(value.getFullYear(), value.getMonth(), 1);
}

function addMonths(value: Date, delta: number) {
  return new Date(value.getFullYear(), value.getMonth() + delta, 1);
}

function differenceInMonths(start: Date, end: Date) {
  return (end.getFullYear() - start.getFullYear()) * 12 + (end.getMonth() - start.getMonth());
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

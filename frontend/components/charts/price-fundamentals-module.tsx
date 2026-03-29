"use client";

import type { ReactNode } from "react";
import { useId, useMemo, useState } from "react";

import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FundamentalsTrendPoint, PriceHistoryPoint } from "@/lib/types";

const RANGE_OPTIONS = ["1Y", "3Y", "5Y", "10Y", "MAX"] as const;

type RangeOption = (typeof RANGE_OPTIONS)[number];

type ToggleState = {
  ma50: boolean;
  ma200: boolean;
  volume: boolean;
};

type PriceChartDatum = {
  date: string;
  close: number | null;
  volume: number | null;
  ma50: number | null;
  ma200: number | null;
  volumeFill: string;
};

type FundamentalsChartDatum = {
  date: string;
  revenueGrowth: number | null;
  epsGrowth: number | null;
  freeCashFlow: number | null;
};

type TooltipEntry = {
  color?: string;
  dataKey?: string | number;
  name?: string;
  value?: number | string | null;
};

interface PriceFundamentalsModuleProps {
  priceData: PriceHistoryPoint[];
  fundamentalsData: FundamentalsTrendPoint[];
  defaultRange?: RangeOption;
  title?: string;
  subtitle?: string;
}

export function PriceFundamentalsModule({
  priceData,
  fundamentalsData,
  defaultRange = "5Y",
  title = "Price & Fundamentals",
  subtitle = "Overlay long-term price action with operational momentum and cash generation"
}: PriceFundamentalsModuleProps) {
  const [range, setRange] = useState<RangeOption>(defaultRange);
  const [toggles, setToggles] = useState<ToggleState>({ ma50: true, ma200: true, volume: true });
  const gradientId = useId().replace(/[:]/g, "");

  const sortedPriceData = useMemo(() => sortByDate(priceData), [priceData]);
  const sortedFundamentalsData = useMemo(() => sortByDate(fundamentalsData), [fundamentalsData]);

  const latestDate = useMemo(() => {
    const latestPrice = sortedPriceData.at(-1)?.date;
    const latestFundamentals = sortedFundamentalsData.at(-1)?.date;
    return [latestPrice, latestFundamentals].filter(Boolean).sort().at(-1) ?? null;
  }, [sortedFundamentalsData, sortedPriceData]);

  const filteredPriceData = useMemo(
    () => filterSeriesByRange(sortedPriceData, range, latestDate),
    [latestDate, range, sortedPriceData]
  );

  const filteredFundamentalsData = useMemo(
    () => filterSeriesByRange(sortedFundamentalsData, range, latestDate),
    [latestDate, range, sortedFundamentalsData]
  );

  const priceChartData = useMemo(() => buildPriceChartData(filteredPriceData), [filteredPriceData]);
  const fundamentalsChartData = useMemo(
    () => buildFundamentalsChartData(filteredFundamentalsData),
    [filteredFundamentalsData]
  );

  const latestPrice = priceChartData.at(-1)?.close ?? null;
  const firstPrice = priceChartData[0]?.close ?? null;
  const rangeReturn = computeGrowth(latestPrice, firstPrice);
  const latestFreeCashFlow = fundamentalsChartData.at(-1)?.freeCashFlow ?? null;
  const latestRevenueGrowth = fundamentalsChartData.at(-1)?.revenueGrowth ?? null;
  const latestEpsGrowth = fundamentalsChartData.at(-1)?.epsGrowth ?? null;

  return (
    <section className="price-fundamentals-shell">
      <div className="price-fundamentals-header">
        <div>
          <h2 className="panel-title" style={{ margin: 0 }}>{title}</h2>
          <div className="text-muted" style={{ marginTop: 6, fontSize: 13 }}>{subtitle}</div>
        </div>

        <div className="price-fundamentals-controls">
          <div className="range-toggle-row">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                className={`chart-chip ${range === option ? "chart-chip-active" : ""}`}
                onClick={() => setRange(option)}
              >
                {option}
              </button>
            ))}
          </div>
          <div className="indicator-toggle-row">
            <ToggleChip label="MA 50" active={toggles.ma50} onClick={() => setToggles((current) => ({ ...current, ma50: !current.ma50 }))} />
            <ToggleChip
              label="MA 200"
              active={toggles.ma200}
              onClick={() => setToggles((current) => ({ ...current, ma200: !current.ma200 }))}
            />
            <ToggleChip
              label="Volume"
              active={toggles.volume}
              onClick={() => setToggles((current) => ({ ...current, volume: !current.volume }))}
            />
          </div>
        </div>
      </div>

      <div className="price-fundamentals-strip">
        <SummaryStat label="Last Price" value={formatCurrency(latestPrice)} accent="cyan" />
        <SummaryStat label={`${range} Return`} value={formatPercent(rangeReturn)} accent="green" />
        <SummaryStat label="Revenue Growth" value={formatPercent(latestRevenueGrowth)} accent="gold" />
        <SummaryStat label="EPS Growth" value={formatPercent(latestEpsGrowth)} accent="cyan" />
        <SummaryStat label="Free Cash Flow" value={formatCompactNumber(latestFreeCashFlow)} accent="green" />
      </div>

      <div className="price-fundamentals-grid">
        <ChartCard
          title="Price Chart"
          subtitle={`${priceChartData.length} sessions${priceChartData.length && latestDate ? ` • through ${formatDate(latestDate)}` : ""}`}
        >
          {priceChartData.length ? (
            <div style={{ width: "100%", height: 360 }}>
              <ResponsiveContainer>
                <ComposedChart data={priceChartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`${gradientId}-price-fill`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.32} />
                      <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis
                    dataKey="date"
                    minTickGap={28}
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick()}
                    tickFormatter={formatAxisDate}
                  />
                  <YAxis
                    yAxisId="price"
                    orientation="right"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick()}
                    tickFormatter={(value) => formatCurrency(value)}
                    domain={[(min: number) => expandMin(min), (max: number) => expandMax(max)]}
                  />
                  <YAxis yAxisId="volume" hide domain={[0, (max: number) => Math.max(max * 1.25, 1)]} />
                  <Tooltip
                    cursor={{ stroke: "var(--panel-border)", strokeWidth: 1 }}
                    content={({ active, payload, label }) => (
                      <PriceTooltip active={active} label={label} payload={payload as TooltipEntry[] | undefined} />
                    )}
                  />
                  {toggles.volume ? (
                    <Bar yAxisId="volume" dataKey="volume" barSize={5} fillOpacity={0.28} radius={[4, 4, 0, 0]}>
                      {priceChartData.map((entry) => (
                        <Cell key={`${entry.date}-volume`} fill={entry.volumeFill} />
                      ))}
                    </Bar>
                  ) : null}
                  <Area
                    yAxisId="price"
                    type="monotone"
                    dataKey="close"
                    stroke="var(--accent)"
                    strokeWidth={2.4}
                    fill={`url(#${gradientId}-price-fill)`}
                    isAnimationActive
                    animationDuration={450}
                    dot={false}
                      activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
                  />
                  {toggles.ma50 ? (
                    <Line
                      yAxisId="price"
                      type="monotone"
                      dataKey="ma50"
                      stroke="var(--warning)"
                      strokeWidth={1.75}
                      dot={false}
                      isAnimationActive
                      animationDuration={450}
                    />
                  ) : null}
                  {toggles.ma200 ? (
                    <Line
                      yAxisId="price"
                      type="monotone"
                      dataKey="ma200"
                      stroke="var(--positive)"
                      strokeWidth={1.75}
                      dot={false}
                      isAnimationActive
                      animationDuration={450}
                    />
                  ) : null}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <ChartEmptyState message="Provide daily price and volume history to render the stock chart and moving-average overlays." />
          )}
        </ChartCard>

        <ChartCard
          title="Fundamentals Trend"
          subtitle={`${fundamentalsChartData.length} reporting periods${fundamentalsChartData.length && latestDate ? ` • through ${formatDate(latestDate)}` : ""}`}
        >
          {fundamentalsChartData.length ? (
            <div style={{ width: "100%", height: 300 }}>
              <ResponsiveContainer>
                <ComposedChart data={fundamentalsChartData} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id={`${gradientId}-fcf-fill`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--positive)" stopOpacity={0.28} />
                      <stop offset="100%" stopColor="var(--positive)" stopOpacity={0.03} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis
                    dataKey="date"
                    minTickGap={24}
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick()}
                    tickFormatter={formatAxisDate}
                  />
                  <YAxis
                    yAxisId="growth"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick()}
                    tickFormatter={(value) => formatPercent(Number(value))}
                  />
                  <YAxis
                    yAxisId="cash"
                    orientation="right"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick()}
                    tickFormatter={(value) => formatCompactNumber(Number(value))}
                  />
                  <Tooltip
                    cursor={{ stroke: "var(--panel-border)", strokeWidth: 1 }}
                    content={({ active, payload, label }) => (
                      <FundamentalsTooltip active={active} label={label} payload={payload as TooltipEntry[] | undefined} />
                    )}
                  />
                  <Area
                    yAxisId="cash"
                    type="monotone"
                    dataKey="freeCashFlow"
                    stroke="var(--positive)"
                    strokeWidth={2}
                    fill={`url(#${gradientId}-fcf-fill)`}
                    dot={false}
                    isAnimationActive
                    animationDuration={450}
                      activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--positive)" }}
                  />
                  <Line
                    yAxisId="growth"
                    type="monotone"
                    dataKey="revenueGrowth"
                    stroke="var(--accent)"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive
                    animationDuration={450}
                      activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
                  />
                  <Line
                    yAxisId="growth"
                    type="monotone"
                    dataKey="epsGrowth"
                    stroke="var(--warning)"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive
                    animationDuration={450}
                      activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--warning)" }}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <ChartEmptyState message="Provide dated revenue, EPS, and free cash flow series to compare operating momentum against cash generation." />
          )}
        </ChartCard>
      </div>
    </section>
  );
}

function ToggleChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`chart-chip chart-chip-toggle ${active ? "chart-chip-active" : ""}`} onClick={onClick}>
      {label}
    </button>
  );
}

function SummaryStat({ label, value, accent }: { label: string; value: string; accent: "green" | "cyan" | "gold" }) {
  return (
    <div className={`summary-card accent-${accent}`}>
      <div className="summary-card-label">{label}</div>
      <div className="summary-card-value">{value}</div>
    </div>
  );
}

function ChartCard({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className="price-chart-card">
      <div className="price-chart-card-header">
        <div>
          <div className="price-chart-card-title">{title}</div>
          <div className="price-chart-card-subtitle">{subtitle}</div>
        </div>
      </div>
      {children}
    </section>
  );
}

function ChartEmptyState({ message }: { message: string }) {
  return (
    <div className="chart-empty-state">
      <div className="grid-empty-kicker">Awaiting series</div>
      <div className="grid-empty-title">Chart data not available</div>
      <div className="grid-empty-copy">{message}</div>
    </div>
  );
}

function PriceTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipEntry[]; label?: string | number }) {
  if (!active || !payload?.length) {
    return null;
  }

  const close = findTooltipNumber(payload, "close");
  const volume = findTooltipNumber(payload, "volume");
  const ma50 = findTooltipNumber(payload, "ma50");
  const ma200 = findTooltipNumber(payload, "ma200");

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{typeof label === "string" ? formatDate(label) : String(label ?? "")}</div>
      <TooltipRow label="Close" value={formatCurrency(close)} color="var(--accent)" />
      <TooltipRow label="50D MA" value={formatCurrency(ma50)} color="var(--warning)" />
      <TooltipRow label="200D MA" value={formatCurrency(ma200)} color="var(--positive)" />
      <TooltipRow label="Volume" value={formatCompactNumber(volume)} color="#8B949E" />
    </div>
  );
}

function FundamentalsTooltip({
  active,
  payload,
  label
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const revenueGrowth = findTooltipNumber(payload, "revenueGrowth");
  const epsGrowth = findTooltipNumber(payload, "epsGrowth");
  const freeCashFlow = findTooltipNumber(payload, "freeCashFlow");

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{typeof label === "string" ? formatDate(label) : String(label ?? "")}</div>
      <TooltipRow label="Revenue Growth" value={formatPercent(revenueGrowth)} color="var(--accent)" />
      <TooltipRow label="EPS Growth" value={formatPercent(epsGrowth)} color="var(--warning)" />
      <TooltipRow label="Free Cash Flow" value={formatCompactNumber(freeCashFlow)} color="var(--positive)" />
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

function buildPriceChartData(priceData: PriceHistoryPoint[]): PriceChartDatum[] {
  const ma50 = movingAverage(priceData, 50);
  const ma200 = movingAverage(priceData, 200);

  return priceData.map((point, index) => {
    const previousClose = index > 0 ? priceData[index - 1]?.close ?? null : null;
    const volumeFill =
      point.close !== null && previousClose !== null && point.close < previousClose ? "rgba(255,77,109,0.38)" : "var(--positive)";

    return {
      date: point.date,
      close: point.close,
      volume: point.volume,
      ma50: ma50[index],
      ma200: ma200[index],
      volumeFill
    };
  });
}

function buildFundamentalsChartData(points: FundamentalsTrendPoint[]): FundamentalsChartDatum[] {
  return points.map((point, index) => {
    const previous = index > 0 ? points[index - 1] : null;
    return {
      date: point.date,
      revenueGrowth: computeGrowth(point.revenue, previous?.revenue ?? null),
      epsGrowth: computeGrowth(point.eps, previous?.eps ?? null),
      freeCashFlow: point.free_cash_flow
    };
  });
}

function movingAverage(points: PriceHistoryPoint[], windowSize: number): Array<number | null> {
  return points.map((_, index) => {
    if (index + 1 < windowSize) {
      return null;
    }

    const window = points.slice(index - windowSize + 1, index + 1).map((point) => point.close).filter(isFiniteNumber);
    if (window.length !== windowSize) {
      return null;
    }

    return window.reduce((sum, value) => sum + value, 0) / window.length;
  });
}

function filterSeriesByRange<T extends { date: string }>(series: T[], range: RangeOption, anchorDate: string | null): T[] {
  if (range === "MAX" || !series.length || !anchorDate) {
    return series;
  }

  const end = new Date(anchorDate);
  const start = new Date(anchorDate);
  start.setFullYear(end.getFullYear() - yearsFromRange(range));

  return series.filter((point) => {
    const current = new Date(point.date);
    return current >= start && current <= end;
  });
}

function yearsFromRange(range: RangeOption): number {
  switch (range) {
    case "1Y":
      return 1;
    case "3Y":
      return 3;
    case "5Y":
      return 5;
    case "10Y":
      return 10;
    case "MAX":
      return 99;
  }
}

function sortByDate<T extends { date: string }>(series: T[]): T[] {
  return [...series].sort((left, right) => Date.parse(left.date) - Date.parse(right.date));
}

function computeGrowth(current: number | null, previous: number | null): number | null {
  if (!isFiniteNumber(current) || !isFiniteNumber(previous) || previous === 0) {
    return null;
  }

  return (current - previous) / Math.abs(previous);
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function findTooltipNumber(payload: TooltipEntry[], key: string): number | null {
  const value = payload.find((entry) => entry.dataKey === key)?.value;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatCurrency(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 100 ? 0 : 2
  }).format(value);
}

function formatAxisDate(value: string): string {
  return new Intl.DateTimeFormat("en-US", { month: "short", year: "2-digit" }).format(new Date(value));
}

function expandMin(value: number): number {
  if (!Number.isFinite(value) || value <= 0) {
    return 0;
  }

  return value * 0.92;
}

function expandMax(value: number): number {
  if (!Number.isFinite(value) || value <= 0) {
    return 1;
  }

  return value * 1.08;
}

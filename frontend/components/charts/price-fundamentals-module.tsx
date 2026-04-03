"use client";

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
  YAxis,
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { MetricLabel } from "@/components/ui/metric-label";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import { getDefaultChartType, type ChartTimeframeMode, type ChartType } from "@/lib/chart-capabilities";
import { buildWindowedSeries, downsampleSeries, sortSeriesByDate } from "@/lib/chart-windowing";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FundamentalsTrendPoint, PriceHistoryPoint } from "@/lib/types";

const RANGE_OPTIONS = ["1Y", "3Y", "5Y", "10Y", "MAX"] as const;
const RANGE_TIMEFRAME_OPTIONS = ["1y", "3y", "5y", "10y", "max"] as const satisfies readonly ChartTimeframeMode[];
const INSPECTOR_CHART_TYPE_OPTIONS = ["line", "area", "composed"] as const satisfies readonly ChartType[];

type RangeOption = (typeof RANGE_OPTIONS)[number];
type RangeTimeframeMode = (typeof RANGE_TIMEFRAME_OPTIONS)[number];

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
  dataKey?: string | number;
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
  subtitle = "Overlay long-term price action with operational momentum and cash generation",
}: PriceFundamentalsModuleProps) {
  const [toggles, setToggles] = useState<ToggleState>({ ma50: true, ma200: true, volume: true });
  const gradientId = useId().replace(/[:]/g, "");
  const { timeframeMode, setTimeframeMode } = useChartPreferences({
    chartFamily: "price-fundamentals",
    defaultTimeframeMode: rangeOptionToTimeframeMode(defaultRange),
    allowedTimeframeModes: RANGE_TIMEFRAME_OPTIONS,
  });
  const { chartType: priceChartType, setChartType: setPriceChartType } = useChartPreferences({
    chartFamily: "price-fundamentals-price",
    defaultChartType: getDefaultChartType("time_series"),
    allowedChartTypes: INSPECTOR_CHART_TYPE_OPTIONS,
  });
  const { chartType: fundamentalsChartType, setChartType: setFundamentalsChartType } = useChartPreferences({
    chartFamily: "price-fundamentals-fundamentals",
    defaultChartType: getDefaultChartType("time_series"),
    allowedChartTypes: INSPECTOR_CHART_TYPE_OPTIONS,
  });
  const selectedTimeframeMode = timeframeMode && isRangeTimeframeMode(timeframeMode) ? timeframeMode : rangeOptionToTimeframeMode(defaultRange);
  const selectedRange = timeframeModeToRangeOption(selectedTimeframeMode);
  const selectedPriceChartType = isInspectorChartType(priceChartType) ? priceChartType : getDefaultChartType("time_series");
  const selectedFundamentalsChartType = isInspectorChartType(fundamentalsChartType)
    ? fundamentalsChartType
    : getDefaultChartType("time_series");

  const sortedPriceData = useMemo(() => sortSeriesByDate(priceData, (point) => point.date, "asc"), [priceData]);
  const sortedFundamentalsData = useMemo(
    () => sortSeriesByDate(fundamentalsData, (point) => point.date, "asc"),
    [fundamentalsData]
  );

  const latestDate = useMemo(() => {
    const latestPrice = sortedPriceData.at(-1)?.date;
    const latestFundamentals = sortedFundamentalsData.at(-1)?.date;
    return [latestPrice, latestFundamentals].filter(Boolean).sort().at(-1) ?? null;
  }, [sortedFundamentalsData, sortedPriceData]);

  const visiblePriceData = useMemo(
    () =>
      buildWindowedSeries(sortedPriceData, {
        timeframeMode: selectedTimeframeMode,
        getDate: (point) => point.date,
        anchorDate: latestDate,
      }),
    [latestDate, selectedTimeframeMode, sortedPriceData]
  );
  const visibleFundamentalsData = useMemo(
    () =>
      buildWindowedSeries(sortedFundamentalsData, {
        timeframeMode: selectedTimeframeMode,
        getDate: (point) => point.date,
        anchorDate: latestDate,
      }),
    [latestDate, selectedTimeframeMode, sortedFundamentalsData]
  );

  const priceChartData = useMemo(() => buildPriceChartData(visiblePriceData), [visiblePriceData]);
  const fundamentalsChartData = useMemo(
    () => buildFundamentalsChartData(visibleFundamentalsData),
    [visibleFundamentalsData]
  );
  const compactPriceChartData = useMemo(() => downsampleSeries(priceChartData, 240), [priceChartData]);
  const expandedPriceChartData = useMemo(() => downsampleSeries(priceChartData, 480), [priceChartData]);
  const compactFundamentalsChartData = useMemo(() => downsampleSeries(fundamentalsChartData, 32), [fundamentalsChartData]);
  const expandedFundamentalsChartData = useMemo(() => downsampleSeries(fundamentalsChartData, 56), [fundamentalsChartData]);

  const latestPrice = priceChartData.at(-1)?.close ?? null;
  const firstPrice = priceChartData[0]?.close ?? null;
  const rangeReturn = computeGrowth(latestPrice, firstPrice);
  const latestFreeCashFlow = fundamentalsChartData.at(-1)?.freeCashFlow ?? null;
  const latestRevenueGrowth = fundamentalsChartData.at(-1)?.revenueGrowth ?? null;
  const latestEpsGrowth = fundamentalsChartData.at(-1)?.epsGrowth ?? null;
  const priceExportRows = useMemo(
    () =>
      priceChartData.map((point) => ({
        date: point.date,
        close: point.close,
        volume: point.volume,
        ma50: point.ma50,
        ma200: point.ma200,
      })),
    [priceChartData]
  );

  const fundamentalsExportRows = useMemo(
    () =>
      fundamentalsChartData.map((point) => ({
        date: point.date,
        revenue_growth: point.revenueGrowth,
        eps_growth: point.epsGrowth,
        free_cash_flow: point.freeCashFlow,
      })),
    [fundamentalsChartData]
  );

  const priceBadgeArea = (
    <ChartSourceBadges
      badges={[
        { label: "Window", value: selectedRange },
        { label: "Sessions", value: String(priceChartData.length) },
        { label: "Latest", value: latestDate ? formatDate(latestDate) : "Unavailable" },
      ]}
    />
  );

  const fundamentalsBadgeArea = (
    <ChartSourceBadges
      badges={[
        { label: "Window", value: selectedRange },
        { label: "Periods", value: String(fundamentalsChartData.length) },
        { label: "Series", value: "Revenue, EPS, FCF" },
      ]}
    />
  );

  const priceControls = (
    <div className="indicator-toggle-row">
      <ToggleChip label="MA 50" active={toggles.ma50} onClick={() => setToggles((current) => ({ ...current, ma50: !current.ma50 }))} />
      <ToggleChip label="MA 200" active={toggles.ma200} onClick={() => setToggles((current) => ({ ...current, ma200: !current.ma200 }))} />
      <ToggleChip label="Volume" active={toggles.volume} onClick={() => setToggles((current) => ({ ...current, volume: !current.volume }))} />
    </div>
  );

  const handleTimeframeModeChange = (mode: ChartTimeframeMode) => {
    if (isRangeTimeframeMode(mode)) {
      setTimeframeMode(mode);
    }
  };
  const resetInspectorView = () => {
    setTimeframeMode(rangeOptionToTimeframeMode(defaultRange));
    setPriceChartType(getDefaultChartType("time_series"));
    setFundamentalsChartType(getDefaultChartType("time_series"));
    setToggles({ ma50: true, ma200: true, volume: true });
  };
  const resetDisabled =
    selectedTimeframeMode === rangeOptionToTimeframeMode(defaultRange) &&
    selectedPriceChartType === getDefaultChartType("time_series") &&
    selectedFundamentalsChartType === getDefaultChartType("time_series") &&
    toggles.ma50 &&
    toggles.ma200 &&
    toggles.volume;
  const priceAnnotations = [
    { label: "Close", color: "var(--accent)" },
    ...(toggles.ma50 ? [{ label: "MA 50", color: "var(--warning)" }] : []),
    ...(toggles.ma200 ? [{ label: "MA 200", color: "var(--positive)" }] : []),
    ...(selectedPriceChartType === "composed" && toggles.volume ? [{ label: "Volume", color: "#8B949E" }] : []),
  ];
  const fundamentalsAnnotations = [
    { label: "Revenue growth", color: "var(--accent)" },
    { label: "EPS growth", color: "var(--warning)" },
    { label: "Free cash flow", color: "var(--positive)" },
  ];
  const footer = (
    <div className="chart-inspector-footer-stack">
      <div className="chart-inspector-footer-pill-row">
        <span className="pill">Window: {selectedRange}</span>
        <span className="pill">As of {latestDate ? formatDate(latestDate) : "Pending"}</span>
        <span className="pill">Source: Price cache + filing history</span>
      </div>
      <div className="chart-inspector-footer-copy">
        Inspector exports include only the visible window, with price overlays and operating trend data aligned to the current selection.
      </div>
    </div>
  );

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
                className={`chart-chip ${selectedRange === option ? "chart-chip-active" : ""}`}
                onClick={() => setTimeframeMode(rangeOptionToTimeframeMode(option))}
              >
                {option}
              </button>
            ))}
          </div>
          <div className="indicator-toggle-row">
            <ToggleChip label="MA 50" active={toggles.ma50} onClick={() => setToggles((current) => ({ ...current, ma50: !current.ma50 }))} />
            <ToggleChip label="MA 200" active={toggles.ma200} onClick={() => setToggles((current) => ({ ...current, ma200: !current.ma200 }))} />
            <ToggleChip label="Volume" active={toggles.volume} onClick={() => setToggles((current) => ({ ...current, volume: !current.volume }))} />
          </div>
        </div>
      </div>

      <div className="price-fundamentals-strip">
        <SummaryStat label="Last Price" value={formatCurrency(latestPrice)} accent="cyan" />
        <SummaryStat label={`${selectedRange} Return`} value={formatPercent(rangeReturn)} accent="green" />
        <SummaryStat label="Revenue Growth" value={formatPercent(latestRevenueGrowth)} accent="gold" />
        <SummaryStat label="EPS Growth" value={formatPercent(latestEpsGrowth)} accent="cyan" />
        <SummaryStat label="Free Cash Flow" value={formatCompactNumber(latestFreeCashFlow)} accent="green" />
      </div>

      <div className="price-fundamentals-grid">
        <InteractiveChartFrame
          title="Price Chart"
          subtitle={`${priceChartData.length} sessions${priceChartData.length && latestDate ? ` • through ${formatDate(latestDate)}` : ""}`}
          className="price-chart-card"
          headerClassName="price-chart-card-header"
          titleClassName="price-chart-card-title"
          subtitleClassName="price-chart-card-subtitle"
          badgeArea={priceBadgeArea}
          controls={priceControls}
          controlState={{
            datasetKind: "time_series",
            chartType: selectedPriceChartType,
            chartTypeOptions: INSPECTOR_CHART_TYPE_OPTIONS,
            onChartTypeChange: setPriceChartType,
            timeframeMode: selectedTimeframeMode,
            timeframeModeOptions: RANGE_TIMEFRAME_OPTIONS,
            onTimeframeModeChange: handleTimeframeModeChange,
          }}
          annotations={priceAnnotations}
          footer={footer}
          stageState={
            priceChartData.length
              ? undefined
              : {
                  kind: "empty",
                  kicker: "Price chart",
                  title: "No visible price history",
                  message: "Load daily price history or widen the selected window to inspect price action.",
                }
          }
          resetState={{ onReset: resetInspectorView, disabled: resetDisabled }}
          exportState={{
            pngFileName: `${normalizeExportFileStem(title, "price-fundamentals")}-price-chart.png`,
            csvFileName: `${normalizeExportFileStem(title, "price-fundamentals")}-price-chart.csv`,
            csvRows: priceExportRows,
          }}
          renderChart={({ expanded }) =>
            priceChartData.length ? (
              <div style={{ width: "100%", height: expanded ? 460 : 360 }}>
                <ResponsiveContainer>
                  {renderPriceChart({
                    chartType: expanded ? selectedPriceChartType : "composed",
                    data: expanded ? expandedPriceChartData : compactPriceChartData,
                    expanded,
                    gradientId,
                    toggles,
                  })}
                </ResponsiveContainer>
              </div>
            ) : (
              <ChartEmptyState message="Provide daily price and volume history to render the stock chart and moving-average overlays." />
            )
          }
        />

        <InteractiveChartFrame
          title="Fundamentals Trend"
          subtitle={`${fundamentalsChartData.length} reporting periods${fundamentalsChartData.length && latestDate ? ` • through ${formatDate(latestDate)}` : ""}`}
          className="price-chart-card"
          headerClassName="price-chart-card-header"
          titleClassName="price-chart-card-title"
          subtitleClassName="price-chart-card-subtitle"
          badgeArea={fundamentalsBadgeArea}
          controlState={{
            datasetKind: "time_series",
            chartType: selectedFundamentalsChartType,
            chartTypeOptions: INSPECTOR_CHART_TYPE_OPTIONS,
            onChartTypeChange: setFundamentalsChartType,
            timeframeMode: selectedTimeframeMode,
            timeframeModeOptions: RANGE_TIMEFRAME_OPTIONS,
            onTimeframeModeChange: handleTimeframeModeChange,
          }}
          annotations={fundamentalsAnnotations}
          footer={footer}
          stageState={
            fundamentalsChartData.length
              ? undefined
              : {
                  kind: "empty",
                  kicker: "Fundamentals trend",
                  title: "No visible fundamentals trend",
                  message: "The expanded trend inspector appears once revenue, EPS, and free cash flow history are available in the selected window.",
                }
          }
          resetState={{ onReset: resetInspectorView, disabled: resetDisabled }}
          exportState={{
            pngFileName: `${normalizeExportFileStem(title, "price-fundamentals")}-fundamentals-trend.png`,
            csvFileName: `${normalizeExportFileStem(title, "price-fundamentals")}-fundamentals-trend.csv`,
            csvRows: fundamentalsExportRows,
          }}
          renderChart={({ expanded }) =>
            fundamentalsChartData.length ? (
              <div style={{ width: "100%", height: expanded ? 420 : 300 }}>
                <ResponsiveContainer>
                  {renderFundamentalsChart({
                    chartType: expanded ? selectedFundamentalsChartType : "composed",
                    data: expanded ? expandedFundamentalsChartData : compactFundamentalsChartData,
                    expanded,
                    gradientId,
                  })}
                </ResponsiveContainer>
              </div>
            ) : (
              <ChartEmptyState message="Provide dated revenue, EPS, and free cash flow series to compare operating momentum against cash generation." />
            )
          }
        />
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
      <div className="summary-card-label">
        <MetricLabel label={label} />
      </div>
      <div className="summary-card-value">{value}</div>
    </div>
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
  label,
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
      volumeFill,
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
      freeCashFlow: point.free_cash_flow,
    };
  });
}

function renderPriceChart({
  chartType,
  data,
  expanded,
  gradientId,
  toggles,
}: {
  chartType: ChartType;
  data: PriceChartDatum[];
  expanded: boolean;
  gradientId: string;
  toggles: ToggleState;
}) {
  const strokeWidth = expanded ? 2.8 : 2.4;
  const overlayStrokeWidth = expanded ? 2 : 1.75;
  const axisTick = chartTick(expanded ? 11 : 10);
  const margin = { top: 8, right: expanded ? 20 : 12, left: 0, bottom: 0 };
  const showVolume = chartType === "composed" && toggles.volume;
  const showMovingAverages = chartType !== "area";

  return (
    <ComposedChart data={data} margin={margin}>
      <defs>
        <linearGradient id={`${gradientId}-price-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity={chartType === "line" ? 0.16 : 0.32} />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
      <XAxis dataKey="date" minTickGap={expanded ? 36 : 28} stroke={CHART_AXIS_COLOR} tick={axisTick} tickFormatter={formatAxisDate} />
      <YAxis
        yAxisId="price"
        orientation="right"
        stroke={CHART_AXIS_COLOR}
        tick={axisTick}
        tickFormatter={(value) => formatCurrency(value)}
        domain={[(min: number) => expandMin(min), (max: number) => expandMax(max)]}
      />
      <YAxis yAxisId="volume" hide domain={[0, (max: number) => Math.max(max * 1.25, 1)]} />
      <Tooltip
        cursor={{ stroke: "var(--panel-border)", strokeWidth: 1 }}
        content={({ active, payload, label }) => <PriceTooltip active={active} label={label} payload={payload as TooltipEntry[] | undefined} />}
      />
      {showVolume ? (
        <Bar yAxisId="volume" dataKey="volume" barSize={5} fillOpacity={0.28} radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell key={`${entry.date}-volume`} fill={entry.volumeFill} />
          ))}
        </Bar>
      ) : null}
      {chartType === "line" ? (
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="close"
          stroke="var(--accent)"
          strokeWidth={strokeWidth}
          dot={false}
          isAnimationActive
          animationDuration={450}
          activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
        />
      ) : (
        <Area
          yAxisId="price"
          type="monotone"
          dataKey="close"
          stroke="var(--accent)"
          strokeWidth={strokeWidth}
          fill={`url(#${gradientId}-price-fill)`}
          isAnimationActive
          animationDuration={450}
          dot={false}
          activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
        />
      )}
      {showMovingAverages && toggles.ma50 ? (
        <Line yAxisId="price" type="monotone" dataKey="ma50" stroke="var(--warning)" strokeWidth={overlayStrokeWidth} dot={false} isAnimationActive animationDuration={450} />
      ) : null}
      {showMovingAverages && toggles.ma200 ? (
        <Line yAxisId="price" type="monotone" dataKey="ma200" stroke="var(--positive)" strokeWidth={overlayStrokeWidth} dot={false} isAnimationActive animationDuration={450} />
      ) : null}
    </ComposedChart>
  );
}

function renderFundamentalsChart({
  chartType,
  data,
  expanded,
  gradientId,
}: {
  chartType: ChartType;
  data: FundamentalsChartDatum[];
  expanded: boolean;
  gradientId: string;
}) {
  const lineStrokeWidth = expanded ? 2.4 : 2;
  const axisTick = chartTick(expanded ? 11 : 10);
  const margin = { top: 8, right: expanded ? 20 : 12, left: 0, bottom: 0 };

  return (
    <ComposedChart data={data} margin={margin}>
      <defs>
        <linearGradient id={`${gradientId}-fcf-fill`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--positive)" stopOpacity={chartType === "area" ? 0.34 : 0.28} />
          <stop offset="100%" stopColor="var(--positive)" stopOpacity={0.03} />
        </linearGradient>
      </defs>
      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
      <XAxis dataKey="date" minTickGap={expanded ? 32 : 24} stroke={CHART_AXIS_COLOR} tick={axisTick} tickFormatter={formatAxisDate} />
      <YAxis yAxisId="growth" stroke={CHART_AXIS_COLOR} tick={axisTick} tickFormatter={(value) => formatPercent(Number(value))} />
      <YAxis yAxisId="cash" orientation="right" stroke={CHART_AXIS_COLOR} tick={axisTick} tickFormatter={(value) => formatCompactNumber(Number(value))} />
      <Tooltip
        cursor={{ stroke: "var(--panel-border)", strokeWidth: 1 }}
        content={({ active, payload, label }) => <FundamentalsTooltip active={active} label={label} payload={payload as TooltipEntry[] | undefined} />}
      />
      {chartType === "line" ? (
        <Line
          yAxisId="cash"
          type="monotone"
          dataKey="freeCashFlow"
          stroke="var(--positive)"
          strokeWidth={lineStrokeWidth}
          dot={false}
          isAnimationActive
          animationDuration={450}
          activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--positive)" }}
        />
      ) : (
        <Area
          yAxisId="cash"
          type="monotone"
          dataKey="freeCashFlow"
          stroke="var(--positive)"
          strokeWidth={lineStrokeWidth}
          fill={`url(#${gradientId}-fcf-fill)`}
          dot={false}
          isAnimationActive
          animationDuration={450}
          activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--positive)" }}
        />
      )}
      {chartType === "area" ? (
        <>
          <Area
            yAxisId="growth"
            type="monotone"
            dataKey="revenueGrowth"
            stroke="var(--accent)"
            strokeWidth={lineStrokeWidth}
            fill="color-mix(in srgb, var(--accent) 14%, transparent)"
            dot={false}
            isAnimationActive
            animationDuration={450}
            activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--accent)" }}
          />
          <Area
            yAxisId="growth"
            type="monotone"
            dataKey="epsGrowth"
            stroke="var(--warning)"
            strokeWidth={lineStrokeWidth}
            fill="color-mix(in srgb, var(--warning) 12%, transparent)"
            dot={false}
            isAnimationActive
            animationDuration={450}
            activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--warning)" }}
          />
        </>
      ) : (
        <>
          <Line
            yAxisId="growth"
            type="monotone"
            dataKey="revenueGrowth"
            stroke="var(--accent)"
            strokeWidth={lineStrokeWidth}
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
            strokeWidth={lineStrokeWidth}
            dot={false}
            isAnimationActive
            animationDuration={450}
            activeDot={{ r: 4, stroke: "var(--panel)", strokeWidth: 2, fill: "var(--warning)" }}
          />
        </>
      )}
    </ComposedChart>
  );
}

function movingAverage(points: PriceHistoryPoint[], windowSize: number): Array<number | null> {
  return points.map((_, index) => {
    if (index + 1 < windowSize) {
      return null;
    }

    const window = points
      .slice(index - windowSize + 1, index + 1)
      .map((point) => point.close)
      .filter(isFiniteNumber);
    if (window.length !== windowSize) {
      return null;
    }

    return window.reduce((sum, value) => sum + value, 0) / window.length;
  });
}

function rangeOptionToTimeframeMode(range: RangeOption): RangeTimeframeMode {
  switch (range) {
    case "1Y":
      return "1y";
    case "3Y":
      return "3y";
    case "5Y":
      return "5y";
    case "10Y":
      return "10y";
    case "MAX":
      return "max";
  }
}

function timeframeModeToRangeOption(mode: RangeTimeframeMode): RangeOption {
  switch (mode) {
    case "1y":
      return "1Y";
    case "3y":
      return "3Y";
    case "5y":
      return "5Y";
    case "10y":
      return "10Y";
    case "max":
      return "MAX";
  }
}

function isInspectorChartType(value: ChartType | null | undefined): value is (typeof INSPECTOR_CHART_TYPE_OPTIONS)[number] {
  return value != null && INSPECTOR_CHART_TYPE_OPTIONS.includes(value as (typeof INSPECTOR_CHART_TYPE_OPTIONS)[number]);
}

function isRangeTimeframeMode(mode: ChartTimeframeMode): mode is RangeTimeframeMode {
  return RANGE_TIMEFRAME_OPTIONS.includes(mode as RangeTimeframeMode);
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
    maximumFractionDigits: value >= 100 ? 0 : 2,
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

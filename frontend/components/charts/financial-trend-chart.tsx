"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
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
import { MetricLabel } from "@/components/ui/metric-label";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import {
  formatChartCadenceLabel,
  formatChartTimeframeLabel,
  getDefaultChartType,
  type ChartCadenceMode,
  type ChartTimeframeMode,
  type ChartType,
} from "@/lib/chart-capabilities";
import {
  buildWindowedSeries,
  downsampleSeries,
  getSupportedFinancialCadenceModes,
  selectFinancialSeriesByCadence,
} from "@/lib/chart-windowing";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber } from "@/lib/format";

const FINANCIAL_TREND_CHART_TYPE_OPTIONS = ["line", "area", "bar", "composed"] as const satisfies readonly ChartType[];
const FINANCIAL_TREND_TIMEFRAME_OPTIONS = ["1y", "3y", "5y", "10y", "max"] as const satisfies readonly ChartTimeframeMode[];

type FinancialTrendRow = {
  period: string;
  revenue: number | null;
  netIncome: number | null;
  freeCashFlow: number | null;
};

export function FinancialTrendChart({ financials }: { financials: FinancialPayload[] }) {
  const availableCadenceModes = useMemo(() => getSupportedFinancialCadenceModes(financials), [financials]);
  const { chartType, timeframeMode, cadenceMode, setCadenceMode, setChartType, setTimeframeMode } = useChartPreferences({
    chartFamily: "financial-trend",
    defaultChartType: getDefaultChartType("time_series"),
    defaultTimeframeMode: "max",
    defaultCadenceMode: "reported",
    allowedChartTypes: FINANCIAL_TREND_CHART_TYPE_OPTIONS,
    allowedTimeframeModes: FINANCIAL_TREND_TIMEFRAME_OPTIONS,
    allowedCadenceModes: availableCadenceModes,
  });

  const selectedChartType = chartType ?? getDefaultChartType("time_series");
  const selectedTimeframeMode = timeframeMode ?? "max";
  const selectedCadenceMode = cadenceMode ?? "reported";

  const cadenceFinancials = useMemo(
    () => selectFinancialSeriesByCadence(financials, selectedCadenceMode),
    [financials, selectedCadenceMode]
  );
  const visibleFinancials = useMemo(
    () =>
      buildWindowedSeries(cadenceFinancials, {
        timeframeMode: selectedTimeframeMode,
        getDate: (statement) => statement.period_end,
      }),
    [cadenceFinancials, selectedTimeframeMode]
  );

  const data = useMemo(
    () =>
      visibleFinancials.map((item) => ({
        period: item.period_end.slice(0, 10),
        revenue: item.revenue,
        netIncome: item.net_income,
        freeCashFlow: item.free_cash_flow,
      })),
    [visibleFinancials]
  );
  const compactData = useMemo(() => downsampleSeries(data, 28), [data]);
  const expandedData = useMemo(() => downsampleSeries(data, 52), [data]);

  const latestStatement = useMemo(
    () =>
      visibleFinancials.reduce<FinancialPayload | null>((latest, statement) => {
        if (!latest) {
          return statement;
        }
        return Date.parse(statement.period_end) > Date.parse(latest.period_end) ? statement : latest;
      }, null),
    [visibleFinancials]
  );

  const badgeArea = latestStatement ? (
    <ChartSourceBadges
      badges={[
        { label: "Window", value: formatChartTimeframeLabel(selectedTimeframeMode) },
        { label: "Cadence", value: selectedCadenceMode === "ttm" ? "TTM (derived)" : formatChartCadenceLabel(selectedCadenceMode) },
        { label: "Source", value: formatSourceLabel(latestStatement.source) },
        { label: "Updated", value: latestStatement.last_updated.slice(0, 10) },
        { label: "Periods", value: String(data.length) },
      ]}
    />
  ) : null;
  const resetDisabled = selectedChartType === getDefaultChartType("time_series") && selectedTimeframeMode === "max" && selectedCadenceMode === "reported";
  const footer = latestStatement ? (
    <div className="chart-inspector-footer-stack">
      <div className="chart-inspector-footer-pill-row">
        <span className="pill">Source: {formatSourceLabel(latestStatement.source)}</span>
        <span className="pill">Updated {latestStatement.last_updated.slice(0, 10)}</span>
        <span className="pill">Visible periods {data.length}</span>
      </div>
      <div className="chart-inspector-footer-copy">
        Expanded exports use only the visible filing window and the active cadence selection.
      </div>
    </div>
  ) : null;

  return (
    <InteractiveChartFrame
      title="Reported financial trend"
      subtitle={data.length ? `${data.length} filing periods across revenue, net income, and free cash flow.` : "Awaiting filing periods"}
      className="price-chart-card"
      headerClassName="price-chart-card-header"
      titleClassName="price-chart-card-title"
      subtitleClassName="price-chart-card-subtitle"
      badgeArea={badgeArea}
      controlState={{
        datasetKind: "time_series",
        chartType: selectedChartType,
        chartTypeOptions: FINANCIAL_TREND_CHART_TYPE_OPTIONS,
        onChartTypeChange: setChartType,
        timeframeMode: selectedTimeframeMode,
        timeframeModeOptions: FINANCIAL_TREND_TIMEFRAME_OPTIONS,
        onTimeframeModeChange: setTimeframeMode,
        cadenceMode: selectedCadenceMode,
        cadenceModeOptions: availableCadenceModes,
        onCadenceModeChange: setCadenceMode,
      }}
      annotations={[
        { label: "Revenue", color: "var(--accent)" },
        { label: "Net income", color: "var(--warning)" },
        { label: "Free cash flow", color: "var(--positive)" },
      ]}
      footer={footer}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Financial trend",
              title: "No visible filing periods",
              message: "Choose a broader window or cadence once more reported periods are available.",
            }
      }
      resetState={{
        onReset: () => {
          setChartType(getDefaultChartType("time_series"));
          setTimeframeMode("max");
          setCadenceMode("reported");
        },
        disabled: resetDisabled,
      }}
      exportState={{
        pngFileName: `${normalizeExportFileStem("financial-trend", "financial-trend")}.png`,
        csvFileName: `${normalizeExportFileStem("financial-trend", "financial-trend")}.csv`,
        csvRows: data,
      }}
      renderChart={({ expanded }) => renderTrendChart({ chartType: selectedChartType, data: expanded ? expandedData : compactData, expanded })}
    />
  );
}

function renderTrendChart({ chartType, data, expanded }: { chartType: ChartType; data: FinancialTrendRow[]; expanded: boolean }) {
  const height = expanded ? 460 : 320;
  const margin = { top: 8, right: expanded ? 28 : 12, left: 0, bottom: 0 };
  const axisTick = chartTick(expanded ? 11 : 10);
  const lineStroke = expanded ? 2.4 : 2;

  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>
        {chartType === "area" ? (
          <AreaChart data={data} margin={margin}>
            <SharedTrendChrome expanded={expanded} />
            <Area type="monotone" dataKey="revenue" stroke="var(--accent)" fill="color-mix(in srgb, var(--accent) 18%, transparent)" strokeWidth={lineStroke} />
            <Area type="monotone" dataKey="netIncome" stroke="var(--warning)" fill="color-mix(in srgb, var(--warning) 14%, transparent)" strokeWidth={lineStroke} />
            <Area type="monotone" dataKey="freeCashFlow" stroke="var(--positive)" fill="color-mix(in srgb, var(--positive) 14%, transparent)" strokeWidth={lineStroke} />
          </AreaChart>
        ) : chartType === "bar" ? (
          <BarChart data={data} margin={margin}>
            <SharedTrendChrome expanded={expanded} />
            <Bar dataKey="revenue" fill="var(--accent)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="netIncome" fill="var(--warning)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="freeCashFlow" fill="var(--positive)" radius={[3, 3, 0, 0]} />
          </BarChart>
        ) : chartType === "composed" ? (
          <ComposedChart data={data} margin={margin}>
            <SharedTrendChrome expanded={expanded} />
            <Area type="monotone" dataKey="revenue" stroke="var(--accent)" fill="color-mix(in srgb, var(--accent) 16%, transparent)" strokeWidth={lineStroke} />
            <Line type="monotone" dataKey="netIncome" stroke="var(--warning)" strokeWidth={lineStroke} dot={false} />
            <Bar dataKey="freeCashFlow" fill="color-mix(in srgb, var(--positive) 72%, transparent)" radius={[3, 3, 0, 0]} />
          </ComposedChart>
        ) : (
          <LineChart data={data} margin={margin}>
            <SharedTrendChrome expanded={expanded} />
            <Line type="monotone" dataKey="revenue" stroke="var(--accent)" strokeWidth={lineStroke} dot={false} />
            <Line type="monotone" dataKey="netIncome" stroke="var(--warning)" strokeWidth={lineStroke} dot={false} />
            <Line type="monotone" dataKey="freeCashFlow" stroke="var(--positive)" strokeWidth={lineStroke} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

function SharedTrendChrome({ expanded }: { expanded: boolean }) {
  const axisTick = chartTick(expanded ? 11 : 10);

  return (
    <>
      <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
      <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={axisTick} />
      <YAxis stroke={CHART_AXIS_COLOR} tick={axisTick} tickFormatter={(value) => formatCompactNumber(Number(value))} />
      <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
      <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
    </>
  );
}

function formatSourceLabel(value: string): string {
  try {
    return new URL(value).hostname.replace(/^www\./, "");
  } catch {
    return value;
  }
}

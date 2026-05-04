"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { useChartPreferences } from "@/hooks/use-chart-preferences";
import { formatChartTimeframeLabel, type ChartTimeframeMode } from "@/lib/chart-capabilities";
import { buildWindowedSeries } from "@/lib/chart-windowing";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber } from "@/lib/format";
import type { FinancialHistoryPoint } from "@/lib/types";

const FINANCIAL_HISTORY_TIMEFRAME_OPTIONS = ["1y", "3y", "5y", "10y", "max"] as const satisfies readonly ChartTimeframeMode[];

interface FinancialHistoryLineChartProps {
  data: FinancialHistoryPoint[];
  metric: "revenue" | "net_income" | "eps" | "operating_cash_flow";
  color: string;
  label: string;
  subtitle?: string;
  valueFormatter?: (value: number | null) => string;
}

export function FinancialHistoryLineChart({
  data,
  metric,
  color,
  label,
  subtitle,
  valueFormatter
}: FinancialHistoryLineChartProps) {
  const formatter = valueFormatter ?? formatCompactNumber;
  const { timeframeMode, setTimeframeMode } = useChartPreferences({
    chartFamily: "financial-history",
    defaultTimeframeMode: "max",
    allowedTimeframeModes: FINANCIAL_HISTORY_TIMEFRAME_OPTIONS,
  });
  const selectedTimeframeMode = timeframeMode ?? "max";

  const coerceNumber = (raw: unknown): number | null => {
    if (raw === null || raw === undefined) {
      return null;
    }

    if (Array.isArray(raw)) {
      return coerceNumber(raw[0]);
    }

    const numeric = typeof raw === "number" ? raw : Number(raw);
    return Number.isFinite(numeric) ? numeric : null;
  };

  const formatValue = (raw: unknown) => formatter(coerceNumber(raw));
  const visibleData = useMemo(
    () =>
      buildWindowedSeries(data, {
        timeframeMode: selectedTimeframeMode,
        getDate: (row) => (typeof row.year === "number" ? `${row.year}-12-31` : null),
      }),
    [data, selectedTimeframeMode]
  );

  const exportRows = useMemo(
    () =>
      visibleData.map((row) => ({
        fiscal_year: row.year,
        [metric]: row[metric],
      })),
    [metric, visibleData]
  );

  const badgeArea = visibleData.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Cadence", value: "Annual" },
        { label: "Window", value: formatChartTimeframeLabel(selectedTimeframeMode) },
        { label: "Coverage", value: `${visibleData.length} FY points` },
      ]}
    />
  ) : null;

  return (
    <InteractiveChartFrame
      title={label}
      subtitle={subtitle ?? (visibleData.length ? `${visibleData.length} annual observations — Source: SEC EDGAR companyfacts` : "Awaiting annual history")}
      className="financial-history-chart-shell"
      titleClassName="financial-history-chart-title"
      bodyClassName="financial-history-chart-canvas"
      badgeArea={badgeArea}
      controlState={{
        datasetKind: "time_series",
        timeframeMode: selectedTimeframeMode,
        timeframeModeOptions: FINANCIAL_HISTORY_TIMEFRAME_OPTIONS,
        onTimeframeModeChange: setTimeframeMode,
      }}
      annotations={[{ label, color }]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Source: SEC companyfacts</span>
            <span className="pill">Cadence: Annual</span>
            <span className="pill">Visible years {visibleData.length}</span>
          </div>
          <div className="chart-inspector-footer-copy">
            This inspector uses the visible annual companyfacts series only; reset returns to the full available history.
          </div>
        </div>
      )}
      stageState={
        visibleData.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Financial history",
              title: "No annual observations in view",
              message: "Expand the timeframe once annual companyfacts become available for this metric.",
            }
      }
      resetState={{
        onReset: () => setTimeframeMode("max"),
        disabled: selectedTimeframeMode === "max",
      }}
      exportState={{
        pngFileName: `${normalizeExportFileStem(metric, "financial-history")}-history.png`,
        csvFileName: `${normalizeExportFileStem(metric, "financial-history")}-history.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) => (
        <div style={{ width: "100%", height: expanded ? 420 : "100%" }}>
          <ResponsiveContainer>
            <LineChart data={visibleData} margin={{ top: 8, right: expanded ? 24 : 18, left: 4, bottom: 8 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="year" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
              <YAxis
                stroke={CHART_AXIS_COLOR}
                tick={chartTick(expanded ? 11 : 10)}
                tickFormatter={(value) => formatValue(value)}
              />
              <Tooltip
                cursor={{ stroke: "var(--accent)", strokeWidth: 1 }}
                formatter={(value) => formatValue(value)}
                labelFormatter={(value) => `FY ${value}`}
              />
              <Line
                type="monotone"
                dataKey={metric}
                stroke={color}
                strokeWidth={expanded ? 2.8 : 2.4}
                dot={false}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    />
  );
}

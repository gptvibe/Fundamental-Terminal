"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber } from "@/lib/format";
import type { FinancialHistoryPoint } from "@/lib/types";

interface FinancialHistoryLineChartProps {
  data: FinancialHistoryPoint[];
  metric: "revenue" | "net_income" | "eps" | "operating_cash_flow";
  color: string;
  label: string;
  valueFormatter?: (value: number | null) => string;
}

export function FinancialHistoryLineChart({
  data,
  metric,
  color,
  label,
  valueFormatter
}: FinancialHistoryLineChartProps) {

  const formatter = valueFormatter ?? formatCompactNumber;

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

  return (
    <div className="financial-history-chart-shell">
      <div className="financial-history-chart-title">{label}</div>
      <div className="financial-history-chart-canvas">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 18, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="year" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
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
              strokeWidth={2.4}
              dot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

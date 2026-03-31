"use client";

import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, XAxis, YAxis } from "recharts";

import { CHART_GRID_COLOR, chartSeriesColor } from "@/lib/chart-theme";

export interface HistoricalSparklinePoint {
  label: string;
  value: number | null;
  isSelected?: boolean;
  isComparison?: boolean;
}

interface HistoricalSparklineCardProps {
  label: string;
  value: string;
  delta?: string;
  detail?: string;
  data: HistoricalSparklinePoint[];
  emptyMessage?: string;
  color?: string;
}

export function HistoricalSparklineCard({
  label,
  value,
  delta,
  detail,
  data,
  emptyMessage = "Trend unavailable",
  color = chartSeriesColor(0),
}: HistoricalSparklineCardProps) {
  const selectedPoint = data.find((point): point is HistoricalSparklinePoint & { value: number } => point.isSelected === true && point.value != null) ?? null;
  const comparisonPoint = data.find((point): point is HistoricalSparklinePoint & { value: number } => point.isComparison === true && point.value != null) ?? null;
  const finitePoints = data.filter((point) => point.value != null);

  return (
    <div className="metric-card" style={{ display: "grid", gap: 8 }}>
      <div className="historical-sparkline-card-header">
        <div className="historical-sparkline-card-heading">
          <div className="metric-label">{label}</div>
          <div className="metric-value">{value}</div>
        </div>
        {delta ? (
          <div className="text-muted historical-sparkline-card-delta">
            {delta}
          </div>
        ) : null}
      </div>

      <div style={{ width: "100%", height: 72 }}>
        {finitePoints.length >= 2 ? (
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: 4 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="label" hide />
              <YAxis hide domain={["auto", "auto"]} />
              <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2.1} dot={false} connectNulls isAnimationActive={false} />
              {selectedPoint ? <ReferenceDot x={selectedPoint.label} y={selectedPoint.value} r={3.5} fill="var(--accent)" stroke="var(--accent)" isFront /> : null}
              {comparisonPoint ? <ReferenceDot x={comparisonPoint.label} y={comparisonPoint.value} r={3.5} fill="var(--warning)" stroke="var(--warning)" isFront /> : null}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-muted" style={{ fontSize: 12, display: "flex", alignItems: "center", height: "100%" }}>
            {emptyMessage}
          </div>
        )}
      </div>

      {detail ? <div className="text-muted" style={{ fontSize: 12 }}>{detail}</div> : null}
    </div>
  );
}
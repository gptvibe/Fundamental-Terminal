import type { CSSProperties } from "react";

export const CHART_GRID_COLOR = "var(--chart-grid)";
export const CHART_AXIS_COLOR = "var(--chart-axis)";
export const CHART_LEGEND_COLOR = "var(--chart-legend)";
export const CHART_TEXT_COLOR = "var(--text)";
export const CHART_SERIES_COLORS = [
  "var(--chart-series-1)",
  "var(--chart-series-2)",
  "var(--chart-series-3)",
  "var(--chart-series-4)",
  "var(--chart-series-5)",
  "var(--chart-series-6)"
] as const;

export const RECHARTS_TOOLTIP_PROPS = {
  contentStyle: {
    background: "var(--tooltip-bg)",
    border: "1px solid var(--tooltip-border)",
    borderRadius: 6,
    color: "var(--tooltip-text)",
    boxShadow: "var(--tooltip-shadow)",
    padding: "6px 10px",
    fontSize: 12
  } as CSSProperties,
  labelStyle: {
    color: "var(--tooltip-text)",
    fontWeight: 600,
    fontFamily: "var(--mono)",
    letterSpacing: "0.02em",
    fontSize: 12
  } as CSSProperties,
  itemStyle: {
    color: "var(--tooltip-text)",
    fontSize: 11
  } as CSSProperties,
  wrapperStyle: {
    outline: "none"
  } as CSSProperties
} as const;

export function chartTick(fontSize = 10): { fill: string; fontSize: number; fontFamily: string } {
  return {
    fill: CHART_AXIS_COLOR,
    fontSize,
    fontFamily: "var(--mono)"
  };
}

export function chartLegendStyle(fontSize = 11): CSSProperties {
  return {
    color: CHART_LEGEND_COLOR,
    fontSize,
    fontFamily: "var(--mono)",
    letterSpacing: "0.02em"
  };
}

export function chartSeriesColor(index: number): string {
  return CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length];
}

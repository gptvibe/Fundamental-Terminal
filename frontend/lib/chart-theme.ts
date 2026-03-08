import type { CSSProperties } from "react";

export const CHART_GRID_COLOR = "var(--chart-grid)";
export const CHART_AXIS_COLOR = "var(--chart-axis)";
export const CHART_LEGEND_COLOR = "var(--chart-legend)";
export const CHART_TEXT_COLOR = "var(--text)";

export const RECHARTS_TOOLTIP_PROPS = {
  contentStyle: {
    background: "var(--tooltip-bg)",
    border: "1px solid var(--tooltip-border)",
    borderRadius: 12,
    color: "var(--tooltip-text)",
    boxShadow: "var(--tooltip-shadow)"
  } as CSSProperties,
  labelStyle: {
    color: "var(--tooltip-text)",
    fontWeight: 600
  } as CSSProperties,
  itemStyle: {
    color: "var(--tooltip-text)"
  } as CSSProperties,
  wrapperStyle: {
    outline: "none"
  } as CSSProperties
} as const;

export function chartTick(fontSize = 12): { fill: string; fontSize: number } {
  return {
    fill: CHART_AXIS_COLOR,
    fontSize
  };
}

export function chartLegendStyle(fontSize = 12): CSSProperties {
  return {
    color: CHART_LEGEND_COLOR,
    fontSize
  };
}

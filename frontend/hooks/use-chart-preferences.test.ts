// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { CHART_PREFERENCES_STORAGE_KEY, useChartPreferences } from "@/hooks/use-chart-preferences";

describe("useChartPreferences", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("hydrates persisted preferences by chart family and filters invalid stored values", () => {
    window.localStorage.setItem(
      CHART_PREFERENCES_STORAGE_KEY,
      JSON.stringify({
        "financial-trend": {
          chartType: "bar",
          timeframeMode: "10y",
          cadenceMode: "annual",
        },
        "price-fundamentals": {
          timeframeMode: "quarterly",
        },
      })
    );

    const { result } = renderHook(() =>
      useChartPreferences({
        chartFamily: "financial-trend",
        defaultChartType: "line",
        defaultTimeframeMode: "5y",
        defaultCadenceMode: "reported",
        allowedChartTypes: ["line", "bar", "area"],
        allowedTimeframeModes: ["1y", "5y", "10y"],
        allowedCadenceModes: ["reported", "annual"],
      })
    );

    expect(result.current.chartType).toBe("bar");
    expect(result.current.timeframeMode).toBe("10y");
    expect(result.current.cadenceMode).toBe("annual");
  });

  it("persists updates for the active chart family", () => {
    const { result } = renderHook(() =>
      useChartPreferences({
        chartFamily: "price-fundamentals",
        defaultChartType: "area",
        defaultTimeframeMode: "5y",
        allowedChartTypes: ["area", "line"],
        allowedTimeframeModes: ["1y", "3y", "5y", "10y", "max"],
      })
    );

    act(() => {
      result.current.setChartType("line");
      result.current.setTimeframeMode("3y");
    });

    expect(result.current.chartType).toBe("line");
    expect(result.current.timeframeMode).toBe("3y");
    expect(window.localStorage.getItem(CHART_PREFERENCES_STORAGE_KEY)).toBe(
      JSON.stringify({
        "price-fundamentals": {
          chartType: "line",
          timeframeMode: "3y",
        },
      })
    );
  });
});
import { describe, expect, it } from "vitest";

import { getAllowedChartTypes, getDefaultChartType } from "@/lib/chart-capabilities";

describe("chart capabilities", () => {
  it("filters invalid pie-family types from time-series datasets", () => {
    expect(getAllowedChartTypes("time_series", ["pie", "line", "donut", "area"])).toEqual(["line", "area"]);
  });

  it("falls back to the dataset defaults when requested types are all invalid", () => {
    expect(getAllowedChartTypes("time_series", ["pie", "donut"])).toEqual(["line", "area", "bar", "composed"]);
    expect(getDefaultChartType("time_series")).toBe("line");
  });

  it("preserves pie-family types for composition datasets", () => {
    expect(getAllowedChartTypes("segment_mix", ["donut", "pie", "bar"])).toEqual(["donut", "pie", "bar"]);
  });
});
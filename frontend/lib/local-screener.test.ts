// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import {
  DEFAULT_LOCAL_SCREENER_DRAFT,
  LOCAL_SCREENER_STORAGE_KEY,
  buildOfficialScreenerSearchRequest,
  countActiveScreenerFilters,
  readLocalScreenerState,
  saveLocalScreenerDraft,
  saveLocalScreenerPreset,
} from "@/lib/local-screener";

describe("local screener persistence", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("persists a draft and builds a typed screener request", () => {
    const state = saveLocalScreenerDraft({
      ...DEFAULT_LOCAL_SCREENER_DRAFT,
      tickerUniverseText: " aapl, msft msft ",
      sortField: "quality_score",
      limit: 100,
      offset: 50,
      filters: {
        ...DEFAULT_LOCAL_SCREENER_DRAFT.filters,
        revenue_growth_min: "0.12",
        shareholder_yield_min: "0.02",
        exclude_restatements: true,
        excluded_quality_flags: ["metrics_cache_stale"],
      },
    });

    const request = buildOfficialScreenerSearchRequest(state.draft);

    expect(request.period_type).toBe("ttm");
    expect(request.ticker_universe).toEqual(["AAPL", "MSFT"]);
    expect(request.sort.field).toBe("quality_score");
    expect(request.limit).toBe(100);
    expect(request.offset).toBe(50);
    expect(request.filters.revenue_growth_min).toBe(0.12);
    expect(request.filters.shareholder_yield_min).toBe(0.02);
    expect(request.filters.exclude_restatements).toBe(true);
    expect(request.filters.excluded_quality_flags).toEqual(["metrics_cache_stale"]);
    expect(readLocalScreenerState().draft.sortField).toBe("quality_score");
  });

  it("upserts presets by name and stores preset drafts with offset reset", () => {
    saveLocalScreenerPreset("Quality Compounders", {
      ...DEFAULT_LOCAL_SCREENER_DRAFT,
      offset: 75,
      sortField: "quality_score",
    });
    const nextState = saveLocalScreenerPreset("Quality Compounders", {
      ...DEFAULT_LOCAL_SCREENER_DRAFT,
      offset: 25,
      sortField: "value_score",
    });

    expect(nextState.presets).toHaveLength(1);
    expect(nextState.presets[0]?.name).toBe("Quality Compounders");
    expect(nextState.presets[0]?.draft.offset).toBe(0);
    expect(nextState.presets[0]?.draft.sortField).toBe("value_score");
  });

  it("counts active filters across numeric inputs, booleans, quality flags, and universe", () => {
    const count = countActiveScreenerFilters({
      ...DEFAULT_LOCAL_SCREENER_DRAFT,
      tickerUniverseText: "AAPL MSFT",
      filters: {
        ...DEFAULT_LOCAL_SCREENER_DRAFT.filters,
        revenue_growth_min: "0.15",
        leverage_ratio_max: "1.0",
        exclude_stale_periods: true,
        excluded_quality_flags: ["metrics_cache_stale"],
      },
    });

    expect(count).toBe(5);
    expect(window.localStorage.getItem(LOCAL_SCREENER_STORAGE_KEY)).toBeNull();
  });
});
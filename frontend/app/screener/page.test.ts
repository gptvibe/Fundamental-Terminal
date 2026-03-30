// @vitest-environment jsdom

import * as React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OfficialScreenerPage from "@/app/screener/page";

const getOfficialScreenerMetadata = vi.fn();
const searchOfficialScreener = vi.fn();
const showAppToast = vi.fn();
const mockUseLocalScreener = vi.fn();

vi.mock("@/lib/api", () => ({
  getOfficialScreenerMetadata: (...args: unknown[]) => getOfficialScreenerMetadata(...args),
  searchOfficialScreener: (...args: unknown[]) => searchOfficialScreener(...args),
}));

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

vi.mock("@/hooks/use-local-screener", () => ({
  useLocalScreener: () => mockUseLocalScreener(),
}));

describe("OfficialScreenerPage", () => {
  beforeEach(() => {
    getOfficialScreenerMetadata.mockReset();
    searchOfficialScreener.mockReset();
    showAppToast.mockReset();
    mockUseLocalScreener.mockReset();

    mockUseLocalScreener.mockReturnValue(createLocalScreenerReturn());

    getOfficialScreenerMetadata.mockResolvedValue(buildMetadataPayload());
    searchOfficialScreener.mockResolvedValue(buildSearchPayload());
  });

  afterEach(() => {
    cleanup();
  });

  it("renders ranked results and exposes a Research Brief jump", async () => {
    render(React.createElement(OfficialScreenerPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    const link = screen.getByRole("link", { name: "Research Brief" });
    expect(link.getAttribute("href")).toBe("/company/AAPL");
    expect(screen.getByText("Quality Compounders")).toBeTruthy();
    expect(searchOfficialScreener).toHaveBeenCalledTimes(1);
  });

  it("saves presets from the current draft and reruns ranking sort from table headers", async () => {
    const savePreset = vi.fn();
    const updateDraft = vi.fn();
    mockUseLocalScreener.mockReturnValue(createLocalScreenerReturn({
      savePreset,
      updateDraft,
      presets: [],
      presetCount: 0,
    }));

    render(React.createElement(OfficialScreenerPage));

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeTruthy();
    });

    fireEvent.change(screen.getByPlaceholderText("Large-cap compounders"), {
      target: { value: "High Quality" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Preset" }));

    expect(savePreset).toHaveBeenCalledWith("High Quality");
    expect(showAppToast).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Quality/ }));

    await waitFor(() => {
      expect(searchOfficialScreener).toHaveBeenCalledTimes(2);
    });
    expect(updateDraft).toHaveBeenCalled();
    expect(searchOfficialScreener.mock.calls[1]?.[0]?.sort?.field).toBe("quality_score");
  });
});

function createLocalScreenerReturn(overrides?: Record<string, unknown>) {
  return {
    hydrated: true,
    draft: {
      periodType: "ttm",
      tickerUniverseText: "",
      sortField: "revenue_growth",
      sortDirection: "desc",
      limit: 50,
      offset: 0,
      filters: {
        revenue_growth_min: "",
        operating_margin_min: "",
        fcf_margin_min: "",
        leverage_ratio_max: "",
        dilution_max: "",
        sbc_burden_max: "",
        shareholder_yield_min: "",
        max_filing_lag_days: "",
        exclude_restatements: false,
        exclude_stale_periods: false,
        excluded_quality_flags: [],
      },
    },
    presets: [
      {
        id: "quality-preset",
        name: "Quality Compounders",
        updatedAt: "2026-03-30T00:00:00Z",
        draft: {
          periodType: "ttm",
          tickerUniverseText: "AAPL MSFT",
          sortField: "quality_score",
          sortDirection: "desc",
          limit: 50,
          offset: 0,
          filters: {
            revenue_growth_min: "0.10",
            operating_margin_min: "0.20",
            fcf_margin_min: "",
            leverage_ratio_max: "",
            dilution_max: "",
            sbc_burden_max: "",
            shareholder_yield_min: "",
            max_filing_lag_days: "",
            exclude_restatements: false,
            exclude_stale_periods: false,
            excluded_quality_flags: [],
          },
        },
      },
    ],
    presetCount: 1,
    updateDraft: vi.fn(),
    resetDraft: vi.fn(),
    savePreset: vi.fn(),
    deletePreset: vi.fn(),
    applyPreset: vi.fn().mockReturnValue(null),
    ...overrides,
  };
}

function buildMetadataPayload() {
  const qualityFlags = ["metrics_cache_stale", "historical_restatement_present"];
  return {
    provenance: [],
    as_of: null,
    last_refreshed_at: null,
    source_mix: {
      source_ids: ["ft_screener_backend"],
      source_tiers: ["derived_from_official"],
      primary_source_ids: ["ft_screener_backend"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: ["official_source_only"],
    strict_official_only: true,
    default_period_type: "ttm",
    period_types: ["quarterly", "annual", "ttm"],
    default_sort: { field: "revenue_growth", direction: "desc" },
    filters: [
      buildFilter("revenue_growth_min", "Revenue growth", "Minimum revenue growth", "ratio"),
      buildFilter("operating_margin_min", "Operating margin", "Minimum operating margin", "ratio"),
      buildFilter("fcf_margin_min", "FCF margin", "Minimum free-cash-flow margin", "ratio"),
      buildFilter("shareholder_yield_min", "Shareholder yield", "Minimum shareholder yield", "ratio"),
      buildFilter("leverage_ratio_max", "Leverage", "Maximum leverage ratio", "ratio"),
      buildFilter("dilution_max", "Dilution", "Maximum dilution", "ratio"),
      buildFilter("sbc_burden_max", "SBC burden", "Maximum SBC burden", "ratio"),
      buildFilter("max_filing_lag_days", "Filing lag", "Maximum filing lag", "days"),
      {
        field: "excluded_quality_flags",
        label: "Exclude quality flags",
        description: "Remove issuers with selected quality flags.",
        comparator: "exclude_any",
        source_kind: "quality_flag",
        source_key: "filing_quality.aggregated_quality_flags",
        unit: null,
        official_only: true,
        notes: [],
        suggested_values: qualityFlags,
      },
    ],
    rankings: [
      buildRanking("quality", "Quality", "higher_is_better"),
      buildRanking("value", "Value", "higher_is_better"),
      buildRanking("capital_allocation", "Capital Allocation", "higher_is_better"),
      buildRanking("dilution_risk", "Dilution Risk", "higher_is_worse"),
      buildRanking("filing_risk", "Filing Risk", "higher_is_worse"),
    ],
    notes: ["Official-source-only screener"],
  };
}

function buildSearchPayload() {
  return {
    provenance: [],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-30T00:00:00Z",
    source_mix: {
      source_ids: ["ft_screener_backend"],
      source_tiers: ["derived_from_official"],
      primary_source_ids: ["ft_screener_backend"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: ["official_source_only"],
    query: {
      period_type: "ttm",
      ticker_universe: [],
      filters: {
        revenue_growth_min: null,
        operating_margin_min: null,
        fcf_margin_min: null,
        leverage_ratio_max: null,
        dilution_max: null,
        sbc_burden_max: null,
        shareholder_yield_min: null,
        max_filing_lag_days: null,
        exclude_restatements: false,
        exclude_stale_periods: false,
        excluded_quality_flags: [],
      },
      sort: { field: "revenue_growth", direction: "desc" },
      limit: 50,
      offset: 0,
      strict_official_only: true,
    },
    coverage: {
      candidate_count: 1,
      matched_count: 1,
      returned_count: 1,
      fresh_count: 1,
      stale_count: 0,
      missing_shareholder_yield_count: 0,
      restatement_flagged_count: 0,
      stale_period_flagged_count: 0,
    },
    results: [
      {
        company: {
          ticker: "AAPL",
          cik: "0000320193",
          name: "Apple Inc.",
          sector: "Technology",
          market_sector: "Technology",
          market_industry: "Consumer Electronics",
          cache_state: "fresh",
        },
        period_type: "ttm",
        period_end: "2025-12-31",
        filing_type: "TTM",
        last_metrics_check: "2026-03-30T00:00:00Z",
        last_model_check: "2026-03-29T00:00:00Z",
        metrics: {
          revenue_growth: metric(0.18, "revenue_growth", true),
          operating_margin: metric(0.31, "operating_margin"),
          fcf_margin: metric(0.27, "fcf_margin"),
          leverage_ratio: metric(0.62, "debt_to_equity"),
          dilution: metric(-0.01, "dilution_trend", true),
          sbc_burden: metric(0.04, "sbc_to_revenue"),
          shareholder_yield: metric(0.06, "capital_allocation.shareholder_yield", true),
        },
        filing_quality: {
          filing_lag_days: metric(33, "filing_lag_days", true, "days"),
          stale_period_flag: metric(0, "stale_period_flag", true, "flag"),
          restatement_flag: metric(0, "restatement_flag", true, "flag"),
          restatement_count: 0,
          latest_restatement_filing_date: null,
          latest_restatement_period_end: null,
          aggregated_quality_flags: [],
        },
        rankings: {
          quality: ranking("quality", "Quality", 82, 1, 100, "higher_is_better"),
          value: ranking("value", "Value", 74, 1, 100, "higher_is_better"),
          capital_allocation: ranking("capital_allocation", "Capital Allocation", 79, 1, 100, "higher_is_better"),
          dilution_risk: ranking("dilution_risk", "Dilution Risk", 19, 1, 0, "higher_is_worse"),
          filing_risk: ranking("filing_risk", "Filing Risk", 22, 1, 0, "higher_is_worse"),
        },
      },
    ],
  };
}

function buildFilter(field: string, label: string, description: string, unit: string | null) {
  return {
    field,
    label,
    description,
    comparator: field.includes("max") ? "max" : "min",
    source_kind: "derived_metric",
    source_key: field,
    unit,
    official_only: true,
    notes: [],
    suggested_values: [],
  };
}

function buildRanking(scoreKey: string, label: string, directionality: "higher_is_better" | "higher_is_worse") {
  return {
    score_key: scoreKey,
    label,
    description: `${label} ranking`,
    score_directionality: directionality,
    universe_basis: "candidate_universe_pre_filter",
    method_summary: "Weighted cross-sectional percentile blend.",
    components: [
      {
        component_key: "revenue_growth",
        label: "Revenue growth",
        source_key: "revenue_growth",
        unit: "ratio",
        weight: 0.3,
        directionality: "higher_increases_score",
        notes: [],
      },
    ],
    confidence_notes_policy: ["missing_components_reweighted:<component_keys>"],
    notes: [],
  };
}

function metric(value: number, sourceKey: string, isProxy = false, unit = "ratio") {
  return {
    value,
    unit,
    is_proxy: isProxy,
    source_key: sourceKey,
    quality_flags: [],
  };
}

function ranking(
  scoreKey: string,
  label: string,
  score: number,
  rank: number,
  percentile: number,
  scoreDirectionality: "higher_is_better" | "higher_is_worse"
) {
  return {
    score_key: scoreKey,
    label,
    score,
    rank,
    percentile,
    universe_size: 1,
    universe_basis: "candidate_universe_pre_filter",
    score_directionality: scoreDirectionality,
    confidence_notes: [],
    components: [],
  };
}
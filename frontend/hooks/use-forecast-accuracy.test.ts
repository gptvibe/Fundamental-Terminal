// @vitest-environment jsdom

import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useForecastAccuracy } from "@/hooks/use-forecast-accuracy";
import { getCompanyChartsForecastAccuracy } from "@/lib/api";
import type { CompanyChartsForecastAccuracyResponse } from "@/lib/types";

vi.mock("@/lib/api", () => ({
  getCompanyChartsForecastAccuracy: vi.fn(),
}));

function buildResponse(): CompanyChartsForecastAccuracyResponse {
  return {
    company: null,
    status: "ok",
    insufficient_history_reason: null,
    max_backtests: 6,
    metrics: [],
    aggregate: {
      snapshot_count: 2,
      sample_count: 4,
      directional_sample_count: 4,
      mean_absolute_percentage_error: 0.12,
      directional_accuracy: 0.75,
    },
    samples: [],
    refresh: {
      triggered: false,
      reason: "fresh",
      ticker: "ACME",
      job_id: null,
    },
    diagnostics: {
      coverage_ratio: 0.9,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: null,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: [],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-04-19T00:00:00Z",
    source_mix: {
      source_ids: [],
      source_tiers: [],
      primary_source_ids: [],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
  };
}

describe("useForecastAccuracy", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("handles success state", async () => {
    vi.mocked(getCompanyChartsForecastAccuracy).mockResolvedValue(buildResponse() as never);

    const { result } = renderHook(() => useForecastAccuracy("ACME"));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBeNull();
    expect(result.current.data?.aggregate.sample_count).toBe(4);
    expect(getCompanyChartsForecastAccuracy).toHaveBeenCalledWith("ACME", { asOf: undefined });
  });

  it("handles error state", async () => {
    vi.mocked(getCompanyChartsForecastAccuracy).mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useForecastAccuracy("ACME"));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("boom");
  });

  it("supports disabled mode", async () => {
    const { result } = renderHook(() => useForecastAccuracy("ACME", { enabled: false }));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(getCompanyChartsForecastAccuracy).not.toHaveBeenCalled();
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });
});

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
    expect(getCompanyChartsForecastAccuracy).toHaveBeenCalledWith("ACME", expect.objectContaining({ asOf: undefined, signal: expect.anything() }));
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

  it("aborts the prior forecast accuracy request when inputs change", async () => {
    let firstSignal: AbortSignal | undefined;

    vi.mocked(getCompanyChartsForecastAccuracy)
      .mockImplementationOnce((_ticker, options) => {
        firstSignal = options?.signal;
        return new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            "abort",
            () => {
              reject(new DOMException("The operation was aborted.", "AbortError"));
            },
            { once: true }
          );
        }) as never;
      })
      .mockResolvedValueOnce(buildResponse() as never);

    const { result, rerender } = renderHook(
      ({ asOf }) => useForecastAccuracy("ACME", { asOf }),
      { initialProps: { asOf: "2025-12-31" as string | null } }
    );

    rerender({ asOf: "2026-01-31" });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(firstSignal?.aborted).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.data?.as_of).toBe("2025-12-31");
  });
});

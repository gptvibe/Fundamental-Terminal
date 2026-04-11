import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyChangesSinceLastFiling,
  getCompanyFinancials,
  refreshCompany,
} from "@/lib/api";

describe("api read cache", () => {
  afterEach(() => {
    __resetApiClientCacheForTests();
    vi.restoreAllMocks();
  });

  it("dedupes repeated read requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        company: null,
        financials: [],
        price_history: [],
        refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFinancials("AAPL");
    await getCompanyFinancials("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/financials",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("returns the same promise for concurrent reads to the same URL", async () => {
    let resolveFetch: ((value: unknown) => void) | null = null;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        })
    );

    vi.stubGlobal("fetch", fetchMock);

    const firstRequest = getCompanyChangesSinceLastFiling("AAPL");
    const secondRequest = getCompanyChangesSinceLastFiling("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/changes-since-last-filing",
      expect.objectContaining({ cache: "no-store" })
    );

    resolveFetch?.({
      ok: true,
      json: async () => ({
        company: null,
        current_filing: null,
        previous_filing: null,
        summary: {},
        metric_deltas: [],
        new_risk_indicators: [],
        segment_shifts: [],
        share_count_changes: [],
        capital_structure_changes: [],
        amended_prior_values: [],
        high_signal_changes: [],
        comment_letter_history: { total_letters: 0, recent_letters: [] },
        refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
        diagnostics: null,
        provenance: [],
        source_mix: null,
        confidence_flags: [],
        as_of: null,
        last_refreshed_at: null,
      }),
    });

    const [firstResult, secondResult] = await Promise.all([firstRequest, secondRequest]);

    expect(firstResult).toEqual(secondResult);
  });

  it("clears the in-flight entry when a request rejects", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Server Error",
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          company: null,
          current_filing: null,
          previous_filing: null,
          summary: {},
          metric_deltas: [],
          new_risk_indicators: [],
          segment_shifts: [],
          share_count_changes: [],
          capital_structure_changes: [],
          amended_prior_values: [],
          high_signal_changes: [],
          comment_letter_history: { total_letters: 0, recent_letters: [] },
          refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
          diagnostics: null,
          provenance: [],
          source_mix: null,
          confidence_flags: [],
          as_of: null,
          last_refreshed_at: null,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    const firstRequest = getCompanyChangesSinceLastFiling("AAPL");
    const secondRequest = getCompanyChangesSinceLastFiling("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);

    const [firstError, secondError] = await Promise.allSettled([firstRequest, secondRequest]);

    expect(firstError.status).toBe("rejected");
    expect(secondError.status).toBe("rejected");
    expect(firstError.status === "rejected" ? firstError.reason.message : null).toBe("API request failed: 500 Server Error");
    expect(secondError.status === "rejected" ? secondError.reason.message : null).toBe("API request failed: 500 Server Error");

    const retryResult = await getCompanyChangesSinceLastFiling("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(retryResult.refresh.ticker).toBe("AAPL");
  });

  it("keeps refresh endpoint uncached", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        refresh: { triggered: true, reason: "manual", ticker: "AAPL", job_id: "job-123" },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await refreshCompany("AAPL", true);

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/refresh?force=true",
      expect.objectContaining({ method: "POST", cache: "no-store" })
    );
  });
});

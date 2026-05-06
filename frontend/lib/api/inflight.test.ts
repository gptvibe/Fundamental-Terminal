// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyFilings,
  getCompanyGovernance,
  getCompanyInsiderTrades,
  getCompanyModels,
  getCompanyDerivedMetrics,
  getWatchlistCalendar,
  getSourceRegistry,
  getCacheMetrics,
  getCompanyBeneficialOwnership,
  getCompanyExecutiveCompensation,
  getCompanyEarnings,
} from "@/lib/api";
import { inflightRequests } from "@/lib/api/inflight";

function buildOkJsonResponse(payload: unknown) {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => payload,
  };
}

describe("inflight dedup via inflightRequests map", () => {
  beforeEach(async () => {
    await __resetApiClientCacheForTests();
  });

  afterEach(async () => {
    await __resetApiClientCacheForTests();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("starts with an empty map", () => {
    expect(inflightRequests.size).toBe(0);
  });

  it("registers an inflight entry while the request is pending", async () => {
    let resolveFetch: ((value: unknown) => void) | null = null;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    const pendingRequest = getCompanyFilings("AAPL");

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    expect(inflightRequests.size).toBeGreaterThan(0);

    resolveFetch?.(buildOkJsonResponse({ filings: [] }));
    await pendingRequest;

    expect(inflightRequests.size).toBe(0);
  });

  it("deduplicates concurrent GET requests to the same endpoint", async () => {
    let resolveFetch: ((value: unknown) => void) | null = null;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        })
    );
    vi.stubGlobal("fetch", fetchMock);

    const first = getCompanyGovernance("AAPL");
    const second = getCompanyGovernance("AAPL");
    const third = getCompanyGovernance("AAPL");

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    resolveFetch?.(buildOkJsonResponse({ board: [], officers: [] }));

    const [r1, r2, r3] = await Promise.all([first, second, third]);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(r1).toBe(r2);
    expect(r2).toBe(r3);
  });

  it("clears inflight entry when request resolves", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ board: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyGovernance("MSFT");

    expect(inflightRequests.size).toBe(0);
  });

  it("clears inflight entry when request rejects", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network error"));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFilings("AAPL").catch(() => undefined);

    expect(inflightRequests.size).toBe(0);
  });
});

describe("representative endpoint routes", () => {
  beforeEach(async () => {
    await __resetApiClientCacheForTests();
  });

  afterEach(async () => {
    await __resetApiClientCacheForTests();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("getCompanyModels builds the correct URL with model names and options", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ models: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyModels("AAPL", ["dupont", "dcf"], { dupontMode: "annual", asOf: "2025-01-01" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/models?model=dupont%2Cdcf&dupont_mode=annual&as_of=2025-01-01",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getCompanyDerivedMetrics builds correct URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ metrics: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyDerivedMetrics("NVDA", { periodType: "ttm", maxPeriods: 8 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/NVDA/metrics?period_type=ttm&max_periods=8",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getCompanyInsiderTrades calls the correct endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ trades: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyInsiderTrades("TSLA");

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/TSLA/insider-trades",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getCompanyBeneficialOwnership calls the correct endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ holders: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyBeneficialOwnership("MSFT");

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/MSFT/beneficial-ownership",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getCompanyExecutiveCompensation calls the correct endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ executives: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyExecutiveCompensation("GOOGL");

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/GOOGL/executive-compensation",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getCompanyEarnings calls the correct endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ quarters: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyEarnings("AMZN");

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AMZN/earnings",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getWatchlistCalendar appends tickers as repeated query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ events: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getWatchlistCalendar(["AAPL", "MSFT", "NVDA"]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/watchlist/calendar?tickers=AAPL&tickers=MSFT&tickers=NVDA",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getSourceRegistry calls the correct endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ sources: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getSourceRegistry();

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/source-registry",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("getCacheMetrics calls the internal metrics endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ entries: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await getCacheMetrics();

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/internal/cache-metrics",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("encodes ticker with special characters in URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse({ filings: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFilings("BRK.B");

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/BRK.B/filings",
      expect.any(Object)
    );
  });
});

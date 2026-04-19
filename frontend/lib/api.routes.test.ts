import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyCapitalStructure,
  getCompanyCharts,
  getCompanyChangesSinceLastFiling,
  getCompaniesCompare,
  getCompanyEarningsWorkspace,
  getCompanyFinancials,
  getCompanyFinancialRestatements,
  getCompanyFilingInsights,
  getCompanyFilings,
  getCompanyMarketContext,
  getCompanyOverview,
  getCompanyResearchBrief,
  getLatestModelEvaluation,
  getCompanyModels,
  getCompanyPeers,
  getCacheMetrics,
  getSourceRegistry,
  getWatchlistCalendar,
  getWatchlistSummary,
} from "@/lib/api";

describe("api route stability", () => {
  afterEach(() => {
    __resetApiClientCacheForTests();
    vi.restoreAllMocks();
  });

  it("keeps key GET helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyEarningsWorkspace("AAPL");
    await getCompanyFilings("MSFT");
    await getCompanyFilingInsights("NVDA");
    await getCompanyMarketContext("AMD");
    await getCompanyOverview("AAPL");
    await getCompanyResearchBrief("AAPL");
    await getLatestModelEvaluation();
    await getCompanyCapitalStructure("AAPL");
    await getCompanyPeers("AAPL", ["MSFT", "NVDA"]);
    await getCompaniesCompare(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/earnings/workspace",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/MSFT/filings",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/NVDA/filing-insights",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AMD/market-context",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/overview",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/brief",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/backend/api/model-evaluations/latest",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      "/backend/api/companies/AAPL/capital-structure",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      9,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      10,
      "/backend/api/companies/compare?tickers=AAPL%2CMSFT",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps workspace POST helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tickers: [], companies: [] }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getWatchlistSummary(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/watchlist/summary",
      expect.objectContaining({
        method: "POST",
        cache: "no-store",
        body: JSON.stringify({ tickers: ["AAPL", "MSFT"] }),
      })
    );
  });

  it("keeps workspace GET helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tickers: [], window_start: "2026-04-04", window_end: "2026-07-03", events: [] }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getWatchlistCalendar(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/watchlist/calendar?tickers=AAPL&tickers=MSFT",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps source registry helper path unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        strict_official_mode: false,
        generated_at: "2026-04-05T00:00:00Z",
        sources: [],
        health: { total_companies_cached: 0, average_data_age_seconds: null, recent_error_window_hours: 72, sources_with_recent_errors: [] },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getSourceRegistry();

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/source-registry",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps internal cache metrics helper path unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        search_cache: { entries: 0, ttl_seconds: 60 },
        hot_cache: {
          backend: "redis",
          shared: true,
          namespace: "ft:hot-cache",
          config: {
            ttl_seconds: 20,
            stale_ttl_seconds: 120,
            singleflight_lock_seconds: 30,
            singleflight_wait_seconds: 15,
            singleflight_poll_seconds: 0.05,
          },
          overall: {
            requests: 0,
            hit_fresh: 0,
            hit_stale: 0,
            hits: 0,
            misses: 0,
            hit_rate: 0,
            fills: 0,
            fill_time_ms_total: 0,
            avg_fill_time_ms: 0,
            stale_served_count: 0,
            invalidation_count: 0,
            invalidated_keys: 0,
            coalesced_waits: 0,
          },
          routes: {},
        },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCacheMetrics();

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/internal/cache-metrics",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("serializes point-in-time query params for research helpers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFinancials("AAPL", { asOf: "2025-02-01", view: "core" });
    await getCompanyOverview("AAPL", { asOf: "2025-02-01", financialsView: "core_segments" });
    await getCompanyCapitalStructure("AAPL", { maxPeriods: 6, asOf: "2025-02-01" });
    await getCompanyResearchBrief("AAPL", { asOf: "2025-02-01" });
    await getCompanyChangesSinceLastFiling("AAPL", { asOf: "2025-02-01" });
    await getCompanyFinancialRestatements("AAPL", { asOf: "2025-02-01" });
    await getCompanyModels("AAPL", ["dcf"], { dupontMode: "ttm", asOf: "2025-02-01" });
    await getCompanyPeers("AAPL", ["MSFT", "NVDA"], { asOf: "2025-02-01" });
    await getCompaniesCompare(["AAPL", "MSFT"], { asOf: "2025-02-01" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/financials?view=core&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/overview?financials_view=core_segments&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/capital-structure?max_periods=6&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AAPL/brief?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/changes-since-last-filing?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/financial-restatements?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/backend/api/companies/AAPL/models?model=dcf&dupont_mode=ttm&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      9,
      "/backend/api/companies/compare?tickers=AAPL%2CMSFT&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps charts helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyCharts("AAPL");
    await getCompanyCharts("AAPL", { asOf: "2025-02-01" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/charts",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/charts?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("serializes model payload expansions only when requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyModels("AAPL", ["dcf", "dupont"], { dupontMode: "annual", expandInputPeriods: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/models?model=dcf%2Cdupont&expand=input_periods&dupont_mode=annual",
      expect.objectContaining({ cache: "no-store" })
    );
  });
});

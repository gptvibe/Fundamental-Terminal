import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyCapitalStructure,
  getCompanyChangesSinceLastFiling,
  getCompaniesCompare,
  getCompanyEarningsWorkspace,
  getCompanyFinancials,
  getCompanyFinancialRestatements,
  getCompanyFilingInsights,
  getCompanyFilings,
  getCompanyMarketContext,
  getLatestModelEvaluation,
  getCompanyModels,
  getCompanyPeers,
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
      "/backend/api/model-evaluations/latest",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/capital-structure",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
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

  it("serializes point-in-time query params for research helpers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFinancials("AAPL", { asOf: "2025-02-01" });
    await getCompanyCapitalStructure("AAPL", { maxPeriods: 6, asOf: "2025-02-01" });
    await getCompanyChangesSinceLastFiling("AAPL", { asOf: "2025-02-01" });
    await getCompanyFinancialRestatements("AAPL", { asOf: "2025-02-01" });
    await getCompanyModels("AAPL", ["dcf"], { dupontMode: "ttm", asOf: "2025-02-01" });
    await getCompanyPeers("AAPL", ["MSFT", "NVDA"], { asOf: "2025-02-01" });
    await getCompaniesCompare(["AAPL", "MSFT"], { asOf: "2025-02-01" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/financials?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/capital-structure?max_periods=6&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/changes-since-last-filing?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AAPL/financial-restatements?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/models?model=dcf&dupont_mode=ttm&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/backend/api/companies/compare?tickers=AAPL%2CMSFT&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
  });
});

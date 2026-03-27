import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyEarningsWorkspace,
  getCompanyFilingInsights,
  getCompanyFilings,
  getCompanyMarketContext,
  getCompanyPeers,
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
    await getCompanyPeers("AAPL", ["MSFT", "NVDA"]);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/earnings/workspace",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/MSFT/filings",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/NVDA/filing-insights",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AMD/market-context",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA",
      expect.objectContaining({ cache: "force-cache" })
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
});

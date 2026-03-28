import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyCapitalStructure,
  getCompanyChangesSinceLastFiling,
  getCompanyEarningsWorkspace,
  getCompanyFinancials,
  getCompanyFinancialRestatements,
  getCompanyFilingInsights,
  getCompanyFilings,
  getCompanyMarketContext,
  getCompanyModels,
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
    await getCompanyCapitalStructure("AAPL");
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
      "/backend/api/companies/AAPL/capital-structure",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
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

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/financials?as_of=2025-02-01",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/capital-structure?max_periods=6&as_of=2025-02-01",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/changes-since-last-filing?as_of=2025-02-01",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AAPL/financial-restatements?as_of=2025-02-01",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/models?model=dcf&dupont_mode=ttm&as_of=2025-02-01",
      expect.objectContaining({ cache: "force-cache" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA&as_of=2025-02-01",
      expect.objectContaining({ cache: "force-cache" })
    );
  });
});

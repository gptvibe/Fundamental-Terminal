import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
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
      expect.objectContaining({ cache: "force-cache" })
    );
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

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyFinancials,
  setApiAuthHeadersProvider,
} from "@/lib/api";

describe("api auth headers provider", () => {
  afterEach(async () => {
    await __resetApiClientCacheForTests();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("applies provider headers to backend requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);
    setApiAuthHeadersProvider(() => ({
      Authorization: "Bearer test-token",
      "X-Forwarded-User": "operator@example.com",
    }));

    await getCompanyFinancials("AAPL");

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/financials",
      expect.objectContaining({
        headers: expect.objectContaining({
          authorization: "Bearer test-token",
          "x-forwarded-user": "operator@example.com",
          "content-type": "application/json",
        }),
      }),
    );
  });

  it("clears provider state through the test reset helper", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);
    setApiAuthHeadersProvider(() => ({
      Authorization: "Bearer test-token",
    }));

    await __resetApiClientCacheForTests();
    await getCompanyFinancials("AAPL", { signal: undefined });

    const firstCallHeaders = fetchMock.mock.calls[0]?.[1]?.headers;
    expect(firstCallHeaders).not.toHaveProperty("Authorization");
  });
});

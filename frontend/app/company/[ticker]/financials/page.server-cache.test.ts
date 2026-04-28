import { beforeEach, describe, expect, it, vi } from "vitest";

import CompanyFinancialsPage from "@/app/company/[ticker]/financials/page";
import { FINANCIALS_ROUTE_REVALIDATE_SECONDS } from "@/app/company/[ticker]/financials/financials-route-data";

const headerFixture = vi.hoisted(() => ({
  host: "localhost:3000",
  protocol: "http",
}));

vi.mock("next/headers", () => ({
  headers: () => ({
    get: (key: string) => {
      if (key === "x-forwarded-host" || key === "host") {
        return headerFixture.host;
      }
      if (key === "x-forwarded-proto") {
        return headerFixture.protocol;
      }
      return null;
    },
  }),
}));

vi.mock("./financials-client-page", () => ({
  default: () => null,
}));

function buildBootstrapPayload() {
  return {
    financials: {
      company: {
        ticker: "ACME",
        name: "Acme Corp",
        cache_state: "fresh",
      },
      financials: [],
      price_history: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: null,
    },
    brief: null,
    earnings_summary: null,
    insider_trades: null,
    institutional_holdings: null,
    errors: { insider: null, institutional: null, earnings_summary: null },
  };
}

describe("financials server page caching", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("uses Next revalidate and cache tags instead of no-store", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => buildBootstrapPayload(),
    });
    vi.stubGlobal("fetch", fetchMock);

    await CompanyFinancialsPage({ params: { ticker: "acme" } });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:3000/backend/api/companies/ACME/workspace-bootstrap?financials_view=core_segments&include_earnings_summary=true",
      expect.objectContaining({
        headers: { Accept: "application/json" },
        next: expect.objectContaining({
          revalidate: FINANCIALS_ROUTE_REVALIDATE_SECONDS,
          tags: expect.arrayContaining([
            "company-workspace:ACME",
            "company-workspace:ACME:latest",
            "company-workspace:ACME:financials",
          ]),
        }),
      })
    );

    const init = fetchMock.mock.calls[0]?.[1] as { cache?: string };
    expect(init.cache).toBeUndefined();
  });
});

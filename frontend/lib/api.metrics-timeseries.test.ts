import { afterEach, describe, expect, it, vi } from "vitest";

import { getCompanyMetricsTimeseries } from "@/lib/api";

describe("getCompanyMetricsTimeseries", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends cadence and max_points query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        company: null,
        series: [],
        last_financials_check: null,
        last_price_check: null,
        staleness_reason: "company_missing",
        refresh: { triggered: true, reason: "missing", ticker: "AAPL", job_id: "job-1" },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyMetricsTimeseries("AAPL", { cadence: "ttm", maxPoints: 12 });

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/metrics-timeseries?cadence=ttm&max_points=12",
      expect.objectContaining({ cache: "no-store" })
    );
  });
});

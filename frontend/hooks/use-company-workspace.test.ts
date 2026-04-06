// @vitest-environment jsdom

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import {
  getCompanyFinancials,
  getCompanyInsiderTrades,
  getCompanyInstitutionalHoldings,
  invalidateApiReadCacheForTicker,
} from "@/lib/api";

const mockUseJobStream = vi.fn();

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: (...args: unknown[]) => mockUseJobStream(...args),
}));

vi.mock("@/lib/active-job", () => ({
  rememberActiveJob: vi.fn(),
}));

vi.mock("@/lib/recent-companies", () => ({
  recordRecentCompany: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFinancials: vi.fn(),
  getCompanyInsiderTrades: vi.fn(),
  getCompanyInstitutionalHoldings: vi.fn(),
  invalidateApiReadCacheForTicker: vi.fn(),
  refreshCompany: vi.fn(),
}));

function buildFinancialsResponse(overrides: Record<string, unknown> = {}) {
  return {
    company: null,
    financials: [],
    price_history: [],
    refresh: { triggered: true, reason: "missing", ticker: "RKLB", job_id: "job-rklb" },
    diagnostics: null,
    ...overrides,
  };
}

describe("useCompanyWorkspace", () => {
  beforeEach(() => {
    mockUseJobStream.mockReturnValue({
      consoleEntries: [],
      connectionState: "open",
      lastEvent: null,
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("invalidates ticker read cache before reloading after a terminal job event", async () => {
    const fetchFinancials = vi.mocked(getCompanyFinancials);
    const fetchInsiders = vi.mocked(getCompanyInsiderTrades);
    const fetchHoldings = vi.mocked(getCompanyInstitutionalHoldings);
    const invalidateTickerCache = vi.mocked(invalidateApiReadCacheForTicker);

    fetchFinancials
      .mockResolvedValueOnce(
        buildFinancialsResponse({
          refresh: { triggered: true, reason: "missing", ticker: "RKLB", job_id: "job-rklb" },
        }) as never
      )
      .mockResolvedValue(
        buildFinancialsResponse({
          company: {
            ticker: "RKLB",
            name: "Rocket Lab Corp",
            sector: "Space",
            market_sector: "Space",
            last_checked: "2026-03-31T00:00:00Z",
            cache_state: "fresh",
          },
          financials: [
            {
              filing_type: "10-K",
              period_end: "2025-12-31",
              revenue: 601800000,
              eps: null,
              free_cash_flow: -321810000,
            },
          ],
          refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
        }) as never
      );

    fetchInsiders.mockResolvedValue({ company: null, insider_trades: [], refresh: { triggered: false, reason: "none", ticker: "RKLB", job_id: null } } as never);
    fetchHoldings.mockResolvedValue({ company: null, institutional_holdings: [], refresh: { triggered: false, reason: "none", ticker: "RKLB", job_id: null } } as never);

    const { result, rerender } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeInsiders: true,
        includeInstitutional: true,
      })
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.activeJobId).toBe("job-rklb");

    mockUseJobStream.mockReturnValue({
      consoleEntries: [],
      connectionState: "closed",
      lastEvent: {
        job_id: "job-rklb",
        trace_id: "trace-rklb",
        sequence: 2,
        timestamp: "2026-03-31T00:00:01Z",
        ticker: "RKLB",
        kind: "refresh",
        stage: "complete",
        message: "Refresh completed",
        status: "completed",
        level: "success",
      },
    });

    await act(async () => {
      rerender();
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(fetchFinancials).toHaveBeenCalledTimes(2);
    });

    expect(invalidateTickerCache).toHaveBeenCalledWith("RKLB");
    expect(invalidateTickerCache.mock.invocationCallOrder[0]).toBeLessThan(fetchFinancials.mock.invocationCallOrder[1]);
  });
});
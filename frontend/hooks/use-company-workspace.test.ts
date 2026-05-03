// @vitest-environment jsdom

import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as React from "react";

import { CompanyLayoutProvider } from "@/components/layout/company-layout-context";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import {
  getCompanyWorkspaceBootstrap,
  getCompanyFinancials,
  getCompanyOverview,
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
  getCompanyWorkspaceBootstrap: vi.fn(),
  getCompanyOverview: vi.fn(),
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

function buildResearchBriefResponse(overrides: Record<string, unknown> = {}) {
  return {
    company: { ticker: "RKLB", name: "Rocket Lab Corp", cache_state: "fresh" },
    schema_version: "company_research_brief_v1",
    generated_at: "2026-03-31T00:00:00Z",
    as_of: "2025-12-31",
    refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
    build_state: "ready",
    build_status: "Research brief ready.",
    available_sections: ["snapshot", "what_changed", "business_quality", "capital_and_risk", "valuation"],
    section_statuses: [],
    filing_timeline: [],
    stale_summary_cards: [],
    snapshot: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
    what_changed: {
      activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      changes: { company: null, current_filing: null, previous_filing: null, summary: {}, metric_deltas: [], new_risk_indicators: [], segment_shifts: [], share_count_changes: [], capital_structure_changes: [], amended_prior_values: [], high_signal_changes: [], comment_letter_history: { total_letters: 0, recent_letters: [] }, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      earnings_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null },
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: null,
      confidence_flags: [],
    },
    business_quality: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
    capital_and_risk: {
      capital_structure: { company: null, latest: null, history: [], last_capital_structure_check: null, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      capital_markets_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null },
      governance_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null },
      ownership_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null },
      equity_claim_risk_summary: {},
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: null,
      confidence_flags: [],
    },
    valuation: {
      models: { company: null, requested_models: [], models: [], refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      peers: { company: null, peer_basis: "Cached peer universe", available_companies: [], selected_tickers: [], peers: [], notes: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: null,
      confidence_flags: [],
    },
    monitor: {
      activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: null,
      confidence_flags: [],
    },
    ...overrides,
  };
}

function buildApiError(status: number, statusText = "Error") {
  return new Error(`API request failed: ${status} ${statusText}`);
}

function buildAbortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

function WorkspaceProbe({
  ticker,
  mode,
}: {
  ticker: string;
  mode: "overview" | "peers";
}) {
  const workspace = useCompanyWorkspace(ticker, mode === "overview" ? { includeOverviewBrief: true } : {});
  const phase = workspace.loading && !workspace.company && workspace.financials.length === 0
    ? "skeleton"
    : workspace.updating
      ? "updating"
      : "ready";

  return React.createElement(
    "div",
    { "data-testid": "workspace-phase" },
    `${mode}:${phase}:${workspace.company?.ticker ?? "none"}:${workspace.financials.length}`
  );
}

function WorkspaceHost({ mode }: { mode: "overview" | "peers" }) {
  return React.createElement(
    CompanyLayoutProvider,
    null,
    React.createElement(WorkspaceProbe, { key: mode, ticker: "RKLB", mode })
  );
}

describe("useCompanyWorkspace", () => {
  beforeEach(() => {
    mockUseJobStream.mockReturnValue({
      consoleEntries: [],
      connectionState: "open",
      lastEvent: null,
    });
    // Default: simulate a deployment that does not yet have the bootstrap
    // endpoint (501 Not Implemented) so that legacy-path tests work without
    // explicitly mocking bootstrap.
    vi.mocked(getCompanyWorkspaceBootstrap).mockRejectedValue(buildApiError(501, "Not Implemented"));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("uses the bootstrap payload for the overview workspace", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockResolvedValue({
      company: { ticker: "RKLB", name: "Rocket Lab Corp", cache_state: "fresh" },
      financials: buildFinancialsResponse({
        company: {
          ticker: "RKLB",
          name: "Rocket Lab Corp",
          sector: "Space",
          market_sector: "Space",
          last_checked: "2026-03-31T00:00:00Z",
          cache_state: "fresh",
        },
        refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
      }),
      brief: buildResearchBriefResponse(),
      earnings_summary: null,
      insider_trades: null,
      institutional_holdings: null,
      errors: { insider: null, institutional: null, earnings_summary: null },
    } as never);

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchBootstrap).toHaveBeenCalledWith(
      "RKLB",
      expect.objectContaining({
        financialsView: "core_segments",
        includeOverviewBrief: true,
        includeInsiders: false,
        includeInstitutional: false,
        includeEarningsSummary: false,
        signal: expect.anything(),
      })
    );
    expect(fetchOverview).not.toHaveBeenCalled();
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.briefData?.company?.ticker).toBe("RKLB");
  });

  it("falls back to overview for expected bootstrap compatibility errors", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));
    fetchOverview.mockResolvedValue({
      financials: buildFinancialsResponse({
        company: {
          ticker: "RKLB",
          name: "Rocket Lab Corp",
          sector: "Space",
          market_sector: "Space",
          last_checked: "2026-03-31T00:00:00Z",
          cache_state: "fresh",
        },
      }),
      brief: buildResearchBriefResponse(),
    } as never);

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchOverview).toHaveBeenCalledWith("RKLB", expect.objectContaining({ financialsView: "core_segments", signal: expect.anything() }));
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.error).toBeNull();
    expect(result.current.briefData?.company?.ticker).toBe("RKLB");
  });

  it("surfaces an error for 404 on bootstrap instead of silently falling back", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(buildApiError(404, "Not Found"));

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchOverview).not.toHaveBeenCalled();
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.error).toBe("API request failed: 404 Not Found");
  });

  it("surfaces an error for 404 on legacy overview instead of falling back to financials-only", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));
    fetchOverview.mockRejectedValue(buildApiError(404, "Not Found"));

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchOverview).toHaveBeenCalled();
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.error).toBe("API request failed: 404 Not Found");
  });

  it("does not fall back on transient bootstrap backend errors", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(buildApiError(500, "Internal Server Error"));

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchOverview).not.toHaveBeenCalled();
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.error).toBe("API request failed: 500 Internal Server Error");
  });

  it("does not fall back on bootstrap timeout or network errors", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(new Error("net::ERR_TIMED_OUT"));

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchOverview).not.toHaveBeenCalled();
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.error).toBe("net::ERR_TIMED_OUT");
  });

  it("falls back from overview to financials only for expected compatibility errors", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));
    fetchOverview.mockRejectedValue(buildApiError(405, "Method Not Allowed"));
    fetchFinancials.mockResolvedValue(
      buildFinancialsResponse({
        company: {
          ticker: "RKLB",
          name: "Rocket Lab Corp",
          sector: "Space",
          market_sector: "Space",
          last_checked: "2026-03-31T00:00:00Z",
          cache_state: "fresh",
        },
        refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
      }) as never
    );

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchOverview).toHaveBeenCalledWith("RKLB", expect.objectContaining({ financialsView: "core_segments", signal: expect.anything() }));
    expect(fetchFinancials).toHaveBeenCalledWith("RKLB", expect.objectContaining({ view: "core_segments", signal: expect.anything() }));
    expect(result.current.error).toBeNull();
    expect(result.current.briefData).toBeNull();
  });

  it("does not fall back from overview to financials on transient legacy errors", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const fetchOverview = vi.mocked(getCompanyOverview);
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));
    fetchOverview.mockRejectedValue(buildApiError(500, "Internal Server Error"));

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        includeOverviewBrief: true,
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.error).toBe("API request failed: 500 Internal Server Error");
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

  it("passes through a compact financials view when requested", async () => {
    const fetchFinancials = vi.mocked(getCompanyFinancials);

    fetchFinancials.mockResolvedValue(
      buildFinancialsResponse({
        company: {
          ticker: "RKLB",
          name: "Rocket Lab Corp",
          sector: "Space",
          market_sector: "Space",
          last_checked: "2026-03-31T00:00:00Z",
          cache_state: "fresh",
        },
        refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
      }) as never
    );

    const { result } = renderHook(() =>
      useCompanyWorkspace("RKLB", {
        financialsView: "core_segments",
      })
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchFinancials).toHaveBeenCalledWith("RKLB", expect.objectContaining({ view: "core_segments", signal: expect.anything() }));
  });

  it("keeps workspace data between tab remounts and avoids duplicate fresh-cache requests", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);

    fetchBootstrap.mockImplementation(async (_ticker, options) => {
      const overviewMode = Boolean(options?.includeOverviewBrief);
      return {
        company: { ticker: "RKLB", name: "Rocket Lab Corp", cache_state: "fresh" },
        financials: buildFinancialsResponse({
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
              period_end: overviewMode ? "2025-12-31" : "2025-09-30",
              revenue: overviewMode ? 601800000 : 582000000,
              eps: null,
              free_cash_flow: -321810000,
            },
          ],
          refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
        }),
        brief: overviewMode ? buildResearchBriefResponse() : null,
        earnings_summary: null,
        insider_trades: null,
        institutional_holdings: null,
        errors: { insider: null, institutional: null, earnings_summary: null },
      } as never;
    });

    const { rerender } = render(React.createElement(WorkspaceHost, { mode: "overview" }));

    await waitFor(() => {
      expect(screen.getByTestId("workspace-phase").textContent).toContain("overview:ready:RKLB:1");
    });

    rerender(React.createElement(WorkspaceHost, { mode: "peers" }));
    await waitFor(() => {
      expect(screen.getByTestId("workspace-phase").textContent).toContain("peers:ready:RKLB:1");
    });

    rerender(React.createElement(WorkspaceHost, { mode: "overview" }));

    expect(screen.getByTestId("workspace-phase").textContent).toContain("overview:ready:RKLB:1");
    expect(screen.getByTestId("workspace-phase").textContent).not.toContain("overview:skeleton");

    const overviewBootstrapCalls = fetchBootstrap.mock.calls.filter(([, options]) => Boolean(options?.includeOverviewBrief));
    const peersBootstrapCalls = fetchBootstrap.mock.calls.filter(([, options]) => !options?.includeOverviewBrief);
    expect(overviewBootstrapCalls).toHaveLength(1);
    expect(peersBootstrapCalls).toHaveLength(1);
  });

  it("aborts the prior workspace request bundle when ticker changes", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    let firstSignal: AbortSignal | undefined;

    fetchBootstrap
      .mockImplementationOnce((_ticker, options) => {
        firstSignal = options?.signal;
        return new Promise((_resolve, reject) => {
          options?.signal?.addEventListener(
            "abort",
            () => {
              reject(buildAbortError());
            },
            { once: true }
          );
        }) as never;
      })
      .mockResolvedValueOnce({
        company: { ticker: "AAPL", name: "Apple Inc.", cache_state: "fresh" },
        financials: buildFinancialsResponse({
          company: {
            ticker: "AAPL",
            name: "Apple Inc.",
            sector: "Technology",
            market_sector: "Technology",
            last_checked: "2026-03-31T00:00:00Z",
            cache_state: "fresh",
          },
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
        }),
        brief: null,
        earnings_summary: null,
        insider_trades: null,
        institutional_holdings: null,
        errors: { insider: null, institutional: null, earnings_summary: null },
      } as never);

    const { result, rerender } = renderHook(
      ({ ticker }) => useCompanyWorkspace(ticker),
      { initialProps: { ticker: "RKLB" } }
    );

    await act(async () => {
      rerender({ ticker: "AAPL" });
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(firstSignal?.aborted).toBe(true);
    expect(result.current.error).toBeNull();
    expect(result.current.company?.ticker).toBe("AAPL");
  });

  describe("Partial Failures - Optional Data", () => {
    it("handles insider trades fetch failure while keeping core data", async () => {
      const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      const fetchFinancials = vi.mocked(getCompanyFinancials);
      const fetchInsiders = vi.mocked(getCompanyInsiderTrades);

      // Bootstrap fails with 501, falling back to legacy path
      fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));

      // Financials succeed
      fetchFinancials.mockResolvedValue(
        buildFinancialsResponse({
          company: {
            ticker: "RKLB",
            name: "Rocket Lab Corp",
            sector: "Space",
            market_sector: "Space",
            last_checked: "2026-03-31T00:00:00Z",
            cache_state: "fresh",
          },
          refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
        }) as never
      );

      // Insider trades fail
      fetchInsiders.mockRejectedValue(new Error("API request failed: 503 Service Unavailable"));

      const { result } = renderHook(() =>
        useCompanyWorkspace("RKLB", {
          includeInsiders: true,
        })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Core workspace should still load successfully
      expect(result.current.company?.ticker).toBe("RKLB");
      expect(result.current.financials.length).toBeGreaterThanOrEqual(0);
      // Insider data should have error but not block the entire workspace
      expect(result.current.insiderError).toBeDefined();
      expect(result.current.insiderError).toMatch(/API request failed: 503/);
      // Main error should be null since core data loaded
      expect(result.current.error).toBeNull();
    });

    it("handles institutional holdings fetch failure while keeping core data", async () => {
      const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      const fetchFinancials = vi.mocked(getCompanyFinancials);
      const fetchHoldings = vi.mocked(getCompanyInstitutionalHoldings);

      fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));
      fetchFinancials.mockResolvedValue(
        buildFinancialsResponse({
          company: {
            ticker: "RKLB",
            name: "Rocket Lab Corp",
            sector: "Space",
            market_sector: "Space",
            last_checked: "2026-03-31T00:00:00Z",
            cache_state: "fresh",
          },
          refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
        }) as never
      );

      fetchHoldings.mockRejectedValue(new Error("API request failed: 502 Bad Gateway"));

      const { result } = renderHook(() =>
        useCompanyWorkspace("RKLB", {
          includeInstitutional: true,
        })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Core workspace should still load successfully
      expect(result.current.company?.ticker).toBe("RKLB");
      expect(result.current.financials.length).toBeGreaterThanOrEqual(0);
      // Institutional data should have error but not block the entire workspace
      expect(result.current.institutionalError).toBeDefined();
      expect(result.current.institutionalError).toMatch(/API request failed: 502/);
      // Main error should be null since core data loaded
      expect(result.current.error).toBeNull();
    });

    it("handles multiple optional data failures independently", async () => {
      const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      const fetchFinancials = vi.mocked(getCompanyFinancials);
      const fetchInsiders = vi.mocked(getCompanyInsiderTrades);
      const fetchHoldings = vi.mocked(getCompanyInstitutionalHoldings);

      fetchBootstrap.mockRejectedValue(buildApiError(501, "Not Implemented"));
      fetchFinancials.mockResolvedValue(
        buildFinancialsResponse({
          company: {
            ticker: "RKLB",
            name: "Rocket Lab Corp",
            sector: "Space",
            market_sector: "Space",
            last_checked: "2026-03-31T00:00:00Z",
            cache_state: "fresh",
          },
          refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
        }) as never
      );

      fetchInsiders.mockRejectedValue(new Error("Insider data unavailable"));
      fetchHoldings.mockRejectedValue(new Error("Holdings data unavailable"));

      const { result } = renderHook(() =>
        useCompanyWorkspace("RKLB", {
          includeInsiders: true,
          includeInstitutional: true,
        })
      );

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // Core workspace should still load
      expect(result.current.company?.ticker).toBe("RKLB");
      expect(result.current.financials.length).toBeGreaterThanOrEqual(0);
      // Both optional fields should have errors
      expect(result.current.insiderError).toBeDefined();
      expect(result.current.insiderError).toMatch(/Insider data unavailable/);
      expect(result.current.institutionalError).toBeDefined();
      expect(result.current.institutionalError).toMatch(/Holdings data unavailable/);
      // Main error should be null since core data loaded
      expect(result.current.error).toBeNull();
    });
  });
});

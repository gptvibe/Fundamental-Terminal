// @vitest-environment jsdom

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

describe("useCompanyWorkspace", () => {
  beforeEach(() => {
    mockUseJobStream.mockReturnValue({
      consoleEntries: [],
      connectionState: "open",
      lastEvent: null,
    });
    vi.mocked(getCompanyWorkspaceBootstrap).mockRejectedValue(new Error("bootstrap unavailable"));
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

    expect(fetchBootstrap).toHaveBeenCalledWith("RKLB", {
      financialsView: "core_segments",
      includeOverviewBrief: true,
      includeInsiders: false,
      includeInstitutional: false,
      includeEarningsSummary: false,
    });
    expect(fetchOverview).not.toHaveBeenCalled();
    expect(fetchFinancials).not.toHaveBeenCalled();
    expect(result.current.briefData?.company?.ticker).toBe("RKLB");
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

    expect(fetchFinancials).toHaveBeenCalledWith("RKLB", { view: "core_segments" });
  });
});

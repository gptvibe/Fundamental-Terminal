// @vitest-environment jsdom

import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { useResearchBriefData } from "./use-research-brief-data";

const mockGetCompanyResearchBrief = vi.fn();
const mockGetCompanyActivityOverview = vi.fn();
const mockGetCompanyChangesSinceLastFiling = vi.fn();
const mockGetCompanyEarningsSummary = vi.fn();
const mockGetCompanyCapitalStructure = vi.fn();
const mockGetCompanyCapitalMarketsSummary = vi.fn();
const mockGetCompanyGovernanceSummary = vi.fn();
const mockGetCompanyBeneficialOwnershipSummary = vi.fn();
const mockGetCompanyModels = vi.fn();
const mockGetCompanyPeers = vi.fn();

vi.mock("@/lib/api", () => ({
  getCompanyResearchBrief: (...args: unknown[]) => mockGetCompanyResearchBrief(...args),
  getCompanyActivityOverview: (...args: unknown[]) => mockGetCompanyActivityOverview(...args),
  getCompanyChangesSinceLastFiling: (...args: unknown[]) => mockGetCompanyChangesSinceLastFiling(...args),
  getCompanyEarningsSummary: (...args: unknown[]) => mockGetCompanyEarningsSummary(...args),
  getCompanyCapitalStructure: (...args: unknown[]) => mockGetCompanyCapitalStructure(...args),
  getCompanyCapitalMarketsSummary: (...args: unknown[]) => mockGetCompanyCapitalMarketsSummary(...args),
  getCompanyGovernanceSummary: (...args: unknown[]) => mockGetCompanyGovernanceSummary(...args),
  getCompanyBeneficialOwnershipSummary: (...args: unknown[]) => mockGetCompanyBeneficialOwnershipSummary(...args),
  getCompanyModels: (...args: unknown[]) => mockGetCompanyModels(...args),
  getCompanyPeers: (...args: unknown[]) => mockGetCompanyPeers(...args),
}));

vi.mock("@/lib/performance-audit", () => ({
  withPerformanceAuditSource: async (_context: unknown, work: () => Promise<unknown>) => work(),
}));

function buildPartialBrief() {
  return {
    company: { ticker: "RKLB", name: "Rocket Lab Corp", cache_state: "fresh" },
    schema_version: "company_research_brief_v1",
    generated_at: "2026-03-31T00:00:00Z",
    as_of: null,
    refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
    build_state: "partial",
    build_status: "Research brief warming.",
    available_sections: ["snapshot", "what_changed"],
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
  };
}

describe("useResearchBriefData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal(
      "requestIdleCallback",
      (callback: IdleRequestCallback) => window.setTimeout(() => callback({ didTimeout: false, timeRemaining: () => 50 } as IdleDeadline), 0)
    );
    vi.stubGlobal("cancelIdleCallback", (handle: number) => window.clearTimeout(handle));
    mockGetCompanyResearchBrief.mockRejectedValue(new Error("brief unavailable"));
    mockGetCompanyActivityOverview.mockResolvedValue({ company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] });
    mockGetCompanyCapitalStructure.mockResolvedValue({ company: null, latest: null, history: [], last_capital_structure_check: null, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] });
    mockGetCompanyCapitalMarketsSummary.mockResolvedValue({ company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null });
    mockGetCompanyGovernanceSummary.mockResolvedValue({ company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null });
    mockGetCompanyBeneficialOwnershipSummary.mockResolvedValue({ company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, error: null });
    mockGetCompanyModels.mockResolvedValue({ company: null, requested_models: [], models: [], refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] });
    mockGetCompanyPeers.mockResolvedValue({ company: null, peer_basis: "Cached peer universe", available_companies: [], selected_tickers: [], peers: [], notes: {}, refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] });
  });

  it("fetches only missing section slices when the brief endpoint fails", async () => {
    const initialBrief = buildPartialBrief();

    const { result } = renderHook(() =>
      useResearchBriefData("RKLB", "reload-1", 0, initialBrief as never, false, null, null)
    );

    await waitFor(() => {
      expect(result.current.capitalStructure.loading).toBe(false);
      expect(result.current.models.loading).toBe(false);
    });

    expect(mockGetCompanyResearchBrief).toHaveBeenCalledTimes(1);
  expect(mockGetCompanyActivityOverview).toHaveBeenCalledTimes(1);
    expect(mockGetCompanyChangesSinceLastFiling).not.toHaveBeenCalled();
    expect(mockGetCompanyEarningsSummary).not.toHaveBeenCalled();
    expect(mockGetCompanyCapitalStructure).toHaveBeenCalledTimes(1);
    expect(mockGetCompanyCapitalMarketsSummary).toHaveBeenCalledTimes(1);
    expect(mockGetCompanyGovernanceSummary).toHaveBeenCalledTimes(1);
    expect(mockGetCompanyBeneficialOwnershipSummary).toHaveBeenCalledTimes(1);
    expect(mockGetCompanyModels).toHaveBeenCalledTimes(1);
    expect(mockGetCompanyPeers).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe("brief unavailable");
    expect(result.current.buildState).toBe("partial");
  });
});
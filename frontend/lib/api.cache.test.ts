// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyChangesSinceLastFiling,
  getCompanyFinancials,
  getCompanyOverview,
  getCompanyResearchBrief,
  invalidateApiReadCacheForTicker,
  refreshCompany,
} from "@/lib/api";

describe("api read cache", () => {
  beforeEach(async () => {
    await __resetApiClientCacheForTests();
  });

  afterEach(async () => {
    await __resetApiClientCacheForTests();
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
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("uses response.json in success path even when performance audit is enabled", async () => {
    const previousAuditFlag = process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED;
    process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED = "true";

    try {
      const responseJson = vi.fn().mockResolvedValue({
        company: null,
        financials: [],
        price_history: [],
        refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
      });
      const responseText = vi.fn().mockResolvedValue("{}");
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers([["content-length", "128"]]),
        json: responseJson,
        text: responseText,
      });

      vi.stubGlobal("fetch", fetchMock);

      await getCompanyFinancials("AAPL");

      expect(responseJson).toHaveBeenCalledTimes(1);
      expect(responseText).not.toHaveBeenCalled();
    } finally {
      if (previousAuditFlag == null) {
        delete process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED;
      } else {
        process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED = previousAuditFlag;
      }
    }
  });

  it("returns the same promise for concurrent reads to the same URL", async () => {
    let resolveFetch: ((value: unknown) => void) | null = null;
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        })
    );

    vi.stubGlobal("fetch", fetchMock);

    const firstRequest = getCompanyChangesSinceLastFiling("AAPL");
    const secondRequest = getCompanyChangesSinceLastFiling("AAPL");

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/changes-since-last-filing",
      expect.objectContaining({ cache: "no-store" })
    );

    resolveFetch?.({
      ok: true,
      json: async () => ({
        company: null,
        current_filing: null,
        previous_filing: null,
        summary: {},
        metric_deltas: [],
        new_risk_indicators: [],
        segment_shifts: [],
        share_count_changes: [],
        capital_structure_changes: [],
        amended_prior_values: [],
        high_signal_changes: [],
        comment_letter_history: { total_letters: 0, recent_letters: [] },
        refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
        diagnostics: null,
        provenance: [],
        source_mix: null,
        confidence_flags: [],
        as_of: null,
        last_refreshed_at: null,
      }),
    });

    const [firstResult, secondResult] = await Promise.all([firstRequest, secondRequest]);

    expect(firstResult).toEqual(secondResult);
  });

  it("dedupes repeated aggregate overview reads", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        company: null,
        financials: {
          company: null,
          financials: [],
          price_history: [],
          refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
          diagnostics: null,
        },
        brief: {
          company: null,
          schema_version: "company_research_brief_v1",
          generated_at: "2026-04-12T00:00:00Z",
          as_of: null,
          refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
          build_state: "ready",
          build_status: "Research brief ready.",
          available_sections: [],
          section_statuses: [],
          filing_timeline: [],
          stale_summary_cards: [],
          snapshot: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          what_changed: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, changes: { company: null, current_filing: null, previous_filing: null, summary: {}, metric_deltas: [], new_risk_indicators: [], segment_shifts: [], share_count_changes: [], capital_structure_changes: [], amended_prior_values: [], high_signal_changes: [], comment_letter_history: { total_letters: 0, recent_letters: [] }, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, earnings_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          business_quality: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          capital_and_risk: { capital_structure: { company: null, latest: null, history: [], last_capital_structure_check: null, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, capital_markets_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, governance_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, ownership_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, equity_claim_risk_summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          valuation: { models: { company: null, requested_models: [], models: [], refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, peers: { company: null, peer_basis: "Cached peer universe", available_companies: [], selected_tickers: [], peers: [], notes: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          monitor: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyOverview("AAPL");
    await getCompanyOverview("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/overview",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("reuses overview financials for later direct financials reads", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        company: null,
        financials: {
          company: { ticker: "AAPL", name: "Apple Inc.", cache_state: "fresh" },
          financials: [],
          price_history: [],
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          diagnostics: null,
        },
        brief: {
          company: null,
          schema_version: "company_research_brief_v1",
          generated_at: "2026-04-12T00:00:00Z",
          as_of: null,
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          build_state: "ready",
          build_status: "Research brief ready.",
          available_sections: [],
          section_statuses: [],
          filing_timeline: [],
          stale_summary_cards: [],
          snapshot: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          what_changed: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, changes: { company: null, current_filing: null, previous_filing: null, summary: {}, metric_deltas: [], new_risk_indicators: [], segment_shifts: [], share_count_changes: [], capital_structure_changes: [], amended_prior_values: [], high_signal_changes: [], comment_letter_history: { total_letters: 0, recent_letters: [] }, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, earnings_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          business_quality: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          capital_and_risk: { capital_structure: { company: null, latest: null, history: [], last_capital_structure_check: null, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, capital_markets_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, governance_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, ownership_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, equity_claim_risk_summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          valuation: { models: { company: null, requested_models: [], models: [], refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, peers: { company: null, peer_basis: "Cached peer universe", available_companies: [], selected_tickers: [], peers: [], notes: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          monitor: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyOverview("AAPL");
    const financials = await getCompanyFinancials("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(financials.company?.ticker).toBe("AAPL");
  });

  it("clears overview-primed financials when ticker cache is invalidated", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          company: null,
          financials: {
            company: { ticker: "AAPL", name: "Apple Inc.", cache_state: "fresh" },
            financials: [],
            price_history: [],
            refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
            diagnostics: null,
          },
          brief: {
            company: null,
            schema_version: "company_research_brief_v1",
            generated_at: "2026-04-12T00:00:00Z",
            as_of: null,
            refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
            build_state: "ready",
            build_status: "Research brief ready.",
            available_sections: [],
            section_statuses: [],
            filing_timeline: [],
            stale_summary_cards: [],
            snapshot: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
            what_changed: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, changes: { company: null, current_filing: null, previous_filing: null, summary: {}, metric_deltas: [], new_risk_indicators: [], segment_shifts: [], share_count_changes: [], capital_structure_changes: [], amended_prior_values: [], high_signal_changes: [], comment_letter_history: { total_letters: 0, recent_letters: [] }, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, earnings_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
            business_quality: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
            capital_and_risk: { capital_structure: { company: null, latest: null, history: [], last_capital_structure_check: null, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, capital_markets_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, governance_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, ownership_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, equity_claim_risk_summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
            valuation: { models: { company: null, requested_models: [], models: [], refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, peers: { company: null, peer_basis: "Cached peer universe", available_companies: [], selected_tickers: [], peers: [], notes: {}, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
            monitor: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
          },
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          company: { ticker: "AAPL", name: "Apple Inc.", cache_state: "fresh" },
          financials: [],
          price_history: [],
          refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
          diagnostics: null,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyOverview("AAPL");
    invalidateApiReadCacheForTicker("AAPL");
    await getCompanyFinancials("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/financials",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("clears the in-flight entry when a request rejects", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Server Error",
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          company: null,
          current_filing: null,
          previous_filing: null,
          summary: {},
          metric_deltas: [],
          new_risk_indicators: [],
          segment_shifts: [],
          share_count_changes: [],
          capital_structure_changes: [],
          amended_prior_values: [],
          high_signal_changes: [],
          comment_letter_history: { total_letters: 0, recent_letters: [] },
          refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
          diagnostics: null,
          provenance: [],
          source_mix: null,
          confidence_flags: [],
          as_of: null,
          last_refreshed_at: null,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    const firstRequest = getCompanyChangesSinceLastFiling("AAPL");
    const secondRequest = getCompanyChangesSinceLastFiling("AAPL");
    const settledRequests = Promise.allSettled([firstRequest, secondRequest]);

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const [firstError, secondError] = await settledRequests;

    expect(firstError.status).toBe("rejected");
    expect(secondError.status).toBe("rejected");
    expect(firstError.status === "rejected" ? firstError.reason.message : null).toBe("API request failed: 500 Server Error");
    expect(secondError.status === "rejected" ? secondError.reason.message : null).toBe("API request failed: 500 Server Error");

    const retryResult = await getCompanyChangesSinceLastFiling("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(retryResult.refresh.ticker).toBe("AAPL");
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

  it("ignores legacy localStorage payload entries and does not persist new payloads to localStorage", async () => {
    window.localStorage.setItem(
      "ft:api-cache:v3:/companies/AAPL/brief",
      JSON.stringify({
        data: {
          company: null,
          generated_at: "2026-04-16T00:00:00Z",
        },
        updatedAt: Date.now(),
      })
    );

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        company: null,
        schema_version: "company_research_brief_v1",
        generated_at: "2026-04-16T00:00:00Z",
        as_of: null,
        refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
        build_state: "ready",
        build_status: "Research brief ready.",
        available_sections: [],
        section_statuses: [],
        filing_timeline: [],
        stale_summary_cards: [],
        snapshot: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        what_changed: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, changes: { company: null, current_filing: null, previous_filing: null, summary: {}, metric_deltas: [], new_risk_indicators: [], segment_shifts: [], share_count_changes: [], capital_structure_changes: [], amended_prior_values: [], high_signal_changes: [], comment_letter_history: { total_letters: 0, recent_letters: [] }, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, earnings_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        business_quality: { summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        capital_and_risk: { capital_structure: { company: null, latest: null, history: [], last_capital_structure_check: null, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, capital_markets_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, governance_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, ownership_summary: { company: null, summary: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, error: null }, equity_claim_risk_summary: {}, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        valuation: { models: { company: null, requested_models: [], models: [], refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, diagnostics: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, peers: { company: null, peer_basis: "Cached peer universe", available_companies: [], selected_tickers: [], peers: [], notes: {}, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
        monitor: { activity_overview: { company: null, entries: [], alerts: [], summary: { total: 0, high: 0, medium: 0, low: 0 }, refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null }, error: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] }, provenance: [], as_of: null, last_refreshed_at: null, source_mix: null, confidence_flags: [] },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    const brief = await getCompanyResearchBrief("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(brief.schema_version).toBe("company_research_brief_v1");
    expect(window.localStorage.getItem("ft:api-cache:v4:/companies/AAPL/brief")).toBeNull();
  });
});

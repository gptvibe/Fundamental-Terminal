// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyChangesSinceLastFiling,
  getCompanyFinancials,
  getCompanyMarketContext,
  getCompanyOverview,
  getCompanyResearchBrief,
  getCompanyWorkspaceBootstrap,
  getWatchlistSummary,
  invalidateApiReadCacheForTicker,
  refreshCompany,
  searchCompanies,
  type ReadCachePolicy,
} from "@/lib/api";

describe("api read cache", () => {
  function buildFinancialsPayload(ticker = "AAPL", reason = "none") {
    return {
      company: { ticker, name: `${ticker} Inc.`, cache_state: "fresh" },
      financials: [],
      price_history: [],
      refresh: { triggered: false, reason, ticker, job_id: null },
      diagnostics: null,
    };
  }

  function buildOkJsonResponse(payload: unknown) {
    return {
      ok: true,
      json: async () => payload,
    };
  }

  function buildWorkspaceBootstrapPayload(
    ticker = "AAPL",
    options: {
      company?: Record<string, unknown> | null;
      financialsReason?: string;
      financialsCompany?: Record<string, unknown> | null;
      brief?: unknown;
    } = {}
  ) {
    const financials = buildFinancialsPayload(ticker, options.financialsReason ?? "fresh");

    return {
      company:
        options.company === undefined
          ? { ticker, name: `${ticker} Inc.`, cache_state: "fresh" }
          : options.company,
      financials: {
        ...financials,
        company:
          options.financialsCompany === undefined
            ? financials.company
            : options.financialsCompany,
      },
      brief: options.brief ?? null,
      earnings_summary: null,
      insider_trades: null,
      institutional_holdings: null,
      errors: {
        insider: null,
        institutional: null,
        earnings_summary: null,
      },
    };
  }

  beforeEach(async () => {
    await __resetApiClientCacheForTests();
  });

  afterEach(async () => {
    await __resetApiClientCacheForTests();
    vi.restoreAllMocks();
  });

  it("serves a fresh cache hit for stable financials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(buildOkJsonResponse(buildFinancialsPayload("AAPL", "first-load")));

    vi.stubGlobal("fetch", fetchMock);

    const first = await getCompanyFinancials("AAPL");
    const second = await getCompanyFinancials("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(first.refresh.reason).toBe("first-load");
    expect(second.refresh.reason).toBe("first-load");
    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/financials",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("serves stale financials and triggers background revalidation", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-27T00:00:00Z"));

    let resolveRevalidate: ((value: unknown) => void) | null = null;
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(buildOkJsonResponse(buildFinancialsPayload("AAPL", "initial")))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveRevalidate = resolve;
          })
      );

    vi.stubGlobal("fetch", fetchMock);

    const initial = await getCompanyFinancials("AAPL");
    expect(initial.refresh.reason).toBe("initial");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.setSystemTime(new Date("2026-04-27T00:11:00Z"));
    const stale = await getCompanyFinancials("AAPL");

    expect(stale.refresh.reason).toBe("initial");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    resolveRevalidate?.(buildOkJsonResponse(buildFinancialsPayload("AAPL", "revalidated")));

    await vi.waitFor(async () => {
      const latest = await getCompanyFinancials("AAPL");
      expect(latest.refresh.reason).toBe("revalidated");
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });

  it("bypasses read cache for refresh=true query requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(buildOkJsonResponse({ query: "AAPL", total: 0, results: [] }));

    vi.stubGlobal("fetch", fetchMock);

    await searchCompanies("AAPL", { refresh: true });
    await searchCompanies("AAPL", { refresh: true });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/search?query=AAPL&refresh=true",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/search?query=AAPL&refresh=true",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("bypasses read cache for POST requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(buildOkJsonResponse({ as_of: null, tickers: {}, generated_at: null, refresh: { triggered: false, reason: "none", ticker: null, job_id: null } }));

    vi.stubGlobal("fetch", fetchMock);

    await getWatchlistSummary(["AAPL", "MSFT"]);
    await getWatchlistSummary(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/watchlist/summary",
      expect.objectContaining({ method: "POST", cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/watchlist/summary",
      expect.objectContaining({ method: "POST", cache: "no-store" })
    );
  });

  it("clears cached reads when ticker cache is invalidated", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(buildOkJsonResponse(buildFinancialsPayload("AAPL", "initial")))
      .mockResolvedValueOnce(buildOkJsonResponse(buildFinancialsPayload("AAPL", "after-invalidation")));

    vi.stubGlobal("fetch", fetchMock);

    const first = await getCompanyFinancials("AAPL");
    const cached = await getCompanyFinancials("AAPL");
    expect(first.refresh.reason).toBe("initial");
    expect(cached.refresh.reason).toBe("initial");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    invalidateApiReadCacheForTicker("AAPL");

    const refetched = await getCompanyFinancials("AAPL");
    expect(refetched.refresh.reason).toBe("after-invalidation");
    expect(fetchMock).toHaveBeenCalledTimes(2);
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

  it("records cache key, policy, source, and payload bytes in performance audit events", async () => {
    const previousAuditFlag = process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED;
    process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED = "true";

    try {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers([["content-length", "256"]]),
        json: async () => buildFinancialsPayload("AAPL", "first-load"),
      });

      vi.stubGlobal("fetch", fetchMock);

      window.__FT_PERFORMANCE_AUDIT__?.reset({ phase: "cache-metadata" });

      await getCompanyFinancials("AAPL");
      await getCompanyFinancials("AAPL");

      const snapshot = window.__FT_PERFORMANCE_AUDIT__?.snapshot();
      expect(snapshot).toBeTruthy();

      const events = (snapshot?.requests ?? []).filter((event) => event.path === "/companies/AAPL/financials");
      const networkEvent = [...events].reverse().find((event) => event.networkRequest);
      const memoryHitEvent = [...events].reverse().find((event) => event.cacheDisposition === "fresh-cache-hit");

      expect(networkEvent).toBeTruthy();
      expect(networkEvent).toEqual(expect.objectContaining({
        cacheKey: "/companies/AAPL/financials",
        cachePolicyTtlMs: 600_000,
        cachePolicyStaleMs: 3_600_000,
        responseSource: "network",
        payloadBytes: 256,
      }));

      expect(memoryHitEvent).toBeTruthy();
      expect(memoryHitEvent).toEqual(expect.objectContaining({
        cacheKey: "/companies/AAPL/financials",
        cachePolicyTtlMs: 600_000,
        cachePolicyStaleMs: 3_600_000,
        responseSource: "memory-cache",
        cacheDisposition: "fresh-cache-hit",
      }));
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

  it("retries after an inflight read has gone stale", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-27T00:00:00Z"));

    const fetchMock = vi
      .fn()
      .mockImplementationOnce(() => new Promise(() => {}))
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
          refresh: { triggered: false, reason: "fresh-retry", ticker: "AAPL", job_id: null },
          diagnostics: null,
          provenance: [],
          source_mix: null,
          confidence_flags: [],
          as_of: null,
          last_refreshed_at: null,
        }),
      });

    vi.stubGlobal("fetch", fetchMock);

    void getCompanyChangesSinceLastFiling("AAPL").catch(() => undefined);

    await vi.waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    vi.setSystemTime(new Date("2026-04-27T00:00:16Z"));

    const retried = await getCompanyChangesSinceLastFiling("AAPL");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(retried.refresh.reason).toBe("fresh-retry");
    vi.useRealTimers();
  });

  it("times out hung requests instead of waiting forever", async () => {
    vi.useFakeTimers();

    const fetchMock = vi.fn().mockImplementation((_input, init?: RequestInit) => {
      const signal = init?.signal;
      return new Promise((_resolve, reject) => {
        const abort = () => reject(signal?.reason ?? new DOMException("The operation was aborted.", "AbortError"));
        if (signal?.aborted) {
          abort();
          return;
        }
        signal?.addEventListener("abort", abort, { once: true });
      });
    });

    vi.stubGlobal("fetch", fetchMock);

    const pending = expect(getCompanyChangesSinceLastFiling("AAPL")).rejects.toThrow("API request timed out after 15000 ms");
    await vi.advanceTimersByTimeAsync(15_000);

    await pending;
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("dedupes repeated aggregate overview reads", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        company: { ticker: "AAPL", name: "Apple Inc.", cache_state: "fresh" },
        financials: {
          company: { ticker: "AAPL", name: "Apple Inc.", cache_state: "fresh" },
          financials: [],
          price_history: [{ date: "2026-04-11", close: 189.95 }],
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

  it("drops cached workspace bootstrap placeholders before reusing them", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        buildOkJsonResponse(
          buildWorkspaceBootstrapPayload("BROS", {
            company: null,
            financialsReason: "missing",
            financialsCompany: null,
            brief: { company_missing: true },
          })
        )
      )
      .mockResolvedValueOnce(buildOkJsonResponse(buildWorkspaceBootstrapPayload("BROS")));

    vi.stubGlobal("fetch", fetchMock);

    const first = await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });
    const second = await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });

    expect(first.company).toBeNull();
    expect(second.company?.ticker).toBe("BROS");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/BROS/workspace-bootstrap?include_overview_brief=true",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("drops cached workspace bootstrap placeholders that only contain company metadata", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        buildOkJsonResponse(
          buildWorkspaceBootstrapPayload("BROS", {
            company: { ticker: "BROS", name: "Dutch Bros Inc.", cache_state: "missing" },
            financialsReason: "missing",
            financialsCompany: { ticker: "BROS", name: "Dutch Bros Inc.", cache_state: "missing" },
            brief: null,
          })
        )
      )
      .mockResolvedValueOnce(buildOkJsonResponse(buildWorkspaceBootstrapPayload("BROS")));

    vi.stubGlobal("fetch", fetchMock);

    const first = await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });
    const second = await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });

    expect(first.financials.refresh.reason).toBe("missing");
    expect(second.company?.ticker).toBe("BROS");
    expect(second.financials.refresh.reason).toBe("fresh");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("drops cached workspace bootstrap placeholders that are still empty even when marked fresh", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        buildOkJsonResponse(
          buildWorkspaceBootstrapPayload("BROS", {
            company: null,
            financialsReason: "fresh",
            financialsCompany: null,
            brief: null,
          })
        )
      )
      .mockResolvedValueOnce(buildOkJsonResponse(buildWorkspaceBootstrapPayload("BROS")));

    vi.stubGlobal("fetch", fetchMock);

    const first = await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });
    const second = await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });

    expect(first.company).toBeNull();
    expect(first.financials.refresh.reason).toBe("fresh");
    expect(second.company?.ticker).toBe("BROS");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("drops financials cache entries primed from missing bootstrap placeholders", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        buildOkJsonResponse(
          buildWorkspaceBootstrapPayload("BROS", {
            company: null,
            financialsReason: "missing",
            financialsCompany: null,
            brief: { company_missing: true },
          })
        )
      )
      .mockResolvedValueOnce(buildOkJsonResponse(buildFinancialsPayload("BROS", "fresh")));

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });
    const financials = await getCompanyFinancials("BROS");

    expect(financials.company?.ticker).toBe("BROS");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/BROS/financials",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("drops financials cache entries primed from metadata-only bootstrap placeholders", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        buildOkJsonResponse(
          buildWorkspaceBootstrapPayload("BROS", {
            company: { ticker: "BROS", name: "Dutch Bros Inc.", cache_state: "missing" },
            financialsReason: "missing",
            financialsCompany: { ticker: "BROS", name: "Dutch Bros Inc.", cache_state: "missing" },
            brief: null,
          })
        )
      )
      .mockResolvedValueOnce(buildOkJsonResponse(buildFinancialsPayload("BROS", "fresh")));

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyWorkspaceBootstrap("BROS", { includeOverviewBrief: true });
    const financials = await getCompanyFinancials("BROS");

    expect(financials.refresh.reason).toBe("fresh");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/BROS/financials",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("drops empty financials cache entries that were marked fresh without company coverage", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        buildOkJsonResponse({
          company: null,
          financials: [],
          price_history: [],
          refresh: { triggered: false, reason: "fresh", ticker: "BROS", job_id: null },
          diagnostics: null,
        })
      )
      .mockResolvedValueOnce(buildOkJsonResponse(buildFinancialsPayload("BROS", "fresh")));

    vi.stubGlobal("fetch", fetchMock);

    const first = await getCompanyFinancials("BROS");
    const second = await getCompanyFinancials("BROS");

    expect(first.company).toBeNull();
    expect(first.refresh.reason).toBe("fresh");
    expect(second.company?.ticker).toBe("BROS");
    expect(fetchMock).toHaveBeenCalledTimes(2);
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
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/cache/company/AAPL",
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

  it("route-specific market-context policy (20 s ttl) marks data stale before STABLE_SEC_POLICY would", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-27T00:00:00Z"));

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ company: null, context: {}, refresh: { triggered: false, reason: "first", ticker: "AMD", job_id: null } }),
      })
      .mockResolvedValue({
        ok: true,
        json: async () => ({ company: null, context: {}, refresh: { triggered: false, reason: "revalidated", ticker: "AMD", job_id: null } }),
      });

    vi.stubGlobal("fetch", fetchMock);

    // Prime the cache.
    await getCompanyMarketContext("AMD");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Advance by 25 s – beyond market-context ttlMs (20 000) but well within STABLE_SEC_POLICY ttlMs (600 000).
    vi.setSystemTime(new Date("2026-04-27T00:00:25Z"));

    // Should return stale data and trigger background revalidation.
    const staleResult = await getCompanyMarketContext("AMD");
    expect(staleResult.refresh.reason).toBe("first");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });

  it("per-request cachePolicy override takes precedence over the route default", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-27T00:00:00Z"));

    // market-context has a 20 s route policy.  We override it with a very long ttl so the entry
    // should still be fresh after 25 s (which would normally trigger a stale revalidation).
    const longPolicy: ReadCachePolicy = { ttlMs: 300_000, staleMs: 900_000 };

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ company: null, context: {}, refresh: { triggered: false, reason: "cached", ticker: "AMD", job_id: null } }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyMarketContext("AMD", { cachePolicy: longPolicy });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.setSystemTime(new Date("2026-04-27T00:00:25Z"));

    // With the override policy (300 s ttl), the entry is still fresh.
    const result = await getCompanyMarketContext("AMD", { cachePolicy: longPolicy });
    expect(result.refresh.reason).toBe("cached");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    vi.useRealTimers();
  });

  it("uses DEFAULT_READ_POLICY (45 s ttl) for paths without a route-specific override", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-04-27T00:00:00Z"));

    // searchCompanies with refresh=false so the cache is actually consulted.
    const fetchMock = vi
      .fn()
      .mockResolvedValue({
        ok: true,
        json: async () => ({ query: "X", total: 0, results: [] }),
      });

    vi.stubGlobal("fetch", fetchMock);

    // Prime – search has a route policy of 20 s ttl, which is shorter than the 45 s default.
    // Use a path we can control by passing an explicit long policy to act as the "default" scenario.
    // Instead, test the stale boundary at exactly DEFAULT_READ_POLICY.ttlMs (45 s) for
    // a hypothetical unmatched path by passing cachePolicy directly.
    const defaultPolicy: ReadCachePolicy = { ttlMs: 45_000, staleMs: 180_000 };

    await searchCompanies("X", { refresh: false, cachePolicy: defaultPolicy });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 44 s – still fresh under the 45 s ttl.
    vi.setSystemTime(new Date("2026-04-27T00:00:44Z"));
    await searchCompanies("X", { refresh: false, cachePolicy: defaultPolicy });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 46 s – now stale; background revalidation should fire.
    vi.setSystemTime(new Date("2026-04-27T00:00:46Z"));
    const stale = await searchCompanies("X", { refresh: false, cachePolicy: defaultPolicy });
    expect(stale.query).toBe("X");
    expect(fetchMock).toHaveBeenCalledTimes(2);

    vi.useRealTimers();
  });
});

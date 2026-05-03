import { afterEach, describe, expect, it, vi } from "vitest";

import {
  __resetApiClientCacheForTests,
  getCompanyCapitalStructure,
  getCompanyCharts,
  createCompanyChartsShareSnapshot,
  createCompanyChartsScenario,
  cloneCompanyChartsScenario,
  getCompanyChartsShareSnapshot,
  getCompanyChartsScenario,
  getCompanyChartsWhatIf,
  getCompanyChangesSinceLastFiling,
  getCompaniesCompare,
  getCompanyEarningsWorkspace,
  getCompanyFinancials,
  getCompanyFinancialRestatements,
  getCompanyFilingInsights,
  getCompanyFilingRiskSignals,
  getCompanyFilings,
  getCompanyMarketContext,
  getCompanyOverview,
  getCompanyWorkspaceBootstrap,
  getCompanyResearchBrief,
  listCompanyChartsScenarios,
  getLatestModelEvaluation,
  getCompanyModels,
  getCompanyPeers,
  getCacheMetrics,
  getSourceRegistry,
  getResearchWorkspace,
  saveResearchWorkspace,
  deleteResearchWorkspace,
  importLocalResearchWorkspace,
  getWatchlistCalendar,
  getWatchlistSummary,
  updateCompanyChartsScenario,
} from "@/lib/api";

describe("api route stability", () => {
  afterEach(() => {
    __resetApiClientCacheForTests();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps key GET helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyEarningsWorkspace("AAPL");
    await getCompanyFilings("MSFT");
    await getCompanyFilingInsights("NVDA");
    await getCompanyFilingRiskSignals("CRM");
    await getCompanyMarketContext("AMD");
    await getCompanyOverview("AAPL");
    await getCompanyWorkspaceBootstrap("AAPL", { includeOverviewBrief: true, includeInsiders: true });
    await getCompanyResearchBrief("AAPL");
    await getLatestModelEvaluation();
    await getCompanyCapitalStructure("AAPL");
    await getCompanyPeers("AAPL", ["MSFT", "NVDA"]);
    await getCompaniesCompare(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/earnings/workspace",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/MSFT/filings",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/NVDA/filing-insights",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/CRM/filing-risk-signals",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AMD/market-context",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/overview",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/backend/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&include_insiders=true",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      "/backend/api/companies/AAPL/brief",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      9,
      "/backend/api/model-evaluations/latest",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      10,
      "/backend/api/companies/AAPL/capital-structure",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      11,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      12,
      "/backend/api/companies/compare?tickers=AAPL%2CMSFT",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps workspace POST helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tickers: [], companies: [] }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getWatchlistSummary(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/watchlist/summary",
      expect.objectContaining({
        method: "POST",
        cache: "no-store",
        body: JSON.stringify({ tickers: ["AAPL", "MSFT"] }),
      })
    );
  });

  it("keeps research workspace helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        workspace_key: "default",
        saved_companies: [],
        notes: [],
        pinned_metrics: [],
        pinned_charts: [],
        compare_baskets: [],
        memo_draft: null,
        updated_at: "2026-04-26T00:00:00Z",
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getResearchWorkspace("alpha");
    await saveResearchWorkspace({
      saved_companies: [],
      notes: [],
      pinned_metrics: [],
      pinned_charts: [],
      compare_baskets: [],
      memo_draft: null,
    }, { workspaceKey: "alpha" });
    await deleteResearchWorkspace("alpha");
    await importLocalResearchWorkspace({ watchlist: [], notes: {}, mode: "merge" }, { workspaceKey: "alpha" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/research-workspace?workspace_key=alpha",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/research-workspace/save?workspace_key=alpha",
      expect.objectContaining({ method: "POST", cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/research-workspace/delete?workspace_key=alpha",
      expect.objectContaining({ method: "POST", cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/research-workspace/import-local?workspace_key=alpha",
      expect.objectContaining({ method: "POST", cache: "no-store" })
    );
  });

  it("keeps workspace GET helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ tickers: [], window_start: "2026-04-04", window_end: "2026-07-03", events: [] }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getWatchlistCalendar(["AAPL", "MSFT"]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/watchlist/calendar?tickers=AAPL&tickers=MSFT",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps source registry helper path unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        strict_official_mode: false,
        generated_at: "2026-04-05T00:00:00Z",
        sources: [],
        health: { total_companies_cached: 0, average_data_age_seconds: null, recent_error_window_hours: 72, sources_with_recent_errors: [] },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getSourceRegistry();

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/source-registry",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps internal cache metrics helper path unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        search_cache: { entries: 0, ttl_seconds: 60 },
        hot_cache: {
          backend: "redis",
          shared: true,
          namespace: "ft:hot-cache",
          config: {
            ttl_seconds: 20,
            stale_ttl_seconds: 120,
            singleflight_lock_seconds: 30,
            singleflight_wait_seconds: 15,
            singleflight_poll_seconds: 0.05,
          },
          overall: {
            requests: 0,
            hit_fresh: 0,
            hit_stale: 0,
            hits: 0,
            misses: 0,
            hit_rate: 0,
            fills: 0,
            fill_time_ms_total: 0,
            avg_fill_time_ms: 0,
            stale_served_count: 0,
            invalidation_count: 0,
            invalidated_keys: 0,
            coalesced_waits: 0,
          },
          routes: {},
        },
      }),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCacheMetrics();

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/internal/cache-metrics",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("serializes point-in-time query params for research helpers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFinancials("AAPL", { asOf: "2025-02-01", view: "core" });
    await getCompanyOverview("AAPL", { asOf: "2025-02-01", financialsView: "core_segments" });
    await getCompanyWorkspaceBootstrap("AAPL", {
      asOf: "2025-02-01",
      financialsView: "core_segments",
      includeOverviewBrief: true,
      includeInsiders: true,
      includeInstitutional: true,
      includeEarningsSummary: true,
    });
    await getCompanyCapitalStructure("AAPL", { maxPeriods: 6, asOf: "2025-02-01" });
    await getCompanyResearchBrief("AAPL", { asOf: "2025-02-01" });
    await getCompanyChangesSinceLastFiling("AAPL", { asOf: "2025-02-01" });
    await getCompanyFinancialRestatements("AAPL", { asOf: "2025-02-01" });
    await getCompanyModels("AAPL", ["dcf"], { dupontMode: "ttm", asOf: "2025-02-01" });
    await getCompanyPeers("AAPL", ["MSFT", "NVDA"], { asOf: "2025-02-01" });
    await getCompaniesCompare(["AAPL", "MSFT"], { asOf: "2025-02-01" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/financials?view=core&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/overview?financials_view=core_segments&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/workspace-bootstrap?financials_view=core_segments&include_overview_brief=true&include_insiders=true&include_institutional=true&include_earnings_summary=true&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AAPL/capital-structure?max_periods=6&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/brief?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      6,
      "/backend/api/companies/AAPL/changes-since-last-filing?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      7,
      "/backend/api/companies/AAPL/financial-restatements?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      8,
      "/backend/api/companies/AAPL/models?model=dcf&dupont_mode=ttm&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      9,
      "/backend/api/companies/AAPL/peers?peers=MSFT%2CNVDA&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      10,
      "/backend/api/companies/compare?tickers=AAPL%2CMSFT&as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("serializes bounded price-history query params for chart-oriented financial helpers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyFinancials("AAPL", {
      view: "core",
      priceStartDate: "2020-01-01",
      priceEndDate: "2025-01-01",
      priceLatestN: 1200,
      priceMaxPoints: 320,
    });
    await getCompanyOverview("AAPL", {
      financialsView: "core_segments",
      priceLatestN: 2400,
      priceMaxPoints: 480,
    });
    await getCompanyWorkspaceBootstrap("AAPL", {
      financialsView: "core_segments",
      priceLatestN: 2400,
      priceMaxPoints: 480,
      includeOverviewBrief: true,
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/financials?view=core&price_start_date=2020-01-01&price_end_date=2025-01-01&price_latest_n=1200&price_max_points=320",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/overview?financials_view=core_segments&price_latest_n=2400&price_max_points=480",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/workspace-bootstrap?financials_view=core_segments&price_latest_n=2400&price_max_points=480&include_overview_brief=true",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps charts helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyCharts("AAPL");
    await getCompanyCharts("AAPL", { asOf: "2025-02-01" });
    await getCompanyChartsWhatIf("AAPL", { overrides: { dso: 60 } });
    await getCompanyChartsWhatIf("AAPL", { overrides: { dso: 60 } }, { asOf: "2025-02-01" });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/charts",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/charts?as_of=2025-02-01",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/charts/what-if",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
        body: JSON.stringify({ overrides: { dso: 60 } }),
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AAPL/charts/what-if?as_of=2025-02-01",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
        body: JSON.stringify({ overrides: { dso: 60 } }),
      })
    );
  });

  it("keeps charts share snapshot helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await createCompanyChartsShareSnapshot("AAPL", {
      schema_version: "company_chart_share_snapshot_v1",
      mode: "outlook",
      ticker: "AAPL",
      company_name: "Apple Inc.",
      title: "Growth Outlook",
      as_of: "2025-02-01",
      source_badge: "SEC Company Facts",
      provenance_badge: "SEC-derived",
      trust_label: "Forecast stability: Moderate stability",
      actual_label: "Reported",
      forecast_label: "Forecast",
      source_path: "/company/AAPL/charts",
      chart_spec: {
        schema_version: "company_chart_spec_v1",
        payload_version: "company_charts_dashboard_v9",
        company: null,
        build_state: "ready",
        build_status: "Charts ready.",
        refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 0.9,
          missing_field_flags: [],
          reconciliation_penalty: null,
          reconciliation_disagreement_count: 0,
        },
        provenance: [],
        as_of: "2025-02-01",
        last_refreshed_at: "2025-02-01T00:00:00Z",
        source_mix: {
          source_ids: [],
          source_tiers: [],
          primary_source_ids: [],
          fallback_source_ids: [],
          official_only: true,
        },
        confidence_flags: [],
        available_modes: ["outlook"],
        default_mode: "outlook",
        outlook: {
          title: "Growth Outlook",
          summary: {
            headline: "Growth Outlook",
            primary_score: { key: "growth", label: "Growth", score: 88, tone: "positive", detail: "Strong" },
            secondary_badges: [],
            thesis: "Projected and reported values are distinct.",
            unavailable_notes: [],
            freshness_badges: [],
            source_badges: [],
          },
          legend: { title: "Actual vs Forecast", items: [] },
          cards: {
            revenue: { key: "revenue", title: "Revenue", subtitle: null, metric_label: null, unit_label: null, empty_state: null, series: [], highlights: [] },
            revenue_growth: { key: "revenue_growth", title: "Revenue Growth", subtitle: null, metric_label: null, unit_label: null, empty_state: null, series: [], highlights: [] },
            profit_metric: { key: "profit_metric", title: "Profit", subtitle: null, metric_label: null, unit_label: null, empty_state: null, series: [], highlights: [] },
            cash_flow_metric: { key: "cash_flow_metric", title: "Cash Flow", subtitle: null, metric_label: null, unit_label: null, empty_state: null, series: [], highlights: [] },
            eps: { key: "eps", title: "EPS", subtitle: null, metric_label: null, unit_label: null, empty_state: null, series: [], highlights: [] },
            growth_summary: { key: "growth_summary", title: "Growth Summary", subtitle: null, comparisons: [], empty_state: null },
            forecast_assumptions: null,
          },
          primary_card_order: ["revenue"],
          secondary_card_order: [],
          comparison_card_order: ["growth_summary"],
          detail_card_order: [],
          methodology: {
            version: "company_charts_dashboard_v9",
            label: "Driver-based integrated forecast",
            summary: "Summary",
            disclaimer: "Disclaimer",
            forecast_horizon_years: 3,
            confidence_label: "Forecast stability: Moderate stability",
          },
          forecast_diagnostics: {
            score_key: "forecast_stability",
            score_name: "Forecast Stability",
            heuristic: true,
            final_score: 72,
            summary: "Moderate stability.",
            history_depth_years: 4,
            thin_history: false,
            growth_volatility: 0.1,
            growth_volatility_band: "moderate",
            missing_data_penalty: 0,
            quality_score: 0.9,
            missing_inputs: [],
            sample_size: 3,
            scenario_dispersion: 0.1,
            sector_template: "Technology",
            guidance_usage: "management_guidance_applied",
            historical_backtest_error_band: "moderate",
            backtest_weighted_error: 0.1,
            backtest_horizon_errors: {},
            backtest_metric_weights: {},
            backtest_metric_errors: {},
            backtest_metric_horizon_errors: {},
            backtest_metric_sample_sizes: {},
            components: [],
          },
        },
        studio: null,
      },
      outlook: {
        headline: "Growth Outlook",
        thesis: "Projected and reported values are distinct.",
        primary_score: { key: "growth", label: "Growth", score: 88, tone: "positive", detail: "Strong" },
        secondary_scores: [],
        summary_metrics: [],
        primary_chart: null,
      },
      studio: null,
    });
    await getCompanyChartsShareSnapshot("AAPL", "share-1");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/charts/share-snapshots",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/charts/share-snapshots/share-1",
      expect.objectContaining({ cache: "no-store" })
    );
  });

  it("keeps Projection Studio scenario helper paths unchanged", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ viewer: { kind: "device", signed_in: false, sync_enabled: true, can_create_private: true }, scenarios: [] }),
    });
    const localStorageMock = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    };

    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("window", { localStorage: localStorageMock });
    localStorageMock.clear();

    await listCompanyChartsScenarios("AAPL");
    await getCompanyChartsScenario("AAPL", "scenario-1");
    await createCompanyChartsScenario("AAPL", {
      name: "Base case",
      visibility: "private",
      source: "sec_base_forecast",
      override_count: 1,
      forecast_year: 2026,
      as_of: "2025-02-01",
      overrides: { dso: 42 },
      metrics: [],
    });
    await updateCompanyChartsScenario("AAPL", "scenario-1", {
      name: "Base case",
      visibility: "public",
      source: "user_scenario",
      override_count: 2,
      forecast_year: 2026,
      as_of: "2025-02-01",
      overrides: { dso: 55 },
      metrics: [],
    });
    await cloneCompanyChartsScenario("AAPL", "scenario-1", {
      name: "Base case copy",
      visibility: "public",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/backend/api/companies/AAPL/charts/scenarios",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/backend/api/companies/AAPL/charts/scenarios/scenario-1",
      expect.objectContaining({ cache: "no-store" })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/backend/api/companies/AAPL/charts/scenarios",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      "/backend/api/companies/AAPL/charts/scenarios/scenario-1",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      "/backend/api/companies/AAPL/charts/scenarios/scenario-1/clone",
      expect.objectContaining({
        cache: "no-store",
        method: "POST",
      })
    );
  });

  it("serializes model payload expansions only when requested", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });

    vi.stubGlobal("fetch", fetchMock);

    await getCompanyModels("AAPL", ["dcf", "dupont"], { dupontMode: "annual", expandInputPeriods: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/backend/api/companies/AAPL/models?model=dcf%2Cdupont&expand=input_periods&dupont_mode=annual",
      expect.objectContaining({ cache: "no-store" })
    );
  });
});

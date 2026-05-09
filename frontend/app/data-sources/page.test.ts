// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DataSourcesPage from "@/app/data-sources/page";

const push = vi.fn();
const getSourceRegistry = vi.fn();
const getCacheMetrics = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api", () => ({
  getSourceRegistry: (...args: unknown[]) => getSourceRegistry(...args),
  getCacheMetrics: (...args: unknown[]) => getCacheMetrics(...args),
}));

describe("DataSourcesPage", () => {
  beforeEach(() => {
    push.mockReset();
    getSourceRegistry.mockReset();
    getCacheMetrics.mockReset();
    getSourceRegistry.mockResolvedValue({
      strict_official_mode: true,
      generated_at: "2026-04-05T12:00:00Z",
      sources: [
        {
          source_id: "sec_companyfacts",
          source_tier: "official_regulator",
          display_label: "SEC Company Facts (XBRL)",
          url: "https://data.sec.gov/api/xbrl/companyfacts/",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
          strict_official_mode_state: "available",
          strict_official_mode_note: "Strict official mode is enabled and this source remains available because it is official/public or derived from official inputs.",
          last_success_at: "2026-04-05T10:30:00Z",
          last_error: null,
          last_error_at: null,
          is_stale: false,
          used_by_paths: ["/api/companies/{ticker}/financials", "/api/companies/{ticker}/charts"],
        },
        {
          source_id: "yahoo_finance",
          source_tier: "commercial_fallback",
          display_label: "Yahoo Finance",
          url: "https://finance.yahoo.com/",
          default_freshness_ttl_seconds: 3600,
          disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
          strict_official_mode_state: "disabled",
          strict_official_mode_note: "Strict official mode is enabled, so this fallback source is currently suppressed.",
          last_success_at: "2026-04-05T11:15:00Z",
          last_error: "timeout",
          last_error_at: "2026-04-05T11:45:00Z",
          is_stale: true,
          used_by_paths: ["/api/companies/{ticker}/financials"],
        },
        {
          source_id: "fred",
          source_tier: "official_treasury_or_fed",
          display_label: "Federal Reserve Economic Data (FRED)",
          url: "https://fred.stlouisfed.org/",
          default_freshness_ttl_seconds: 86400,
          disclosure_note: "Federal Reserve public macro series used for supplemental rates, inflation, labor, and credit context.",
          strict_official_mode_state: "available",
          strict_official_mode_note: "Strict official mode is enabled and this source remains available because it is official/public or derived from official inputs.",
          last_success_at: null,
          last_error: null,
          last_error_at: null,
          is_stale: false,
          used_by_paths: ["/api/companies/{ticker}/models"],
        },
      ],
      health: {
        total_companies_cached: 412,
        average_data_age_seconds: 5400,
        recent_error_window_hours: 72,
        stale_source_count: 1,
        sources_with_active_errors_count: 1,
        fallback_source_count: 1,
        fallback_sources_recently_used_count: 1,
        last_successful_refresh_at: "2026-04-05T11:15:00Z",
        worker_queue: {
          available: true,
          status: "degraded",
          active_job_count: 2,
          stalled_job_count: 1,
          datasets_with_failures: 1,
          failed_refresh_count: 3,
          recent_failed_jobs: 1,
        },
        slos: [
          {
            key: "sec_companyfacts_freshness",
            label: "SEC companyfacts freshness",
            status: "healthy",
            monitored_source_ids: ["sec_companyfacts"],
            source_count: 1,
            stale_count: 0,
            active_error_count: 0,
            last_success_at: "2026-04-05T10:30:00Z",
            note: "Last tracked success 2026-04-05T10:30:00Z.",
          },
          {
            key: "sec_submissions_freshness",
            label: "SEC submissions freshness",
            status: "stale",
            monitored_source_ids: ["sec_edgar"],
            source_count: 1,
            stale_count: 1,
            active_error_count: 0,
            last_success_at: "2026-04-05T08:00:00Z",
            note: "1 stale source currently tracked.",
          },
          {
            key: "macro_freshness",
            label: "Macro freshness",
            status: "unknown",
            monitored_source_ids: ["fred"],
            source_count: 1,
            stale_count: 0,
            active_error_count: 0,
            last_success_at: null,
            note: "No telemetry available yet.",
          },
          {
            key: "fallback_usage",
            label: "Fallback usage",
            status: "degraded",
            monitored_source_ids: ["yahoo_finance"],
            source_count: 1,
            stale_count: 1,
            active_error_count: 1,
            last_success_at: "2026-04-05T11:15:00Z",
            note: "1 fallback source(s) with recent successful refresh.",
          },
          {
            key: "worker_queue_health",
            label: "Worker and queue health",
            status: "degraded",
            monitored_source_ids: [],
            source_count: 0,
            stale_count: 1,
            active_error_count: 1,
            last_success_at: null,
            note: "Worker refresh failures or queue backlogs are currently tracked.",
          },
        ],
        sources_with_recent_errors: [
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            affected_dataset_ids: ["prices"],
            affected_company_count: 3,
            failure_count: 5,
            last_error: "timeout",
            last_error_at: "2026-04-05T11:00:00Z",
          },
        ],
      },
    });
    getCacheMetrics.mockResolvedValue({
      search_cache: {
        entries: 12,
        ttl_seconds: 60,
      },
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
          requests: 200,
          hit_fresh: 150,
          hit_stale: 10,
          hits: 160,
          misses: 40,
          hit_rate: 0.8,
          fills: 35,
          fill_time_ms_total: 4200,
          avg_fill_time_ms: 120,
          stale_served_count: 10,
          invalidation_count: 8,
          invalidated_keys: 19,
          coalesced_waits: 6,
        },
        routes: {},
      },
    });
  });

  it("renders summary cards, source table, and technical accordions", async () => {
    render(React.createElement(DataSourcesPage));

    await waitFor(() => {
      expect(screen.getByText("Data Sources")).toBeTruthy();
    });

      expect(screen.getByText("SEC companyfacts freshness")).toBeTruthy();
      expect(screen.getByText("SEC submissions freshness")).toBeTruthy();
      expect(screen.getByText("Macro freshness")).toBeTruthy();
      expect(screen.getByText("Fallback usage")).toBeTruthy();
      expect(screen.getByText("Worker and queue health")).toBeTruthy();
    expect(screen.getByRole("table", { name: "Source health table" })).toBeTruthy();
    expect(screen.getByText("Source")).toBeTruthy();
    expect(screen.getByText("Last success")).toBeTruthy();
    expect(screen.getByText("Last error")).toBeTruthy();
    expect(screen.getByText("Used by")).toBeTruthy();
    expect(screen.getAllByText("Official").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fallback").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Disabled in strict mode").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stale").length).toBeGreaterThan(0);
    expect(screen.getByText("How to read this page")).toBeTruthy();
    expect(screen.getByText("Methodology and source notes")).toBeTruthy();
    expect(screen.getByText("Raw configuration and debug details")).toBeTruthy();
    expect(screen.getByText("Charts")).toBeTruthy();
    expect(screen.getAllByText("Financials").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Healthy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Degraded").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Stale").length).toBeGreaterThan(0);
  });

  it("shows a loading state before the registry resolves", async () => {
    let resolveRegistry: ((value: unknown) => void) | null = null;
    let resolveCache: ((value: unknown) => void) | null = null;
    getSourceRegistry.mockReturnValue(new Promise((resolve) => {
      resolveRegistry = resolve;
    }));
    getCacheMetrics.mockReturnValue(new Promise((resolve) => {
      resolveCache = resolve;
    }));

    render(React.createElement(DataSourcesPage));

    expect(screen.getByLabelText("Loading source health table")).toBeTruthy();

    resolveRegistry?.({
      strict_official_mode: false,
      generated_at: "2026-04-05T12:00:00Z",
      sources: [],
      health: {
        total_companies_cached: 0,
        average_data_age_seconds: null,
        recent_error_window_hours: 72,
        stale_source_count: 0,
        sources_with_active_errors_count: 0,
        fallback_source_count: 0,
        fallback_sources_recently_used_count: 0,
        last_successful_refresh_at: null,
        worker_queue: null,
        slos: [],
        sources_with_recent_errors: [],
      },
    });
    resolveCache?.({ search_cache: { entries: 0, ttl_seconds: 60 }, hot_cache: { backend: "redis", shared: true, namespace: "ft", config: { ttl_seconds: 20, stale_ttl_seconds: 120, singleflight_lock_seconds: 30, singleflight_wait_seconds: 15, singleflight_poll_seconds: 0.05 }, overall: { requests: 0, hit_fresh: 0, hit_stale: 0, hits: 0, misses: 0, hit_rate: 0, fills: 0, fill_time_ms_total: 0, avg_fill_time_ms: 0, stale_served_count: 0, invalidation_count: 0, invalidated_keys: 0, coalesced_waits: 0 }, routes: {} } });

    await waitFor(() => {
      expect(screen.getByText("No sources registered")).toBeTruthy();
    });
  });

  it("shows an empty state when the registry returns no sources", async () => {
    getSourceRegistry.mockResolvedValue({
      strict_official_mode: false,
      generated_at: "2026-04-05T12:00:00Z",
      sources: [],
      health: {
        total_companies_cached: 0,
        average_data_age_seconds: null,
        recent_error_window_hours: 72,
        stale_source_count: 0,
        sources_with_active_errors_count: 0,
        fallback_source_count: 0,
        fallback_sources_recently_used_count: 0,
        last_successful_refresh_at: null,
        worker_queue: null,
        slos: [],
        sources_with_recent_errors: [],
      },
    });

    render(React.createElement(DataSourcesPage));

    await waitFor(() => {
      expect(screen.getByText("No sources registered")).toBeTruthy();
    });
  });

  it("shows an error state when the source registry fails", async () => {
    getSourceRegistry.mockRejectedValue(new Error("registry down"));
    getCacheMetrics.mockRejectedValue(new Error("cache down"));

    render(React.createElement(DataSourcesPage));

    await waitFor(() => {
      expect(screen.getByText("Source registry unavailable")).toBeTruthy();
    });

    expect(screen.getByText("registry down")).toBeTruthy();
    expect(screen.getByText("Retry")).toBeTruthy();
  });

  it("falls back to computed cards when backend slos are missing", async () => {
    getSourceRegistry.mockResolvedValue({
      strict_official_mode: false,
      generated_at: "2026-04-05T12:00:00Z",
      sources: [
        {
          source_id: "sec_companyfacts",
          source_tier: "official_regulator",
          display_label: "SEC Company Facts (XBRL)",
          url: "https://data.sec.gov/api/xbrl/companyfacts/",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
          strict_official_mode_state: "available",
          strict_official_mode_note: "Strict official mode is disabled, so this source is currently available.",
          last_success_at: "2026-04-05T10:30:00Z",
          last_error: null,
          last_error_at: null,
          is_stale: false,
          used_by_paths: ["/api/companies/{ticker}/financials"],
        },
        {
          source_id: "sec_edgar",
          source_tier: "official_regulator",
          display_label: "SEC EDGAR Filing Archive",
          url: "https://www.sec.gov/edgar/search/",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Official SEC filing archive.",
          strict_official_mode_state: "available",
          strict_official_mode_note: "Strict official mode is disabled, so this source is currently available.",
          last_success_at: "2026-04-05T08:00:00Z",
          last_error: "parse timeout",
          last_error_at: "2026-04-05T09:00:00Z",
          is_stale: true,
          used_by_paths: ["/api/companies/{ticker}/filings"],
        },
      ],
      health: {
        total_companies_cached: 1,
        average_data_age_seconds: 600,
        recent_error_window_hours: 72,
        stale_source_count: 1,
        sources_with_active_errors_count: 1,
        fallback_source_count: 0,
        fallback_sources_recently_used_count: 0,
        last_successful_refresh_at: "2026-04-05T10:30:00Z",
        worker_queue: null,
        slos: [],
        sources_with_recent_errors: [],
      },
    });

    render(React.createElement(DataSourcesPage));

    await waitFor(() => {
      expect(screen.getByText("SEC companyfacts freshness")).toBeTruthy();
    });

    expect(screen.getByText("SEC submissions freshness")).toBeTruthy();
    expect(screen.getByText("Worker and queue health")).toBeTruthy();
    expect(screen.getAllByText("Healthy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Degraded").length).toBeGreaterThan(0);
  });
});
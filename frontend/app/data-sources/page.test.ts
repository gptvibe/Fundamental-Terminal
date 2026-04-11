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
        },
        {
          source_id: "yahoo_finance",
          source_tier: "commercial_fallback",
          display_label: "Yahoo Finance",
          url: "https://finance.yahoo.com/",
          default_freshness_ttl_seconds: 3600,
          disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
          strict_official_mode_state: "available",
          strict_official_mode_note: "Strict official mode is disabled, so this source is currently available.",
        },
      ],
      health: {
        total_companies_cached: 412,
        average_data_age_seconds: 5400,
        recent_error_window_hours: 72,
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

  it("renders grouped source cards and health summary", async () => {
    render(React.createElement(DataSourcesPage));

    await waitFor(() => {
      expect(screen.getByText("Data Sources")).toBeTruthy();
    });

    expect(screen.getByText("Official Regulators")).toBeTruthy();
    expect(screen.getByText("Commercial Fallbacks")).toBeTruthy();
    expect(screen.getAllByText("SEC Company Facts (XBRL)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Yahoo Finance").length).toBeGreaterThan(0);
    expect(screen.getByText("Companies cached")).toBeTruthy();
    expect(screen.getByText("412")).toBeTruthy();
    expect(screen.getAllByText(/Strict mode available/i).length).toBeGreaterThan(0);
    expect(screen.getByText("Shared Hot Cache")).toBeTruthy();
    expect(screen.getByText("Redis")).toBeTruthy();
    expect(screen.getByText("80.0%")).toBeTruthy();
    expect(screen.getByText("120ms")).toBeTruthy();
  });
});
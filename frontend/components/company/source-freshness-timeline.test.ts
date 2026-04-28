// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SourceFreshnessTimeline } from "@/components/company/source-freshness-timeline";

const mockIsPerformanceAuditEnabled = vi.fn();

vi.mock("@/lib/performance-audit", () => ({
  isPerformanceAuditEnabled: () => mockIsPerformanceAuditEnabled(),
}));

describe("SourceFreshnessTimeline", () => {
  afterEach(() => {
    vi.clearAllMocks();
    delete (window as Window & { __FT_PERFORMANCE_AUDIT__?: unknown }).__FT_PERFORMANCE_AUDIT__;
  });

  it("renders graceful placeholders when freshness fields are missing", () => {
    mockIsPerformanceAuditEnabled.mockReturnValue(false);

    render(
      React.createElement(SourceFreshnessTimeline, {
        ticker: "AAPL",
      })
    );

    expect(screen.getByText("Source freshness timeline")).toBeTruthy();
    expect(screen.getByText(/No filing date yet/i)).toBeTruthy();
    expect(screen.getByText(/Refresh state unavailable/i)).toBeTruthy();
    expect(screen.getByText(/Cache state unavailable/i)).toBeTruthy();
  });

  it("shows endpoint-level cache status when performance audit data is available", async () => {
    mockIsPerformanceAuditEnabled.mockReturnValue(true);

    (window as Window & {
      __FT_PERFORMANCE_AUDIT__?: {
        snapshot: () => { requests: Array<Record<string, unknown>> };
      };
    }).__FT_PERFORMANCE_AUDIT__ = {
      snapshot: () => ({
        requests: [
          {
            id: "evt-1",
            startedAt: "2026-04-27T10:00:00Z",
            method: "GET",
            path: "/companies/AAPL/financials",
            scenario: "company_overview",
            pageRoute: "/company/[ticker]",
            source: "company-workspace:initial-load",
            cacheDisposition: "fresh-cache-hit",
            cacheKey: "/companies/AAPL/financials",
            cachePolicyTtlMs: 600000,
            cachePolicyStaleMs: 3600000,
            responseSource: "memory-cache",
            networkRequest: false,
            backgroundRevalidate: false,
            statusCode: null,
            payloadBytes: 2400,
            durationMs: 0,
            responseBytes: 2400,
            error: null,
          },
          {
            id: "evt-2",
            startedAt: "2026-04-27T10:01:00Z",
            method: "GET",
            path: "/companies/AAPL/charts",
            scenario: "company_overview",
            pageRoute: "/company/[ticker]",
            source: "company-workspace:initial-load",
            cacheDisposition: "network",
            cacheKey: "/companies/AAPL/charts",
            cachePolicyTtlMs: 45000,
            cachePolicyStaleMs: 180000,
            responseSource: "network",
            networkRequest: true,
            backgroundRevalidate: false,
            statusCode: 200,
            payloadBytes: 8000,
            durationMs: 80,
            responseBytes: 8000,
            error: null,
          },
        ],
      }),
    };

    render(
      React.createElement(SourceFreshnessTimeline, {
        ticker: "AAPL",
        company: {
          ticker: "AAPL",
          cik: "0000320193",
          name: "Apple Inc.",
          sector: "Technology",
          market_sector: "Technology",
          market_industry: "Consumer Electronics",
          oil_exposure_type: "non_oil",
          oil_support_status: "unsupported",
          oil_support_reasons: [],
          strict_official_mode: true,
          last_checked: "2026-04-27T09:59:00Z",
          last_checked_financials: null,
          last_checked_prices: null,
          last_checked_insiders: null,
          last_checked_institutional: null,
          last_checked_filings: null,
          cache_state: "fresh",
        },
      })
    );

    await waitFor(() => {
      expect(screen.getByText(/Endpoint cache status/i)).toBeTruthy();
    });

    expect(screen.getByText(/Financials: memory-cache/i)).toBeTruthy();
    expect(screen.getAllByText(/Charts: network/i).length).toBeGreaterThan(0);
  });
});

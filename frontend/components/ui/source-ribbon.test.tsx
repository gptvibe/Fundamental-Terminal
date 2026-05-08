// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceRibbon } from "@/components/ui/source-ribbon";

describe("SourceRibbon", () => {
  it("renders provenance badges, source mix, freshness, and fallback disclosure", () => {
    render(
      React.createElement(SourceRibbon, {
        provenance: [
          {
            source_id: "sec_companyfacts",
            source_tier: "official_regulator",
            display_label: "SEC Company Facts (XBRL)",
            url: "https://data.sec.gov/api/xbrl/companyfacts/",
            default_freshness_ttl_seconds: 21600,
            disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
            role: "primary",
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
          },
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            url: "https://finance.yahoo.com/",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
            role: "fallback",
            as_of: "2026-03-21",
            last_refreshed_at: "2026-03-22T00:00:00Z",
          },
        ],
        sourceMix: {
          source_ids: ["sec_companyfacts", "yahoo_finance"],
          source_tiers: ["official_regulator", "commercial_fallback"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        },
        asOf: "2025-12-31",
        lastRefreshedAt: "2026-03-22T00:00:00Z",
        confidenceFlags: ["commercial_fallback_present"],
        diagnostics: {
          coverage_ratio: 0.92,
          fallback_ratio: 0.14,
          stale_flags: [],
          parser_confidence: null,
          missing_field_flags: ["market_cap"],
          reconciliation_penalty: null,
          reconciliation_disagreement_count: 0,
        },
      })
    );

    expect(screen.getByTestId("source-ribbon")).toBeTruthy();
    expect(screen.getByText("Source mix: Official + labeled fallback")).toBeTruthy();
    expect(screen.getByText("As of: Dec 31, 2025")).toBeTruthy();
    expect(screen.getByText("Refreshed: Mar 22, 2026")).toBeTruthy();
    expect(screen.getByTestId("source-ribbon-fallback").textContent).toContain("Yahoo Finance");
    expect(screen.getByText("Coverage 92%")).toBeTruthy();
    expect(screen.getByText("Fallback ratio 14%")).toBeTruthy();
    expect(screen.getByText("Missing fields 1")).toBeTruthy();
  });

  it("renders source unavailable when provenance entries are absent", () => {
    render(
      React.createElement(SourceRibbon, {
        provenance: [],
        sourceMix: {
          source_ids: [],
          source_tiers: [],
          primary_source_ids: [],
          fallback_source_ids: [],
          official_only: true,
        },
      })
    );

    expect(screen.getByTestId("source-ribbon-unavailable")).toBeTruthy();
    expect(screen.getAllByText("Source unavailable").length).toBeGreaterThan(0);
  });
});

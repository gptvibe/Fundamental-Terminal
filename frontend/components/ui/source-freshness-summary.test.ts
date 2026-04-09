// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";

describe("SourceFreshnessSummary", () => {
  it("renders source registry metadata, freshness, and confidence flags", () => {
    render(
      React.createElement(SourceFreshnessSummary, {
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
        asOf: "2025-12-31",
        lastRefreshedAt: "2026-03-22T00:00:00Z",
        sourceMix: {
          source_ids: ["sec_companyfacts", "yahoo_finance"],
          source_tiers: ["commercial_fallback", "official_regulator"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        },
        confidenceFlags: ["commercial_fallback_present", "partial_model_inputs"],
      })
    );

    expect(screen.getAllByText("SEC Company Facts (XBRL)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Yahoo Finance").length).toBeGreaterThan(0);
    expect(screen.getByText("Official + labeled fallback")).toBeTruthy();
    expect(screen.getAllByText("Fallback label").length).toBeGreaterThan(0);
    expect(screen.getByText(/includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Hide provenance drawer" })).toBeTruthy();
    expect(screen.getByLabelText("Provenance drawer")).toBeTruthy();
    expect(screen.getByText(/Confidence flags: commercial fallback present, partial model inputs/i)).toBeTruthy();
    expect(screen.getByText("Refreshed Mar 22, 2026 · TTL 6h")).toBeTruthy();
    expect(screen.getByText("Refreshed Mar 22, 2026 · TTL 1h")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Hide provenance drawer" }));

    expect(screen.queryByLabelText("Provenance drawer")).toBeNull();
    expect(screen.getByRole("button", { name: "Open provenance drawer" })).toBeTruthy();
  });
});

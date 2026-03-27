// @vitest-environment jsdom

import * as React from "react";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CommercialFallbackNotice, resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";

describe("CommercialFallbackNotice", () => {
  it("renders a stable labeled fallback badge snapshot", () => {
    const { container } = render(
      React.createElement(CommercialFallbackNotice, {
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
          source_tiers: ["commercial_fallback", "official_regulator"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        },
      })
    );

    const normalizedText = Array.from(container.querySelectorAll(".pill, .text-muted"))
      .map((element) => element.textContent?.replace(/\s+/g, " ").trim() ?? "")
      .join(" ");

    expect(normalizedText).toMatchInlineSnapshot(
      '"commercial_fallback Yahoo Finance Price or market profile data on this surface includes a labeled commercial fallback from Yahoo Finance. Core fundamentals remain sourced from official filings and public datasets."'
    );
  });

  it("resolves fallback labels from provenance tiers and source mix ids", () => {
    expect(
      resolveCommercialFallbackLabels(
        [
          {
            source_id: "manual_feed",
            source_tier: "manual_override",
            display_label: "Manual Feed",
            url: "https://example.com/manual",
            default_freshness_ttl_seconds: 300,
            disclosure_note: "Manual override feed.",
            role: "supplemental",
            as_of: null,
            last_refreshed_at: null,
          },
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            url: "https://finance.yahoo.com/",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
            role: "fallback",
            as_of: null,
            last_refreshed_at: null,
          },
        ],
        {
          source_ids: ["manual_feed", "yahoo_finance"],
          source_tiers: ["manual_override", "commercial_fallback"],
          primary_source_ids: [],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        }
      )
    ).toEqual(["Yahoo Finance"]);
  });
});
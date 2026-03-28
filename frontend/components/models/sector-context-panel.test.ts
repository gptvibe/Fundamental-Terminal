// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectorContextPanel } from "@/components/models/sector-context-panel";

describe("SectorContextPanel", () => {
  it("renders plugin cards, metrics, and charts", () => {
    render(
      React.createElement(SectorContextPanel, {
        context: {
          company: null,
          status: "ok",
          matched_plugin_ids: ["fhfa_housing"],
          plugins: [
            {
              plugin_id: "fhfa_housing",
              title: "Housing Exposure",
              description: "Official FHFA house-price trends for housing- and mortgage-sensitive companies.",
              status: "ok",
              relevance_reasons: ["industry: homebuilder"],
              source_ids: ["fhfa_house_price_index"],
              refresh_policy: { cadence_label: "Monthly", ttl_seconds: 86400, notes: ["FHFA monthly purchase-only HPI"] },
              summary_metrics: [
                {
                  metric_id: "national_hpi",
                  label: "National HPI",
                  unit: "index",
                  value: 437.2,
                  previous_value: 435.8,
                  change: 1.4,
                  change_percent: 0.0032,
                  as_of: "2026-01",
                  status: "ok",
                },
              ],
              charts: [
                {
                  chart_id: "national_hpi_trend",
                  title: "National house price index",
                  subtitle: "Seasonally adjusted FHFA monthly index",
                  unit: "index",
                  series: [
                    {
                      series_key: "national_hpi",
                      label: "United States",
                      unit: "index",
                      points: [
                        { label: "2025-11", value: 432.1 },
                        { label: "2025-12", value: 435.8 },
                        { label: "2026-01", value: 437.2 },
                      ],
                    },
                  ],
                },
              ],
              detail_view: {
                title: "Latest FHFA housing snapshot",
                rows: [
                  {
                    label: "United States",
                    unit: "index",
                    current_value: 437.2,
                    prior_value: 416.9,
                    change: 20.3,
                    change_percent: 0.0487,
                    as_of: "2026-01",
                    note: "Prior value is the same month one year earlier",
                  },
                ],
              },
              confidence_flags: [],
              as_of: "2026-01",
              last_refreshed_at: "2026-03-28T00:00:00Z",
            },
          ],
          fetched_at: "2026-03-28T00:00:00Z",
          refresh: { triggered: false, reason: "fresh", ticker: "KBH", job_id: null },
          provenance: [
            {
              source_id: "fhfa_house_price_index",
              source_tier: "official_statistical",
              display_label: "FHFA House Price Index",
              url: "https://www.fhfa.gov/data/hpi/datasets",
              default_freshness_ttl_seconds: 86400,
              disclosure_note: "Official FHFA home-price index used for housing and mortgage exposure context.",
              role: "primary",
              as_of: "2026-01",
              last_refreshed_at: "2026-03-28T00:00:00Z",
            },
          ],
          as_of: "2026-01",
          last_refreshed_at: "2026-03-28T00:00:00Z",
          source_mix: {
            source_ids: ["fhfa_house_price_index"],
            source_tiers: ["official_statistical"],
            primary_source_ids: ["fhfa_house_price_index"],
            fallback_source_ids: [],
            official_only: true,
          },
          confidence_flags: [],
        },
      })
    );

    expect(screen.getByText("Housing Exposure")).toBeTruthy();
    expect(screen.getByText("Matched plug-ins: 1")).toBeTruthy();
    expect(screen.getByText("National HPI")).toBeTruthy();
    expect(screen.getByText("National house price index")).toBeTruthy();
    expect(screen.getByText("Latest FHFA housing snapshot")).toBeTruthy();
  });
});
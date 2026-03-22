// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarketContextPanel } from "@/components/models/market-context-panel";

describe("MarketContextPanel", () => {
  it("renders treasury slopes and partial provenance badges", () => {
    render(
      React.createElement(MarketContextPanel, {
        context: {
          company: null,
          status: "partial",
          curve_points: [
            { tenor: "rrp", rate: 0.048, observation_date: "2026-03-21" },
            { tenor: "1m", rate: 0.0455, observation_date: "2026-03-21" },
            { tenor: "2m", rate: 0.0452, observation_date: "2026-03-21" },
            { tenor: "2y", rate: 0.04, observation_date: "2026-03-21" },
            { tenor: "3m", rate: 0.045, observation_date: "2026-03-21" },
            { tenor: "4m", rate: 0.0447, observation_date: "2026-03-21" },
            { tenor: "6m", rate: 0.0442, observation_date: "2026-03-21" },
            { tenor: "1y", rate: 0.043, observation_date: "2026-03-21" },
            { tenor: "3y", rate: 0.0408, observation_date: "2026-03-21" },
            { tenor: "5y", rate: 0.0405, observation_date: "2026-03-21" },
            { tenor: "7y", rate: 0.0416, observation_date: "2026-03-21" },
            { tenor: "10y", rate: 0.0425, observation_date: "2026-03-21" },
            { tenor: "20y", rate: 0.0448, observation_date: "2026-03-21" },
            { tenor: "30y", rate: 0.0461, observation_date: "2026-03-21" },
          ],
          slope_2s10s: { label: "2s10s", value: 0.0025, short_tenor: "2y", long_tenor: "10y", observation_date: "2026-03-21" },
          slope_3m10y: { label: "3m10y", value: -0.0025, short_tenor: "3m", long_tenor: "10y", observation_date: "2026-03-21" },
          fred_series: [],
          provenance: {
            treasury: { status: "ok" },
            fred: { enabled: false, status: "missing_api_key" },
          },
          fetched_at: "2026-03-22T00:00:00Z",
          refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        },
      })
    );

    expect(screen.getByText("Status: Partial")).toBeTruthy();
    expect(screen.getByText("2s10s")).toBeTruthy();
    expect(screen.getByText("3m10y")).toBeTruthy();
    expect(screen.getByText("RRP")).toBeTruthy();
    expect(screen.getByText("4M")).toBeTruthy();
    expect(screen.getByText(/Supplemental macro indicators are unavailable/i)).toBeTruthy();
  });
});

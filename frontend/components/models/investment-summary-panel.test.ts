// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InvestmentSummaryPanel } from "@/components/models/investment-summary-panel";

vi.mock("recharts", () => ({
  PolarAngleAxis: () => React.createElement("div"),
  RadialBar: () => React.createElement("div"),
  RadialBarChart: ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children),
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children),
}));

describe("InvestmentSummaryPanel", () => {
  it("uses valuation ranges vs latest price and shows net debt separately", () => {
    render(
      React.createElement(InvestmentSummaryPanel, {
        ticker: "ACME",
        models: [
          {
            model_name: "dcf",
            model_version: "2.1.0",
            calculation_version: "dcf_ev_bridge_v1",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              calculation_version: "dcf_ev_bridge_v1",
              fair_value_per_share: 120,
              net_debt: 50000000,
            },
          },
          {
            model_name: "residual_income",
            model_version: "1.0.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              intrinsic_value: {
                intrinsic_value_per_share: 110,
              },
            },
          },
          {
            model_name: "piotroski",
            model_version: "1.0.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: { score: 7, score_max: 9, available_criteria: 9 },
          },
        ],
        financials: [
          {
            filing_type: "10-K",
            statement_type: "annual",
            period_start: "2025-01-01",
            period_end: "2025-12-31",
            source: "sec",
            last_updated: "2026-03-21T00:00:00Z",
            last_checked: "2026-03-21T00:00:00Z",
            revenue: 1000,
            net_income: 100,
            total_assets: 1200,
            total_liabilities: 500,
            eps: 2,
            shares_outstanding: 100,
            segment_breakdown: [],
          },
        ] as never,
        priceHistory: [{ date: "2026-03-21", close: 100, volume: 1000 }],
      })
    );

    expect(screen.getByText(/^Valuation range \/ share$/i)).toBeTruthy();
    expect(screen.getByText(/^Valuation midpoint$/i)).toBeTruthy();
    expect(screen.getByText(/^Latest price$/i)).toBeTruthy();
    expect(screen.getByText(/^Gap vs midpoint$/i)).toBeTruthy();
    expect(screen.getByText(/^Net debt$/i)).toBeTruthy();
    expect(screen.getByText("15.00%")).toBeTruthy();
    expect(screen.getByText("$110.00 - $120.00")).toBeTruthy();
  });

  it("surfaces unsupported valuation state explicitly", () => {
    render(
      React.createElement(InvestmentSummaryPanel, {
        ticker: "BANK",
        models: [
          {
            model_name: "dcf",
            model_version: "2.1.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "unsupported",
            },
          },
        ],
        financials: [],
        priceHistory: [{ date: "2026-03-21", close: 100, volume: 1000 }],
      })
    );

    expect(screen.getByText("Valuation state unsupported")).toBeTruthy();
    expect(screen.getAllByText(/unsupported for this company classification/i)).toHaveLength(2);
  });

  it("omits legacy DCF fair value until the current bridge version is recomputed", () => {
    render(
      React.createElement(InvestmentSummaryPanel, {
        ticker: "ACME",
        models: [
          {
            model_name: "dcf",
            model_version: "2.1.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              fair_value_per_share: 120,
              net_debt: 50000000,
            },
          },
          {
            model_name: "residual_income",
            model_version: "1.0.0",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "supported",
              intrinsic_value: {
                intrinsic_value_per_share: 110,
              },
            },
          },
        ],
        financials: [],
        priceHistory: [{ date: "2026-03-21", close: 100, volume: 1000 }],
      })
    );

    expect(screen.getByText("$110.00 - $110.00")).toBeTruthy();
    expect(screen.getByText(/Legacy cached DCF payload detected/i)).toBeTruthy();
    expect(screen.getByText(/Legacy DCF bridge withheld pending recompute/i)).toBeTruthy();
  });

  it("surfaces enterprise value proxy caveats when capital structure inputs are incomplete", () => {
    render(
      React.createElement(InvestmentSummaryPanel, {
        ticker: "ACME",
        models: [
          {
            model_name: "dcf",
            model_version: "2.4.0",
            calculation_version: "dcf_ev_bridge_v1",
            created_at: "2026-03-22T00:00:00Z",
            input_periods: {},
            result: {
              model_status: "proxy",
              calculation_version: "dcf_ev_bridge_v1",
              value_basis: "enterprise_value_proxy",
              enterprise_value_proxy: 12500000000,
              capital_structure_proxied: true,
              fair_value_per_share: null,
              equity_value: null,
            },
          },
        ],
        financials: [],
        priceHistory: [{ date: "2026-03-21", close: 100, volume: 1000 }],
      })
    );

    expect(screen.getByText(/DCF currently exposes an enterprise value proxy only/i)).toBeTruthy();
    expect(screen.getByText(/Enterprise Value Proxy, not a precise equity fair value/i)).toBeTruthy();
    expect(screen.getByText(/Capital structure incomplete; net-debt bridge is provisional/i)).toBeTruthy();
  });
});


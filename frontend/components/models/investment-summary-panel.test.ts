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

    expect(screen.getByText("Valuation Range / Share")).toBeTruthy();
    expect(screen.getByText("Valuation Midpoint")).toBeTruthy();
    expect(screen.getByText("Latest Price")).toBeTruthy();
    expect(screen.getByText("Gap vs Midpoint")).toBeTruthy();
    expect(screen.getByText("Net Debt")).toBeTruthy();
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
    expect(screen.getByText(/unsupported for this company classification/i)).toBeTruthy();
  });
});


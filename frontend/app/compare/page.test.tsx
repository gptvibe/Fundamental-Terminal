// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ComparePageClient } from "@/components/compare/compare-page-client";

const getCompaniesCompare = vi.fn();

vi.mock("@/lib/api", () => ({
  getCompaniesCompare: (...args: unknown[]) => getCompaniesCompare(...args),
}));

describe("ComparePage", () => {
  beforeEach(() => {
    getCompaniesCompare.mockReset();
  });

  it("renders an empty state when tickers are missing", async () => {
    render(React.createElement(ComparePageClient, { tickers: [] }));

    expect(screen.getByText("No compare tickers provided")).toBeTruthy();
    expect(getCompaniesCompare).not.toHaveBeenCalled();
  });

  it("loads and renders compare tables for requested tickers", async () => {
    getCompaniesCompare.mockResolvedValue({
      tickers: ["AAPL", "MSFT"],
      companies: [
        {
          ticker: "AAPL",
          financials: {
            company: { ticker: "AAPL", name: "Apple Inc.", sector: "Technology", last_checked: "2026-04-01T00:00:00Z" },
            financials: [
              { filing_type: "10-K", period_end: "2025-12-31", revenue: 100, operating_income: 20, net_income: 18, free_cash_flow: 22 },
            ],
          },
          metrics_summary: {
            metrics: [
              { metric_key: "gross_margin", metric_value: 0.45 },
              { metric_key: "operating_margin", metric_value: 0.2 },
              { metric_key: "fcf_margin", metric_value: 0.22 },
              { metric_key: "roic_proxy", metric_value: 0.18 },
              { metric_key: "leverage_ratio", metric_value: 1.1 },
              { metric_key: "share_dilution", metric_value: -0.01 },
            ],
          },
          models: {
            models: [
              { model_name: "dcf", result: { fair_value_per_share: 210 } },
              { model_name: "piotroski", result: { score: 8, score_max: 9, available_criteria: 9 } },
              { model_name: "altman_z", result: { z_score_approximate: 4.2 } },
            ],
          },
        },
        {
          ticker: "MSFT",
          financials: {
            company: { ticker: "MSFT", name: "Microsoft", sector: "Technology", last_checked: "2026-04-01T00:00:00Z" },
            financials: [
              { filing_type: "10-K", period_end: "2025-12-31", revenue: 120, operating_income: 30, net_income: 25, free_cash_flow: 28 },
            ],
          },
          metrics_summary: {
            metrics: [
              { metric_key: "gross_margin", metric_value: 0.5 },
              { metric_key: "operating_margin", metric_value: 0.25 },
              { metric_key: "fcf_margin", metric_value: 0.23 },
              { metric_key: "roic_proxy", metric_value: 0.2 },
              { metric_key: "leverage_ratio", metric_value: 0.9 },
              { metric_key: "share_dilution", metric_value: -0.02 },
            ],
          },
          models: {
            models: [
              { model_name: "dcf", result: { fair_value_per_share: 415 } },
              { model_name: "piotroski", result: { score: 7, score_max: 9, available_criteria: 9 } },
              { model_name: "altman_z", result: { z_score_approximate: 5.1 } },
            ],
          },
        },
      ],
    });

    render(React.createElement(ComparePageClient, { tickers: ["AAPL", "MSFT"] }));

    await waitFor(() => {
      expect(getCompaniesCompare).toHaveBeenCalledWith(["AAPL", "MSFT"], expect.any(Object));
    });
    expect(screen.getByText("Financial Statements")).toBeTruthy();
    expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    expect(screen.getByText("Derived Metrics")).toBeTruthy();
    expect(screen.getByText("Valuation Models")).toBeTruthy();
  });
});
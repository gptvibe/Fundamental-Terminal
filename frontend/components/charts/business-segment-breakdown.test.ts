// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BusinessSegmentBreakdown } from "@/components/charts/business-segment-breakdown";
import type { FinancialPayload, SegmentAnalysisPayload } from "@/lib/types";

vi.mock("recharts", () => {
  const React = require("react");
  const Mock = ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children);
  return {
    ResponsiveContainer: Mock,
    BarChart: Mock,
    Bar: Mock,
    CartesianGrid: Mock,
    Cell: Mock,
    Pie: Mock,
    PieChart: Mock,
    Tooltip: Mock,
    Treemap: Mock,
    XAxis: Mock,
    YAxis: Mock,
  };
});

function financialPayload(periodEnd: string, revenue: number, operatingIncome: number | null, segmentBreakdown: FinancialPayload["segment_breakdown"]): FinancialPayload {
  return {
    filing_type: "10-K",
    statement_type: "canonical_xbrl",
    period_start: `${periodEnd.slice(0, 4)}-01-01`,
    period_end: periodEnd,
    source: "https://data.sec.gov/api/xbrl/companyfacts/CIK0000123456.json",
    last_updated: "2026-03-28T00:00:00Z",
    last_checked: "2026-03-28T00:00:00Z",
    revenue,
    gross_profit: null,
    operating_income: operatingIncome,
    net_income: null,
    total_assets: null,
    current_assets: null,
    total_liabilities: null,
    current_liabilities: null,
    retained_earnings: null,
    sga: null,
    research_and_development: null,
    interest_expense: null,
    income_tax_expense: null,
    inventory: null,
    cash_and_cash_equivalents: null,
    short_term_investments: null,
    cash_and_short_term_investments: null,
    accounts_receivable: null,
    accounts_payable: null,
    goodwill_and_intangibles: null,
    current_debt: null,
    long_term_debt: null,
    stockholders_equity: null,
    lease_liabilities: null,
    operating_cash_flow: null,
    depreciation_and_amortization: null,
    capex: null,
    acquisitions: null,
    debt_changes: null,
    dividends: null,
    share_buybacks: null,
    free_cash_flow: null,
    eps: null,
    shares_outstanding: null,
    stock_based_compensation: null,
    weighted_average_diluted_shares: null,
    segment_breakdown: segmentBreakdown,
    reconciliation: null,
  };
}

describe("BusinessSegmentBreakdown", () => {
  it("renders summary-led business and geography insights before the charts", () => {
    const financials: FinancialPayload[] = [
      financialPayload("2025-12-31", 1000, 260, [
        { segment_id: "cloud", segment_name: "Cloud", axis_key: "StatementBusinessSegmentsAxis", axis_label: "Business Segments", kind: "business", revenue: 520, share_of_revenue: 0.52, operating_income: 170, assets: null },
        { segment_id: "devices", segment_name: "Devices", axis_key: "StatementBusinessSegmentsAxis", axis_label: "Business Segments", kind: "business", revenue: 300, share_of_revenue: 0.30, operating_income: 45, assets: null },
        { segment_id: "services", segment_name: "Services", axis_key: "StatementBusinessSegmentsAxis", axis_label: "Business Segments", kind: "business", revenue: 180, share_of_revenue: 0.18, operating_income: 45, assets: null },
        { segment_id: "us", segment_name: "United States", axis_key: "StatementGeographicalAxis", axis_label: "Geographic Segments", kind: "geographic", revenue: 610, share_of_revenue: 0.61, operating_income: null, assets: null },
        { segment_id: "emea", segment_name: "EMEA", axis_key: "StatementGeographicalAxis", axis_label: "Geographic Segments", kind: "geographic", revenue: 210, share_of_revenue: 0.21, operating_income: null, assets: null },
        { segment_id: "apac", segment_name: "APAC", axis_key: "StatementGeographicalAxis", axis_label: "Geographic Segments", kind: "geographic", revenue: 180, share_of_revenue: 0.18, operating_income: null, assets: null },
      ]),
      financialPayload("2024-12-31", 900, 220, [
        { segment_id: "cloud", segment_name: "Cloud", axis_key: "StatementBusinessSegmentsAxis", axis_label: "Business Segments", kind: "business", revenue: 410, share_of_revenue: 0.4556, operating_income: 125, assets: null },
        { segment_id: "devices", segment_name: "Devices", axis_key: "StatementBusinessSegmentsAxis", axis_label: "Business Segments", kind: "business", revenue: 340, share_of_revenue: 0.3778, operating_income: 55, assets: null },
        { segment_id: "services", segment_name: "Services", axis_key: "StatementBusinessSegmentsAxis", axis_label: "Business Segments", kind: "business", revenue: 150, share_of_revenue: 0.1667, operating_income: 40, assets: null },
        { segment_id: "us", segment_name: "United States", axis_key: "StatementGeographicalAxis", axis_label: "Geographic Segments", kind: "geographic", revenue: 520, share_of_revenue: 0.5778, operating_income: null, assets: null },
        { segment_id: "emea", segment_name: "EMEA", axis_key: "StatementGeographicalAxis", axis_label: "Geographic Segments", kind: "geographic", revenue: 190, share_of_revenue: 0.2111, operating_income: null, assets: null },
        { segment_id: "apac", segment_name: "APAC", axis_key: "StatementGeographicalAxis", axis_label: "Geographic Segments", kind: "geographic", revenue: 190, share_of_revenue: 0.2111, operating_income: null, assets: null },
      ]),
    ];
    const segmentAnalysis: SegmentAnalysisPayload = {
      business: {
        kind: "business",
        axis_label: "Business Segments",
        as_of: "2025-12-31",
        last_refreshed_at: "2026-03-28T00:00:00Z",
        provenance_sources: ["sec_companyfacts"],
        confidence_score: 0.84,
        confidence_flags: ["business_dominant_segment"],
        summary: "Mix shifted most in Cloud +6.4 pts and Devices -7.8 pts; the top two business lines now represent 82.0% of revenue.",
        top_mix_movers: [
          { segment_id: "cloud", segment_name: "Cloud", kind: "business", status: "existing", current_revenue: 520, previous_revenue: 410, revenue_delta: 110, current_share_of_revenue: 0.52, previous_share_of_revenue: 0.4556, share_delta: 0.0644, operating_income: 170, operating_margin: 0.3269, previous_operating_margin: 0.3049, operating_margin_delta: 0.022, share_of_operating_income: 0.6538 },
          { segment_id: "devices", segment_name: "Devices", kind: "business", status: "existing", current_revenue: 300, previous_revenue: 340, revenue_delta: -40, current_share_of_revenue: 0.30, previous_share_of_revenue: 0.3778, share_delta: -0.0778, operating_income: 45, operating_margin: 0.15, previous_operating_margin: 0.1618, operating_margin_delta: -0.0118, share_of_operating_income: 0.1731 },
        ],
        top_margin_contributors: [
          { segment_id: "cloud", segment_name: "Cloud", kind: "business", status: "existing", current_revenue: 520, previous_revenue: 410, revenue_delta: 110, current_share_of_revenue: 0.52, previous_share_of_revenue: 0.4556, share_delta: 0.0644, operating_income: 170, operating_margin: 0.3269, previous_operating_margin: 0.3049, operating_margin_delta: 0.022, share_of_operating_income: 0.6538 },
        ],
        concentration: { segment_count: 3, top_segment_id: "cloud", top_segment_name: "Cloud", top_segment_share: 0.52, top_two_share: 0.82, hhi: 0.3928 },
        unusual_disclosures: [
          { code: "business_dominant_segment", label: "Mix is concentrated in one line", detail: "Cloud accounts for 52.0% of the latest business revenue mix.", severity: "medium" },
        ],
      },
      geographic: {
        kind: "geographic",
        axis_label: "Geographic Segments",
        as_of: "2025-12-31",
        last_refreshed_at: "2026-03-28T00:00:00Z",
        provenance_sources: ["sec_companyfacts"],
        confidence_score: 0.76,
        confidence_flags: ["geographic_revenue_only"],
        summary: "Mix shifted most in United States +3.2 pts and APAC -3.1 pts; the top two geographic lines now represent 82.0% of revenue.",
        top_mix_movers: [
          { segment_id: "us", segment_name: "United States", kind: "geographic", status: "existing", current_revenue: 610, previous_revenue: 520, revenue_delta: 90, current_share_of_revenue: 0.61, previous_share_of_revenue: 0.5778, share_delta: 0.0322, operating_income: null, operating_margin: null, previous_operating_margin: null, operating_margin_delta: null, share_of_operating_income: null },
          { segment_id: "apac", segment_name: "APAC", kind: "geographic", status: "existing", current_revenue: 180, previous_revenue: 190, revenue_delta: -10, current_share_of_revenue: 0.18, previous_share_of_revenue: 0.2111, share_delta: -0.0311, operating_income: null, operating_margin: null, previous_operating_margin: null, operating_margin_delta: null, share_of_operating_income: null },
        ],
        top_margin_contributors: [],
        concentration: { segment_count: 3, top_segment_id: "us", top_segment_name: "United States", top_segment_share: 0.61, top_two_share: 0.82, hhi: 0.4526 },
        unusual_disclosures: [
          { code: "geographic_revenue_only", label: "Geographic disclosure is revenue-only", detail: "The latest geographic disclosure reports revenue by region or country without segment margin detail.", severity: "info" },
        ],
      },
    };

    render(React.createElement(BusinessSegmentBreakdown, { financials, segmentAnalysis }));

    expect(screen.getByText("What Moved The Business Mix")).toBeTruthy();
    expect(screen.getByText(/Mix shifted most in Cloud \+6.4 pts/i)).toBeTruthy();
    expect(screen.getByText("Margin Contribution")).toBeTruthy();
    expect(screen.getByText("Mix is concentrated in one line")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Geography" }));

    expect(screen.getByText("What Moved The Geographic Mix")).toBeTruthy();
    expect(screen.getByText("Geographic disclosure is revenue-only")).toBeTruthy();
    expect(screen.getAllByText(/United States/i).length).toBeGreaterThan(0);
  });
});
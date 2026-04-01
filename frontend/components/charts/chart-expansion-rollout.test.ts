// @vitest-environment jsdom

import * as React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { BalanceSheetChart } from "@/components/charts/balance-sheet-chart";
import { BeneficialOwnershipFormChart } from "@/components/charts/beneficial-ownership-form-chart";
import { CapitalMarketsSignalChart } from "@/components/charts/capital-markets-signal-chart";
import { CashFlowWaterfallChart } from "@/components/charts/cash-flow-waterfall-chart";
import { EarningsTrendChart } from "@/components/charts/earnings-trend-chart";
import { FilingEventCategoryChart } from "@/components/charts/filing-event-category-chart";
import { FinancialHistoryLineChart } from "@/components/charts/financial-history-line-chart";
import { GovernanceFilingChart } from "@/components/charts/governance-filing-chart";
import { GrowthWaterfallChart } from "@/components/charts/growth-waterfall-chart";
import { InsiderActivityTrendChart } from "@/components/charts/insider-activity-trend-chart";
import { InsiderRoleActivityChart } from "@/components/charts/insider-role-activity-chart";
import { InstitutionalOwnershipTrendChart } from "@/components/charts/institutional-ownership-trend-chart";
import { LiquidityCapitalChart } from "@/components/charts/liquidity-capital-chart";
import { MarginTrendChart } from "@/components/charts/margin-trend-chart";
import { OperatingCostStructureChart } from "@/components/charts/operating-cost-structure-chart";
import { ShareDilutionTrackerChart } from "@/components/charts/share-dilution-tracker-chart";
import { SmartMoneyFlowChart } from "@/components/charts/smart-money-flow-chart";

function makeFinancial(overrides: Record<string, unknown>) {
  return {
    filing_type: "10-K",
    statement_type: "income_statement",
    period_start: "2024-01-01",
    period_end: "2024-12-31",
    source: "https://www.sec.gov/Archives/example",
    last_updated: "2026-03-01T00:00:00Z",
    last_checked: "2026-03-01T00:00:00Z",
    revenue: 1000,
    gross_profit: 600,
    operating_income: 240,
    net_income: 180,
    total_assets: 1600,
    current_assets: 520,
    total_liabilities: 700,
    current_liabilities: 260,
    retained_earnings: 320,
    sga: 140,
    research_and_development: 80,
    interest_expense: 18,
    income_tax_expense: 38,
    inventory: 90,
    cash_and_cash_equivalents: 220,
    short_term_investments: 0,
    cash_and_short_term_investments: 220,
    accounts_receivable: 120,
    accounts_payable: 95,
    goodwill_and_intangibles: 140,
    current_debt: 60,
    long_term_debt: 310,
    stockholders_equity: 900,
    lease_liabilities: 40,
    operating_cash_flow: 260,
    depreciation_and_amortization: 44,
    capex: 72,
    acquisitions: 20,
    debt_changes: 35,
    dividends: 16,
    share_buybacks: 24,
    free_cash_flow: 188,
    eps: 2.4,
    shares_outstanding: 500,
    stock_based_compensation: 28,
    weighted_average_diluted_shares: 490,
    segment_breakdown: [],
    reconciliation: null,
    ...overrides,
  } as any;
}

const financials = [
  makeFinancial({ period_start: "2024-01-01", period_end: "2024-12-31", filing_type: "10-K", revenue: 1200, gross_profit: 720, operating_income: 280, net_income: 210, total_assets: 1800, total_liabilities: 760, current_assets: 560, current_liabilities: 250, retained_earnings: 360, operating_cash_flow: 290, free_cash_flow: 210, shares_outstanding: 520 }),
  makeFinancial({ period_start: "2023-01-01", period_end: "2023-12-31", filing_type: "10-K", revenue: 1000, gross_profit: 610, operating_income: 240, net_income: 180, total_assets: 1600, total_liabilities: 700, current_assets: 520, current_liabilities: 260, retained_earnings: 320, operating_cash_flow: 260, free_cash_flow: 188, shares_outstanding: 500 }),
  makeFinancial({ period_start: "2024-07-01", period_end: "2024-09-30", filing_type: "10-Q", revenue: 310, gross_profit: 188, operating_income: 70, net_income: 52, total_assets: 1760, total_liabilities: 740, current_assets: 545, current_liabilities: 255, retained_earnings: 342, operating_cash_flow: 74, free_cash_flow: 52, shares_outstanding: 515 }),
  makeFinancial({ period_start: "2024-04-01", period_end: "2024-06-30", filing_type: "10-Q", revenue: 295, gross_profit: 179, operating_income: 66, net_income: 48, total_assets: 1710, total_liabilities: 725, current_assets: 532, current_liabilities: 252, retained_earnings: 334, operating_cash_flow: 69, free_cash_flow: 48, shares_outstanding: 510 }),
] as any;

const beneficialFilings = [
  { base_form: "SC 13G", is_amendment: false },
  { base_form: "SC 13G", is_amendment: true },
  { base_form: "SC 13D", is_amendment: false },
] as any;

const filingEvents = [
  { category: "Financing", filing_date: "2024-03-12", report_date: "2024-03-12" },
  { category: "Capital Markets", filing_date: "2025-02-10", report_date: "2025-02-10" },
  { category: "Leadership", filing_date: "2024-06-01", report_date: "2024-06-01" },
] as any;

const governanceFilings = [
  { form: "DEF 14A" },
  { form: "DEFA14A" },
  { form: "DEF 14A" },
] as any;

const earnings = [
  { reported_period_label: "Q4 2024", reported_period_end: "2024-12-31", filing_date: "2025-02-01", report_date: "2025-02-01", revenue: 1200, diluted_eps: 2.4, parse_state: "parsed" },
  { reported_period_label: "Q4 2023", reported_period_end: "2023-12-31", filing_date: "2024-02-01", report_date: "2024-02-01", revenue: 1000, diluted_eps: 2.1, parse_state: "parsed" },
] as any;

const insiderTrades = [
  { date: "2025-01-15", transaction_code: "P", action: "buy", value: 120000, shares: 1000, price: 120, name: "Jane Doe", role: "Chief Executive Officer" },
  { date: "2025-02-11", transaction_code: "S", action: "sell", value: 48000, shares: 400, price: 120, name: "John Smith", role: "Director" },
  { date: "2025-03-03", transaction_code: "P", action: "buy", value: 36000, shares: 300, price: 120, name: "Jamie Lee", role: "Chief Financial Officer" },
] as any;

const holdings = [
  { fund_name: "Alpha Fund", reporting_date: "2024-03-31", shares_held: 120, change_in_shares: 20, value: 12000 },
  { fund_name: "Alpha Fund", reporting_date: "2023-12-31", shares_held: 100, change_in_shares: 10, value: 9000 },
  { fund_name: "Beta Partners", reporting_date: "2024-03-31", shares_held: 45, change_in_shares: -15, value: 4500 },
  { fund_name: "Beta Partners", reporting_date: "2023-12-31", shares_held: 60, change_in_shares: 5, value: 5400 },
  { fund_name: "Gamma Capital", reporting_date: "2024-03-31", shares_held: 30, change_in_shares: 10, value: 3300 },
  { fund_name: "Gamma Capital", reporting_date: "2023-12-31", shares_held: 20, change_in_shares: 4, value: 1800 },
] as any;

const financialHistory = [
  { year: 2021, revenue: 820 },
  { year: 2022, revenue: 900 },
  { year: 2023, revenue: 1000 },
  { year: 2024, revenue: 1200 },
] as any;

const expansionFactories: Array<[string, () => React.ReactElement]> = [
  ["BalanceSheetChart", () => React.createElement(BalanceSheetChart, { financials })],
  ["BeneficialOwnershipFormChart", () => React.createElement(BeneficialOwnershipFormChart, { filings: beneficialFilings })],
  ["CapitalMarketsSignalChart", () => React.createElement(CapitalMarketsSignalChart, { financials, events: filingEvents })],
  ["CashFlowWaterfallChart", () => React.createElement(CashFlowWaterfallChart, { financials })],
  ["EarningsTrendChart", () => React.createElement(EarningsTrendChart, { earnings })],
  ["FilingEventCategoryChart", () => React.createElement(FilingEventCategoryChart, { events: filingEvents })],
  ["GovernanceFilingChart", () => React.createElement(GovernanceFilingChart, { filings: governanceFilings })],
  ["GrowthWaterfallChart", () => React.createElement(GrowthWaterfallChart, { financials, visibleFinancials: financials })],
  ["InsiderActivityTrendChart", () => React.createElement(InsiderActivityTrendChart, { trades: insiderTrades })],
  ["InsiderRoleActivityChart", () => React.createElement(InsiderRoleActivityChart, { trades: insiderTrades })],
  ["InstitutionalOwnershipTrendChart", () => React.createElement(InstitutionalOwnershipTrendChart, { holdings, financials })],
  ["LiquidityCapitalChart", () => React.createElement(LiquidityCapitalChart, { financials })],
  ["MarginTrendChart", () => React.createElement(MarginTrendChart, { financials })],
  ["OperatingCostStructureChart", () => React.createElement(OperatingCostStructureChart, { financials })],
  ["ShareDilutionTrackerChart", () => React.createElement(ShareDilutionTrackerChart, { financials })],
  ["SmartMoneyFlowChart", () => React.createElement(SmartMoneyFlowChart, { holdings })],
];

describe("chart expansion rollout", () => {
  it.each(expansionFactories)("exposes shared expansion for %s", async (_name, buildElement) => {
    const user = userEvent.setup();

    render(buildElement());

    await user.click(screen.getByRole("button", { name: /expand/i }));

    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("does not show timeframe controls for snapshot charts", async () => {
    const user = userEvent.setup();

    render(React.createElement(BeneficialOwnershipFormChart, { filings: beneficialFilings }));

    await user.click(screen.getByRole("button", { name: /expand/i }));

    expect(screen.queryByRole("group", { name: "Window" })).toBeNull();
  });

  it("shows timeframe controls only for charts that support them", async () => {
    const user = userEvent.setup();

    render(
      React.createElement(FinancialHistoryLineChart, {
        data: financialHistory,
        metric: "revenue",
        color: "var(--accent)",
        label: "Revenue history",
      })
    );

    await user.click(screen.getByRole("button", { name: /expand revenue history/i }));

    expect(screen.getByRole("group", { name: "Window" })).toBeTruthy();
  });

  it("shows chart type and timeframe controls for margin trend", async () => {
    const user = userEvent.setup();

    render(React.createElement(MarginTrendChart, { financials }));

    await user.click(screen.getByRole("button", { name: /expand margin trend/i }));

    expect(screen.getByRole("group", { name: "Chart type" })).toBeTruthy();
    const windowGroup = screen.getByRole("group", { name: "Window" });
    expect(windowGroup).toBeTruthy();
    expect(within(windowGroup).getByRole("button", { name: "MAX" })).toBeTruthy();
  });

  it("filters timeframe options for stacked operating cost charts", async () => {
    const user = userEvent.setup();

    render(React.createElement(OperatingCostStructureChart, { financials }));

    await user.click(screen.getByRole("button", { name: /expand operating cost structure/i }));

    expect(screen.getByRole("group", { name: "Chart type" })).toBeTruthy();
    const windowGroup = screen.getByRole("group", { name: "Window" });
    expect(within(windowGroup).queryByRole("button", { name: "1Y" })).toBeNull();
    expect(within(windowGroup).getByRole("button", { name: "3Y" })).toBeTruthy();
  });

  it("keeps share dilution on timeframe-only controls", async () => {
    const user = userEvent.setup();

    render(React.createElement(ShareDilutionTrackerChart, { financials }));

    await user.click(screen.getByRole("button", { name: /expand share dilution tracker/i }));

    expect(screen.queryByRole("group", { name: "Chart type" })).toBeNull();
    expect(screen.getByRole("group", { name: "Window" })).toBeTruthy();
  });
});
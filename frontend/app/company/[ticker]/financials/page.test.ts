// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompanyFinancialsTabPage from "@/app/company/[ticker]/financials/page";

const workspaceFixture = vi.hoisted(() => ({ current: null as any }));
const navigationFixture = vi.hoisted(() => ({
  pathname: "/company/acme/financials",
  searchParams: new URLSearchParams(),
  replace: vi.fn(),
}));

function makeWorkspaceFixture() {
  return {
    data: {
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        last_checked: "2026-03-22T00:00:00Z",
        last_checked_financials: "2026-03-22T00:00:00Z",
        last_checked_prices: "2026-03-21T00:00:00Z",
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        cache_state: "fresh",
        regulated_entity: null,
      },
      financials: [],
      price_history: [],
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
          last_refreshed_at: "2026-03-21T00:00:00Z",
        },
      ],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
      source_mix: {
        source_ids: ["sec_companyfacts", "yahoo_finance"],
        source_tiers: ["commercial_fallback", "official_regulator"],
        primary_source_ids: ["sec_companyfacts"],
        fallback_source_ids: ["yahoo_finance"],
        official_only: false,
      },
      confidence_flags: ["commercial_fallback_present"],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: 1,
        fallback_ratio: 0.1,
        stale_flags: [],
        parser_confidence: 0.95,
        missing_field_flags: [],
        reconciliation_penalty: 0.05,
        reconciliation_disagreement_count: 1,
      },
    },
    company: {
      ticker: "ACME",
      name: "Acme Corp",
      sector: "Technology",
      cache_state: "fresh",
      last_checked: "2026-03-22T00:00:00Z",
      last_checked_financials: "2026-03-22T00:00:00Z",
      last_checked_prices: "2026-03-21T00:00:00Z",
      regulated_entity: null,
    },
    financials: [],
    annualStatements: [],
    priceHistory: [],
    latestFinancial: {
      filing_type: "10-K",
      statement_type: "canonical_xbrl",
      period_start: "2025-01-01",
      period_end: "2025-12-31",
      source: "https://data.sec.gov/api/xbrl/companyfacts/CIK0000001.json",
      last_updated: "2026-03-22T00:00:00Z",
      last_checked: "2026-03-22T00:00:00Z",
      revenue: 1_000_000_000,
      gross_profit: null,
      operating_income: 300_000_000,
      net_income: 200_000_000,
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
      segment_breakdown: [],
      regulated_bank: null,
      reconciliation: {
        status: "disagreement",
        as_of: "2025-12-31",
        last_refreshed_at: "2026-03-22T00:00:00Z",
        provenance_sources: ["sec_companyfacts", "sec_edgar"],
        confidence_score: 0.95,
        confidence_penalty: 0.05,
        confidence_flags: ["revenue_reconciliation_disagreement"],
        missing_field_flags: [],
        matched_accession_number: "0000001-26-000010",
        matched_filing_type: "10-K",
        matched_period_start: "2025-01-01",
        matched_period_end: "2025-12-31",
        matched_source: "https://www.sec.gov/Archives/edgar/data/1/000000126000010/form10k.htm",
        disagreement_count: 1,
        comparisons: [
          {
            metric_key: "revenue",
            status: "disagreement",
            companyfacts_value: 1_000_000_000,
            filing_parser_value: 980_000_000,
            delta: -20_000_000,
            relative_delta: 0.02,
            confidence_penalty: 0.05,
            companyfacts_fact: {
              accession_number: "0000001-26-000010",
              form: "10-K",
              taxonomy: "us-gaap",
              tag: "RevenueFromContractWithCustomerExcludingAssessedTax",
              unit: "USD",
              source: "https://data.sec.gov/api/xbrl/companyfacts/CIK0000001.json",
              filed_at: "2026-02-01",
              period_start: "2025-01-01",
              period_end: "2025-12-31",
              value: 1_000_000_000,
            },
            filing_parser_fact: {
              accession_number: "0000001-26-000010",
              form: "10-K",
              taxonomy: null,
              tag: null,
              unit: null,
              source: "https://www.sec.gov/Archives/edgar/data/1/000000126000010/form10k.htm",
              filed_at: null,
              period_start: "2025-01-01",
              period_end: "2025-12-31",
              value: 980_000_000,
            },
          },
        ],
      },
    },
    loading: false,
    error: null,
    refreshing: false,
    refreshState: null,
    consoleEntries: [],
    connectionState: "connected",
    queueRefresh: vi.fn(),
    reloadKey: "reload-1",
  };
}

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
  useRouter: () => ({ replace: navigationFixture.replace }),
  usePathname: () => navigationFixture.pathname,
  useSearchParams: () => navigationFixture.searchParams,
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => workspaceFixture.current,
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) => React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, subtitle, aside, children }: { title: React.ReactNode; subtitle?: React.ReactNode; aside?: React.ReactNode; children?: React.ReactNode }) =>
    React.createElement(
      "section",
      null,
      React.createElement("div", null, React.createElement("h2", null, title), subtitle ? React.createElement("p", null, subtitle) : null, aside),
      children
    ),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/company/capital-structure-intelligence-panel", () => ({
  CapitalStructureIntelligencePanel: () => React.createElement("div", null, "capital-structure-panel"),
}));

describe("CompanyFinancialsTabPage", () => {
  beforeEach(() => {
    workspaceFixture.current = makeWorkspaceFixture();
    navigationFixture.searchParams = new URLSearchParams();
    navigationFixture.replace.mockReset();
  });

  it("renders registry-backed source freshness metadata for financials", () => {
    render(React.createElement(CompanyFinancialsTabPage));

    expect(screen.getByText("Source & Freshness")).toBeTruthy();
    expect(screen.getByText("Capital Structure Intelligence")).toBeTruthy();
    expect(screen.getByText("Period & Comparison")).toBeTruthy();
    expect(screen.getByText("Annual Financial Comparison")).toBeTruthy();
    expect(screen.getAllByText("Point-in-Time Composition").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Period Comparison").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Historical Trends").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Annual only").length).toBe(2);
    expect(screen.getByText("Statement Reconciliation")).toBeTruthy();
    expect(screen.getByText(/RevenueFromContractWithCustomerExcludingAssessedTax/i)).toBeTruthy();
    expect(screen.getByText("revenue_reconciliation_disagreement")).toBeTruthy();
    expect(screen.getByText("SEC Company Facts (XBRL)")).toBeTruthy();
    expect(screen.getAllByText("Yahoo Finance").length).toBeGreaterThan(0);
    expect(screen.getAllByText("commercial_fallback").length).toBeGreaterThan(0);
    expect(screen.getByText(/Price history and market profile data on this surface includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();
  });

  it("switches to the regulated bank workspace for bank issuers", () => {
    const bankStatement = {
      ...workspaceFixture.current.latestFinancial,
      filing_type: "CALL",
      statement_type: "canonical_bank_regulatory",
      source: "https://api.fdic.gov/banks/financials",
      revenue: null,
      operating_income: null,
      free_cash_flow: null,
      regulated_bank: {
        source_id: "fdic_bankfind_financials",
        reporting_basis: "fdic_call_report",
        confidence_score: 0.94,
        confidence_flags: ["matched_by_cert"],
        net_interest_income: 1_200_000_000,
        noninterest_income: 400_000_000,
        noninterest_expense: 900_000_000,
        pretax_income: 500_000_000,
        provision_for_credit_losses: 200_000_000,
        deposits_total: 80_000_000_000,
        core_deposits: 60_000_000_000,
        uninsured_deposits: 12_000_000_000,
        loans_net: 55_000_000_000,
        net_interest_margin: 0.038,
        nonperforming_assets_ratio: 0.011,
        common_equity_tier1_ratio: 0.121,
        tier1_risk_weighted_ratio: 0.133,
        total_risk_based_capital_ratio: 0.149,
        return_on_assets_ratio: 0.011,
        return_on_equity_ratio: 0.124,
        tangible_common_equity: 9_000_000_000,
      },
    };
    workspaceFixture.current.company = {
      ...workspaceFixture.current.company,
      sector: "Financials",
      regulated_entity: {
        issuer_type: "bank",
        reporting_basis: "fdic_call_report",
        confidence_score: 0.98,
        confidence_flags: [],
      },
    };
    workspaceFixture.current.data.company = {
      ...workspaceFixture.current.data.company,
      sector: "Financials",
      market_sector: "Financials",
      market_industry: "Banks",
      regulated_entity: workspaceFixture.current.company.regulated_entity,
    };
    workspaceFixture.current.latestFinancial = bankStatement;
    workspaceFixture.current.financials = [bankStatement];
    workspaceFixture.current.annualStatements = [bankStatement];

    render(React.createElement(CompanyFinancialsTabPage));

    expect(screen.getByText("Regulated Bank Snapshot")).toBeTruthy();
    expect(screen.getByText("Derived Bank Metrics")).toBeTruthy();
    expect(screen.getByText("Regulated Bank Statements")).toBeTruthy();
    expect(screen.getAllByText("Point-in-Time Composition").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Period Comparison").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Historical Trends").length).toBeGreaterThan(0);
    expect(screen.getByText("FDIC / FR Y-9C + SEC")).toBeTruthy();
    expect(screen.getAllByText("3.80%").length).toBeGreaterThan(0);
    expect(screen.queryByText("Capital Structure Intelligence")).toBeNull();
  });
});

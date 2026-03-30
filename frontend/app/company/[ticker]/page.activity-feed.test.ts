// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import CompanyResearchBriefPage from "@/app/company/[ticker]/page";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import {
  getCompanyActivityOverview,
  getCompanyBeneficialOwnershipSummary,
  getCompanyCapitalMarketsSummary,
  getCompanyCapitalStructure,
  getCompanyChangesSinceLastFiling,
  getCompanyEarningsSummary,
  getCompanyGovernanceSummary,
  getCompanyModels,
  getCompanyPeers,
} from "@/lib/api";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: vi.fn(),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) =>
    React.createElement("div", null, children, rail),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ primaryActionLabel, children }: { primaryActionLabel: string; children?: React.ReactNode }) =>
    React.createElement(
      "aside",
      null,
      React.createElement("button", { type: "button" }, primaryActionLabel),
      children,
    ),
}));

vi.mock("@/components/layout/company-research-header", () => ({
  CompanyResearchHeader: ({ title, children }: { title: string; children?: React.ReactNode }) =>
    React.createElement("header", null, React.createElement("h1", null, title), children),
  CompanyMetricGrid: ({ items }: { items: Array<{ label: string; value: string | null }> }) =>
    React.createElement(
      "div",
      null,
      items.map((item) => React.createElement("span", { key: item.label }, `${item.label}: ${item.value ?? "?"}`)),
    ),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, subtitle, aside, children }: { title: React.ReactNode; subtitle?: React.ReactNode; aside?: React.ReactNode; children?: React.ReactNode }) =>
    React.createElement(
      "section",
      null,
      React.createElement("h2", null, title),
      subtitle ? React.createElement("p", null, subtitle) : null,
      aside,
      children,
    ),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/alerts/risk-red-flag-panel", () => ({
  RiskRedFlagPanel: () => React.createElement("div", null, "risk-red-flags"),
}));

vi.mock("@/components/charts/price-fundamentals-module", () => ({
  PriceFundamentalsModule: () => React.createElement("div", null, "price-fundamentals"),
}));

vi.mock("@/components/charts/business-segment-breakdown", () => ({
  BusinessSegmentBreakdown: () => React.createElement("div", null, "segment-breakdown"),
}));

vi.mock("@/components/company/changes-since-last-filing-card", () => ({
  ChangesSinceLastFilingCard: () => React.createElement("div", null, "changes-since-last-filing"),
}));

vi.mock("@/components/company/financial-quality-summary", () => ({
  FinancialQualitySummary: () => React.createElement("div", null, "financial-quality-summary"),
}));

vi.mock("@/components/charts/margin-trend-chart", () => ({
  MarginTrendChart: () => React.createElement("div", null, "margin-trend-chart"),
}));

vi.mock("@/components/charts/cash-flow-waterfall-chart", () => ({
  CashFlowWaterfallChart: () => React.createElement("div", null, "cash-flow-waterfall"),
}));

vi.mock("@/components/charts/share-dilution-tracker-chart", () => ({
  ShareDilutionTrackerChart: () => React.createElement("div", null, "share-dilution-tracker"),
}));

vi.mock("@/components/company/capital-structure-intelligence-panel", () => ({
  CapitalStructureIntelligencePanel: () => React.createElement("div", null, "capital-structure-panel"),
}));

vi.mock("@/components/models/investment-summary-panel", () => ({
  InvestmentSummaryPanel: () => React.createElement("div", null, "investment-summary-panel"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyActivityOverview: vi.fn(),
  getCompanyBeneficialOwnershipSummary: vi.fn(),
  getCompanyCapitalMarketsSummary: vi.fn(),
  getCompanyCapitalStructure: vi.fn(),
  getCompanyChangesSinceLastFiling: vi.fn(),
  getCompanyEarningsSummary: vi.fn(),
  getCompanyGovernanceSummary: vi.fn(),
  getCompanyModels: vi.fn(),
  getCompanyPeers: vi.fn(),
}));

const refresh = { triggered: false, reason: "fresh", ticker: "ACME", job_id: null } as const;

const provenance = [
  {
    source_id: "sec_companyfacts",
    source_tier: "official_regulator",
    display_label: "SEC Company Facts (XBRL)",
    url: "https://data.sec.gov/api/xbrl/companyfacts/",
    default_freshness_ttl_seconds: 21600,
    disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
    role: "primary",
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-10T00:00:00Z",
  },
  {
    source_id: "yahoo_finance",
    source_tier: "commercial_fallback",
    display_label: "Yahoo Finance",
    url: "https://finance.yahoo.com/",
    default_freshness_ttl_seconds: 3600,
    disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
    role: "fallback",
    as_of: "2026-03-10",
    last_refreshed_at: "2026-03-10T00:00:00Z",
  },
];

const sourceMix = {
  source_ids: ["sec_companyfacts", "yahoo_finance"],
  source_tiers: ["commercial_fallback", "official_regulator"],
  primary_source_ids: ["sec_companyfacts"],
  fallback_source_ids: ["yahoo_finance"],
  official_only: false,
};

beforeAll(() => {
  class MockIntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }

  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useCompanyWorkspace).mockReturnValue(buildWorkspaceMock());
  vi.mocked(getCompanyActivityOverview).mockResolvedValue(buildActivityOverviewResponse());
  vi.mocked(getCompanyChangesSinceLastFiling).mockResolvedValue(buildChangesResponse());
  vi.mocked(getCompanyEarningsSummary).mockResolvedValue(buildEarningsSummaryResponse());
  vi.mocked(getCompanyCapitalStructure).mockResolvedValue(buildCapitalStructureResponse());
  vi.mocked(getCompanyCapitalMarketsSummary).mockResolvedValue(buildCapitalMarketsSummaryResponse());
  vi.mocked(getCompanyGovernanceSummary).mockResolvedValue(buildGovernanceSummaryResponse());
  vi.mocked(getCompanyBeneficialOwnershipSummary).mockResolvedValue(buildOwnershipSummaryResponse());
  vi.mocked(getCompanyModels).mockResolvedValue(buildModelsResponse());
  vi.mocked(getCompanyPeers).mockResolvedValue(buildPeersResponse());
});

describe("CompanyResearchBriefPage", () => {
  it("renders the six narrative brief sections with fallback and monitoring cues", async () => {
    render(React.createElement(CompanyResearchBriefPage));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Snapshot" })).toBeTruthy();
    });

    expect(screen.getByRole("button", { name: "Refresh Brief Data" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "What Changed" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Business Quality" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Capital & Risk" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Valuation" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Monitor" })).toBeTruthy();
    expect(screen.getAllByText("Jane Doe filed Form 144 planned sale").length).toBeGreaterThan(0);
    expect(screen.getAllByText("planned-sale").length).toBeGreaterThan(0);
    expect(screen.getAllByText("planned-sale")[0]?.className).toContain("tone-red");
    expect(screen.getAllByText("high")[0]?.className).toContain("tone-red");
    expect(screen.getByText("Insider watch").closest(".research-brief-checklist-card")?.className).toContain("tone-green");
    expect(screen.getByText(/includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();
    expect(screen.getByText("price-fundamentals")).toBeTruthy();
    expect(screen.getByText("Peer comparison snapshot")).toBeTruthy();
    expect(screen.getByText("DCF-derived fair value gap")).toBeTruthy();
  });

  it("renders deterministic empty states when persisted brief slices are unavailable", async () => {
    vi.mocked(useCompanyWorkspace).mockReturnValue(buildWorkspaceMock({
      financials: [],
      annualStatements: [],
      priceHistory: [],
      fundamentalsTrendData: [],
      latestFinancial: null,
      insiderData: null,
      institutionalHoldings: [],
      data: {
        provenance,
        source_mix: sourceMix,
        as_of: "2025-12-31",
        last_refreshed_at: "2026-03-10T00:00:00Z",
        confidence_flags: [],
        company: null,
        segment_analysis: null,
      },
    }));
    vi.mocked(getCompanyActivityOverview).mockResolvedValue({
      ...buildActivityOverviewResponse(),
      entries: [],
      alerts: [],
      summary: { total: 0, high: 0, medium: 0, low: 0 },
    });
    vi.mocked(getCompanyChangesSinceLastFiling).mockResolvedValue({
      ...buildChangesResponse(),
      current_filing: null,
      previous_filing: null,
      metric_deltas: [],
      new_risk_indicators: [],
      segment_shifts: [],
      share_count_changes: [],
      capital_structure_changes: [],
      amended_prior_values: [],
      summary: {
        filing_type: null,
        current_period_start: null,
        current_period_end: null,
        previous_period_start: null,
        previous_period_end: null,
        metric_delta_count: 0,
        new_risk_indicator_count: 0,
        segment_shift_count: 0,
        share_count_change_count: 0,
        capital_structure_change_count: 0,
        amended_prior_value_count: 0,
      },
    });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue(buildCapitalStructureResponse());
    vi.mocked(getCompanyModels).mockResolvedValue({ ...buildModelsResponse(), models: [] });
    vi.mocked(getCompanyPeers).mockResolvedValue({ ...buildPeersResponse(), peers: [] });

    render(React.createElement(CompanyResearchBriefPage));

    await waitFor(() => {
      expect(screen.getByText("No persisted filing context yet")).toBeTruthy();
    });

    expect(screen.getByText("No cached model outputs yet")).toBeTruthy();
    expect(screen.getByText("No active alerts")).toBeTruthy();
  });
});

function buildWorkspaceMock(overrides: Record<string, unknown> = {}) {
  const financials = [
    {
      filing_type: "10-K",
      period_end: "2025-12-31",
      revenue: 6200,
      free_cash_flow: 1280,
      operating_income: 1400,
      net_income: 1120,
      total_liabilities: 4300,
      total_assets: 9800,
      segment_breakdown: [
        {
          segment_id: "core",
          segment_name: "Core Platform",
          axis_key: null,
          axis_label: null,
          kind: "business",
          revenue: 4100,
          share_of_revenue: 0.661,
          operating_income: 1010,
          assets: 5200,
        },
      ],
    },
    {
      filing_type: "10-K",
      period_end: "2024-12-31",
      revenue: 5700,
      free_cash_flow: 1140,
      operating_income: 1180,
      net_income: 930,
      total_liabilities: 4150,
      total_assets: 9100,
      segment_breakdown: [],
    },
  ];

  return {
    data: {
      provenance,
      source_mix: sourceMix,
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-10T00:00:00Z",
      confidence_flags: [],
      company: {
        ticker: "ACME",
        name: "Acme Corp",
      },
      segment_analysis: null,
    },
    company: {
      ticker: "ACME",
      cik: "0000001",
      name: "Acme Corp",
      sector: "Technology",
      market_sector: "Technology",
      strict_official_mode: false,
      last_checked: "2026-03-10T00:00:00Z",
      last_checked_financials: "2026-03-10T00:00:00Z",
      last_checked_prices: "2026-03-10T00:00:00Z",
      last_checked_insiders: "2026-03-10T00:00:00Z",
      cache_state: "fresh",
    },
    financials,
    annualStatements: financials,
    priceHistory: [
      { date: "2026-03-07", close: 109 },
      { date: "2026-03-10", close: 112 },
    ],
    fundamentalsTrendData: [
      { date: "2024-12-31", revenue: 5700, eps: 3.78, free_cash_flow: 1140 },
      { date: "2025-12-31", revenue: 6200, eps: 4.52, free_cash_flow: 1280 },
    ],
    latestFinancial: financials[0],
    insiderData: {
      summary: {
        sentiment: "bullish",
        summary_lines: ["Net open-market insider buying remained positive."],
        metrics: {
          total_buy_value: 1800000,
          total_sell_value: 250000,
          net_value: 1550000,
          unique_insiders_buying: 2,
          unique_insiders_selling: 1,
        },
      },
    },
    insiderTrades: [],
    institutionalHoldings: [
      {
        reporting_date: "2025-12-31",
        fund_manager: "Long Horizon Capital",
        fund_name: "Long Horizon Capital",
      },
    ],
    loading: false,
    error: null,
    insiderError: null,
    institutionalError: null,
    refreshing: false,
    refreshState: null,
    consoleEntries: [],
    connectionState: "open",
    queueRefresh: vi.fn(),
    reloadKey: "brief-1",
    ...overrides,
  };
}

function buildActivityOverviewResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp", last_checked: "2026-03-10T00:00:00Z" },
    entries: [
      {
        id: "entry-144",
        date: "2026-03-10",
        type: "form144",
        badge: "144",
        title: "Jane Doe filed Form 144 planned sale",
        detail: "Planned sale 2026-03-18 | Jane Doe | 12,500 shares | $2,500,000",
        href: null,
      },
    ],
    alerts: [
      {
        id: "alert-1",
        level: "high",
        title: "Working capital tightened",
        detail: "Current ratio compressed quarter over quarter.",
        source: "derived-metrics",
        date: "2026-03-10",
        href: null,
      },
    ],
    summary: { total: 1, high: 1, medium: 0, low: 0 },
    provenance: [
      {
        source_id: "ft_activity_overview",
        source_tier: "derived_from_official",
        display_label: "Fundamental Terminal Activity Overview",
        url: "https://github.com/gptvibe/Fundamental-Terminal",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Unified activity feed assembled from official SEC disclosures and official macro status signals.",
        role: "derived",
        as_of: "2026-03-10",
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
    ],
    as_of: "2026-03-10",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: {
      source_ids: ["ft_activity_overview", "sec_edgar"],
      source_tiers: ["derived_from_official", "official_regulator"],
      primary_source_ids: ["sec_edgar"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    refresh,
    error: null,
  };
}

function buildChangesResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    current_filing: {
      accession_number: "0000001-26-000001",
      filing_type: "10-K",
      statement_type: "annual",
      period_start: "2025-01-01",
      period_end: "2025-12-31",
      source: "sec",
      last_updated: "2026-03-10T00:00:00Z",
      last_checked: "2026-03-10T00:00:00Z",
      filing_acceptance_at: "2026-03-10T00:00:00Z",
      fetch_timestamp: "2026-03-10T00:00:00Z",
    },
    previous_filing: {
      accession_number: "0000001-25-000001",
      filing_type: "10-K",
      statement_type: "annual",
      period_start: "2024-01-01",
      period_end: "2024-12-31",
      source: "sec",
      last_updated: "2025-03-10T00:00:00Z",
      last_checked: "2025-03-10T00:00:00Z",
      filing_acceptance_at: "2025-03-10T00:00:00Z",
      fetch_timestamp: "2025-03-10T00:00:00Z",
    },
    summary: {
      filing_type: "10-K",
      current_period_start: "2025-01-01",
      current_period_end: "2025-12-31",
      previous_period_start: "2024-01-01",
      previous_period_end: "2024-12-31",
      metric_delta_count: 2,
      new_risk_indicator_count: 1,
      segment_shift_count: 1,
      share_count_change_count: 1,
      capital_structure_change_count: 1,
      amended_prior_value_count: 0,
    },
    metric_deltas: [
      {
        metric_key: "revenue",
        label: "Revenue",
        unit: "usd",
        previous_value: 5700,
        current_value: 6200,
        delta: 500,
        relative_change: 0.0877,
        direction: "increase",
      },
    ],
    new_risk_indicators: [
      {
        indicator_key: "working_capital",
        label: "Working capital compression",
        severity: "high",
        description: "Current ratio compressed year over year.",
        current_value: 1.8,
        previous_value: 2.1,
      },
    ],
    segment_shifts: [
      {
        segment_id: "core",
        segment_name: "Core Platform",
        kind: "business",
        current_revenue: 4100,
        previous_revenue: 3800,
        revenue_delta: 300,
        current_share_of_revenue: 0.661,
        previous_share_of_revenue: 0.645,
        share_delta: 0.016,
        direction: "increase",
      },
    ],
    share_count_changes: [],
    capital_structure_changes: [],
    amended_prior_values: [],
    provenance: [],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: {
      source_ids: ["sec_companyfacts"],
      source_tiers: ["official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    refresh,
    diagnostics: {} as never,
  };
}

function buildEarningsSummaryResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    summary: {
      total_releases: 2,
      parsed_releases: 2,
      metadata_only_releases: 0,
      releases_with_guidance: 1,
      releases_with_buybacks: 1,
      releases_with_dividends: 1,
      latest_filing_date: "2026-03-09",
      latest_report_date: "2026-03-09",
      latest_reported_period_end: "2025-12-31",
      latest_revenue: 6200,
      latest_operating_income: 1400,
      latest_net_income: 1120,
      latest_diluted_eps: 4.52,
    },
    refresh,
    diagnostics: {} as never,
    error: null,
  };
}

function buildCapitalStructureResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    latest: null,
    history: [],
    last_capital_structure_check: null,
    provenance: [],
    as_of: null,
    last_refreshed_at: null,
    source_mix: {
      source_ids: ["sec_companyfacts"],
      source_tiers: ["official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    refresh,
    diagnostics: {} as never,
  };
}

function buildCapitalMarketsSummaryResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    summary: {
      total_filings: 2,
      late_filer_notices: 0,
      registration_filings: 1,
      prospectus_filings: 1,
      latest_filing_date: "2026-02-22",
      max_offering_amount: 500,
    },
    refresh,
    diagnostics: {} as never,
    error: null,
  };
}

function buildGovernanceSummaryResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    summary: {
      total_filings: 3,
      definitive_proxies: 1,
      supplemental_proxies: 2,
      filings_with_meeting_date: 1,
      filings_with_exec_comp: 1,
      filings_with_vote_items: 1,
      latest_meeting_date: "2026-02-15",
      max_vote_item_count: 4,
    },
    refresh,
    diagnostics: {} as never,
    error: null,
  };
}

function buildOwnershipSummaryResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    summary: {
      total_filings: 2,
      initial_filings: 1,
      amendments: 1,
      unique_reporting_persons: 2,
      latest_filing_date: "2026-03-05",
      latest_event_date: "2026-03-05",
      max_reported_percent: 0.09,
      chains_with_amendments: 1,
      amendments_with_delta: 1,
      ownership_increase_events: 1,
      ownership_decrease_events: 0,
      ownership_unchanged_events: 0,
      largest_increase_pp: 0.02,
      largest_decrease_pp: null,
    },
    refresh,
    error: null,
  };
}

function buildModelsResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp", strict_official_mode: false },
    requested_models: ["dcf", "residual_income", "ratios", "dupont", "piotroski", "altman_z"],
    models: [
      {
        model_name: "dcf",
        model_version: "v1",
        created_at: "2026-03-10T00:00:00Z",
        input_periods: {},
        result: {
          fair_value_per_share: 130,
          net_debt: 420,
          model_status: "supported",
        },
      },
      {
        model_name: "residual_income",
        model_version: "v1",
        created_at: "2026-03-10T00:00:00Z",
        input_periods: {},
        result: {
          intrinsic_value: { intrinsic_value_per_share: 125 },
          primary_for_sector: true,
          model_status: "supported",
        },
      },
      {
        model_name: "ratios",
        model_version: "v1",
        created_at: "2026-03-10T00:00:00Z",
        input_periods: {},
        result: {
          values: {
            revenue_growth: 0.09,
            net_margin: 0.18,
            liabilities_to_assets: 0.44,
            equity_ratio: 0.56,
          },
        },
      },
      {
        model_name: "dupont",
        model_version: "v1",
        created_at: "2026-03-10T00:00:00Z",
        input_periods: {},
        result: {
          net_profit_margin: 0.18,
        },
      },
      {
        model_name: "piotroski",
        model_version: "v1",
        created_at: "2026-03-10T00:00:00Z",
        input_periods: {},
        result: {
          score: 8,
          score_max: 9,
        },
      },
      {
        model_name: "altman_z",
        model_version: "v1",
        created_at: "2026-03-10T00:00:00Z",
        input_periods: {},
        result: {
          z_score_approximate: 4.1,
        },
      },
    ],
    provenance,
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: sourceMix,
    confidence_flags: [],
    refresh,
    diagnostics: {} as never,
  };
}

function buildPeersResponse() {
  return {
    company: { ticker: "ACME", name: "Acme Corp" },
    peer_basis: "cached peer universe",
    available_companies: [],
    selected_tickers: ["MSFT"],
    peers: [
      {
        ticker: "ACME",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        is_focus: true,
        cache_state: "fresh",
        last_checked: "2026-03-10T00:00:00Z",
        period_end: "2025-12-31",
        price_date: "2026-03-10",
        latest_price: 112,
        pe: 24,
        ev_to_ebit: 18,
        price_to_free_cash_flow: 20,
        roe: 0.2,
        revenue_growth: 0.09,
        piotroski_score: 8,
        altman_z_score: 4.1,
        fair_value_gap: 0.14,
        roic: 0.17,
        shareholder_yield: 0.03,
        implied_growth: 0.07,
        valuation_band_percentile: 0.62,
        revenue_history: [],
      },
      {
        ticker: "MSFT",
        name: "Microsoft",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        is_focus: false,
        cache_state: "fresh",
        last_checked: "2026-03-10T00:00:00Z",
        period_end: "2025-12-31",
        price_date: "2026-03-10",
        latest_price: 418,
        pe: 31,
        ev_to_ebit: 23,
        price_to_free_cash_flow: 29,
        roe: 0.28,
        revenue_growth: 0.11,
        piotroski_score: 8,
        altman_z_score: 5.2,
        fair_value_gap: 0.08,
        roic: 0.21,
        shareholder_yield: 0.025,
        implied_growth: 0.09,
        valuation_band_percentile: 0.58,
        revenue_history: [],
      },
    ],
    notes: {
      fair_value_gap: "DCF-derived fair value gap",
      ev_to_ebit: "Enterprise value versus EBIT from cached peer metrics",
    },
    provenance: [],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: {
      source_ids: ["sec_companyfacts"],
      source_tiers: ["official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    refresh,
  };
}

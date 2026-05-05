import { describe, expect, it } from "vitest";

import { investmentMemoFixture } from "@/lib/__fixtures__/investment-memo-fixture";
import { buildInvestmentMemo } from "@/lib/investment-memo";
import type { InvestmentMemoInput } from "@/lib/investment-memo";

// ---------------------------------------------------------------------------
// Fixture helpers
// ---------------------------------------------------------------------------

function buildMinimalInput(overrides: Partial<InvestmentMemoInput> = {}): InvestmentMemoInput {
  return {
    ticker: "ACME",
    exportedAt: "2026-05-04T12:00:00.000Z",
    company: {
      ticker: "ACME",
      name: "Acme Corp",
      cik: "0000123456",
      sector: "Technology",
      market_industry: "Software",
      last_checked: "2026-03-10T00:00:00Z",
      cache_state: "fresh",
    },
    asOf: "2025-12-31",
    lastRefreshedAt: "2026-03-10T00:00:00Z",
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
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
    ],
    sourceMix: {
      source_ids: ["sec_companyfacts"],
      source_tiers: ["official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: [],
      official_only: true,
    },
    filingTimeline: [
      {
        date: "2025-12-31",
        form: "10-K",
        description: "Annual report",
        accession: "0000123456-26-000001",
      },
      {
        date: "2025-09-30",
        form: "10-Q",
        description: "Quarterly report",
        accession: "0000123456-25-000002",
      },
    ],
    latestFinancial: {
      filing_type: "10-K",
      statement_type: "annual",
      period_start: "2025-01-01",
      period_end: "2025-12-31",
      source: "sec_companyfacts",
      last_updated: "2026-03-10T00:00:00Z",
      last_checked: "2026-03-10T00:00:00Z",
      revenue: 6_200_000_000,
      gross_profit: 3_800_000_000,
      operating_income: 1_500_000_000,
      net_income: 1_200_000_000,
      total_assets: 25_000_000_000,
      current_assets: 8_000_000_000,
      total_liabilities: 12_000_000_000,
      current_liabilities: 3_000_000_000,
      retained_earnings: 5_000_000_000,
      sga: 1_000_000_000,
      research_and_development: 800_000_000,
      interest_expense: 150_000_000,
      income_tax_expense: 300_000_000,
      inventory: 500_000_000,
      cash_and_cash_equivalents: 2_000_000_000,
      short_term_investments: 500_000_000,
      cash_and_short_term_investments: 2_500_000_000,
      accounts_receivable: 1_200_000_000,
      accounts_payable: 600_000_000,
      goodwill_and_intangibles: 4_000_000_000,
      current_debt: 200_000_000,
      long_term_debt: 3_500_000_000,
      stockholders_equity: 13_000_000_000,
      lease_liabilities: 400_000_000,
      operating_cash_flow: 2_000_000_000,
      depreciation_and_amortization: 300_000_000,
      capex: 500_000_000,
      acquisitions: null,
      debt_changes: null,
      dividends: 200_000_000,
      share_buybacks: 400_000_000,
      free_cash_flow: 1_500_000_000,
      eps: 3.25,
      shares_outstanding: 400_000_000,
      stock_based_compensation: 120_000_000,
      weighted_average_diluted_shares: 385_000_000,
      segment_breakdown: [
        {
          segment_name: "Core Platform",
          revenue: 4_092_000_000,
          share_of_revenue: 0.661,
        },
        {
          segment_name: "Services",
          revenue: 2_108_000_000,
          share_of_revenue: 0.339,
        },
      ],
      reconciliation: null,
    },
    annualStatementsCount: 5,
    topSegment: {
      segment_name: "Core Platform",
      revenue: 4_092_000_000,
      share_of_revenue: 0.661,
    },
    snapshotNarrative:
      "Acme Corp last reported $6.20B of revenue and $1.50B of free cash flow; Core Platform contributes 66.1% of reported revenue; 2 current alerts are already on the monitor.",
    whatChangedNarrative:
      "The latest comparable filing surfaced 3 curated high-signal changes and 0 comment-letter updates.",
    businessQualityNarrative:
      "Revenue is up 8.5% year over year, operating margin sits at 24.2%, free-cash-flow margin at 24.2%, and debt-to-assets at 48.0%.",
    capitalRiskNarrative:
      "Near-term debt due is $200.00M, net dilution is 2.1%, governance coverage spans 3 proxy filings.",
    valuationNarrative:
      "Cached model anchors put intrinsic value about 15.0% above the latest price.",
    monitorNarrative:
      "2 alerts are currently on the monitor for ACME.",
    capitalSignalRows: [
      {
        signal: "Capital markets",
        currentRead: "4 filings · largest offering $500.00M",
        latestEvidence: "Mar 10, 2026",
      },
      {
        signal: "Governance",
        currentRead: "3 proxy filings · 2 with vote items",
        latestEvidence: "Jun 15, 2025",
      },
    ],
    monitorChecklist: [
      {
        title: "Refresh status",
        detail: "No refresh queued. Last full company check ran on Mar 10, 2026.",
      },
      {
        title: "Alert count",
        detail: "0 high, 2 medium, and 0 low alerts are currently active.",
      },
    ],
    changes: {
      current_filing: null,
      previous_filing: null,
      metric_deltas: [],
      new_risk_indicators: [],
      segment_shifts: [],
      share_count_changes: [],
      capital_structure_changes: [],
      amended_prior_values: [],
      high_signal_changes: [],
      comment_letter_history: {
        total_letters: 0,
        letters_since_previous_filing: 0,
        latest_filing_date: null,
        recent_letters: [],
      },
      summary: {
        filing_type: "10-K",
        current_period_start: "2025-01-01",
        current_period_end: "2025-12-31",
        previous_period_start: "2024-01-01",
        previous_period_end: "2024-12-31",
        metric_delta_count: 42,
        new_risk_indicator_count: 1,
        segment_shift_count: 0,
        share_count_change_count: 2,
        capital_structure_change_count: 1,
        amended_prior_value_count: 0,
        high_signal_change_count: 3,
        comment_letter_count: 0,
      },
    },
    earningsSummary: {
      company: {
        id: 1,
        ticker: "ACME",
        cik: "0000123456",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        last_checked: null,
        cache_state: "fresh",
        strict_official_mode: false,
        last_checked_financials: null,
        last_checked_filings: null,
      },
      summary: {
        latest_revenue: 6_200_000_000,
        latest_diluted_eps: 3.25,
        latest_period_end: "2025-12-31",
        latest_report_date: "2026-02-14",
        period_count: 5,
        has_beats: false,
        beat_count: 0,
        miss_count: 0,
      },
      earnings: [],
    },
    activityOverview: {
      company: {
        id: 1,
        ticker: "ACME",
        cik: "0000123456",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        last_checked: null,
        cache_state: "fresh",
        strict_official_mode: false,
        last_checked_financials: null,
        last_checked_filings: null,
      },
      summary: { total: 2, high: 0, medium: 2, low: 0 },
      alerts: [
        {
          id: "a1",
          title: "Increased share repurchase program",
          severity: "medium",
          date: "2026-02-14",
          category: "capital_structure",
          description: null,
        },
      ],
      entries: [
        {
          id: "e1",
          title: "10-K filed",
          date: "2026-02-14",
          type: "filing",
          severity: "low",
          description: null,
          source_id: "sec_companyfacts",
        },
      ],
    },
    capitalStructure: {
      company: {
        id: 1,
        ticker: "ACME",
        cik: "0000123456",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        last_checked: null,
        cache_state: "fresh",
        strict_official_mode: false,
        last_checked_financials: null,
        last_checked_filings: null,
      },
      latest: {
        period_end: "2025-12-31",
        summary: {
          total_debt: 3_700_000_000,
          lease_liabilities: 400_000_000,
          interest_expense: 150_000_000,
          debt_due_next_twelve_months: 200_000_000,
          lease_due_next_twelve_months: 50_000_000,
          gross_shareholder_payout: 600_000_000,
          net_shareholder_payout: 400_000_000,
          net_share_change: -1_000_000,
          net_dilution_ratio: 0.021,
        },
        debt_schedule: [],
        dilution_sources: [],
      },
      history: [],
    },
    capitalMarketsSummary: null,
    governanceSummary: null,
    ownershipSummary: null,
    models: {
      company: {
        id: 1,
        ticker: "ACME",
        cik: "0000123456",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        last_checked: null,
        cache_state: "fresh",
        strict_official_mode: false,
        last_checked_financials: null,
        last_checked_filings: null,
      },
      models: [
        {
          model_name: "dcf",
          result: {
            fair_value_per_share: 85.5,
          },
          as_of: "2025-12-31",
          status: "ready",
          error: null,
        },
      ],
    },
    peers: {
      company: {
        id: 1,
        ticker: "ACME",
        cik: "0000123456",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        last_checked: null,
        cache_state: "fresh",
        strict_official_mode: false,
        last_checked_financials: null,
        last_checked_filings: null,
      },
      peers: [
        {
          ticker: "ACME",
          name: "Acme Corp",
          sector: "Technology",
          market_sector: "Technology",
          market_industry: "Software",
          is_focus: true,
          cache_state: "fresh" as const,
          last_checked: null,
          period_end: "2025-12-31",
          price_date: "2026-05-04",
          latest_price: 74.0,
          pe: 22.5,
          ev_to_ebit: 14.3,
          price_to_free_cash_flow: 18.0,
          roe: 0.12,
          revenue_growth: 0.085,
          piotroski_score: 7,
          altman_z_score: 3.2,
          fair_value_gap: 0.15,
          roic: 0.14,
          shareholder_yield: 0.04,
          implied_growth: 0.08,
          valuation_band_percentile: 55,
          revenue_history: [],
        },
        {
          ticker: "BETA",
          name: "Beta Inc",
          sector: "Technology",
          market_sector: "Technology",
          market_industry: "Software",
          is_focus: false,
          cache_state: "fresh" as const,
          last_checked: null,
          period_end: "2025-12-31",
          price_date: "2026-05-04",
          latest_price: 45.0,
          pe: 18.2,
          ev_to_ebit: 12.1,
          price_to_free_cash_flow: 14.0,
          roe: 0.09,
          revenue_growth: 0.05,
          piotroski_score: 6,
          altman_z_score: 2.8,
          fair_value_gap: -0.05,
          roic: 0.10,
          shareholder_yield: 0.02,
          implied_growth: 0.05,
          valuation_band_percentile: 40,
          revenue_history: [],
        },
        {
          ticker: "GAMA",
          name: "Gamma Ltd",
          sector: "Technology",
          market_sector: "Technology",
          market_industry: "Software",
          is_focus: false,
          cache_state: "fresh" as const,
          last_checked: null,
          period_end: "2025-12-31",
          price_date: "2026-05-04",
          latest_price: 120.0,
          pe: 25.8,
          ev_to_ebit: 16.9,
          price_to_free_cash_flow: 22.0,
          roe: 0.18,
          revenue_growth: 0.12,
          piotroski_score: 8,
          altman_z_score: 4.1,
          fair_value_gap: 0.22,
          roic: 0.20,
          shareholder_yield: 0.05,
          implied_growth: 0.11,
          valuation_band_percentile: 70,
          revenue_history: [],
        },
      ],
    },
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("buildInvestmentMemo", () => {
  it("renders the persisted research-brief fixture into a readable Markdown memo", () => {
    const memo = buildInvestmentMemo(investmentMemoFixture);

    expect(memo).toContain("# Investment Memo: Acme Corp");
    expect(memo).toContain("## Source & Freshness State");
    expect(memo).toContain("## Source Links & Provenance");
    expect(memo).toContain("Core Platform contributes 66.1% of reported revenue");
    expect(memo).toContain("[SEC Company Facts (XBRL)](https://data.sec.gov/api/xbrl/companyfacts/)");
  });

  it("returns a string with the expected top-level heading", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("# Investment Memo: Acme Corp");
  });

  it("includes all nine required sections", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("## Company Identity");
    expect(memo).toContain("## Source & Freshness State");
    expect(memo).toContain("## Business Summary");
    expect(memo).toContain("## What Changed");
    expect(memo).toContain("## Business Quality");
    expect(memo).toContain("## Capital, Risk, Dilution & Governance");
    expect(memo).toContain("## Peer & Valuation Summary");
    expect(memo).toContain("## Monitor Checklist");
    expect(memo).toContain("## Source Links & Provenance");
  });

  it("embeds company identity fields", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("ACME");
    expect(memo).toContain("Acme Corp");
    expect(memo).toContain("0000123456");
    expect(memo).toContain("Technology");
    expect(memo).toContain("Software");
  });

  it("includes the snapshot narrative in the business summary section", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("last reported $6.20B of revenue");
  });

  it("includes financial metrics table with revenue and FCF", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("$6.20B");
    expect(memo).toContain("$1.50B");
  });

  it("shows the correct operating margin in the financial table", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    // Operating income 1.5B / revenue 6.2B ≈ 24.19%
    expect(memo).toMatch(/24\.\d+%/);
  });

  it("includes what-changed narrative and change summary", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("high-signal change");
    expect(memo).toContain("High-signal changes: 3");
    expect(memo).toContain("Total metric deltas: 42");
  });

  it("includes capital signal rows in the capital section", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("Capital markets");
    expect(memo).toContain("Governance");
  });

  it("includes the DCF fair value in the valuation section", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("DCF");
    expect(memo).toContain("$85.50");
  });

  it("includes the peer comparison table", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("BETA");
    expect(memo).toContain("GAMA");
    expect(memo).toContain("22.5");
  });

  it("includes monitor checklist items", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("Refresh status");
    expect(memo).toContain("Alert count");
  });

  it("includes provenance source links", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("SEC Company Facts (XBRL)");
    expect(memo).toContain("https://data.sec.gov/api/xbrl/companyfacts/");
    expect(memo).toContain("official_regulator");
  });

  it("includes the filing timeline", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("10-K");
    expect(memo).toContain("0000123456-26-000001");
  });

  it("includes the export timestamp", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("2026-05-04T12:00:00.000Z");
  });

  it("handles null company gracefully", () => {
    const memo = buildInvestmentMemo(
      buildMinimalInput({
        company: null,
        snapshotNarrative: "Company data not yet available.",
      })
    );
    expect(memo).toContain("# Investment Memo: ACME");
    expect(memo).toContain("## Company Identity");
  });

  it("handles null latestFinancial gracefully", () => {
    const memo = buildInvestmentMemo(
      buildMinimalInput({
        latestFinancial: null,
        topSegment: null,
        annualStatementsCount: 0,
      })
    );
    expect(memo).toContain("## Business Summary");
    expect(memo).not.toContain("Key financials");
  });

  it("handles empty provenance and filing timeline gracefully", () => {
    const memo = buildInvestmentMemo(
      buildMinimalInput({
        provenance: [],
        filingTimeline: [],
      })
    );
    expect(memo).toContain("## Source Links & Provenance");
    expect(memo).toContain("No provenance data is available");
  });

  it("handles null models gracefully", () => {
    const memo = buildInvestmentMemo(buildMinimalInput({ models: null }));
    expect(memo).toContain("## Peer & Valuation Summary");
    expect(memo).not.toContain("DCF");
  });

  it("handles null peers gracefully", () => {
    const memo = buildInvestmentMemo(buildMinimalInput({ peers: null }));
    expect(memo).toContain("## Peer & Valuation Summary");
    expect(memo).not.toContain("BETA");
  });

  it("includes official-source-only label in freshness section", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("official-source-only mode");
  });

  it("includes fallback source label when sourceMix has fallbacks", () => {
    const memo = buildInvestmentMemo(
      buildMinimalInput({
        sourceMix: {
          source_ids: ["sec_companyfacts", "yahoo_finance"],
          source_tiers: ["official_regulator", "commercial_fallback"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        },
      })
    );
    expect(memo).toContain("mixed-source mode");
    expect(memo).toContain("yahoo_finance");
  });

  it("includes the capital structure summary in the capital section", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("Net dilution ratio");
    expect(memo).toContain("Debt due next 12 months");
  });

  it("includes activity alert top items when available", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo).toContain("Increased share repurchase program");
  });

  it("produces a memo that starts with a top-level heading", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo.trimStart()).toMatch(/^# /);
  });

  it("produces a memo that ends with a generation timestamp footer", () => {
    const memo = buildInvestmentMemo(buildMinimalInput());
    expect(memo.trimEnd()).toContain("cached workspace data at");
  });
});

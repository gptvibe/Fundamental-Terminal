import { expect, test, type Page, type Route } from "@playwright/test";

const ticker = "ACME";
const cik = "0000000001";

const refresh = {
  triggered: false,
  reason: "fresh",
  ticker,
  job_id: null,
} as const;

const company = {
  ticker,
  cik,
  name: "Acme Corporation",
  sector: "Technology",
  market_sector: "Technology",
  market_industry: "Application Software",
  last_checked: "2026-05-08T00:00:00Z",
  last_checked_financials: "2026-05-08T00:00:00Z",
  last_checked_prices: "2026-05-08T00:00:00Z",
  last_checked_insiders: "2026-05-08T00:00:00Z",
  last_checked_institutional: "2026-05-08T00:00:00Z",
  last_checked_filings: "2026-05-08T00:00:00Z",
  earnings_last_checked: "2026-05-08T00:00:00Z",
  cache_state: "fresh",
} as const;

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
    last_refreshed_at: "2026-05-08T00:00:00Z",
  },
  {
    source_id: "yahoo_finance",
    source_tier: "commercial_fallback",
    display_label: "Yahoo Finance",
    url: "https://finance.yahoo.com/",
    default_freshness_ttl_seconds: 3600,
    disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
    role: "fallback",
    as_of: "2026-05-08",
    last_refreshed_at: "2026-05-08T00:00:00Z",
  },
] as const;

const sourceMix = {
  source_ids: ["sec_companyfacts", "yahoo_finance"],
  source_tiers: ["commercial_fallback", "official_regulator"],
  primary_source_ids: ["sec_companyfacts"],
  fallback_source_ids: ["yahoo_finance"],
  official_only: false,
} as const;

const officialSourceMix = {
  source_ids: ["sec_companyfacts"],
  source_tiers: ["official_regulator"],
  primary_source_ids: ["sec_companyfacts"],
  fallback_source_ids: [],
  official_only: true,
} as const;

const diagnostics = {
  coverage_ratio: 1,
  fallback_ratio: 0,
  stale_flags: [],
  parser_confidence: 0.95,
  missing_field_flags: [],
  reconciliation_penalty: null,
  reconciliation_disagreement_count: 0,
} as const;

const globalMarketContext = {
  provenance: [],
  as_of: "2026-05-08",
  last_refreshed_at: "2026-05-08T00:00:00Z",
  source_mix: {
    source_ids: ["treasury", "fred"],
    source_tiers: ["official_treasury_or_fed", "official_statistical"],
    primary_source_ids: ["treasury", "fred"],
    fallback_source_ids: [],
    official_only: true,
  },
  confidence_flags: [],
  company: null,
  status: "ready",
  curve_points: [
    { tenor: "10y", rate: 0.043, observation_date: "2026-05-08" },
    { tenor: "2y", rate: 0.04, observation_date: "2026-05-08" },
    { tenor: "3m", rate: 0.047, observation_date: "2026-05-08" },
  ],
  slope_2s10s: {
    label: "2s10s",
    value: 0.003,
    short_tenor: "2y",
    long_tenor: "10y",
    observation_date: "2026-05-08",
  },
  slope_3m10y: {
    label: "3m10y",
    value: -0.004,
    short_tenor: "3m",
    long_tenor: "10y",
    observation_date: "2026-05-08",
  },
  fred_series: [
    {
      series_id: "BAA10Y",
      label: "BAA spread",
      category: "credit",
      units: "ratio",
      value: 0.021,
      observation_date: "2026-05-08",
      state: "fresh",
    },
    {
      series_id: "UNRATE",
      label: "Unemployment",
      category: "labor",
      units: "ratio",
      value: 0.041,
      observation_date: "2026-05-08",
      state: "fresh",
    },
  ],
  provenance_details: null,
  fetched_at: "2026-05-08T00:00:00Z",
  refresh,
} as const;

const watchlistSummaryCompanies = [
  {
    ticker: "MSFT",
    name: "Microsoft",
    sector: "Technology",
    cik: "0000789019",
    last_checked: "2026-05-08T00:00:00Z",
    refresh,
    alert_summary: { high: 1, medium: 0, low: 0, total: 1 },
    latest_alert: {
      id: "alert-msft-1",
      level: "high",
      title: "Late filer notice",
      source: "filings",
      date: "2026-05-08",
      href: null,
    },
    latest_activity: {
      id: "activity-msft-1",
      type: "filing",
      badge: "8-K",
      title: "8-K filed",
      date: "2026-05-07",
      href: null,
    },
    coverage: { financial_periods: 8, price_points: 250 },
    fair_value_gap: 0.08,
    roic: 0.21,
    shareholder_yield: 0.025,
    implied_growth: 0.09,
    valuation_band_percentile: 0.58,
    balance_sheet_risk: 1.8,
  },
  {
    ticker: "NVDA",
    name: "NVIDIA",
    sector: "Technology",
    cik: "0001045810",
    last_checked: "2026-05-08T00:00:00Z",
    refresh,
    alert_summary: { high: 0, medium: 1, low: 0, total: 1 },
    latest_alert: {
      id: "alert-nvda-1",
      level: "medium",
      title: "Valuation stretched",
      source: "models",
      date: "2026-05-08",
      href: null,
    },
    latest_activity: {
      id: "activity-nvda-1",
      type: "event",
      badge: "Update",
      title: "Guidance commentary updated",
      date: "2026-05-06",
      href: null,
    },
    coverage: { financial_periods: 8, price_points: 250 },
    fair_value_gap: -0.06,
    roic: 0.28,
    shareholder_yield: 0.01,
    implied_growth: 0.12,
    valuation_band_percentile: 0.81,
    balance_sheet_risk: 1.2,
  },
] as const;

const homeLocalUserData = {
  watchlist: [
    { ticker: "MSFT", name: "Microsoft", sector: "Technology", savedAt: "2026-05-01T00:00:00.000Z" },
    { ticker: "NVDA", name: "NVIDIA", sector: "Technology", savedAt: "2026-05-02T00:00:00.000Z" },
  ],
  notes: {
    MSFT: {
      ticker: "MSFT",
      name: "Microsoft",
      sector: "Technology",
      note: "Track Azure bookings and capital return mix.",
      updatedAt: "2026-05-08T00:00:00.000Z",
    },
  },
} as const;

const homeRecentCompanies = [
  {
    ticker: "AAPL",
    name: "Apple Inc.",
    sector: "Technology",
    openedAt: "2026-05-07T10:00:00.000Z",
  },
] as const;

const financials = [
  {
    filing_type: "10-K",
    statement_type: "annual",
    period_start: "2025-01-01",
    period_end: "2025-12-31",
    source: "sec",
    last_updated: "2026-02-01T00:00:00Z",
    last_checked: "2026-05-08T00:00:00Z",
    revenue: 6200,
    gross_profit: 3600,
    operating_income: 1400,
    net_income: 1120,
    total_assets: 9800,
    current_assets: 4100,
    total_liabilities: 4300,
    current_liabilities: 1800,
    retained_earnings: 2200,
    sga: 980,
    research_and_development: 640,
    interest_expense: 44,
    income_tax_expense: 180,
    inventory: 210,
    cash_and_cash_equivalents: 1440,
    short_term_investments: 220,
    cash_and_short_term_investments: 1660,
    accounts_receivable: 510,
    accounts_payable: 470,
    goodwill_and_intangibles: 620,
    current_debt: 160,
    long_term_debt: 980,
    stockholders_equity: 5500,
    lease_liabilities: 120,
    operating_cash_flow: 1540,
    depreciation_and_amortization: 180,
    capex: 260,
    acquisitions: 0,
    debt_changes: -90,
    dividends: 120,
    share_buybacks: 220,
    free_cash_flow: 1280,
    eps: 4.52,
    shares_outstanding: 248,
    stock_based_compensation: 98,
    weighted_average_diluted_shares: 250,
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
      {
        segment_id: "cloud",
        segment_name: "Cloud Services",
        axis_key: null,
        axis_label: null,
        kind: "business",
        revenue: 2100,
        share_of_revenue: 0.339,
        operating_income: 390,
        assets: 2100,
      },
    ],
  },
  {
    filing_type: "10-K",
    statement_type: "annual",
    period_start: "2024-01-01",
    period_end: "2024-12-31",
    source: "sec",
    last_updated: "2025-02-01T00:00:00Z",
    last_checked: "2026-05-08T00:00:00Z",
    revenue: 5700,
    gross_profit: 3250,
    operating_income: 1180,
    net_income: 930,
    total_assets: 9100,
    current_assets: 3860,
    total_liabilities: 4150,
    current_liabilities: 1710,
    retained_earnings: 2050,
    sga: 920,
    research_and_development: 590,
    interest_expense: 46,
    income_tax_expense: 150,
    inventory: 190,
    cash_and_cash_equivalents: 1310,
    short_term_investments: 200,
    cash_and_short_term_investments: 1510,
    accounts_receivable: 470,
    accounts_payable: 430,
    goodwill_and_intangibles: 620,
    current_debt: 180,
    long_term_debt: 1020,
    stockholders_equity: 4950,
    lease_liabilities: 126,
    operating_cash_flow: 1380,
    depreciation_and_amortization: 172,
    capex: 240,
    acquisitions: 0,
    debt_changes: -60,
    dividends: 110,
    share_buybacks: 200,
    free_cash_flow: 1140,
    eps: 3.78,
    shares_outstanding: 252,
    stock_based_compensation: 92,
    weighted_average_diluted_shares: 254,
    segment_breakdown: [],
  },
];

const priceHistory = [
  { date: "2026-05-05", close: 101, volume: 1200000 },
  { date: "2026-05-06", close: 104, volume: 1320000 },
  { date: "2026-05-07", close: 107, volume: 1410000 },
  { date: "2026-05-08", close: 109, volume: 1395000 },
];

const earningsReleases = [
  {
    accession_number: "0000001-26-000010",
    form: "8-K",
    filing_date: "2026-05-07",
    report_date: "2026-05-07",
    primary_document: "acme-q2-earnings.htm",
    exhibit_document: "ex99-1.htm",
    exhibit_type: "99.1",
    source_url: "https://www.sec.gov/acme/earnings/q2",
    parse_state: "parsed",
    reported_period_label: "Q2 2026",
    reported_period_end: "2026-04-30",
    revenue: 120,
    operating_income: 35,
    net_income: 28,
    diluted_eps: 1.18,
    revenue_guidance_low: 125,
    revenue_guidance_high: 130,
    eps_guidance_low: 1.2,
    eps_guidance_high: 1.3,
    share_repurchase_amount: 500,
    dividend_per_share: 0.24,
    highlights: ["Revenue grew 18%", "Free cash flow stayed positive"],
  },
  {
    accession_number: "0000001-26-000004",
    form: "8-K",
    filing_date: "2026-02-06",
    report_date: "2026-02-06",
    primary_document: "acme-q1-earnings.htm",
    exhibit_document: "ex99-1.htm",
    exhibit_type: "99.1",
    source_url: "https://www.sec.gov/acme/earnings/q1",
    parse_state: "metadata_only",
    reported_period_label: "Q1 2026",
    reported_period_end: "2026-01-31",
    revenue: 95,
    operating_income: 21,
    net_income: 18,
    diluted_eps: 0.91,
    revenue_guidance_low: null,
    revenue_guidance_high: null,
    eps_guidance_low: null,
    eps_guidance_high: null,
    share_repurchase_amount: null,
    dividend_per_share: null,
    highlights: [],
  },
];

function buildPeersResponse(selectedTickers: string[]) {
  return {
    company,
    peer_basis: "cached peer universe",
    available_companies: [
      { ticker: "ACME", name: "Acme Corporation", sector: "Technology", market_sector: "Technology", market_industry: "Application Software", last_checked: company.last_checked, cache_state: "fresh", is_focus: true },
      { ticker: "MSFT", name: "Microsoft", sector: "Technology", market_sector: "Technology", market_industry: "Software", last_checked: company.last_checked, cache_state: "fresh", is_focus: false },
      { ticker: "GOOG", name: "Alphabet", sector: "Technology", market_sector: "Technology", market_industry: "Internet", last_checked: company.last_checked, cache_state: "fresh", is_focus: false },
    ],
    selected_tickers: selectedTickers,
    peers: [
      {
        ticker: "ACME",
        name: "Acme Corporation",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Application Software",
        is_focus: true,
        cache_state: "fresh",
        last_checked: company.last_checked,
        period_end: "2025-12-31",
        price_date: "2026-05-08",
        latest_price: 109,
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
        revenue_history: [
          { period_end: "2024-12-31", revenue: 5700, revenue_growth: 0.07 },
          { period_end: "2025-12-31", revenue: 6200, revenue_growth: 0.09 },
        ],
      },
      {
        ticker: "MSFT",
        name: "Microsoft",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        is_focus: false,
        cache_state: "fresh",
        last_checked: company.last_checked,
        period_end: "2025-12-31",
        price_date: "2026-05-08",
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
        revenue_history: [
          { period_end: "2024-12-31", revenue: 24500, revenue_growth: 0.1 },
          { period_end: "2025-12-31", revenue: 27200, revenue_growth: 0.11 },
        ],
      },
      {
        ticker: "GOOG",
        name: "Alphabet",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Internet",
        is_focus: false,
        cache_state: "fresh",
        last_checked: company.last_checked,
        period_end: "2025-12-31",
        price_date: "2026-05-08",
        latest_price: 168,
        pe: 26,
        ev_to_ebit: 17,
        price_to_free_cash_flow: 24,
        roe: 0.22,
        revenue_growth: 0.1,
        piotroski_score: 7,
        altman_z_score: 4.8,
        fair_value_gap: 0.11,
        roic: 0.19,
        shareholder_yield: 0.018,
        implied_growth: 0.08,
        valuation_band_percentile: 0.6,
        revenue_history: [
          { period_end: "2024-12-31", revenue: 19800, revenue_growth: 0.09 },
          { period_end: "2025-12-31", revenue: 21800, revenue_growth: 0.1 },
        ],
      },
    ],
    notes: {
      fair_value_gap: "DCF-derived fair value gap",
      roic: "Operating efficiency from cached filings",
    },
    provenance,
    as_of: "2025-12-31",
    last_refreshed_at: "2026-05-08T00:00:00Z",
    source_mix: officialSourceMix,
    confidence_flags: [],
    refresh,
  };
}

function buildResearchBriefResponse(selectedTickers: string[]) {
  return {
    company,
    schema_version: "company_research_brief_v1",
    generated_at: "2026-05-08T00:00:00Z",
    as_of: "2025-12-31",
    refresh,
    build_state: "ready",
    build_status: "Research brief ready.",
    available_sections: ["snapshot", "what_changed", "business_quality", "capital_and_risk", "valuation"],
    section_statuses: [
      { id: "snapshot", title: "Snapshot", state: "ready", available: true, detail: "Available now." },
      { id: "what_changed", title: "What Changed", state: "ready", available: true, detail: "Available now." },
      { id: "business_quality", title: "Business Quality", state: "ready", available: true, detail: "Available now." },
      { id: "capital_and_risk", title: "Capital And Risk", state: "ready", available: true, detail: "Available now." },
      { id: "valuation", title: "Valuation", state: "ready", available: true, detail: "Available now." },
    ],
    filing_timeline: [
      { accession: "0000001-26-000001", form: "10-K", date: "2026-05-08", description: "Annual report posted." },
      { accession: "0000001-26-000010", form: "8-K", date: "2026-05-07", description: "Quarterly earnings release filed." },
    ],
    stale_summary_cards: [
      { key: "latest_filing", title: "Latest Filing", value: "10-K", detail: "2025-12-31" },
      { key: "latest_revenue", title: "Revenue", value: "$6.2K", detail: "2025-12-31" },
      { key: "free_cash_flow", title: "Free Cash Flow", value: "$1.3K", detail: "2025-12-31" },
      { key: "top_segment", title: "Top Segment", value: "Core Platform · 66%", detail: "Latest reported segment" },
    ],
    snapshot: {
      summary: {
        latest_filing_type: "10-K",
        latest_period_end: "2025-12-31",
        annual_statement_count: 2,
        price_history_points: priceHistory.length,
        latest_revenue: 6200,
        latest_free_cash_flow: 1280,
        top_segment_name: "Core Platform",
        top_segment_share_of_revenue: 0.661,
        alert_count: 1,
      },
      provenance,
      as_of: "2025-12-31",
      last_refreshed_at: "2026-05-08T00:00:00Z",
      source_mix: sourceMix,
      confidence_flags: [],
    },
    what_changed: {
      activity_overview: {
        company,
        entries: [
          {
            id: "entry-1",
            date: "2026-05-07",
            type: "earnings",
            badge: "8-K",
            title: "Q2 earnings filing posted",
            detail: "Acme filed its Q2 2026 earnings release through an 8-K Item 2.02 current report.",
            href: "https://www.sec.gov/acme/earnings/q2",
          },
        ],
        alerts: [
          {
            id: "alert-1",
            level: "high",
            title: "Working capital tightened",
            detail: "Current ratio compressed quarter over quarter.",
            source: "derived-metrics",
            date: "2026-05-07",
            href: null,
          },
        ],
        summary: { total: 1, high: 1, medium: 0, low: 0 },
        provenance: [],
        as_of: "2026-05-08",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        market_context_status: {
          state: "fresh",
          label: "Macro context fresh",
          observation_date: "2026-05-06",
          source: "Treasury + BLS",
        },
        refresh,
        error: null,
      },
      changes: {
        company,
        current_filing: {
          accession_number: "0000001-26-000001",
          filing_type: "10-K",
          statement_type: "annual",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
          source: "sec",
          last_updated: "2026-05-08T00:00:00Z",
          last_checked: "2026-05-08T00:00:00Z",
          filing_acceptance_at: "2026-05-08T00:00:00Z",
          fetch_timestamp: "2026-05-08T00:00:00Z",
        },
        previous_filing: {
          accession_number: "0000001-25-000001",
          filing_type: "10-K",
          statement_type: "annual",
          period_start: "2024-01-01",
          period_end: "2024-12-31",
          source: "sec",
          last_updated: "2025-05-08T00:00:00Z",
          last_checked: "2025-05-08T00:00:00Z",
          filing_acceptance_at: "2025-05-08T00:00:00Z",
          fetch_timestamp: "2025-05-08T00:00:00Z",
        },
        summary: {
          filing_type: "10-K",
          current_period_start: "2025-01-01",
          current_period_end: "2025-12-31",
          previous_period_start: "2024-01-01",
          previous_period_end: "2024-12-31",
          high_signal_change_count: 1,
          comment_letter_count: 0,
          metric_delta_count: 2,
          new_risk_indicator_count: 1,
          segment_shift_count: 1,
          share_count_change_count: 1,
          capital_structure_change_count: 1,
          amended_prior_value_count: 0,
        },
        metric_deltas: [],
        new_risk_indicators: [],
        segment_shifts: [],
        share_count_changes: [],
        capital_structure_changes: [],
        amended_prior_values: [],
        high_signal_changes: [
          {
            change_key: "mda-2025-12-31",
            category: "mda",
            importance: "high",
            title: "MD&A discussion changed materially",
            summary: "Management commentary added emphasis on liquidity and margin pressure versus the prior filing.",
            why_it_matters: "Management discussion often surfaces operating pressure before it is fully obvious in the statement tables.",
            signal_tags: ["liquidity", "margin"],
            current_period_end: "2025-12-31",
            previous_period_end: "2024-12-31",
            evidence: [
              {
                label: "Latest MD&A excerpt",
                excerpt: "Liquidity tightened while management highlighted margin pressure.",
                source: "https://www.sec.gov/acme/filings/10k",
                filing_type: "10-K",
                period_end: "2025-12-31",
              },
            ],
          },
        ],
        comment_letter_history: {
          total_letters: 0,
          letters_since_previous_filing: 0,
          latest_filing_date: null,
          recent_letters: [],
        },
        provenance: [],
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      },
      earnings_summary: {
        company,
        summary: {
          total_releases: 2,
          parsed_releases: 1,
          metadata_only_releases: 1,
          releases_with_guidance: 1,
          releases_with_buybacks: 1,
          releases_with_dividends: 1,
          latest_filing_date: "2026-05-07",
          latest_report_date: "2026-05-07",
          latest_reported_period_end: "2026-04-30",
          latest_revenue: 120,
          latest_operating_income: 35,
          latest_net_income: 28,
          latest_diluted_eps: 1.18,
        },
        refresh,
        diagnostics,
        error: null,
      },
      provenance,
      as_of: "2025-12-31",
      last_refreshed_at: "2026-05-08T00:00:00Z",
      source_mix: sourceMix,
      confidence_flags: [],
    },
    business_quality: {
      summary: {
        latest_period_end: "2025-12-31",
        previous_period_end: "2024-12-31",
        annual_statement_count: 2,
        revenue_growth: 0.0877,
        operating_margin: 0.2258,
        free_cash_flow_margin: 0.2064,
        share_dilution: 0.01,
      },
      provenance,
      as_of: "2025-12-31",
      last_refreshed_at: "2026-05-08T00:00:00Z",
      source_mix: sourceMix,
      confidence_flags: [],
    },
    capital_and_risk: {
      as_of: "2025-12-31",
      last_refreshed_at: "2026-05-08T00:00:00Z",
      provenance,
      source_mix: sourceMix,
      confidence_flags: [],
      equity_claim_risk_summary: {
        overall_risk_level: "low",
        dilution_risk_level: "low",
        financing_risk_level: "low",
        reporting_risk_level: "low",
        latest_period_end: "2025-12-31",
        headline: "Dilution pressure remains elevated because recent financing and reporting signals are still active.",
        net_dilution_ratio: 0.03,
        sbc_to_revenue: 0.04,
        shelf_capacity_remaining: 500,
        recent_atm_activity: false,
        recent_warrant_or_convertible_activity: false,
        debt_due_next_twenty_four_months: 200,
        restatement_severity: "low",
        internal_control_flag_count: 0,
        key_points: ["Shelf capacity remains ample for near-term needs."],
      },
      capital_structure: {
        company,
        latest: null,
        history: [],
        last_capital_structure_check: null,
        provenance: [],
        as_of: null,
        last_refreshed_at: null,
        source_mix: officialSourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      },
      capital_markets_summary: {
        company,
        summary: {
          total_filings: 2,
          late_filer_notices: 0,
          registration_filings: 1,
          prospectus_filings: 1,
          latest_filing_date: "2026-04-30",
          max_offering_amount: 500,
        },
        refresh,
        diagnostics,
        error: null,
      },
      governance_summary: {
        company,
        summary: {
          total_filings: 3,
          definitive_proxies: 1,
          supplemental_proxies: 2,
          filings_with_meeting_date: 1,
          filings_with_exec_comp: 1,
          filings_with_vote_items: 1,
          latest_meeting_date: "2026-04-18",
          max_vote_item_count: 4,
        },
        refresh,
        diagnostics,
        error: null,
      },
      ownership_summary: {
        company,
        summary: {
          total_filings: 2,
          initial_filings: 1,
          amendments: 1,
          unique_reporting_persons: 2,
          latest_filing_date: "2026-05-02",
          latest_event_date: "2026-05-02",
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
      },
    },
    valuation: {
      models: {
        company: { ...company, strict_official_mode: false },
        requested_models: ["dcf", "residual_income", "ratios", "dupont", "piotroski", "altman_z"],
        models: [
          {
            model_name: "dcf",
            model_version: "v1",
            created_at: "2026-05-08T00:00:00Z",
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
            created_at: "2026-05-08T00:00:00Z",
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
            created_at: "2026-05-08T00:00:00Z",
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
            created_at: "2026-05-08T00:00:00Z",
            input_periods: {},
            result: {
              net_profit_margin: 0.18,
            },
          },
          {
            model_name: "piotroski",
            model_version: "v1",
            created_at: "2026-05-08T00:00:00Z",
            input_periods: {},
            result: {
              score: 8,
              score_max: 9,
            },
          },
          {
            model_name: "altman_z",
            model_version: "v1",
            created_at: "2026-05-08T00:00:00Z",
            input_periods: {},
            result: {
              z_score_approximate: 4.1,
            },
          },
        ],
        provenance,
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: sourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      },
      peers: buildPeersResponse(selectedTickers),
      provenance,
      as_of: "2025-12-31",
      last_refreshed_at: "2026-05-08T00:00:00Z",
      source_mix: sourceMix,
      confidence_flags: [],
    },
    monitor: {
      activity_overview: {
        company,
        entries: [
          {
            id: "entry-1",
            date: "2026-05-07",
            type: "earnings",
            badge: "8-K",
            title: "Q2 earnings filing posted",
            detail: "Acme filed its Q2 2026 earnings release through an 8-K Item 2.02 current report.",
            href: "https://www.sec.gov/acme/earnings/q2",
          },
        ],
        alerts: [
          {
            id: "alert-1",
            level: "high",
            title: "Working capital tightened",
            detail: "Current ratio compressed quarter over quarter.",
            source: "derived-metrics",
            date: "2026-05-07",
            href: null,
          },
        ],
        summary: { total: 1, high: 1, medium: 0, low: 0 },
        provenance: [],
        as_of: "2026-05-08",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        market_context_status: {
          state: "fresh",
          label: "Macro context fresh",
          observation_date: "2026-05-06",
          source: "Treasury + BLS",
        },
        refresh,
        error: null,
      },
      provenance,
      as_of: "2025-12-31",
      last_refreshed_at: "2026-05-08T00:00:00Z",
      source_mix: sourceMix,
      confidence_flags: [],
    },
  };
}

function json(route: Route, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installCompanyWorkspaceMocks(page: Page) {
  await page.route("**/backend/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const peersParam = url.searchParams.get("peers");
    const selectedPeers = peersParam ? peersParam.split(",").filter(Boolean) : ["MSFT"];

    if (path.endsWith("/source-registry")) {
      return json(route, {
        strict_official_mode: false,
        generated_at: "2026-05-08T00:00:00Z",
        sources: [
          {
            source_id: "sec_companyfacts",
            source_tier: "official_regulator",
            display_label: "SEC Company Facts (XBRL)",
            url: "https://data.sec.gov/api/xbrl/companyfacts/",
            default_freshness_ttl_seconds: 21600,
            disclosure_note: "Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
            strict_official_mode_state: "available",
            strict_official_mode_note: "Core fundamentals remain available in strict official mode.",
          },
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            url: "https://finance.yahoo.com/",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
            strict_official_mode_state: "disabled",
            strict_official_mode_note: "Fallback market context is suppressed when strict official mode is enabled.",
          },
        ],
        health: {
          total_companies_cached: 128,
          average_data_age_seconds: 5400,
          recent_error_window_hours: 24,
          sources_with_recent_errors: [],
        },
      });
    }

    if (path.endsWith("/market-context")) {
      return json(route, globalMarketContext);
    }

    if (path.endsWith("/watchlist/summary")) {
      const body = route.request().postDataJSON() as { tickers?: string[] } | null;
      const requestedTickers = (body?.tickers ?? []).map((item) => item.trim().toUpperCase());
      return json(route, {
        tickers: requestedTickers,
        companies: watchlistSummaryCompanies.filter((item) => requestedTickers.includes(item.ticker)),
      });
    }

    if (path.endsWith(`/companies/${ticker}/financials`)) {
      return json(route, {
        company,
        financials,
        price_history: priceHistory,
        provenance,
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: sourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
        segment_analysis: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/brief`)) {
      return json(route, buildResearchBriefResponse(selectedPeers));
    }

    if (path.endsWith(`/companies/${ticker}/financial-restatements`)) {
      return json(route, {
        company,
        summary: {
          total_restatements: 0,
          amended_filings: 0,
          companyfacts_revisions: 0,
          amended_metric_keys: [],
          changed_periods: [],
          high_confidence_impacts: 0,
          medium_confidence_impacts: 0,
          low_confidence_impacts: 0,
          latest_filing_date: null,
          latest_filing_acceptance_at: null,
        },
        restatements: [],
        provenance: [],
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        refresh,
      });
    }

    if (path.endsWith(`/companies/${ticker}/changes-since-last-filing`)) {
      return json(route, {
        company,
        current_filing: {
          accession_number: "0000001-26-000001",
          filing_type: "10-K",
          statement_type: "annual",
          period_start: "2025-01-01",
          period_end: "2025-12-31",
          source: "sec",
          last_updated: "2026-05-08T00:00:00Z",
          last_checked: "2026-05-08T00:00:00Z",
          filing_acceptance_at: "2026-05-08T00:00:00Z",
          fetch_timestamp: "2026-05-08T00:00:00Z",
        },
        previous_filing: {
          accession_number: "0000001-25-000001",
          filing_type: "10-K",
          statement_type: "annual",
          period_start: "2024-01-01",
          period_end: "2024-12-31",
          source: "sec",
          last_updated: "2025-05-08T00:00:00Z",
          last_checked: "2025-05-08T00:00:00Z",
          filing_acceptance_at: "2025-05-08T00:00:00Z",
          fetch_timestamp: "2025-05-08T00:00:00Z",
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
        high_signal_changes: [
          {
            change_key: "mda-2025-12-31",
            category: "mda",
            importance: "high",
            title: "MD&A discussion changed materially",
            summary: "Management commentary added emphasis on liquidity and margin pressure versus the prior filing.",
            why_it_matters: "Management discussion often surfaces operating pressure before it is fully obvious in the statement tables.",
            signal_tags: ["liquidity", "margin"],
            current_period_end: "2025-12-31",
            previous_period_end: "2024-12-31",
            evidence: [
              {
                label: "Latest MD&A excerpt",
                excerpt: "Liquidity tightened while management highlighted margin pressure.",
                source: "https://www.sec.gov/acme/filings/10k",
                filing_type: "10-K",
                period_end: "2025-12-31",
              },
            ],
          },
        ],
        comment_letter_history: {
          total_letters: 0,
          letters_since_previous_filing: 0,
          latest_filing_date: null,
          recent_letters: [],
        },
        provenance: [],
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      });
    }

    if (path.endsWith(`/companies/${ticker}/capital-structure`)) {
      return json(route, {
        company,
        latest: null,
        history: [],
        last_capital_structure_check: null,
        provenance: [],
        as_of: null,
        last_refreshed_at: null,
        source_mix: officialSourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      });
    }

    if (path.endsWith(`/companies/${ticker}/segment-history`)) {
      const kind = url.searchParams.get("kind") === "geographic" ? "geographic" : "business";
      const years = Number(url.searchParams.get("years") ?? "2");
      return json(route, {
        company,
        kind,
        years,
        periods: [],
        provenance: [],
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      });
    }

    if (path.endsWith(`/companies/${ticker}/activity-overview`)) {
      return json(route, {
        company,
        entries: [
          {
            id: "entry-1",
            date: "2026-05-07",
            type: "earnings",
            badge: "8-K",
            title: "Q2 earnings filing posted",
            detail: "Acme filed its Q2 2026 earnings release through an 8-K Item 2.02 current report.",
            href: "https://www.sec.gov/acme/earnings/q2",
          },
        ],
        alerts: [
          {
            id: "alert-1",
            level: "high",
            title: "Working capital tightened",
            detail: "Current ratio compressed quarter over quarter.",
            source: "derived-metrics",
            date: "2026-05-07",
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
            as_of: "2026-05-08",
            last_refreshed_at: "2026-05-08T00:00:00Z",
          },
        ],
        as_of: "2026-05-08",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: officialSourceMix,
        confidence_flags: [],
        market_context_status: {
          state: "fresh",
          label: "Macro context fresh",
          observation_date: "2026-05-06",
          source: "Treasury + BLS",
        },
        refresh,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/beneficial-ownership/summary`)) {
      return json(route, {
        company,
        summary: {
          total_filings: 2,
          initial_filings: 1,
          amendments: 1,
          unique_reporting_persons: 2,
          latest_filing_date: "2026-05-02",
          latest_event_date: "2026-05-02",
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
      });
    }

    if (path.endsWith(`/companies/${ticker}/governance/summary`)) {
      return json(route, {
        company,
        summary: {
          total_filings: 3,
          definitive_proxies: 1,
          supplemental_proxies: 2,
          filings_with_meeting_date: 1,
          filings_with_exec_comp: 1,
          filings_with_vote_items: 1,
          latest_meeting_date: "2026-04-18",
          max_vote_item_count: 4,
        },
        refresh,
        diagnostics,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/capital-markets/summary`)) {
      return json(route, {
        company,
        summary: {
          total_filings: 2,
          late_filer_notices: 0,
          registration_filings: 1,
          prospectus_filings: 1,
          latest_filing_date: "2026-04-30",
          max_offering_amount: 500,
        },
        refresh,
        diagnostics,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/earnings/summary`)) {
      return json(route, {
        company,
        summary: {
          total_releases: 2,
          parsed_releases: 1,
          metadata_only_releases: 1,
          releases_with_guidance: 1,
          releases_with_buybacks: 1,
          releases_with_dividends: 1,
          latest_filing_date: "2026-05-07",
          latest_report_date: "2026-05-07",
          latest_reported_period_end: "2026-04-30",
          latest_revenue: 120,
          latest_operating_income: 35,
          latest_net_income: 28,
          latest_diluted_eps: 1.18,
        },
        refresh,
        diagnostics,
        error: null,
      });
    }

    if (path.endsWith("/companies/search")) {
      return json(route, {
        query: url.searchParams.get("query") ?? "",
        results: [company],
        refresh,
      });
    }

    if (path.endsWith("/companies/resolve")) {
      return json(route, {
        query: url.searchParams.get("query") ?? "",
        resolved: true,
        ticker,
        name: company.name,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/metrics/summary`)) {
      return json(route, {
        company,
        period_type: "ttm",
        latest_period_end: "2025-12-31",
        metrics: [],
        diagnostics,
        confidence_flags: [],
        last_metrics_check: "2026-05-08T00:00:00Z",
        last_financials_check: "2026-05-08T00:00:00Z",
        last_price_check: "2026-05-08T00:00:00Z",
        staleness_reason: null,
        refresh,
      });
    }

    if (path.endsWith(`/companies/${ticker}/metrics-timeseries`)) {
      return json(route, {
        company,
        series: [],
        last_financials_check: "2026-05-08T00:00:00Z",
        last_price_check: "2026-05-08T00:00:00Z",
        staleness_reason: null,
        refresh,
      });
    }

    if (path.endsWith(`/companies/${ticker}/filing-events`)) {
      return json(route, {
        company,
        events: [
          {
            accession_number: "0000001-26-000010",
            form: "8-K",
            filing_date: "2026-05-07",
            report_date: "2026-05-07",
            items: "2.02",
            item_code: "2.02",
            category: "earnings",
            primary_document: "acme-q2-earnings.htm",
            primary_doc_description: "Quarterly earnings release",
            source_url: "https://www.sec.gov/acme/earnings/q2",
            summary: "Acme reported Q2 earnings and reiterated margin expansion targets.",
            key_amounts: [500],
            exhibit_references: ["99.1"],
          },
        ],
        refresh,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/earnings`)) {
      return json(route, {
        company,
        earnings_releases: earningsReleases,
        refresh,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/capital-markets`)) {
      return json(route, {
        company,
        filings: [],
        refresh,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/insider-trades`)) {
      return json(route, {
        company,
        insider_trades: [],
        summary: {
          sentiment: "neutral",
          summary_lines: [],
          metrics: {
            total_buy_value: 0,
            total_sell_value: 0,
            net_value: 0,
            unique_insiders_buying: 0,
            unique_insiders_selling: 0,
          },
        },
        refresh,
      });
    }

    if (path.endsWith(`/companies/${ticker}/institutional-holdings`)) {
      return json(route, {
        company,
        institutional_holdings: [
          {
            reporting_date: "2025-12-31",
            fund_manager: "Long Horizon Capital",
            fund_name: "Long Horizon Capital",
            shares: 1250000,
            market_value: 136250000,
            filing_type: "13F-HR",
            accession_number: "0002000-26-000001",
            source: "sec",
          },
        ],
        refresh,
      });
    }

    if (path.endsWith(`/companies/${ticker}/beneficial-ownership`)) {
      return json(route, {
        company,
        filings: [],
        refresh,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${ticker}/models`)) {
      return json(route, {
        company: { ...company, strict_official_mode: false },
        requested_models: ["dcf", "residual_income", "ratios", "dupont", "piotroski", "altman_z"],
        models: [
          {
            model_name: "dcf",
            model_version: "v1",
            created_at: "2026-05-08T00:00:00Z",
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
            created_at: "2026-05-08T00:00:00Z",
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
            created_at: "2026-05-08T00:00:00Z",
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
            created_at: "2026-05-08T00:00:00Z",
            input_periods: {},
            result: {
              net_profit_margin: 0.18,
            },
          },
          {
            model_name: "piotroski",
            model_version: "v1",
            created_at: "2026-05-08T00:00:00Z",
            input_periods: {},
            result: {
              score: 8,
              score_max: 9,
            },
          },
          {
            model_name: "altman_z",
            model_version: "v1",
            created_at: "2026-05-08T00:00:00Z",
            input_periods: {},
            result: {
              z_score_approximate: 4.1,
            },
          },
        ],
        provenance,
        as_of: "2025-12-31",
        last_refreshed_at: "2026-05-08T00:00:00Z",
        source_mix: sourceMix,
        confidence_flags: [],
        refresh,
        diagnostics,
      });
    }

    if (path.endsWith(`/companies/${ticker}/peers`)) {
      return json(route, buildPeersResponse(selectedPeers));
    }

    if (path.endsWith(`/companies/${ticker}/earnings/workspace`)) {
      return json(route, {
        company,
        earnings_releases: earningsReleases,
        summary: {
          total_releases: 2,
          parsed_releases: 1,
          metadata_only_releases: 1,
          releases_with_guidance: 1,
          releases_with_buybacks: 1,
          releases_with_dividends: 1,
          latest_filing_date: "2026-05-07",
          latest_report_date: "2026-05-07",
          latest_reported_period_end: "2026-04-30",
          latest_revenue: 120,
          latest_operating_income: 35,
          latest_net_income: 28,
          latest_diluted_eps: 1.18,
        },
        model_points: [
          {
            period_start: "2026-01-01",
            period_end: "2026-04-30",
            filing_type: "10-Q",
            quality_score: 72,
            quality_score_delta: 6,
            eps_drift: 0.27,
            earnings_momentum_drift: 0.08,
            segment_contribution_delta: 0.1,
            release_statement_coverage_ratio: 0.8,
            fallback_ratio: 0.25,
            stale_period_warning: false,
            quality_flags: [],
            source_statement_ids: [101, 102],
            source_release_ids: [10],
            explainability: {
              formula_version: "sec_earnings_intel_v1",
              period_end: "2026-04-30",
              filing_type: "10-Q",
              inputs: [
                {
                  field: "revenue",
                  value: 120,
                  period_end: "2026-04-30",
                  sec_tags: ["us-gaap:Revenues"],
                },
              ],
              component_values: {},
              proxy_usage: {},
              segment_deltas: [],
              release_statement_coverage: {},
              quality_formula: "quality-f",
              eps_drift_formula: "eps-f",
              momentum_formula: "mom-f",
            },
          },
        ],
        backtests: {
          window_sessions: 3,
          quality_directional_consistency: 0.75,
          quality_total_windows: 4,
          quality_consistent_windows: 3,
          eps_directional_consistency: 0.5,
          eps_total_windows: 2,
          eps_consistent_windows: 1,
          windows: [],
        },
        peer_context: {
          peer_group_basis: "market_sector",
          peer_group_size: 8,
          quality_percentile: 0.88,
          eps_drift_percentile: 0.67,
          sector_group_size: 12,
          sector_quality_percentile: 0.84,
          sector_eps_drift_percentile: 0.63,
        },
        alerts: [
          {
            id: "quality-regime:2026-04-30",
            type: "quality_regime_shift",
            level: "high",
            title: "Quality score regime shift",
            detail: "Quality regime moved from mid to high.",
            period_end: "2026-04-30",
          },
        ],
        refresh,
        error: null,
      });
    }

    if (path.endsWith(`/companies/${cik}/financial-history`)) {
      return json(route, {});
    }

    throw new Error(`Unhandled backend route in smoke test: ${path}${url.search}`);
  });
}

test.beforeEach(async ({ page }) => {
  await installCompanyWorkspaceMocks(page);
});

test("home research-entry smoke", async ({ page }) => {
  await page.addInitScript(
    ({ localUserData, recentCompanies }) => {
      window.localStorage.setItem("ft-local-user-data", JSON.stringify(localUserData));
      window.localStorage.setItem("ft-home-recent-companies", JSON.stringify(recentCompanies));
      window.sessionStorage.clear();
    },
    { localUserData: homeLocalUserData, recentCompanies: homeRecentCompanies }
  );

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Start with a company, then move into evidence." })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent Companies" })).toBeVisible();
  await expect(page.getByText("Apple Inc.")).toBeVisible();
  await expect(page.getByText("Saved & Watchlist")).toBeVisible();
  await expect(page.getByText("Track Azure bookings and capital return mix.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent Changes" })).toBeVisible();
  await expect(page.getByText("Late filer notice").first()).toBeVisible();
  await expect(page.getByText("Curve still looks restrictive")).toBeVisible();
});

test("home reflects recent company visits from company routes", async ({ page }) => {
  await page.goto(`/company/${ticker.toLowerCase()}`);
  await expect(page.getByRole("heading", { name: "Acme Corporation", exact: true })).toBeVisible();

  await page.waitForFunction(() => {
    const recentCompanies = JSON.parse(window.localStorage.getItem("ft-home-recent-companies") ?? "[]");
    return Array.isArray(recentCompanies) && recentCompanies.some((item) => item?.ticker === "ACME");
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Recent Companies" })).toBeVisible();
  await expect(page.getByText("Acme Corporation")).toBeVisible();
});

test("research brief smoke", async ({ page }) => {
  await page.goto(`/company/${ticker.toLowerCase()}`);

  await expect(page.getByRole("button", { name: "Refresh Brief Data" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Acme Corporation", exact: true })).toBeVisible();
  const snapshotHeading = page.getByRole("heading", { name: "Snapshot", exact: true });
  await snapshotHeading.scrollIntoViewIfNeeded();
  await expect(snapshotHeading).toBeVisible();
  const whatChangedHeading = page.getByRole("heading", { name: "What changed", exact: true });
  await whatChangedHeading.scrollIntoViewIfNeeded();
  await expect(whatChangedHeading).toBeVisible();
  await expect(page.getByText("Working capital tightened").first()).toBeVisible();
  await expect(page.getByText("Q2 earnings filing posted").first()).toBeVisible();
  const valuationHeading = page.getByRole("heading", { name: "Valuation", exact: true });
  await valuationHeading.scrollIntoViewIfNeeded();
  await expect(valuationHeading).toBeVisible();
  await expect(page.locator("#valuation").getByText("Fallback label").first()).toBeVisible();
  await expect(page.locator("#valuation").getByText("Yahoo Finance").first()).toBeVisible();
});

test("peers workspace smoke", async ({ page }) => {
  await page.goto(`/company/${ticker.toLowerCase()}/peers`);

  await expect(page.getByRole("button", { name: "Refresh Peer Data" })).toBeVisible();
  const resetButton = page.getByRole("button", { name: "Reset to Focus" });
  await resetButton.scrollIntoViewIfNeeded();
  await expect(resetButton).toBeVisible();
  
    const googChip = page.locator('[title="GOOG — Alphabet"]').first();
  await googChip.click();
    await expect(page.locator('[title="GOOG — Alphabet"].peer-chip.active').first()).toBeVisible();
});

test("earnings workspace smoke", async ({ page }) => {
  await page.goto(`/company/${ticker.toLowerCase()}/earnings`);

  await expect(page.getByRole("button", { name: "Refresh Earnings Data" })).toBeVisible();
  const trendPanel = page.getByText("Reported Revenue vs Diluted EPS");
  await trendPanel.scrollIntoViewIfNeeded();
  await expect(trendPanel).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Revenue grew 18%" })).toBeVisible();
  await expect(page.getByText(/Revenue 125-130/)).toBeVisible();

  await page.getByRole("button", { name: "Show metadata-only releases" }).click();
  await expect(page.getByRole("button", { name: "Hide metadata-only releases" })).toBeVisible();
  await page.getByRole("cell", { name: "Q1 2026" }).click();
  await expect(page.getByText("Metadata only capture; open the SEC filing to inspect the full release narrative.")).toBeVisible();
});

test("chart inspector smoke", async ({ page }, testInfo) => {
  await page.goto(`/company/${ticker.toLowerCase()}`);

  await expect(page.getByRole("button", { name: "Refresh Brief Data" })).toBeVisible();

  const priceChartTitle = page.getByText("Price Chart", { exact: true }).first();
  await priceChartTitle.scrollIntoViewIfNeeded();
  await expect(priceChartTitle).toBeVisible();
  const priceChartFrame = priceChartTitle.locator(
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' price-chart-card ')][1]"
  );
  await expect(priceChartFrame).toBeVisible();
  await page.waitForFunction(() => Boolean(document.querySelector('button[aria-label="Expand Price Chart"]')));
  await page.evaluate(() => {
    const expandButton = document.querySelector('button[aria-label="Expand Price Chart"]');
    if (!(expandButton instanceof HTMLButtonElement)) {
      throw new Error("Expand Price Chart button is missing.");
    }
    expandButton.click();
  });

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Reset view" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Export PNG" })).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Export CSV" })).toBeVisible();
  await expect(dialog.getByText(/Source: Price cache \+ filing history/)).toBeVisible();

  const dialogBox = await dialog.boundingBox();
  const viewport = page.viewportSize();
  expect(dialogBox).not.toBeNull();
  expect(viewport).not.toBeNull();

  if (!dialogBox || !viewport) {
    return;
  }

  if (testInfo.project.name.includes("mobile")) {
    const dialogMetrics = await dialog.evaluate((element) => {
      const styles = window.getComputedStyle(element);
      return {
        innerWidth: window.innerWidth,
        width: styles.width,
        maxHeight: styles.maxHeight,
        height: styles.height,
        backdropPadding: window.getComputedStyle(element.parentElement as Element).padding,
        mobile720: window.matchMedia("(max-width: 720px)").matches,
        mobile960: window.matchMedia("(max-width: 960px)").matches,
        coarse: window.matchMedia("(hover: none) and (pointer: coarse)").matches,
      };
    });

    expect(dialogBox.x).toBeLessThanOrEqual(2);
    expect(Math.abs(dialogBox.width - dialogMetrics.innerWidth)).toBeLessThanOrEqual(4);
  } else {
    expect(dialogBox.width).toBeLessThan(viewport.width);
  }
});
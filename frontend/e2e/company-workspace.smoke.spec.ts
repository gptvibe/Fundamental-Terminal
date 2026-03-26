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
    refresh,
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

    if (path.endsWith(`/companies/${ticker}/financials`)) {
      return json(route, { company, financials, price_history: priceHistory, refresh });
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

    if (path.endsWith(`/companies/${ticker}/beneficial-ownership`)) {
      return json(route, {
        company,
        filings: [],
        refresh,
        error: null,
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

test("overview workspace smoke", async ({ page }) => {
  await page.goto(`/company/${ticker.toLowerCase()}`);

  await expect(page.getByRole("button", { name: "Refresh Company Data" })).toBeVisible();
  await expect(page.getByText("Acme Corporation")).toBeVisible();
  await expect(page.getByText("Working capital tightened")).toBeVisible();
  const priceAndFundamentals = page.getByText("Price & Fundamentals");
  await priceAndFundamentals.scrollIntoViewIfNeeded();
  await expect(priceAndFundamentals).toBeVisible();
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
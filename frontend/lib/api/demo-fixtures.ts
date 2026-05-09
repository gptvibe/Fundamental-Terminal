const DEMO_SOURCE_ID = "ft_demo_fixture_pack";
const DEMO_TIMESTAMP = "2026-05-08T00:00:00Z";
const DEMO_AS_OF = "2025-12-31";

function boolFromEnv(raw: string | undefined): boolean {
  if (!raw) {
    return false;
  }
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

export function isDemoModeEnabled(): boolean {
  return boolFromEnv(process.env.NEXT_PUBLIC_DEMO_MODE) || boolFromEnv(process.env.DEMO_MODE);
}

function normalizeTicker(value: string): string {
  const normalized = value.trim().toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  return normalized || "AAPL";
}

function decodeTicker(pathValue: string): string {
  try {
    return normalizeTicker(decodeURIComponent(pathValue));
  } catch {
    return normalizeTicker(pathValue);
  }
}

function buildCompany(ticker: string): Record<string, unknown> {
  const normalizedTicker = normalizeTicker(ticker);
  const known: Record<string, { cik: string; name: string; sector: string; industry: string }> = {
    AAPL: {
      cik: "0000320193",
      name: "Apple Inc.",
      sector: "Technology",
      industry: "Consumer Electronics",
    },
    MSFT: {
      cik: "0000789019",
      name: "Microsoft Corporation",
      sector: "Technology",
      industry: "Software - Infrastructure",
    },
  };

  const profile = known[normalizedTicker] ?? {
    cik: "0000000000",
    name: `${normalizedTicker} Demo Company`,
    sector: "Technology",
    industry: "Software",
  };

  return {
    ticker: normalizedTicker,
    cik: profile.cik,
    name: profile.name,
    sector: profile.sector,
    market_sector: profile.sector,
    market_industry: profile.industry,
    oil_exposure_type: "non_oil",
    oil_support_status: "unsupported",
    oil_support_reasons: [],
    regulated_entity: null,
    strict_official_mode: false,
    last_checked: DEMO_TIMESTAMP,
    last_checked_financials: DEMO_TIMESTAMP,
    last_checked_prices: DEMO_TIMESTAMP,
    last_checked_insiders: DEMO_TIMESTAMP,
    last_checked_institutional: DEMO_TIMESTAMP,
    last_checked_filings: DEMO_TIMESTAMP,
    earnings_last_checked: DEMO_TIMESTAMP,
    cache_state: "fresh",
  };
}

function buildDemoProvenance(role: "primary" | "supplemental" | "derived" | "fallback" = "primary"): Record<string, unknown>[] {
  return [
    {
      source_id: DEMO_SOURCE_ID,
      source_tier: "manual_override",
      display_label: "Fundamental Terminal Demo Fixture Pack",
      url: "https://github.com/gptvibe/Fundamental-Terminal",
      default_freshness_ttl_seconds: 0,
      disclosure_note: "Deterministic demo fixture payload for local/public walkthroughs. Not live source data.",
      role,
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
    },
  ];
}

function buildDemoSourceMix(): Record<string, unknown> {
  return {
    source_ids: [DEMO_SOURCE_ID],
    source_tiers: ["manual_override"],
    primary_source_ids: [DEMO_SOURCE_ID],
    fallback_source_ids: [],
    official_only: false,
  };
}

function buildFinancialsResponse(ticker: string): Record<string, unknown> {
  const company = buildCompany(ticker);
  return {
    company,
    financials: [
      {
        filing_type: "10-K",
        statement_type: "annual",
        period_start: "2025-01-01",
        period_end: "2025-12-31",
        source: "demo_fixture",
        last_updated: DEMO_TIMESTAMP,
        last_checked: DEMO_TIMESTAMP,
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
    ],
    price_history: [
      { date: "2026-05-05", close: 103.1, volume: 1200000 },
      { date: "2026-05-06", close: 104.4, volume: 1320000 },
      { date: "2026-05-07", close: 106.8, volume: 1275000 },
      { date: "2026-05-08", close: 109.0, volume: 1420000 },
    ],
    segment_analysis: null,
    refresh: { triggered: false, reason: "fresh", ticker: normalizeTicker(ticker), job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: 0.95,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: buildDemoProvenance("primary"),
    as_of: DEMO_AS_OF,
    last_refreshed_at: DEMO_TIMESTAMP,
    source_mix: buildDemoSourceMix(),
    confidence_flags: ["demo_fixture_data"],
  };
}

function buildActivityOverviewResponse(ticker: string): Record<string, unknown> {
  return {
    company: buildCompany(ticker),
    entries: [
      {
        id: `${normalizeTicker(ticker)}-entry-1`,
        date: "2026-05-07",
        type: "earnings",
        badge: "8-K",
        title: "Demo earnings filing posted",
        detail: "Deterministic fixture event for demo walkthroughs.",
        href: null,
      },
    ],
    alerts: [
      {
        id: `${normalizeTicker(ticker)}-alert-1`,
        level: "medium",
        title: "Demo balance sheet signal",
        detail: "Synthetic alert from demo fixtures.",
        source: "demo_fixture",
        date: "2026-05-07",
        href: null,
      },
    ],
    summary: { total: 1, high: 0, medium: 1, low: 0 },
    market_context_status: {
      state: "fresh",
      label: "Demo macro context",
      observation_date: "2026-05-08",
      source: "Demo fixture",
    },
    refresh: { triggered: false, reason: "fresh", ticker: normalizeTicker(ticker), job_id: null },
    error: null,
    provenance: buildDemoProvenance("derived"),
    as_of: DEMO_AS_OF,
    last_refreshed_at: DEMO_TIMESTAMP,
    source_mix: buildDemoSourceMix(),
    confidence_flags: ["demo_fixture_data"],
  };
}

function buildChangesResponse(ticker: string): Record<string, unknown> {
  return {
    company: buildCompany(ticker),
    current_filing: {
      accession_number: "0000001-26-000001",
      filing_type: "10-K",
      statement_type: "annual",
      period_start: "2025-01-01",
      period_end: "2025-12-31",
      source: "demo_fixture",
      last_updated: DEMO_TIMESTAMP,
      last_checked: DEMO_TIMESTAMP,
      filing_acceptance_at: DEMO_TIMESTAMP,
      fetch_timestamp: DEMO_TIMESTAMP,
    },
    previous_filing: {
      accession_number: "0000001-25-000001",
      filing_type: "10-K",
      statement_type: "annual",
      period_start: "2024-01-01",
      period_end: "2024-12-31",
      source: "demo_fixture",
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
      capital_structure_change_count: 0,
      amended_prior_value_count: 0,
      high_signal_change_count: 1,
      comment_letter_count: 0,
    },
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
    refresh: { triggered: false, reason: "fresh", ticker: normalizeTicker(ticker), job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: 0.95,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: buildDemoProvenance("derived"),
    as_of: DEMO_AS_OF,
    last_refreshed_at: DEMO_TIMESTAMP,
    source_mix: buildDemoSourceMix(),
    confidence_flags: ["demo_fixture_data"],
  };
}

function buildEarningsSummaryResponse(ticker: string): Record<string, unknown> {
  return {
    company: buildCompany(ticker),
    summary: {
      total_releases: 2,
      parsed_releases: 2,
      metadata_only_releases: 0,
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
    refresh: { triggered: false, reason: "fresh", ticker: normalizeTicker(ticker), job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: 0.95,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    error: null,
  };
}

function buildModelsResponse(ticker: string): Record<string, unknown> {
  return {
    company: buildCompany(ticker),
    requested_models: ["dcf", "reverse_dcf", "owner_earnings"],
    models: [
      {
        schema_version: "v1",
        model_name: "dcf",
        model_version: "demo-v1",
        calculation_version: "demo-v1",
        created_at: DEMO_TIMESTAMP,
        input_periods: null,
        result: {
          fair_value_per_share: 124.5,
          implied_upside_percent: 0.14,
        },
      },
    ],
    refresh: { triggered: false, reason: "fresh", ticker: normalizeTicker(ticker), job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: 0.95,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: buildDemoProvenance("derived"),
    as_of: DEMO_AS_OF,
    last_refreshed_at: DEMO_TIMESTAMP,
    source_mix: buildDemoSourceMix(),
    confidence_flags: ["demo_fixture_data"],
  };
}

function buildPeersResponse(ticker: string): Record<string, unknown> {
  const normalizedTicker = normalizeTicker(ticker);
  return {
    company: buildCompany(normalizedTicker),
    peer_basis: "demo fixture universe",
    available_companies: [
      { ticker: normalizedTicker, name: `${normalizedTicker} Demo`, sector: "Technology", market_sector: "Technology", market_industry: "Software", last_checked: DEMO_TIMESTAMP, cache_state: "fresh", is_focus: true },
      { ticker: "AAPL", name: "Apple Inc.", sector: "Technology", market_sector: "Technology", market_industry: "Consumer Electronics", last_checked: DEMO_TIMESTAMP, cache_state: "fresh", is_focus: false },
      { ticker: "MSFT", name: "Microsoft Corporation", sector: "Technology", market_sector: "Technology", market_industry: "Software", last_checked: DEMO_TIMESTAMP, cache_state: "fresh", is_focus: false },
    ],
    selected_tickers: [normalizedTicker, "AAPL", "MSFT"],
    peers: [],
    notes: { mode: "Demo fixture data" },
    refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
    provenance: buildDemoProvenance("derived"),
    as_of: DEMO_AS_OF,
    last_refreshed_at: DEMO_TIMESTAMP,
    source_mix: buildDemoSourceMix(),
    confidence_flags: ["demo_fixture_data"],
  };
}

function buildResearchBriefResponse(ticker: string): Record<string, unknown> {
  const normalizedTicker = normalizeTicker(ticker);
  return {
    company: buildCompany(normalizedTicker),
    schema_version: "company_research_brief_demo_v1",
    generated_at: DEMO_TIMESTAMP,
    as_of: DEMO_AS_OF,
    refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
    build_state: "ready",
    build_status: "Demo fixture brief ready.",
    available_sections: ["snapshot", "what_changed", "business_quality", "capital_and_risk", "valuation", "monitor"],
    section_statuses: [
      { id: "snapshot", title: "Snapshot", state: "ready", available: true, detail: "Demo fixture" },
      { id: "what_changed", title: "What Changed", state: "ready", available: true, detail: "Demo fixture" },
      { id: "business_quality", title: "Business Quality", state: "ready", available: true, detail: "Demo fixture" },
      { id: "capital_and_risk", title: "Capital and Risk", state: "ready", available: true, detail: "Demo fixture" },
      { id: "valuation", title: "Valuation", state: "ready", available: true, detail: "Demo fixture" },
      { id: "monitor", title: "Monitor", state: "ready", available: true, detail: "Demo fixture" },
    ],
    filing_timeline: [
      { accession: "0000001-26-000001", form: "10-K", date: "2026-05-08", description: "Deterministic demo filing snapshot." },
    ],
    stale_summary_cards: [
      { key: "latest_filing", title: "Latest Filing", value: "10-K", detail: "Fixture" },
      { key: "latest_revenue", title: "Revenue", value: "$6.2K", detail: "Fixture" },
      { key: "free_cash_flow", title: "Free Cash Flow", value: "$1.3K", detail: "Fixture" },
    ],
    snapshot: {
      summary: {
        latest_filing_type: "10-K",
        latest_period_end: "2025-12-31",
        annual_statement_count: 1,
        price_history_points: 4,
        latest_revenue: 6200,
        latest_free_cash_flow: 1280,
        top_segment_name: "Core Platform",
        top_segment_share_of_revenue: 0.661,
        alert_count: 1,
      },
      provenance: buildDemoProvenance("primary"),
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
      source_mix: buildDemoSourceMix(),
      confidence_flags: ["demo_fixture_data"],
    },
    what_changed: {
      activity_overview: buildActivityOverviewResponse(normalizedTicker),
      changes: buildChangesResponse(normalizedTicker),
      earnings_summary: buildEarningsSummaryResponse(normalizedTicker),
      provenance: buildDemoProvenance("derived"),
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
      source_mix: buildDemoSourceMix(),
      confidence_flags: ["demo_fixture_data"],
    },
    business_quality: {
      summary: {
        latest_period_end: "2025-12-31",
        previous_period_end: "2024-12-31",
        annual_statement_count: 1,
        revenue_growth: 0.09,
        operating_margin: 0.226,
        free_cash_flow_margin: 0.206,
        share_dilution: 0.01,
      },
      provenance: buildDemoProvenance("derived"),
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
      source_mix: buildDemoSourceMix(),
      confidence_flags: ["demo_fixture_data"],
    },
    capital_and_risk: {
      capital_structure: {
        company: buildCompany(normalizedTicker),
        latest: null,
        history: [],
        last_capital_structure_check: DEMO_TIMESTAMP,
        refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 0.95,
          missing_field_flags: [],
          reconciliation_penalty: null,
          reconciliation_disagreement_count: 0,
        },
        provenance: buildDemoProvenance("derived"),
        as_of: DEMO_AS_OF,
        last_refreshed_at: DEMO_TIMESTAMP,
        source_mix: buildDemoSourceMix(),
        confidence_flags: ["demo_fixture_data"],
      },
      capital_markets_summary: {
        company: buildCompany(normalizedTicker),
        summary: {
          total_filings: 2,
          late_filer_notices: 0,
          registration_filings: 1,
          prospectus_filings: 1,
          equity_plan_registrations: 0,
          latest_filing_date: "2026-05-07",
          max_offering_amount: 750,
          total_registered_equity_plan_shares: null,
        },
        refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 0.95,
          missing_field_flags: [],
          reconciliation_penalty: null,
          reconciliation_disagreement_count: 0,
        },
        error: null,
      },
      governance_summary: {
        company: buildCompany(normalizedTicker),
        summary: {
          total_filings: 1,
          definitive_proxies: 1,
          supplemental_proxies: 0,
          filings_with_meeting_date: 1,
          filings_with_exec_comp: 1,
          filings_with_vote_items: 1,
          latest_meeting_date: "2026-04-30",
          max_vote_item_count: 3,
        },
        refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 0.95,
          missing_field_flags: [],
          reconciliation_penalty: null,
          reconciliation_disagreement_count: 0,
        },
        error: null,
      },
      ownership_summary: {
        company: buildCompany(normalizedTicker),
        summary: {
          total_filings: 2,
          initial_filings: 1,
          amendments: 1,
          unique_reporting_persons: 2,
          latest_filing_date: "2026-05-06",
          latest_event_date: "2026-05-05",
          max_reported_percent: 0.083,
          chains_with_amendments: 1,
          amendments_with_delta: 1,
          ownership_increase_events: 1,
          ownership_decrease_events: 0,
          ownership_unchanged_events: 0,
          largest_increase_pp: 0.012,
          largest_decrease_pp: null,
        },
        refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 0.95,
          missing_field_flags: [],
          reconciliation_penalty: null,
          reconciliation_disagreement_count: 0,
        },
        error: null,
      },
      equity_claim_risk_summary: {
        headline: "Moderate dilution pressure from ongoing equity-based compensation.",
        overall_risk_level: "medium",
        dilution_risk_level: "medium",
        financing_risk_level: "low",
        reporting_risk_level: "low",
        latest_period_end: "2025-12-31",
        net_dilution_ratio: 0.01,
        sbc_to_revenue: 0.016,
        shelf_capacity_remaining: 750,
        recent_atm_activity: false,
        recent_warrant_or_convertible_activity: false,
        debt_due_next_twenty_four_months: 120,
        restatement_severity: "none",
        internal_control_flag_count: 0,
        key_points: [
          "Share count grew modestly year over year in the demo fixture set.",
          "No recent ATM, warrant, or convertible financing detected in fixtures.",
        ],
      },
      provenance: buildDemoProvenance("derived"),
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
      source_mix: buildDemoSourceMix(),
      confidence_flags: ["demo_fixture_data"],
    },
    valuation: {
      models: buildModelsResponse(normalizedTicker),
      peers: buildPeersResponse(normalizedTicker),
      provenance: buildDemoProvenance("derived"),
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
      source_mix: buildDemoSourceMix(),
      confidence_flags: ["demo_fixture_data"],
    },
    monitor: {
      activity_overview: buildActivityOverviewResponse(normalizedTicker),
      provenance: buildDemoProvenance("derived"),
      as_of: DEMO_AS_OF,
      last_refreshed_at: DEMO_TIMESTAMP,
      source_mix: buildDemoSourceMix(),
      confidence_flags: ["demo_fixture_data"],
    },
  };
}

function buildWorkspaceBootstrapResponse(ticker: string): Record<string, unknown> {
  const normalizedTicker = normalizeTicker(ticker);
  return {
    company: buildCompany(normalizedTicker),
    financials: buildFinancialsResponse(normalizedTicker),
    brief: buildResearchBriefResponse(normalizedTicker),
    earnings_summary: buildEarningsSummaryResponse(normalizedTicker),
    insider_trades: {
      company: buildCompany(normalizedTicker),
      insider_trades: [],
      summary: {
        sentiment: "neutral",
        summary_lines: ["Demo fixture: no live insider transactions in this deterministic payload."],
        metrics: {
          total_buy_value: 0,
          total_sell_value: 0,
          net_value: 0,
          unique_insiders_buying: 0,
          unique_insiders_selling: 0,
        },
      },
      refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
    },
    institutional_holdings: {
      company: buildCompany(normalizedTicker),
      institutional_holdings: [],
      refresh: { triggered: false, reason: "fresh", ticker: normalizedTicker, job_id: null },
    },
    errors: { insider: null, institutional: null, earnings_summary: null },
  };
}

function buildGlobalMarketContextResponse(): Record<string, unknown> {
  return {
    company: null,
    status: "ready",
    curve_points: [
      { tenor: "10y", rate: 0.043, observation_date: "2026-05-08" },
      { tenor: "2y", rate: 0.04, observation_date: "2026-05-08" },
      { tenor: "3m", rate: 0.047, observation_date: "2026-05-08" },
    ],
    slope_2s10s: { label: "2s10s", value: 0.003, short_tenor: "2y", long_tenor: "10y", observation_date: "2026-05-08" },
    slope_3m10y: { label: "3m10y", value: -0.004, short_tenor: "3m", long_tenor: "10y", observation_date: "2026-05-08" },
    fred_series: [
      { series_id: "BAA10Y", label: "BAA spread", category: "credit", units: "ratio", value: 0.021, observation_date: "2026-05-08", state: "fresh" },
      { series_id: "UNRATE", label: "Unemployment", category: "labor", units: "ratio", value: 0.041, observation_date: "2026-05-08", state: "fresh" },
    ],
    provenance_details: {
      mode: "demo_fixture",
      note: "Deterministic macro fixture payload",
    },
    fetched_at: DEMO_TIMESTAMP,
    refresh: { triggered: false, reason: "fresh", ticker: null, job_id: null },
    rates_credit: [],
    inflation_labor: [],
    growth_activity: [],
    cyclical_demand: [],
    cyclical_costs: [],
    relevant_series: [],
    relevant_indicators: [],
    sector_exposure: [],
    hqm_snapshot: null,
    provenance: buildDemoProvenance("derived"),
    as_of: DEMO_AS_OF,
    last_refreshed_at: DEMO_TIMESTAMP,
    source_mix: buildDemoSourceMix(),
    confidence_flags: ["demo_fixture_data"],
  };
}

function buildSourceRegistryResponse(): Record<string, unknown> {
  return {
    strict_official_mode: false,
    generated_at: DEMO_TIMESTAMP,
    sources: [
      {
        source_id: DEMO_SOURCE_ID,
        source_tier: "manual_override",
        display_label: "Fundamental Terminal Demo Fixture Pack",
        url: "https://github.com/gptvibe/Fundamental-Terminal",
        default_freshness_ttl_seconds: 0,
        disclosure_note: "Deterministic demo fixture payload for local/public walkthroughs. Not live source data.",
        strict_official_mode_state: "available",
        strict_official_mode_note: "Demo mode is enabled. This fixture source is active and explicitly labeled.",
        last_success_at: DEMO_TIMESTAMP,
        last_error: null,
        last_error_at: null,
        is_stale: false,
        used_by_paths: ["/api/companies/search", "/api/companies/{ticker}/workspace-bootstrap", "/api/watchlist/summary"],
      },
    ],
    health: {
      total_companies_cached: 2,
      average_data_age_seconds: 0,
      recent_error_window_hours: 72,
      sources_with_recent_errors: [],
      stale_source_count: 0,
      sources_with_active_errors_count: 0,
      fallback_source_count: 0,
      fallback_sources_recently_used_count: 0,
      last_successful_refresh_at: DEMO_TIMESTAMP,
      worker_queue: {
        available: true,
        status: "healthy",
        active_job_count: 0,
        stalled_job_count: 0,
        datasets_with_failures: 0,
        failed_refresh_count: 0,
        recent_failed_jobs: 0,
      },
      slos: [],
    },
  };
}

function buildWatchlistSummaryResponse(tickers: string[]): Record<string, unknown> {
  const normalized = tickers.map((ticker) => normalizeTicker(ticker)).filter(Boolean);
  const companies = (normalized.length ? normalized : ["AAPL", "MSFT"]).slice(0, 8).map((ticker, index) => ({
    ticker,
    name: String(buildCompany(ticker).name ?? ticker),
    sector: "Technology",
    cik: String(buildCompany(ticker).cik ?? "0000000000"),
    last_checked: DEMO_TIMESTAMP,
    refresh: { triggered: false, reason: "fresh", ticker, job_id: null },
    alert_summary: { high: index === 0 ? 1 : 0, medium: index === 0 ? 0 : 1, low: 0, total: 1 },
    latest_alert: {
      id: `${ticker}-demo-alert`,
      level: index === 0 ? "high" : "medium",
      title: "Demo fixture alert",
      source: "demo_fixture",
      date: "2026-05-08",
      href: null,
    },
    latest_activity: {
      id: `${ticker}-demo-activity`,
      type: "filing",
      badge: "10-K",
      title: "Demo fixture filing update",
      date: "2026-05-07",
      href: null,
    },
    coverage: { financial_periods: 2, price_points: 4 },
    fair_value_gap: 0.08,
    roic: 0.21,
    shareholder_yield: 0.025,
    implied_growth: 0.09,
    fair_value_gap_status: "ok",
    implied_growth_status: "ok",
    valuation_band_percentile: 0.58,
    balance_sheet_risk: 1.8,
    market_context_status: {
      state: "fresh",
      label: "Demo fixture",
      observation_date: "2026-05-08",
      source: "Demo fixture",
    },
    material_change: {
      status: "ready",
      headline: "Demo filing deltas detected",
      detail: "Deterministic fixture highlights for watchlist surfaces.",
      current_filing_type: "10-K",
      current_period_end: "2025-12-31",
      previous_period_end: "2024-12-31",
      high_signal_change_count: 1,
      new_risk_indicator_count: 0,
      share_count_change_count: 0,
      capital_structure_change_count: 0,
      comment_letter_count: 0,
      highlights: [],
    },
  }));

  return {
    tickers: normalized,
    companies,
  };
}

function buildSearchResults(query: string): Record<string, unknown>[] {
  const normalizedQuery = query.trim().toUpperCase();
  const candidates = [buildCompany("AAPL"), buildCompany("MSFT")];
  const filtered = candidates.filter((company) => {
    const ticker = String(company.ticker ?? "");
    const name = String(company.name ?? "").toUpperCase();
    const cik = String(company.cik ?? "");
    return (
      !normalizedQuery ||
      ticker.includes(normalizedQuery) ||
      name.includes(normalizedQuery) ||
      cik.includes(normalizedQuery)
    );
  });
  if (filtered.length) {
    return filtered;
  }
  return [buildCompany(normalizedQuery)];
}

function parseRequestBody(init?: RequestInit): Record<string, unknown> {
  if (!init?.body || typeof init.body !== "string") {
    return {};
  }
  try {
    return JSON.parse(init.body) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function getDemoFixtureResponse(path: string, init?: RequestInit): unknown | null {
  const url = new URL(path, "https://demo.local");
  const pathname = url.pathname;

  if (pathname === "/market-context") {
    return buildGlobalMarketContextResponse();
  }

  if (pathname === "/source-registry") {
    return buildSourceRegistryResponse();
  }

  if (pathname === "/watchlist/summary") {
    const body = parseRequestBody(init);
    const tickers = Array.isArray(body.tickers) ? body.tickers.map((value) => String(value)) : [];
    return buildWatchlistSummaryResponse(tickers);
  }

  if (pathname === "/companies/search") {
    const query = url.searchParams.get("query") ?? "";
    return {
      query,
      results: buildSearchResults(query),
      refresh: { triggered: false, reason: "fresh", ticker: null, job_id: null },
    };
  }

  if (pathname === "/companies/resolve") {
    const query = (url.searchParams.get("query") ?? "").trim();
    const cleaned = normalizeTicker(query);
    return {
      query,
      resolved: Boolean(cleaned),
      ticker: cleaned || null,
      name: cleaned ? String(buildCompany(cleaned).name ?? cleaned) : null,
      error: cleaned ? null : "not_found",
    };
  }

  const workspaceMatch = pathname.match(/^\/companies\/([^/]+)\/workspace-bootstrap$/);
  if (workspaceMatch) {
    return buildWorkspaceBootstrapResponse(decodeTicker(workspaceMatch[1]));
  }

  const briefMatch = pathname.match(/^\/companies\/([^/]+)\/brief$/);
  if (briefMatch) {
    return buildResearchBriefResponse(decodeTicker(briefMatch[1]));
  }

  const filingRiskMatch = pathname.match(/^\/companies\/([^/]+)\/filing-risk-signals$/);
  if (filingRiskMatch) {
    const ticker = decodeTicker(filingRiskMatch[1]);
    const company = buildCompany(ticker);
    return {
      company,
      summary: {
        total_signals: 1,
        high_severity_count: 1,
        medium_severity_count: 0,
        latest_filed_date: "2026-05-07",
      },
      signals: [
        {
          ticker,
          cik: company.cik,
          accession_number: "0000001-26-000010",
          form_type: "8-K",
          filed_date: "2026-05-07",
          signal_category: "demo_fixture_signal",
          matched_phrase: "Deterministic fixture",
          context_snippet: "Demo fixture signal surfaced for deterministic walkthrough behavior.",
          confidence: "high",
          severity: "high",
          source: "demo_fixture",
          provenance: "demo_fixture",
          last_updated: DEMO_TIMESTAMP,
          last_checked: DEMO_TIMESTAMP,
        },
      ],
      refresh: { triggered: false, reason: "fresh", ticker, job_id: null },
      diagnostics: {
        coverage_ratio: 1,
        fallback_ratio: 0,
        stale_flags: [],
        parser_confidence: 0.95,
        missing_field_flags: [],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    };
  }

  return null;
}

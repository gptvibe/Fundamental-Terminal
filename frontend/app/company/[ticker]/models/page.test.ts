// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyModelsPage from "@/app/company/[ticker]/models/page";
import { getCompanyFinancials, getCompanyMarketContext, getCompanyModels } from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: () => ({ consoleEntries: [], connectionState: "connected", lastEvent: null }),
}));

vi.mock("@/lib/active-job", () => ({
  rememberActiveJob: vi.fn(),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) => React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/performance/deferred-client-section", () => ({
  DeferredClientSection: ({ children }: { children?: React.ReactNode }) => React.createElement(React.Fragment, null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, children }: { title: string; children?: React.ReactNode }) => React.createElement("section", null, React.createElement("h2", null, title), children),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/company/capital-structure-intelligence-panel", () => ({
  CapitalStructureIntelligencePanel: () => React.createElement("div", null, "capital-structure-panel"),
}));

vi.mock("@/components/models/market-context-panel", () => ({
  MarketContextPanel: () => React.createElement("div", null, "market-context-panel"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyModels: vi.fn(),
  getCompanyFinancials: vi.fn(),
  getCompanyMarketContext: vi.fn(),
  refreshCompany: vi.fn(),
}));

describe("CompanyModelsPage", () => {
  it("renders registry-backed source freshness metadata for model outputs", async () => {
    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        strict_official_mode: false,
        last_checked: "2026-03-22T00:00:00Z",
        last_checked_financials: "2026-03-22T00:00:00Z",
        last_checked_prices: "2026-03-21T00:00:00Z",
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        cache_state: "fresh",
      },
      requested_models: MODEL_NAMES,
      models: [],
      provenance: [
        {
          source_id: "ft_model_engine",
          source_tier: "derived_from_official",
          display_label: "Fundamental Terminal Model Engine",
          url: "https://github.com/gptvibe/Fundamental-Terminal",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Cached model outputs derived from official filings, Treasury/Fed rates, and labeled price fallbacks.",
          role: "derived",
          as_of: "2025-12-31",
          last_refreshed_at: "2026-03-22T00:00:00Z",
        },
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
        source_ids: ["ft_model_engine", "sec_companyfacts", "yahoo_finance"],
        source_tiers: ["commercial_fallback", "derived_from_official", "official_regulator"],
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
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        strict_official_mode: false,
        last_checked: "2026-03-22T00:00:00Z",
        last_checked_financials: "2026-03-22T00:00:00Z",
        last_checked_prices: "2026-03-21T00:00:00Z",
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        cache_state: "fresh",
      },
      financials: [],
      price_history: [],
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: {
        source_ids: [],
        source_tiers: [],
        primary_source_ids: [],
        fallback_source_ids: [],
        official_only: false,
      },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: 1,
        fallback_ratio: 0,
        stale_flags: [],
        parser_confidence: 1,
        missing_field_flags: [],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getCompanyMarketContext).mockResolvedValue({
      company: null,
      status: "ok",
      curve_points: [],
      slope_2s10s: { label: "2s10s", value: null, short_tenor: "2y", long_tenor: "10y", observation_date: null },
      slope_3m10y: { label: "3m10y", value: null, short_tenor: "3m", long_tenor: "10y", observation_date: null },
      fred_series: [],
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: {
        source_ids: [],
        source_tiers: [],
        primary_source_ids: [],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: [],
      provenance_details: {},
      fetched_at: "2026-03-22T00:00:00Z",
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      rates_credit: [],
      inflation_labor: [],
      growth_activity: [],
      cyclical_demand: [],
      cyclical_costs: [],
      relevant_series: [],
      relevant_indicators: [],
      sector_exposure: [],
      hqm_snapshot: null,
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyModels).toHaveBeenCalledWith("ACME", MODEL_NAMES, { dupontMode: "auto" });
    });

    expect(screen.getByText("Source & Freshness")).toBeTruthy();
    expect(screen.getByText("Macro Demand & Cost Context")).toBeTruthy();
    expect(screen.getByText("Capital Structure Intelligence")).toBeTruthy();
    expect(screen.getByText("market-context-panel")).toBeTruthy();
    expect(screen.getByText("Fundamental Terminal Model Engine")).toBeTruthy();
    expect(screen.getByText("SEC Company Facts (XBRL)")).toBeTruthy();
    expect(screen.getAllByText("commercial_fallback").length).toBeGreaterThan(0);
    expect(screen.getByText(/Price-sensitive valuation outputs on this surface includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();
  });

  it("explains strict official mode when commercial price inputs are disabled", async () => {
    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "prepackaged software",
        market_sector: "Technology",
        market_industry: "Software",
        strict_official_mode: true,
        last_checked: "2026-03-22T00:00:00Z",
        last_checked_financials: "2026-03-22T00:00:00Z",
        last_checked_prices: null,
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        cache_state: "fresh",
      },
      requested_models: MODEL_NAMES,
      models: [],
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
      source_mix: {
        source_ids: ["ft_model_engine", "sec_companyfacts"],
        source_tiers: ["derived_from_official", "official_regulator"],
        primary_source_ids: ["sec_companyfacts"],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: ["strict_official_mode"],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: 1,
        fallback_ratio: 0,
        stale_flags: [],
        parser_confidence: 0.95,
        missing_field_flags: [],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "prepackaged software",
        market_sector: "Technology",
        market_industry: "Software",
        strict_official_mode: true,
        last_checked: "2026-03-22T00:00:00Z",
        last_checked_financials: "2026-03-22T00:00:00Z",
        last_checked_prices: null,
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        cache_state: "fresh",
      },
      financials: [],
      price_history: [],
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: {
        source_ids: [],
        source_tiers: [],
        primary_source_ids: [],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: ["strict_official_mode"],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: 1,
        fallback_ratio: 0,
        stale_flags: [],
        parser_confidence: 1,
        missing_field_flags: [],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getCompanyMarketContext).mockResolvedValue({
      company: null,
      status: "ok",
      curve_points: [],
      slope_2s10s: { label: "2s10s", value: null, short_tenor: "2y", long_tenor: "10y", observation_date: null },
      slope_3m10y: { label: "3m10y", value: null, short_tenor: "3m", long_tenor: "10y", observation_date: null },
      fred_series: [],
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: {
        source_ids: [],
        source_tiers: [],
        primary_source_ids: [],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: [],
      provenance_details: {},
      fetched_at: "2026-03-22T00:00:00Z",
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      rates_credit: [],
      inflation_labor: [],
      growth_activity: [],
      cyclical_demand: [],
      cyclical_costs: [],
      relevant_series: [],
      relevant_indicators: [],
      sector_exposure: [],
      hqm_snapshot: null,
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyModels).toHaveBeenCalledWith("ACME", MODEL_NAMES, { dupontMode: "auto" });
    });

    expect(getCompanyMarketContext).toHaveBeenCalledWith("ACME");

    expect(screen.getByText(/Strict official mode disables commercial equity price inputs/i)).toBeTruthy();
    expect(screen.getAllByText("SEC SIC mapping").length).toBeGreaterThan(0);
  });
});

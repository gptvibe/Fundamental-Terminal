// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CompanyModelsPage from "@/app/company/[ticker]/models/page";
import { getCompanyCapitalStructure, getCompanyChartsForecastAccuracy, getCompanyFinancials, getCompanyMarketContext, getCompanyModels, getCompanyOilScenarioOverlay, getCompanySectorContext, getLatestModelEvaluation } from "@/lib/api";
import { MODEL_NAMES } from "@/lib/constants";
import { FORECAST_HANDOFF_QUERY_PARAM, encodeForecastHandoffPayload, type ForecastHandoffPayload } from "@/lib/forecast-handoff";

let mockedSearchParams = new URLSearchParams();
const mockUseForecastAccuracy = vi.fn();
const downloadJsonFile = vi.fn();
const showAppToast = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
  useSearchParams: () => mockedSearchParams,
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: () => ({ consoleEntries: [], connectionState: "connected", lastEvent: null }),
}));

vi.mock("@/hooks/use-forecast-accuracy", () => ({
  useForecastAccuracy: (...args: unknown[]) => mockUseForecastAccuracy(...args),
}));

vi.mock("@/lib/active-job", () => ({
  rememberActiveJob: vi.fn(),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) => React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children, extraActions }: { children?: React.ReactNode; extraActions?: Array<{ label: string; onClick: () => void; disabled?: boolean }> }) =>
    React.createElement(
      "aside",
      null,
      children,
      extraActions?.map((action) => React.createElement("button", { key: action.label, disabled: action.disabled, onClick: action.onClick }, action.label))
    ),
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

vi.mock("@/components/models/sector-context-panel", () => ({
  SectorContextPanel: () => React.createElement("div", null, "sector-context-panel"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyCapitalStructure: vi.fn(),
  getCompanyChartsForecastAccuracy: vi.fn(),
  getCompanyModels: vi.fn(),
  getCompanyFinancials: vi.fn(),
  getCompanyMarketContext: vi.fn(),
  getCompanyOilScenarioOverlay: vi.fn(),
  getCompanySectorContext: vi.fn(),
  getLatestModelEvaluation: vi.fn(),
  invalidateApiReadCacheForTicker: vi.fn(),
  refreshCompany: vi.fn(),
}));

vi.mock("@/lib/export", async () => {
  const actual = await vi.importActual<typeof import("@/lib/export")>("@/lib/export");
  return {
    ...actual,
    downloadJsonFile: (...args: unknown[]) => downloadJsonFile(...args),
  };
});

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

describe("CompanyModelsPage", () => {
  beforeEach(() => {
    mockedSearchParams = new URLSearchParams();
    mockUseForecastAccuracy.mockReset();
    mockUseForecastAccuracy.mockReturnValue({ data: null, loading: false, error: null });
    downloadJsonFile.mockReset();
    showAppToast.mockReset();
  });

  it("adds forecast-backed valuation card when handoff params are present and supports reset", async () => {
    const handoffPayload: ForecastHandoffPayload = {
      version: 1,
      ticker: "ACME",
      asOf: "2025-12-31",
      forecastYear: 2026,
      source: "user_scenario",
      scenarioName: "Upside Scenario",
      overrideCount: 2,
      metrics: [
        { key: "revenue", label: "Revenue", unit: "usd", base: 1210, scenario: 1300 },
        { key: "free_cash_flow", label: "Free Cash Flow", unit: "usd", base: 200, scenario: 245 },
        { key: "net_income", label: "Net Income", unit: "usd", base: 180, scenario: 205 },
      ],
      createdAt: "2026-04-19T00:00:00Z",
    };
    mockedSearchParams = new URLSearchParams({ [FORECAST_HANDOFF_QUERY_PARAM]: encodeForecastHandoffPayload(handoffPayload) });
    mockUseForecastAccuracy.mockReturnValue({
      data: {
        company: null,
        status: "ok",
        insufficient_history_reason: null,
        max_backtests: 6,
        metrics: [],
        aggregate: { snapshot_count: 2, sample_count: 4, directional_sample_count: 4, mean_absolute_percentage_error: 0.12, directional_accuracy: 0.75 },
        samples: [],
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: null, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
        provenance: [],
        as_of: "2025-12-31",
        last_refreshed_at: null,
        source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
        confidence_flags: [],
      },
      loading: false,
      error: null,
    });

    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        oil_exposure_type: "non_oil",
        oil_support_status: "unsupported",
        oil_support_reasons: ["sector_not_oil_exposed"],
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
      models: [
        {
          schema_version: "2.0",
          model_name: "dcf",
          model_version: "2.2.0",
          created_at: "2026-03-22T00:00:00Z",
          input_periods: {},
          result: { model_status: "supported", fair_value_per_share: 88.2 },
        },
      ],
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
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
      price_history: [{ date: "2026-03-21", close: 123.45, volume: 1000 }],
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
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue(undefined as never);
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
    vi.mocked(getCompanySectorContext).mockResolvedValue({
      company: null,
      status: "ok",
      matched_plugin_ids: [],
      plugins: [],
      fetched_at: "2026-03-22T00:00:00Z",
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
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({
      company: null,
      latest: null,
      history: [],
      last_capital_structure_check: null,
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
      confidence_flags: ["capital_structure_missing"],
      refresh: { triggered: false, reason: "missing", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: null,
        fallback_ratio: null,
        stale_flags: [],
        parser_confidence: null,
        missing_field_flags: ["capital_structure_missing"],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({
      run: null,
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
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(screen.getByText("Forecast-backed Valuation Impact")).toBeTruthy();
    });

    expect(screen.getByTestId("forecast-backed-valuation-card")).toBeTruthy();
    expect(screen.getByText(/Source User scenario/i)).toBeTruthy();
    expect(screen.getByTestId("forecast-trust-cue")).toBeTruthy();
    expect(screen.getByText("User Scenario")).toBeTruthy();
    expect(screen.getByText("MAPE 12.00%")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Reset to Standard Models View" }).getAttribute("href")).toBe("/company/ACME/models");
  });

  it("includes forecast source-state and accuracy metadata in JSON exports", async () => {
    const handoffPayload: ForecastHandoffPayload = {
      version: 1,
      ticker: "ACME",
      asOf: "2025-12-31",
      forecastYear: 2026,
      source: "sec_base_forecast",
      scenarioName: null,
      overrideCount: 0,
      metrics: [{ key: "revenue", label: "Revenue", unit: "usd", base: 1210, scenario: 1250 }],
      createdAt: "2026-04-19T00:00:00Z",
    };
    mockedSearchParams = new URLSearchParams({ [FORECAST_HANDOFF_QUERY_PARAM]: encodeForecastHandoffPayload(handoffPayload) });
    mockUseForecastAccuracy.mockReturnValue({
      data: {
        company: null,
        status: "ok",
        insufficient_history_reason: null,
        max_backtests: 6,
        metrics: [],
        aggregate: { snapshot_count: 3, sample_count: 6, directional_sample_count: 6, mean_absolute_percentage_error: 0.09, directional_accuracy: 0.83 },
        samples: [],
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: null, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
        provenance: [],
        as_of: "2025-12-31",
        last_refreshed_at: null,
        source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
        confidence_flags: [],
      },
      loading: false,
      error: null,
    });

    vi.mocked(getCompanyModels).mockResolvedValue({
      company: null,
      requested_models: MODEL_NAMES,
      models: [],
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: null,
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: null,
      financials: [],
      price_history: [],
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue(undefined as never);
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
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
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
    vi.mocked(getCompanySectorContext).mockResolvedValue({
      company: null,
      status: "ok",
      matched_plugin_ids: [],
      plugins: [],
      fetched_at: "2026-03-22T00:00:00Z",
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({
      company: null,
      latest: null,
      history: [],
      last_capital_structure_check: null,
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({
      run: null,
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Export Model Outputs (JSON)" })).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: "Export Model Outputs (JSON)" }));

    await waitFor(() => {
      expect(downloadJsonFile).toHaveBeenCalledTimes(1);
    });

    const [, payload] = downloadJsonFile.mock.calls[0] as [string, Record<string, unknown>];
    expect(payload.forecast_context).toEqual({
      handoff: handoffPayload,
      source_state: "sec_default",
      forecast_accuracy: {
        status: "ok",
        insufficient_history_reason: null,
        aggregate: { snapshot_count: 3, sample_count: 6, directional_sample_count: 6, mean_absolute_percentage_error: 0.09, directional_accuracy: 0.83 },
      },
    });
    expect(vi.mocked(getCompanyChartsForecastAccuracy)).not.toHaveBeenCalled();
  });

  it("keeps model surfaces available when market context fails", async () => {
    mockedSearchParams = new URLSearchParams();
    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        oil_exposure_type: "non_oil",
        oil_support_status: "unsupported",
        oil_support_reasons: ["sector_not_oil_exposed"],
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
      models: [
        {
          schema_version: "2.0",
          model_name: "dcf",
          model_version: "2.2.0",
          created_at: "2026-03-22T00:00:00Z",
          input_periods: {},
          result: { model_status: "supported", enterprise_value_proxy: 12500000000 },
        },
      ],
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
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
      price_history: [{ date: "2026-03-21", close: 123.45, volume: 1000 }],
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
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue(undefined as never);
    vi.mocked(getCompanyMarketContext).mockRejectedValue(new Error("API request failed: 500 Internal Server Error"));
    vi.mocked(getCompanySectorContext).mockResolvedValue({
      company: null,
      status: "ok",
      matched_plugin_ids: [],
      plugins: [],
      fetched_at: "2026-03-22T00:00:00Z",
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
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({
      company: null,
      latest: null,
      history: [],
      last_capital_structure_check: null,
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
      confidence_flags: ["capital_structure_missing"],
      refresh: { triggered: false, reason: "missing", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: null,
        fallback_ratio: null,
        stale_flags: [],
        parser_confidence: null,
        missing_field_flags: ["capital_structure_missing"],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({
      run: null,
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
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyModels).toHaveBeenCalledWith("ACME", MODEL_NAMES, { dupontMode: "auto" });
    });

    expect(screen.getByText("Investment Summary")).toBeTruthy();
    expect(screen.getByText("Model Analytics")).toBeTruthy();
    expect(screen.queryByText("Macro Exposure Context")).toBeNull();
    expect(screen.queryByText("market-context-panel")).toBeNull();
    expect(screen.queryByText(/API request failed: 500/i)).toBeNull();
  });

  it("renders registry-backed source freshness metadata for model outputs", async () => {
    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        oil_exposure_type: "non_oil",
        oil_support_status: "unsupported",
        oil_support_reasons: ["sector_not_oil_exposed"],
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
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue(undefined as never);
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Software",
        oil_exposure_type: "non_oil",
        oil_support_status: "unsupported",
        oil_support_reasons: ["sector_not_oil_exposed"],
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
    vi.mocked(getCompanySectorContext).mockResolvedValue({
      company: null,
      status: "ok",
      matched_plugin_ids: [],
      plugins: [],
      fetched_at: "2026-03-22T00:00:00Z",
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
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({
      company: null,
      latest: null,
      history: [],
      last_capital_structure_check: null,
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
      confidence_flags: ["capital_structure_missing"],
      refresh: { triggered: false, reason: "missing", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: null,
        fallback_ratio: null,
        stale_flags: [],
        parser_confidence: null,
        missing_field_flags: ["capital_structure_missing"],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({
      run: {
        id: 12,
        suite_key: "historical_fixture_v1",
        candidate_label: "fixture_baseline_v1",
        baseline_label: "fixture_baseline_v1",
        status: "completed",
        completed_at: "2026-03-22T00:00:00Z",
        configuration: { horizon_days: 420, earnings_horizon_days: 30 },
        summary: { company_count: 2, snapshot_count: 8, model_count: 5, provenance_mode: "synthetic_fixture", latest_as_of: "2025-02-15" },
        models: [
          {
            model_name: "dcf",
            sample_count: 8,
            calibration: 0.75,
            stability: 0.08,
            mean_absolute_error: 0.11,
            root_mean_square_error: 0.13,
            mean_signed_error: 0.02,
            status: "supported",
            delta: {
              calibration: 0,
              stability: 0,
              mean_absolute_error: 0,
              root_mean_square_error: 0,
              mean_signed_error: 0,
              sample_count: 0,
            },
          },
        ],
        deltas_present: false,
      },
      provenance: [
        {
          source_id: "ft_model_evaluation_fixture",
          source_tier: "manual_override",
          display_label: "Fundamental Terminal Evaluation Fixture",
          url: "https://github.com/gptvibe/Fundamental-Terminal",
          default_freshness_ttl_seconds: 0,
          disclosure_note: "Synthetic historical fixture suite used only for deterministic model-evaluation regression gating.",
          role: "derived",
          as_of: "2025-02-15",
          last_refreshed_at: "2026-03-22T00:00:00Z",
        },
      ],
      as_of: "2025-02-15",
      last_refreshed_at: "2026-03-22T00:00:00Z",
      source_mix: {
        source_ids: ["ft_model_evaluation_fixture"],
        source_tiers: ["manual_override"],
        primary_source_ids: [],
        fallback_source_ids: [],
        official_only: false,
      },
      confidence_flags: ["synthetic_fixture_suite"],
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyModels).toHaveBeenCalledWith("ACME", MODEL_NAMES, { dupontMode: "auto" });
    });

    expect(screen.getByText("Source & Freshness")).toBeTruthy();
    expect(screen.getByText("Model Evaluation Harness")).toBeTruthy();
    expect(screen.queryByText("Macro Exposure Context")).toBeNull();
    expect(screen.queryByText("Capital Structure Intelligence")).toBeNull();
    expect(screen.queryByText("Sector Exposure Context")).toBeNull();
    expect(screen.queryByText("market-context-panel")).toBeNull();
    expect(screen.getByText(/Suite historical_fixture_v1/i)).toBeTruthy();
    expect(screen.getAllByText("Fundamental Terminal Model Engine").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SEC Company Facts (XBRL)").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Fallback label").length).toBeGreaterThan(0);
    expect(screen.getByText(/Price-sensitive valuation outputs on this surface includes a labeled commercial fallback from Yahoo Finance/i)).toBeTruthy();

    const panelHeadings = Array.from(document.querySelectorAll("section > h2"), (node) => node.textContent ?? "");
    expect(panelHeadings.indexOf("Source & Freshness")).toBeGreaterThan(panelHeadings.indexOf("Model Analytics"));
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
        oil_exposure_type: "non_oil",
        oil_support_status: "unsupported",
        oil_support_reasons: ["sector_not_oil_exposed"],
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
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue(undefined as never);
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Corp",
        sector: "prepackaged software",
        market_sector: "Technology",
        market_industry: "Software",
        oil_exposure_type: "non_oil",
        oil_support_status: "unsupported",
        oil_support_reasons: ["sector_not_oil_exposed"],
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
    vi.mocked(getCompanySectorContext).mockResolvedValue({
      company: null,
      status: "ok",
      matched_plugin_ids: [],
      plugins: [],
      fetched_at: "2026-03-22T00:00:00Z",
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
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({
      company: null,
      latest: null,
      history: [],
      last_capital_structure_check: null,
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
      confidence_flags: ["capital_structure_missing"],
      refresh: { triggered: false, reason: "missing", ticker: "ACME", job_id: null },
      diagnostics: {
        coverage_ratio: null,
        fallback_ratio: null,
        stale_flags: [],
        parser_confidence: null,
        missing_field_flags: ["capital_structure_missing"],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({
      run: null,
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
    });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyModels).toHaveBeenCalledWith("ACME", MODEL_NAMES, { dupontMode: "auto" });
    });

    expect(getCompanyMarketContext).toHaveBeenCalledWith("ACME");

    expect(screen.getByText(/Fair value gap, reverse DCF, and price-comparison workflow steps stay unavailable until an official end-of-day price source is configured\./i)).toBeTruthy();
    expect(screen.getByLabelText("Data sources and freshness").textContent).toContain("Price Layer");
    expect(screen.getByLabelText("Data sources and freshness").textContent).toContain("Disabled");
  });

  it("shows an Oil workspace summary and deep link for supported oil companies", async () => {
    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Energy",
        sector: "Energy",
        market_sector: "Energy",
        market_industry: "Integrated Oil & Gas",
        oil_exposure_type: "integrated",
        oil_support_status: "supported",
        oil_support_reasons: ["integrated_upstream_supported"],
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
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Energy",
        sector: "Energy",
        market_sector: "Energy",
        market_industry: "Integrated Oil & Gas",
        oil_exposure_type: "integrated",
        oil_support_status: "supported",
        oil_support_reasons: ["integrated_upstream_supported"],
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
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue({
      company: null,
      status: "supported",
      fetched_at: "2026-04-04T00:00:00Z",
      strict_official_mode: false,
      exposure_profile: {
        profile_id: "integrated",
        label: "Integrated",
        oil_exposure_type: "integrated",
        oil_support_status: "supported",
        oil_support_reasons: ["integrated_upstream_supported"],
        relevance_reasons: ["integrated_upstream_supported"],
        hedging_signal: "unknown",
        pass_through_signal: "unknown",
        evidence: [],
      },
      benchmark_series: [],
      scenarios: [],
      sensitivity: null,
      provenance: [],
      as_of: "2026-04-04",
      last_refreshed_at: "2026-04-04T00:00:00Z",
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: null, fallback_ratio: null, stale_flags: [], parser_confidence: null, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyMarketContext).mockResolvedValue({ company: null, status: "ok", curve_points: [], slope_2s10s: { label: "2s10s", value: null, short_tenor: "2y", long_tenor: "10y", observation_date: null }, slope_3m10y: { label: "3m10y", value: null, short_tenor: "3m", long_tenor: "10y", observation_date: null }, fred_series: [], provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], provenance_details: {}, fetched_at: "2026-03-22T00:00:00Z", refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null }, rates_credit: [], inflation_labor: [], growth_activity: [], cyclical_demand: [], cyclical_costs: [], relevant_series: [], relevant_indicators: [], sector_exposure: [], hqm_snapshot: null });
    vi.mocked(getCompanySectorContext).mockResolvedValue({ company: null, status: "ok", matched_plugin_ids: [], plugins: [], fetched_at: "2026-03-22T00:00:00Z", provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null } });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({ company: null, latest: null, history: [], last_capital_structure_check: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null }, diagnostics: { coverage_ratio: null, fallback_ratio: null, stale_flags: [], parser_confidence: null, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 } });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({ run: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: false }, confidence_flags: [] });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyOilScenarioOverlay).toHaveBeenCalledWith("ACME");
    });

    expect(screen.getByText("Oil Workspace")).toBeTruthy();
    expect(screen.getByText(/Oil moved into its own workspace/i)).toBeTruthy();
    const oilWorkspaceLink = screen.getByRole("link", { name: "Open Oil Workspace" });
    expect(oilWorkspaceLink.getAttribute("href")).toBe("/company/ACME/oil");
  });

  it("hides the oil scenario overlay panel for unsupported issuers and shows a precise reason", async () => {
    vi.mocked(getCompanyModels).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Midstream",
        sector: "Energy",
        market_sector: "Energy",
        market_industry: "Pipeline Transportation",
        oil_exposure_type: "midstream",
        oil_support_status: "unsupported",
        oil_support_reasons: ["midstream_not_supported_v1"],
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
      provenance: [],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyFinancials).mockResolvedValue({
      company: {
        ticker: "ACME",
        cik: "0000001",
        name: "Acme Midstream",
        sector: "Energy",
        market_sector: "Energy",
        market_industry: "Pipeline Transportation",
        oil_exposure_type: "midstream",
        oil_support_status: "unsupported",
        oil_support_reasons: ["midstream_not_supported_v1"],
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
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue({
      company: null,
      status: "not_applicable",
      fetched_at: "2026-04-04T00:00:00Z",
      strict_official_mode: false,
      exposure_profile: {
        profile_id: "midstream",
        label: "Midstream",
        oil_exposure_type: "midstream",
        oil_support_status: "unsupported",
        oil_support_reasons: ["midstream_not_supported_v1"],
        relevance_reasons: ["midstream_not_supported_v1"],
        hedging_signal: "unknown",
        pass_through_signal: "unknown",
        evidence: [],
      },
      benchmark_series: [],
      scenarios: [],
      sensitivity: null,
      provenance: [],
      as_of: "2026-04-04",
      last_refreshed_at: "2026-04-04T00:00:00Z",
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      diagnostics: { coverage_ratio: null, fallback_ratio: null, stale_flags: [], parser_confidence: null, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    });
    vi.mocked(getCompanyMarketContext).mockResolvedValue({ company: null, status: "ok", curve_points: [], slope_2s10s: { label: "2s10s", value: null, short_tenor: "2y", long_tenor: "10y", observation_date: null }, slope_3m10y: { label: "3m10y", value: null, short_tenor: "3m", long_tenor: "10y", observation_date: null }, fred_series: [], provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], provenance_details: {}, fetched_at: "2026-03-22T00:00:00Z", refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null }, rates_credit: [], inflation_labor: [], growth_activity: [], cyclical_demand: [], cyclical_costs: [], relevant_series: [], relevant_indicators: [], sector_exposure: [], hqm_snapshot: null });
    vi.mocked(getCompanySectorContext).mockResolvedValue({ company: null, status: "ok", matched_plugin_ids: [], plugins: [], fetched_at: "2026-03-22T00:00:00Z", provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null } });
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({ company: null, latest: null, history: [], last_capital_structure_check: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null }, diagnostics: { coverage_ratio: null, fallback_ratio: null, stale_flags: [], parser_confidence: null, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 } });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({ run: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: false }, confidence_flags: [] });

    render(React.createElement(CompanyModelsPage));

    await waitFor(() => {
      expect(getCompanyOilScenarioOverlay).toHaveBeenCalledWith("ACME");
    });

    expect(screen.getByText(/Oil scenario overlay unavailable: v1 does not model midstream or pipeline oil economics yet\./i)).toBeTruthy();
  });
});

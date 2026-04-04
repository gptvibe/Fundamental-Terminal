// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyOilPage from "@/app/company/[ticker]/oil/page";
import { getCompanyModels, getCompanyOilScenarioOverlay, getLatestModelEvaluation } from "@/lib/api";

const useCompanyWorkspace = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: (...args: unknown[]) => useCompanyWorkspace(...args),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) => React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/layout/company-research-header", () => ({
  CompanyResearchHeader: ({ children, title }: { children?: React.ReactNode; title: string }) => React.createElement("section", null, React.createElement("h1", null, title), children),
}));

vi.mock("@/components/models/oil-scenario-overlay-panel", () => ({
  OilScenarioOverlayPanel: () => React.createElement("div", null, "oil-scenario-overlay-panel"),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, children, bodyId }: { title: string; children?: React.ReactNode; bodyId?: string }) => React.createElement("section", null, React.createElement("h2", null, title), React.createElement("div", { id: bodyId }, children)),
}));

vi.mock("@/components/ui/source-freshness-summary", () => ({
  SourceFreshnessSummary: () => React.createElement("div", null, "source-freshness-summary"),
}));

vi.mock("@/components/ui/data-quality-diagnostics", () => ({
  DataQualityDiagnostics: () => React.createElement("div", null, "data-quality-diagnostics"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyModels: vi.fn(),
  getCompanyOilScenarioOverlay: vi.fn(),
  getLatestModelEvaluation: vi.fn(),
}));

describe("CompanyOilPage", () => {
  it("renders the dedicated oil workspace for supported companies", async () => {
    useCompanyWorkspace.mockReturnValue({
      company: {
        ticker: "ACME",
        name: "Acme Energy",
        sector: "Energy",
        cache_state: "fresh",
        last_checked: "2026-04-04T00:00:00Z",
        oil_support_status: "supported",
        oil_support_reasons: ["integrated_upstream_supported"],
        oil_exposure_type: "integrated",
        strict_official_mode: false,
      },
      financials: [],
      priceHistory: [],
      loading: false,
      error: null,
      refreshing: false,
      refreshState: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      consoleEntries: [],
      connectionState: "connected",
      queueRefresh: vi.fn(),
      reloadKey: "1",
    });
    vi.mocked(getCompanyModels).mockResolvedValue({ company: null, models: [], requested_models: [], provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null }, diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 } });
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue({
      company: null,
      status: "supported",
      fetched_at: "2026-04-04T00:00:00Z",
      as_of: "2026-04-04",
      last_refreshed_at: "2026-04-04T00:00:00Z",
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
      sensitivity_source: { kind: "manual_override", value: null, metric_basis: null, status: null, confidence_flags: [] },
      official_base_curve: { benchmark_id: "wti_short_term_baseline", label: "WTI", units: "usd_per_barrel", points: [{ year: 2026, price: 80 }], available_benchmarks: [] },
      phase2_extensions: {
        downstream_offset_supported: true,
        downstream_offset_percent: 25,
        downstream_offset_reason: null,
        refiner_rac_supported: false,
        refiner_rac_reason: "Official EIA RAC inputs are not wired yet.",
        aeo_presets_supported: false,
        aeo_presets_reason: "Official EIA AEO long-term cases are not wired yet.",
        aeo_preset_options: [
          { preset_id: "reference", label: "Reference", status: "pending_eia_wiring", reason: "pending", source_id: "eia_aeo" },
        ],
      },
      overlay_outputs: { status: "supported", model_status: "supported", reason: "ok", yearly_deltas: [], assumptions: {}, confidence_flags: [] },
      requirements: { strict_official_mode: false, manual_price_required: false, manual_price_reason: null, manual_sensitivity_required: false, manual_sensitivity_reason: null, price_input_mode: "cached_market_price", realized_spread_supported: false, realized_spread_reason: null, realized_spread_fallback_label: null },
      direct_company_evidence: { status: "not_available", checked_at: null, parser_confidence_flags: [], disclosed_sensitivity: { status: "not_available", confidence_flags: [], provenance_sources: [] }, diluted_shares: { status: "not_available", confidence_flags: [], provenance_sources: [] }, realized_price_comparison: { status: "not_available", rows: [], confidence_flags: [], provenance_sources: [] } },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
      provenance: [],
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      user_editable_defaults: { benchmark_id: "wti_short_term_baseline", benchmark_options: [], short_term_curve: [], long_term_anchor: 80, fade_years: 2, annual_after_tax_sensitivity: 1, base_fair_value_per_share: 100, diluted_shares: 10, current_share_price: 90, current_share_price_source: "cached_market_price", current_oil_price: 80, current_oil_price_source: "wti_spot_history", realized_spread_mode: "benchmark_only", current_realized_spread: null, current_realized_spread_source: null, custom_realized_spread: null, mean_reversion_target_spread: 0, mean_reversion_years: 3, realized_spread_reference_benchmark: null },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({
      run: {
        id: 1,
        suite_key: "oil_overlay_point_in_time_v1",
        candidate_label: "oil",
        baseline_label: "base",
        status: "completed",
        completed_at: "2026-04-04T00:00:00Z",
        configuration: {},
        summary: { comparison: { sample_count: 6, mean_absolute_error_lift: 0.12, improvement_rate: 0.67 }, latest_as_of: "2026-04-04" },
        artifacts: {},
        models: [],
        deltas_present: true,
      },
      provenance: [],
      as_of: null,
      last_refreshed_at: null,
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
    });

    render(React.createElement(CompanyOilPage));

    await waitFor(() => {
      expect(getCompanyOilScenarioOverlay).toHaveBeenCalledWith("ACME");
    });

    expect(screen.getByRole("heading", { name: "Oil" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Oil workspace section picker" })).toBeTruthy();
    expect(screen.getByText("oil-scenario-overlay-panel")).toBeTruthy();
    expect(screen.getByText("Latest Oil Overlay Evaluation")).toBeTruthy();
  });

  it("shows an unavailable message for unsupported companies", async () => {
    useCompanyWorkspace.mockReturnValue({
      company: {
        ticker: "ACME",
        name: "Acme Midstream",
        sector: "Energy",
        cache_state: "fresh",
        last_checked: "2026-04-04T00:00:00Z",
        oil_support_status: "unsupported",
        oil_support_reasons: ["midstream_not_supported_v1"],
        oil_exposure_type: "midstream",
        strict_official_mode: false,
      },
      financials: [],
      priceHistory: [],
      loading: false,
      error: null,
      refreshing: false,
      refreshState: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      consoleEntries: [],
      connectionState: "connected",
      queueRefresh: vi.fn(),
      reloadKey: "1",
    });
    vi.mocked(getCompanyModels).mockResolvedValue({ company: null, models: [], requested_models: [], provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [], refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null }, diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 } });
    vi.mocked(getCompanyOilScenarioOverlay).mockResolvedValue({
      company: null,
      status: "unsupported",
      fetched_at: "2026-04-04T00:00:00Z",
      as_of: "2026-04-04",
      last_refreshed_at: "2026-04-04T00:00:00Z",
      strict_official_mode: false,
      exposure_profile: { profile_id: "midstream", label: "Midstream", oil_exposure_type: "midstream", oil_support_status: "unsupported", oil_support_reasons: ["midstream_not_supported_v1"], relevance_reasons: ["midstream_not_supported_v1"], hedging_signal: "unknown", pass_through_signal: "unknown", evidence: [] },
      benchmark_series: [],
      scenarios: [],
      sensitivity: null,
      sensitivity_source: { kind: "manual_override", value: null, metric_basis: null, status: null, confidence_flags: [] },
      official_base_curve: { benchmark_id: null, label: null, units: "usd_per_barrel", points: [], available_benchmarks: [] },
      phase2_extensions: { downstream_offset_supported: false, downstream_offset_percent: null, downstream_offset_reason: "Downstream offsets are only surfaced for integrated majors.", refiner_rac_supported: false, refiner_rac_reason: "pending", aeo_presets_supported: false, aeo_presets_reason: "pending", aeo_preset_options: [] },
      overlay_outputs: { status: "unsupported", model_status: "unsupported", reason: "unsupported", yearly_deltas: [], assumptions: {}, confidence_flags: [] },
      requirements: { strict_official_mode: false, manual_price_required: true, manual_price_reason: null, manual_sensitivity_required: true, manual_sensitivity_reason: null, price_input_mode: "manual", realized_spread_supported: false, realized_spread_reason: null, realized_spread_fallback_label: null },
      direct_company_evidence: { status: "not_available", checked_at: null, parser_confidence_flags: [], disclosed_sensitivity: { status: "not_available", confidence_flags: [], provenance_sources: [] }, diluted_shares: { status: "not_available", confidence_flags: [], provenance_sources: [] }, realized_price_comparison: { status: "not_available", rows: [], confidence_flags: [], provenance_sources: [] } },
      diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
      provenance: [],
      source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
      confidence_flags: [],
      refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
      user_editable_defaults: { benchmark_id: null, benchmark_options: [], short_term_curve: [], long_term_anchor: null, fade_years: 0, annual_after_tax_sensitivity: null, base_fair_value_per_share: null, diluted_shares: null, current_share_price: null, current_share_price_source: "manual_required", current_oil_price: null, current_oil_price_source: null, realized_spread_mode: "benchmark_only", current_realized_spread: null, current_realized_spread_source: null, custom_realized_spread: null, mean_reversion_target_spread: null, mean_reversion_years: 0, realized_spread_reference_benchmark: null },
    });
    vi.mocked(getLatestModelEvaluation).mockResolvedValue({ run: null, provenance: [], as_of: null, last_refreshed_at: null, source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true }, confidence_flags: [] });

    render(React.createElement(CompanyOilPage));

    await waitFor(() => {
      expect(getCompanyOilScenarioOverlay).toHaveBeenCalledWith("ACME");
    });

    expect(screen.queryByText("oil-scenario-overlay-panel")).toBeNull();
    expect(screen.getAllByText(/Oil workspace unavailable: v1 does not model midstream or pipeline oil economics yet\./i).length).toBeGreaterThan(0);
  });
});
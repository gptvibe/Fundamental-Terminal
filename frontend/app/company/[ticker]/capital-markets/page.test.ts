// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyCapitalMarketsPage from "@/app/company/[ticker]/capital-markets/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: null },
    financials: [{ debt_changes: 1250000 }],
    loading: false,
    refreshing: false,
    refreshState: null,
    consoleEntries: [],
    connectionState: "connected",
    queueRefresh: vi.fn(),
    reloadKey: 0,
  }),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, children }: { title: string; children?: React.ReactNode }) =>
    React.createElement("section", null, React.createElement("h2", null, title), children),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/charts/share-dilution-tracker-chart", () => ({
  ShareDilutionTrackerChart: () => React.createElement("div", null, "dilution-chart"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyEquityClaimRisk: vi.fn(async () => ({
    company: {
      ticker: "ACME",
      cik: "0000001",
      name: "Acme Corp",
      sector: "Tech",
      market_sector: "Tech",
      market_industry: null,
      oil_exposure_type: "non_oil",
      oil_support_status: "unsupported",
      oil_support_reasons: [],
      strict_official_mode: false,
      last_checked: null,
      last_checked_financials: null,
      last_checked_prices: null,
      last_checked_insiders: null,
      last_checked_institutional: null,
      last_checked_filings: null,
      cache_state: "fresh",
    },
    summary: {
      headline: "Capital needs look elevated because dilution, financing, and reporting signals are all active.",
      overall_risk_level: "high",
      dilution_risk_level: "high",
      financing_risk_level: "medium",
      reporting_risk_level: "medium",
      latest_period_end: "2025-12-31",
      net_dilution_ratio: 0.081,
      sbc_to_revenue: 0.064,
      shelf_capacity_remaining: 225000000,
      recent_atm_activity: true,
      recent_warrant_or_convertible_activity: true,
      debt_due_next_twenty_four_months: 180000000,
      restatement_severity: "medium",
      internal_control_flag_count: 2,
      key_points: ["ATM activity was detected in recent SEC filings."],
    },
    share_count_bridge: {
      latest_period_end: "2025-12-31",
      bridge: {
        opening_shares: 100000000,
        shares_issued: 9000000,
        shares_issued_proxy: null,
        shares_repurchased: 1000000,
        other_share_change: null,
        ending_shares: 108000000,
        weighted_average_diluted_shares: 106000000,
        net_share_change: 8000000,
        net_dilution_ratio: 0.08,
        share_repurchase_cash: null,
        stock_based_compensation: 42000000,
        meta: { confidence_score: null, quality_flags: [], source_fields: [] },
      },
      evidence: [
        {
          category: "capital_structure",
          title: "Latest share-count bridge",
          detail: "10-K bridge shows a net share increase during the latest annual period.",
          form: "10-K",
          filing_date: "2025-12-31",
          accession_number: "0000001-26-000001",
          source_url: "https://example.com/share-bridge",
          source_id: "sec_companyfacts",
        },
      ],
    },
    shelf_registration: {
      status: "partially_used",
      latest_shelf_form: "S-3",
      latest_shelf_filing_date: "2026-01-15",
      gross_capacity: 500000000,
      utilized_capacity: 275000000,
      remaining_capacity: 225000000,
      evidence: [],
    },
    atm_and_financing_dependency: {
      atm_detected: true,
      recent_atm_filing_count: 2,
      latest_atm_filing_date: "2026-02-10",
      financing_dependency_level: "medium",
      negative_free_cash_flow: true,
      cash_runway_years: 1.2,
      debt_due_next_twelve_months: 90000000,
      evidence: [],
    },
    warrants_and_convertibles: {
      warrant_filing_count: 1,
      convertible_filing_count: 1,
      latest_security_filing_date: "2026-02-20",
      evidence: [],
    },
    sbc_and_dilution: {
      latest_stock_based_compensation: 42000000,
      sbc_to_revenue: 0.064,
      current_net_dilution_ratio: 0.081,
      trailing_three_period_net_dilution_ratio: 0.072,
      weighted_average_diluted_shares_growth: 0.055,
      evidence: [],
    },
    debt_maturity_wall: {
      total_debt: 400000000,
      debt_due_next_twelve_months: 90000000,
      debt_due_year_two: 90000000,
      debt_due_next_twenty_four_months: 180000000,
      debt_due_next_twenty_four_months_ratio: 0.45,
      interest_coverage_proxy: 1.8,
      evidence: [],
    },
    covenant_risk_signals: {
      level: "medium",
      match_count: 2,
      matched_terms: ["covenant", "waiver"],
      evidence: [],
    },
    reporting_and_controls: {
      restatement_count: 1,
      restatement_severity: "medium",
      high_impact_restatements: 0,
      latest_restatement_date: "2026-02-28",
      internal_control_flag_count: 2,
      internal_control_terms: ["material weakness"],
      evidence: [],
    },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: null,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: [],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: {
      source_ids: ["ft_equity_claim_risk_pack", "sec_companyfacts", "sec_edgar"],
      source_tiers: ["derived_from_official", "official_regulator"],
      primary_source_ids: ["sec_companyfacts"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
  })),
  getCompanyCapitalMarkets: vi.fn(async () => ({
    company: null,
    filings: [
      {
        accession_number: "0000099-26-000001",
        form: "S-8",
        filing_date: "2026-03-15",
        report_date: "2026-03-15",
        primary_document: "s8.htm",
        primary_doc_description: "Registration of 12,000,000 shares pursuant to the 2026 Long-Term Incentive Plan",
        source_url: "https://example.com/s8",
        summary: "Registration of 12,000,000 shares pursuant to the 2026 Long-Term Incentive Plan",
        event_type: "Equity Plan Registration",
        security_type: "Common Equity",
        offering_amount: null,
        shelf_size: null,
        is_late_filer: false,
        plan_name: "2026 Long-Term Incentive Plan",
        registered_shares: 12000000,
        shares_parse_confidence: "high",
      },
    ],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: null,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    error: null,
  })),
}));

describe("CompanyCapitalMarketsPage", () => {
  it("renders the equity claim risk pack summary and evidence panels", async () => {
    render(React.createElement(CompanyCapitalMarketsPage));

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Equity Claim Risk Pack" })).toBeTruthy();
    });

    expect(screen.getByText(/SEC-derived underwriting workspace covering dilution/i)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Investor summary" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Share-count bridge" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Financing capacity and dependency" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Equity plan registrations (S-8)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Hybrid securities and debt maturity wall" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Covenant, restatement, and control signals" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Provenance and diagnostics" })).toBeTruthy();
    expect(screen.getByText("Capital needs look elevated because dilution, financing, and reporting signals are all active.")).toBeTruthy();
    expect(screen.getByText("Latest share-count bridge")).toBeTruthy();
    expect(screen.queryByText("dilution-chart") ?? screen.getByText(/Loading share dilution chart/i)).toBeTruthy();
  });

  it("renders S-8 equity plan filing card with plan name and confidence", async () => {
    render(React.createElement(CompanyCapitalMarketsPage));

    await waitFor(() => {
      expect(screen.getByText("2026 Long-Term Incentive Plan")).toBeTruthy();
    });

    expect(screen.getByText(/high confidence/i)).toBeTruthy();
  });
});

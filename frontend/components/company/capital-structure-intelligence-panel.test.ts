// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CapitalStructureIntelligencePanel } from "@/components/company/capital-structure-intelligence-panel";
import { getCompanyCapitalStructure } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCompanyCapitalStructure: vi.fn(),
  invalidateApiReadCacheForTicker: vi.fn(),
}));

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: () => ({ lastEvent: null }),
}));

describe("CapitalStructureIntelligencePanel", () => {
  it("loads the persisted capital structure route and renders ladder and provenance details", async () => {
    vi.mocked(getCompanyCapitalStructure).mockResolvedValue({
      company: {
        ticker: "AAPL",
        cik: "0000320193",
        name: "Apple Inc.",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Consumer Electronics",
        strict_official_mode: false,
        last_checked: "2026-03-22T00:00:00Z",
        last_checked_financials: "2026-03-22T00:00:00Z",
        last_checked_prices: null,
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        earnings_last_checked: null,
        cache_state: "fresh",
      },
      latest: {
        accession_number: "0000320193-26-000010",
        filing_type: "10-K",
        statement_type: "canonical_xbrl",
        period_start: "2025-01-01",
        period_end: "2025-12-31",
        source: "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        filing_acceptance_at: "2026-02-01T00:00:00Z",
        last_updated: "2026-03-21T00:00:00Z",
        last_checked: "2026-03-22T00:00:00Z",
        summary: {
          total_debt: 110000000000,
          lease_liabilities: 18000000000,
          interest_expense: 4500000000,
          debt_due_next_twelve_months: 8000000000,
          lease_due_next_twelve_months: 3000000000,
          gross_shareholder_payout: 96000000000,
          net_shareholder_payout: 84000000000,
          net_share_change: -420000000,
          net_dilution_ratio: -0.0269,
        },
        debt_maturity_ladder: {
          buckets: [{ bucket_key: "debt_maturity_due_next_twelve_months", label: "Next 12 months", amount: 8000000000 }],
          meta: {
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
            provenance_sources: ["sec_companyfacts", "ft_capital_structure_intelligence"],
            confidence_score: 0.5,
            confidence_flags: ["debt_maturity_ladder_partial"],
          },
        },
        lease_obligations: {
          buckets: [{ bucket_key: "lease_due_next_twelve_months", label: "Next 12 months", amount: 3000000000 }],
          meta: {
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
            provenance_sources: ["sec_companyfacts", "ft_capital_structure_intelligence"],
            confidence_score: 0.5,
            confidence_flags: ["lease_obligations_partial"],
          },
        },
        debt_rollforward: {
          opening_total_debt: 100000000000,
          ending_total_debt: 110000000000,
          debt_issued: 15000000000,
          debt_repaid: 5000000000,
          net_debt_change: 10000000000,
          unexplained_change: 0,
          meta: {
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
            provenance_sources: ["sec_companyfacts"],
            confidence_score: 1,
            confidence_flags: [],
          },
        },
        interest_burden: {
          interest_expense: 4500000000,
          average_total_debt: 105000000000,
          interest_to_average_debt: 0.0429,
          interest_to_revenue: 0.011,
          interest_to_operating_cash_flow: 0.052,
          interest_coverage_proxy: 20,
          meta: {
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
            provenance_sources: ["sec_companyfacts"],
            confidence_score: 1,
            confidence_flags: [],
          },
        },
        capital_returns: {
          dividends: 15000000000,
          share_repurchases: 81000000000,
          stock_based_compensation: 12000000000,
          gross_shareholder_payout: 96000000000,
          net_shareholder_payout: 84000000000,
          payout_mix: { dividends_share: 0.156, repurchases_share: 0.844, sbc_offset_share: 0.111 },
          meta: {
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
            provenance_sources: ["sec_companyfacts"],
            confidence_score: 1,
            confidence_flags: [],
          },
        },
        net_dilution_bridge: {
          opening_shares: 15600000000,
          shares_issued: 80000000,
          shares_issued_proxy: null,
          shares_repurchased: 500000000,
          other_share_change: 0,
          ending_shares: 15180000000,
          weighted_average_diluted_shares: 15220000000,
          net_share_change: -420000000,
          net_dilution_ratio: -0.0269,
          share_repurchase_cash: 81000000000,
          stock_based_compensation: 12000000000,
          meta: {
            as_of: "2025-12-31",
            last_refreshed_at: "2026-03-22T00:00:00Z",
            provenance_sources: ["sec_companyfacts"],
            confidence_score: 1,
            confidence_flags: [],
          },
        },
        provenance_details: { formula_version: "capital_structure_v1", official_source_id: "sec_companyfacts" },
        quality_flags: ["debt_maturity_ladder_partial"],
        confidence_score: 0.83,
      },
      history: [],
      last_capital_structure_check: "2026-03-22T00:00:00Z",
      provenance: [
        {
          source_id: "ft_capital_structure_intelligence",
          source_tier: "derived_from_official",
          display_label: "Fundamental Terminal Capital Structure Intelligence",
          url: "https://github.com/gptvibe/Fundamental-Terminal",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Persisted capital structure roll-forwards, maturities, payout mix, and dilution bridges derived from official SEC companyfacts statements.",
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
      ],
      as_of: "2025-12-31",
      last_refreshed_at: "2026-03-22T00:00:00Z",
      source_mix: {
        source_ids: ["ft_capital_structure_intelligence", "sec_companyfacts"],
        source_tiers: ["derived_from_official", "official_regulator"],
        primary_source_ids: ["sec_companyfacts"],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: ["debt_maturity_ladder_partial"],
      refresh: { triggered: false, reason: "fresh", ticker: "AAPL", job_id: null },
      diagnostics: {
        coverage_ratio: 0.83,
        fallback_ratio: 0,
        stale_flags: [],
        parser_confidence: 0.83,
        missing_field_flags: [],
        reconciliation_penalty: null,
        reconciliation_disagreement_count: 0,
      },
    });

    render(React.createElement(CapitalStructureIntelligencePanel, { ticker: "AAPL", maxPeriods: 4 }));

    await waitFor(() => {
      expect(getCompanyCapitalStructure).toHaveBeenCalledWith("AAPL", { maxPeriods: 4 });
    });

    expect(screen.getByText("Debt Maturity Ladder")).toBeTruthy();
    expect(screen.getByText("Lease Obligations")).toBeTruthy();
    expect(screen.getAllByText("Next 12 months")).toHaveLength(2);
    expect(screen.getByText("Fundamental Terminal Capital Structure Intelligence")).toBeTruthy();
    expect(screen.getByText("SEC Company Facts (XBRL)")).toBeTruthy();
  });
});

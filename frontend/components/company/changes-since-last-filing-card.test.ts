// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChangesSinceLastFilingCard } from "@/components/company/changes-since-last-filing-card";
import { getCompanyChangesSinceLastFiling } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  getCompanyChangesSinceLastFiling: vi.fn(),
}));

describe("ChangesSinceLastFilingCard", () => {
  it("renders metric deltas, risk indicators, and amended prior values", async () => {
    vi.mocked(getCompanyChangesSinceLastFiling).mockResolvedValue({
      company: null,
      current_filing: {
        accession_number: "0000123456-26-000001",
        filing_type: "10-Q",
        statement_type: "canonical_xbrl",
        period_start: "2025-07-01",
        period_end: "2025-09-30",
        source: "https://www.sec.gov/Archives/edgar/data/123456/000012345626000001/form10q.htm",
        last_updated: "2026-03-27T18:00:00Z",
        last_checked: "2026-03-27T18:00:00Z",
        filing_acceptance_at: "2025-11-02T20:00:00Z",
        fetch_timestamp: "2026-03-27T18:00:00Z",
      },
      previous_filing: {
        accession_number: "0000123456-26-000000",
        filing_type: "10-Q",
        statement_type: "canonical_xbrl",
        period_start: "2025-04-01",
        period_end: "2025-06-30",
        source: "https://www.sec.gov/Archives/edgar/data/123456/000012345626000000/form10q.htm",
        last_updated: "2026-03-27T18:00:00Z",
        last_checked: "2026-03-27T18:00:00Z",
        filing_acceptance_at: "2025-08-10T20:00:00Z",
        fetch_timestamp: "2026-03-27T18:00:00Z",
      },
      summary: {
        filing_type: "10-Q",
        current_period_start: "2025-07-01",
        current_period_end: "2025-09-30",
        previous_period_start: "2025-04-01",
        previous_period_end: "2025-06-30",
        metric_delta_count: 3,
        new_risk_indicator_count: 1,
        segment_shift_count: 1,
        share_count_change_count: 1,
        capital_structure_change_count: 1,
        amended_prior_value_count: 1,
      },
      metric_deltas: [
        {
          metric_key: "revenue",
          label: "Revenue",
          unit: "usd",
          previous_value: 100,
          current_value: 120,
          delta: 20,
          relative_change: 0.2,
          direction: "increase",
        },
      ],
      new_risk_indicators: [
        {
          indicator_key: "negative_free_cash_flow",
          label: "Negative Free Cash Flow",
          severity: "high",
          description: "Cash generation turned negative or remained negative in the latest filing.",
          current_value: -4,
          previous_value: 6,
        },
      ],
      segment_shifts: [
        {
          segment_id: "products",
          segment_name: "Products",
          kind: "business",
          current_revenue: 84,
          previous_revenue: 61,
          revenue_delta: 23,
          current_share_of_revenue: 0.7,
          previous_share_of_revenue: 0.6,
          share_delta: 0.1,
          direction: "increase",
        },
      ],
      share_count_changes: [
        {
          metric_key: "shares_outstanding",
          label: "Shares Outstanding",
          unit: "shares",
          previous_value: 100,
          current_value: 108,
          delta: 8,
          relative_change: 0.08,
          direction: "increase",
        },
      ],
      capital_structure_changes: [
        {
          metric_key: "long_term_debt",
          label: "Long-Term Debt",
          unit: "usd",
          previous_value: 70,
          current_value: 88,
          delta: 18,
          relative_change: 0.257,
          direction: "increase",
        },
      ],
      amended_prior_values: [
        {
          metric_key: "revenue",
          label: "Revenue",
          previous_value: 100,
          amended_value: 102,
          delta: 2,
          relative_change: 0.02,
          direction: "increase",
          accession_number: "0000123456-26-000099",
          form: "10-Q/A",
          detection_kind: "amended_filing",
          amended_at: "2026-03-20T20:00:00Z",
          source: "https://www.sec.gov/Archives/edgar/data/123456/000012345626000099/amended10q.htm",
          confidence_severity: "medium",
          confidence_flags: ["amended_sec_filing"],
        },
      ],
      provenance: [
        {
          source_id: "ft_changes_since_last_filing",
          source_tier: "derived_from_official",
          display_label: "Fundamental Terminal Filing Changes Service",
          url: "https://github.com/gptvibe/Fundamental-Terminal",
          default_freshness_ttl_seconds: 21600,
          disclosure_note: "Latest-versus-prior filing comparison derived from cached SEC statements and amendment history.",
          role: "derived",
          as_of: "2025-11-02T20:00:00Z",
          last_refreshed_at: "2026-03-27T18:00:00Z",
        },
      ],
      as_of: "2025-11-02T20:00:00Z",
      last_refreshed_at: "2026-03-27T18:00:00Z",
      source_mix: {
        source_ids: ["ft_changes_since_last_filing"],
        source_tiers: ["derived_from_official"],
        primary_source_ids: [],
        fallback_source_ids: [],
        official_only: true,
      },
      confidence_flags: ["prior_values_amended"],
      refresh: { triggered: false, reason: "none", ticker: "AAPL", job_id: null },
      diagnostics: {
        coverage_ratio: 1,
        fallback_ratio: null,
        stale_flags: [],
        parser_confidence: null,
        missing_field_flags: [],
      },
    });

    render(React.createElement(ChangesSinceLastFilingCard, { ticker: "AAPL" }));

    await waitFor(() => {
      expect(screen.getAllByText("Revenue").length).toBeGreaterThan(0);
    });

    expect(screen.getByText("Negative Free Cash Flow")).toBeTruthy();
    expect(screen.getByText("Products")).toBeTruthy();
    expect(screen.getByText("Shares Outstanding")).toBeTruthy();
    expect(screen.getByText("Long-Term Debt")).toBeTruthy();
    expect(screen.getAllByText("10-Q/A").length).toBeGreaterThan(0);
  });
});
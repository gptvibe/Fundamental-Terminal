import { describe, expect, it } from "vitest";

import { buildWhatChangedHighlights } from "./what-changed-summary";

describe("buildWhatChangedHighlights", () => {
  it("builds ranked highlights for populated data", () => {
    const highlights = buildWhatChangedHighlights({
      changes: {
        current_filing: {
          accession_number: "0000001",
          filing_type: "10-Q",
          statement_type: "quarterly",
          period_start: "2026-01-01",
          period_end: "2026-03-31",
          source: "sec",
          last_updated: "2026-04-30T00:00:00Z",
          last_checked: "2026-04-30T00:00:00Z",
          filing_acceptance_at: "2026-04-30T00:00:00Z",
          fetch_timestamp: null,
        },
        previous_filing: null,
        summary: {
          filing_type: "10-Q",
          current_period_start: "2026-01-01",
          current_period_end: "2026-03-31",
          previous_period_start: "2025-01-01",
          previous_period_end: "2025-03-31",
          metric_delta_count: 2,
          new_risk_indicator_count: 0,
          segment_shift_count: 0,
          share_count_change_count: 0,
          capital_structure_change_count: 0,
          amended_prior_value_count: 0,
          high_signal_change_count: 3,
          comment_letter_count: 1,
        },
        metric_deltas: [
          {
            metric_key: "revenue",
            label: "Revenue",
            unit: "usd",
            previous_value: 100000000,
            current_value: 135000000,
            delta: 35000000,
            relative_change: 0.35,
            direction: "increase",
          },
        ],
        new_risk_indicators: [],
        segment_shifts: [],
        share_count_changes: [],
        capital_structure_changes: [],
        amended_prior_values: [],
        high_signal_changes: [],
        comment_letter_history: {
          total_letters: 1,
          letters_since_previous_filing: 1,
          latest_filing_date: "2026-04-29",
          recent_letters: [],
        },
        company: null,
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 1,
          missing_field_flags: [],
          reconciliation_penalty: 0,
          reconciliation_disagreement_count: 0,
        },
        provenance: [
          {
            source_id: "sec_companyfacts",
            source_tier: "official_regulator",
            display_label: "SEC Company Facts",
            url: "https://www.sec.gov",
            default_freshness_ttl_seconds: 21600,
            disclosure_note: "Official",
            role: "primary",
            as_of: "2026-03-31",
            last_refreshed_at: "2026-04-30T00:00:00Z",
          },
        ],
        as_of: "2026-03-31",
        last_refreshed_at: "2026-04-30T00:00:00Z",
        source_mix: {
          source_ids: ["sec_companyfacts"],
          source_tiers: ["official_regulator"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: [],
          official_only: true,
        },
        confidence_flags: [],
      },
      earningsSummary: {
        company: null,
        summary: {
          total_releases: 1,
          parsed_releases: 1,
          metadata_only_releases: 0,
          releases_with_guidance: 0,
          releases_with_buybacks: 0,
          releases_with_dividends: 0,
          latest_filing_date: "2026-04-29",
          latest_report_date: "2026-04-29",
          latest_reported_period_end: "2026-03-31",
          latest_revenue: 135000000,
          latest_operating_income: 10000000,
          latest_net_income: 7000000,
          latest_diluted_eps: 1.23,
        },
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 1,
          missing_field_flags: [],
          reconciliation_penalty: 0,
          reconciliation_disagreement_count: 0,
        },
        error: null,
      },
      activityOverview: {
        company: null,
        entries: [
          {
            id: "evt-1",
            date: "2026-05-01T00:00:00Z",
            type: "filing",
            badge: "new",
            title: "8-K filed for financing update",
            detail: "Financing update",
            href: null,
          },
        ],
        alerts: [
          {
            id: "a1",
            level: "high",
            title: "Liquidity pressure",
            detail: "Short runway",
            source: "capital",
            date: "2026-05-01T00:00:00Z",
            href: null,
          },
        ],
        summary: { total: 1, high: 1, medium: 0, low: 0 },
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        error: null,
        provenance: [
          {
            source_id: "sec_filings",
            source_tier: "official_regulator",
            display_label: "SEC Filings",
            url: "https://www.sec.gov",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Official",
            role: "primary",
            as_of: "2026-05-01",
            last_refreshed_at: "2026-05-01T00:00:00Z",
          },
        ],
        as_of: "2026-05-01",
        last_refreshed_at: "2026-05-01T00:00:00Z",
        source_mix: {
          source_ids: ["sec_filings"],
          source_tiers: ["official_regulator"],
          primary_source_ids: ["sec_filings"],
          fallback_source_ids: [],
          official_only: true,
        },
        confidence_flags: [],
      },
      models: {
        company: null,
        requested_models: ["dcf"],
        models: [
          {
            model_name: "dcf",
            model_version: "1",
            created_at: "2026-04-20T00:00:00Z",
            input_periods: null,
            result: { fair_value_per_share: 45 },
          },
          {
            model_name: "dcf",
            model_version: "1",
            created_at: "2026-04-10T00:00:00Z",
            input_periods: null,
            result: { fair_value_per_share: 30 },
          },
        ],
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 1,
          missing_field_flags: [],
          reconciliation_penalty: 0,
          reconciliation_disagreement_count: 0,
        },
        provenance: [
          {
            source_id: "sec_companyfacts",
            source_tier: "official_regulator",
            display_label: "SEC Company Facts",
            url: "https://www.sec.gov",
            default_freshness_ttl_seconds: 21600,
            disclosure_note: "Official",
            role: "primary",
            as_of: "2026-03-31",
            last_refreshed_at: "2026-04-20T00:00:00Z",
          },
        ],
        as_of: "2026-03-31",
        last_refreshed_at: "2026-04-20T00:00:00Z",
        source_mix: {
          source_ids: ["sec_companyfacts"],
          source_tiers: ["official_regulator"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: [],
          official_only: true,
        },
        confidence_flags: [],
      },
      ownershipSummary: {
        company: null,
        summary: {
          total_filings: 6,
          initial_filings: 2,
          amendments: 4,
          unique_reporting_persons: 4,
          latest_filing_date: "2026-04-27",
          latest_event_date: "2026-04-25",
          max_reported_percent: 0.12,
          chains_with_amendments: 1,
          amendments_with_delta: 1,
          ownership_increase_events: 1,
          ownership_decrease_events: 4,
          ownership_unchanged_events: 1,
          largest_increase_pp: 0.02,
          largest_decrease_pp: 0.05,
        },
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        error: null,
      },
      governanceSummary: {
        company: null,
        summary: {
          total_filings: 2,
          definitive_proxies: 1,
          supplemental_proxies: 1,
          filings_with_meeting_date: 2,
          filings_with_exec_comp: 1,
          filings_with_vote_items: 2,
          latest_meeting_date: "2026-04-21",
          max_vote_item_count: 9,
        },
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 1,
          missing_field_flags: [],
          reconciliation_penalty: 0,
          reconciliation_disagreement_count: 0,
        },
        error: null,
      },
    });

    expect(highlights).toHaveLength(4);
    expect(["Latest filing/event", "Alert pressure"]).toContain(highlights[0]?.title);
    expect(highlights.some((item) => item.title === "Financial movement")).toBe(true);
    expect(highlights.some((item) => item.title === "Valuation/model movement")).toBe(true);
    expect(highlights.some((item) => item.title === "Ownership signal")).toBe(true);
    expect(highlights.every((item) => item.sourceLabel.length > 0)).toBe(true);
    expect(highlights.every((item) => item.provenance.length > 0)).toBe(true);
  });

  it("handles partial data with a graceful single highlight", () => {
    const highlights = buildWhatChangedHighlights({
      changes: null,
      earningsSummary: {
        company: null,
        summary: {
          total_releases: 1,
          parsed_releases: 1,
          metadata_only_releases: 0,
          releases_with_guidance: 0,
          releases_with_buybacks: 0,
          releases_with_dividends: 0,
          latest_filing_date: "2026-04-29",
          latest_report_date: "2026-04-29",
          latest_reported_period_end: "2026-03-31",
          latest_revenue: 52000000,
          latest_operating_income: null,
          latest_net_income: null,
          latest_diluted_eps: 0.32,
        },
        refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
        diagnostics: {
          coverage_ratio: 1,
          fallback_ratio: 0,
          stale_flags: [],
          parser_confidence: 1,
          missing_field_flags: [],
          reconciliation_penalty: 0,
          reconciliation_disagreement_count: 0,
        },
        error: null,
      },
      activityOverview: null,
      models: null,
      ownershipSummary: null,
      governanceSummary: null,
    });

    expect(highlights).toHaveLength(1);
    expect(highlights[0]?.title).toBe("Financial movement");
    expect(highlights[0]?.severity).toBe("low");
  });

  it("returns an empty list when no source data is available", () => {
    const highlights = buildWhatChangedHighlights({
      changes: null,
      earningsSummary: null,
      activityOverview: null,
      models: null,
      ownershipSummary: null,
      governanceSummary: null,
    });

    expect(highlights).toEqual([]);
  });
});

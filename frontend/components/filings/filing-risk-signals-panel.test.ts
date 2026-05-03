import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FilingRiskSignalsPanel } from "@/components/filings/filing-risk-signals-panel";
import type { CompanyFilingRiskSignalsResponse } from "@/lib/types";

function buildPayload(): CompanyFilingRiskSignalsResponse {
  return {
    company: null,
    summary: {
      total_signals: 2,
      high_severity_count: 1,
      medium_severity_count: 1,
      latest_filed_date: "2026-02-02",
    },
    signals: [
      {
        ticker: "ACME",
        cik: "0000000000",
        accession_number: "0000000000-26-000001",
        form_type: "10-K",
        filed_date: "2026-02-02",
        signal_category: "material_weakness",
        matched_phrase: "material weakness",
        context_snippet: "Management identified a material weakness in internal control over financial reporting.",
        confidence: "high",
        severity: "high",
        source: "https://www.sec.gov/Archives/edgar/data/0/1.htm",
        provenance: "sec_filing_text",
        last_updated: "2026-02-02T00:00:00Z",
        last_checked: "2026-02-02T00:00:00Z",
      },
      {
        ticker: "ACME",
        cik: "0000000000",
        accession_number: "0000000000-26-000002",
        form_type: "8-K",
        filed_date: "2026-01-15",
        signal_category: "cybersecurity_incident",
        matched_phrase: "cybersecurity incident",
        context_snippet: "The company disclosed a cybersecurity incident affecting internal systems.",
        confidence: "high",
        severity: "medium",
        source: "https://www.sec.gov/Archives/edgar/data/0/2.htm",
        provenance: "sec_filing_text",
        last_updated: "2026-01-15T00:00:00Z",
        last_checked: "2026-01-15T00:00:00Z",
      },
    ],
    refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    diagnostics: {
      coverage_ratio: 1,
      fallback_ratio: null,
      stale_flags: [],
      parser_confidence: null,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
  };
}

describe("FilingRiskSignalsPanel", () => {
  it("renders recent filing signals with high severity pinned first", () => {
    const html = renderToStaticMarkup(React.createElement(FilingRiskSignalsPanel, { payload: buildPayload() }));

    expect(html).toContain("Recent high-signal filing alerts");
    expect(html).toContain("Material weakness");
    expect(html).toContain("High Priority");
    expect(html).toContain("Cybersecurity incident");
    expect(html).toContain("Latest filing with signal: Feb 02, 2026");
  });

  it("renders an empty-state message when no cached signals exist yet", () => {
    const html = renderToStaticMarkup(
      React.createElement(FilingRiskSignalsPanel, {
        payload: {
          ...buildPayload(),
          summary: { total_signals: 0, high_severity_count: 0, medium_severity_count: 0, latest_filed_date: null },
          signals: [],
          refresh: { triggered: true, reason: "manual", ticker: "ACME", job_id: "job-1" },
        },
      })
    );

    expect(html).toContain("No recent filing text alerts");
    expect(html).toContain("background refresh");
  });
});
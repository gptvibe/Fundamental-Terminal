import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { FilingParserInsights } from "@/components/filings/filing-parser-insights";
import type { FilingParserInsightPayload } from "@/lib/types";

vi.mock("recharts", () => {
  const MockWithChildren = ({ children }: { children?: React.ReactNode }) => React.createElement("div", null, children);
  const MockLeaf = () => React.createElement("div");

  return {
    CartesianGrid: MockLeaf,
    Legend: MockWithChildren,
    Line: MockLeaf,
    LineChart: MockWithChildren,
    ResponsiveContainer: MockWithChildren,
    Tooltip: MockLeaf,
    XAxis: MockLeaf,
    YAxis: MockLeaf,
  };
});

function makeInsight(partial: Partial<FilingParserInsightPayload>): FilingParserInsightPayload {
  return {
    accession_number: partial.accession_number ?? "0001234567-26-000999",
    filing_type: partial.filing_type ?? "10-K",
    period_start: partial.period_start ?? "2025-01-01",
    period_end: partial.period_end ?? "2025-12-31",
    source: partial.source ?? "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000999/form10k.htm",
    last_updated: partial.last_updated ?? "2026-03-10T00:00:00Z",
    last_checked: partial.last_checked ?? "2026-03-10T00:00:00Z",
    revenue: partial.revenue ?? 100000000,
    net_income: partial.net_income ?? 18000000,
    operating_income: partial.operating_income ?? 22000000,
    segments: partial.segments ?? [{ name: "Cloud", revenue: 70000000 }],
    mdna: partial.mdna ?? {
      key: "mda",
      label: "MD&A",
      title: "Item 2. Management's Discussion and Analysis",
      source: "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000999/form10q.htm",
      excerpt: "Liquidity tightened while management highlighted margin pressure.",
      signal_terms: ["liquidity", "margin"],
    },
    footnotes: partial.footnotes ?? [
      {
        key: "debt",
        label: "Debt And Borrowings",
        title: "Debt",
        source: "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000999/debt.htm",
        excerpt: "The company amended its credit facility.",
        signal_terms: ["debt", "credit facility"],
      },
    ],
    non_gaap: partial.non_gaap ?? {
      mention_count: 3,
      terms: ["non-gaap", "adjusted ebitda"],
      reconciliation_mentions: 0,
      has_reconciliation: false,
      source: "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000999/form10q.htm",
      excerpt: "Management emphasized adjusted EBITDA without a visible reconciliation.",
    },
    controls: partial.controls ?? {
      auditor_names: ["deloitte"],
      auditor_change_terms: ["engaged"],
      control_terms: ["material weakness"],
      material_weakness: true,
      ineffective_controls: true,
      non_reliance: false,
      source: "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000999/form10q.htm",
      excerpt: "Disclosure controls were not effective due to a material weakness.",
    },
  };
}

describe("FilingParserInsights", () => {
  it("renders latest filing metadata and SEC source link", () => {
    const html = renderToStaticMarkup(
      React.createElement(FilingParserInsights, {
        insights: [makeInsight({})],
      })
    );

    expect(html).toContain("Accession 0001234567-26-000999");
    expect(html).toContain("View SEC source");
    expect(html).toContain("href=\"https://www.sec.gov/Archives/edgar/data/1234567/000123456726000999/form10k.htm\"");
    expect(html).toContain("Cloud");
    expect(html).toContain("MD&amp;A excerpt");
    expect(html).toContain("High-signal footnotes");
    expect(html).toContain("material weakness");
  });

  it("renders refresh-aware empty state when no insights exist", () => {
    const html = renderToStaticMarkup(
      React.createElement(FilingParserInsights, {
        insights: [],
        refresh: {
          triggered: true,
          reason: "manual",
          ticker: "ACME",
          job_id: "job-1",
        },
      })
    );

    expect(html).toContain("No parsed filing snapshot yet");
    expect(html).toContain("This view will populate once the run completes");
  });
});

import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import CompanyFilingsPage from "@/app/company/[ticker]/filings/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: null },
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

vi.mock("@/components/filings/company-filings-timeline", () => ({
  CompanyFilingsTimeline: () => React.createElement("div", null, "timeline"),
}));

vi.mock("@/components/filings/filing-parser-insights", () => ({
  FilingParserInsights: () => React.createElement("div", null, "insights"),
}));

vi.mock("@/components/filings/filing-document-viewer", () => ({
  FilingDocumentViewer: () => React.createElement("div", null, "viewer"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFilings: vi.fn(async () => ({
    company: null,
    filings: [],
    timeline_source: "sec_submissions",
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyFilingInsights: vi.fn(async () => ({
    company: null,
    insights: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
  })),
  getCompanyChangesSinceLastFiling: vi.fn(async () => ({
    company: null,
    current_filing: null,
    previous_filing: null,
    summary: {
      filing_type: null,
      current_period_start: null,
      current_period_end: null,
      previous_period_start: null,
      previous_period_end: null,
      metric_delta_count: 0,
      new_risk_indicator_count: 0,
      segment_shift_count: 0,
      share_count_change_count: 0,
      capital_structure_change_count: 0,
      amended_prior_value_count: 0,
      high_signal_change_count: 0,
      comment_letter_count: 0,
    },
    metric_deltas: [],
    new_risk_indicators: [],
    segment_shifts: [],
    share_count_changes: [],
    capital_structure_changes: [],
    amended_prior_values: [],
    high_signal_changes: [],
    comment_letter_history: { total_letters: 0, letters_since_previous_filing: 0, latest_filing_date: null, recent_letters: [] },
    provenance: [],
    as_of: null,
    last_refreshed_at: null,
    source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
    confidence_flags: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    diagnostics: {} as never,
  })),
}));

describe("CompanyFilingsPage", () => {
  it("renders filing workspace panels and shell without crashing", () => {
    const html = renderToStaticMarkup(React.createElement(CompanyFilingsPage));

    expect(html).toContain("Filings");
    expect(html).toContain("SEC-first filing workflow");
    expect(html).toContain("Recent Filing Timeline");
    expect(html).toContain("Filing Parser Snapshot");
    expect(html).toContain("High-Signal Filing Changes");
    expect(html).toContain("Filing Viewer");
    expect(html).toContain("Form Coverage");
    expect(html).toContain("timeline");
    expect(html).toContain("insights");
  });
});

// @vitest-environment jsdom

import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import CompanyFilingsPage from "@/app/company/[ticker]/filings/page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: () => ({
    company: { ticker: "ACME", name: "Acme Corp", sector: "Tech", last_checked: "2026-03-10" },
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
  CompanyFilingsTimeline: ({ filings, onSelectFiling }: { filings: Array<{ source_url: string; accession_number: string | null }>; onSelectFiling: (filing: { source_url: string }) => void }) =>
    React.createElement(
      "div",
      null,
      filings.map((filing) =>
        React.createElement(
          "button",
          {
            key: filing.source_url,
            type: "button",
            onClick: () => onSelectFiling(filing),
          },
          filing.accession_number ?? filing.source_url
        )
      )
    ),
}));

vi.mock("@/components/filings/filing-parser-insights", () => ({
  FilingParserInsights: () => React.createElement("div", null, "insights"),
}));

vi.mock("@/components/filings/filing-document-viewer", () => ({
  FilingDocumentViewer: ({ filing }: { filing: { accession_number: string | null } | null }) =>
    React.createElement("div", null, `viewer:${filing?.accession_number ?? "none"}`),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFilings: vi.fn(async () => ({
    company: null,
    filings: [
      {
        accession_number: "0000001",
        form: "10-K",
        filing_date: "2026-03-01",
        report_date: "2025-12-31",
        primary_document: "annual.htm",
        primary_doc_description: "Annual",
        items: null,
        source_url: "https://sec.example/1",
      },
      {
        accession_number: "0000002",
        form: "8-K",
        filing_date: "2026-03-05",
        report_date: "2026-03-04",
        primary_document: "current.htm",
        primary_doc_description: "Current",
        items: "2.02",
        source_url: "https://sec.example/2",
      },
    ],
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
  getCompanyFilingEvents: vi.fn(async () => ({
    company: null,
    events: [
      {
        accession_number: "0000002",
        form: "8-K",
        filing_date: "2026-03-05",
        report_date: "2026-03-04",
        items: "2.02,9.01",
        item_code: "2.02",
        category: "Earnings",
        primary_document: "current.htm",
        primary_doc_description: "Item 2.02 earnings update",
        source_url: "https://sec.example/2",
        summary: "Item 2.02 earnings update",
        key_amounts: [],
        exhibit_references: ["99.1"],
        exhibit_previews: [
          {
            accession_number: "0000002",
            item_code: "2.02",
            exhibit_filename: "acme-ex99-1.htm",
            exhibit_type: "99.1",
            filing_date: "2026-03-05",
            source_url: "https://sec.example/2/acme-ex99-1.htm",
            snippet: "Acme reported quarterly earnings and reaffirmed full-year guidance.",
          },
        ],
      },
    ],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyFilingsPage integration", () => {
  it("updates filing viewer when timeline selection changes", async () => {
    const user = userEvent.setup();
    render(React.createElement(CompanyFilingsPage));

    await waitFor(() => {
      expect(screen.getByText("viewer:0000001")).toBeTruthy();
    });

    await user.click(screen.getByRole("button", { name: "0000002" }));
    expect(screen.getByText("viewer:0000002")).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText(/Exhibit preview/i)).toBeTruthy();
      expect(screen.getByText(/Acme reported quarterly earnings/i)).toBeTruthy();
    });
  });
});

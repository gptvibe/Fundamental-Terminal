import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import CompanyOwnershipChangesPage from "@/app/company/[ticker]/ownership-changes/page";

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

vi.mock("@/components/charts/beneficial-ownership-form-chart", () => ({
  BeneficialOwnershipFormChart: () => React.createElement("div", null, "form-chart"),
}));

vi.mock("@/components/ui/plain-english-scorecard", () => ({
  PlainEnglishScorecard: () => React.createElement("div", null, "scorecard"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyBeneficialOwnership: vi.fn(async () => ({
    company: null,
    filings: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyBeneficialOwnershipSummary: vi.fn(async () => ({
    company: null,
    summary: {
      total_filings: 0,
      initial_filings: 0,
      amendments: 0,
      unique_reporting_persons: 0,
      latest_filing_date: null,
      latest_event_date: null,
      max_reported_percent: null,
      chains_with_amendments: 0,
      amendments_with_delta: 0,
      ownership_increase_events: 0,
      ownership_decrease_events: 0,
      ownership_unchanged_events: 0,
      largest_increase_pp: null,
      largest_decrease_pp: null,
    },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyOwnershipChangesPage", () => {
  it("renders ownership sections including owner table and activist panel", () => {
    const html = renderToStaticMarkup(React.createElement(CompanyOwnershipChangesPage));

    expect(html).toContain("Stake Changes");
    expect(html).toContain("SEC-first stake-change workspace centered on Schedules 13D and 13G");
    expect(html).toContain("Signal Visuals");
    expect(html).toContain("Beneficial Owner Table");
    expect(html).toContain("Activist Signals");
    expect(html).toContain("Filing Timeline");
    expect(html).toContain("Preparing stake-change visuals...");
    expect(html).toContain("Loading owner table...");
    expect(html).toContain("Loading activist signal panel...");
    expect(html).toContain("Loading beneficial ownership activity...");
    expect(html).toContain("form-chart");
  });
});

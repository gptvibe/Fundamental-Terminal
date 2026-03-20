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
}));

describe("CompanyFilingsPage", () => {
  it("renders filing workspace panels and shell without crashing", () => {
    const html = renderToStaticMarkup(React.createElement(CompanyFilingsPage));

    expect(html).toContain("Filings");
    expect(html).toContain("Recent Filing Timeline");
    expect(html).toContain("Filing Parser Snapshot");
    expect(html).toContain("Filing Viewer");
    expect(html).toContain("Form Coverage");
    expect(html).toContain("timeline");
    expect(html).toContain("insights");
  });
});

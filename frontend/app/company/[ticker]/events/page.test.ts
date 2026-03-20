import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import CompanyEventsPage from "@/app/company/[ticker]/events/page";

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

vi.mock("@/components/charts/filing-event-category-chart", () => ({
  FilingEventCategoryChart: () => React.createElement("div", null, "event-chart"),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFilingEvents: vi.fn(async () => ({
    company: null,
    events: [],
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
  getCompanyFilingEventsSummary: vi.fn(async () => ({
    company: null,
    summary: {
      total_events: 0,
      unique_accessions: 0,
      categories: {},
      latest_event_date: null,
      max_key_amount: null,
    },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanyEventsPage", () => {
  it("renders event page sections and initial loading state", () => {
    const html = renderToStaticMarkup(React.createElement(CompanyEventsPage));

    expect(html).toContain("Event Feed");
    expect(html).toContain("Event Categories");
    expect(html).toContain("Recent 8-K Timeline");
    expect(html).toContain("Loading filing events...");
    expect(html).toContain("event-chart");
  });
});

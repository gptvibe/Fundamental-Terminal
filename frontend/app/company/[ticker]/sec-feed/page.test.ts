import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import CompanySecFeedPage from "@/app/company/[ticker]/sec-feed/page";

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

vi.mock("@/lib/api", () => ({
  getCompanyActivityOverview: vi.fn(async () => ({
    company: null,
    entries: [],
    alerts: [],
    summary: { total: 0, high: 0, medium: 0, low: 0 },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanySecFeedPage", () => {
  it("renders SEC feed page panels and loading placeholders", () => {
    const html = renderToStaticMarkup(React.createElement(CompanySecFeedPage));

    expect(html).toContain("SEC Feed");
    expect(html).toContain("Priority Alerts");
    expect(html).toContain("Chronological SEC Stream");
    expect(html).toContain("Loading alerts...");
    expect(html).toContain("Loading SEC feed...");
  });
});

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
    provenance: [
      {
        source_id: "ft_activity_overview",
        source_tier: "derived_from_official",
        display_label: "Fundamental Terminal Activity Overview",
        url: "https://github.com/gptvibe/Fundamental-Terminal",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Unified activity feed assembled from official SEC disclosures and official macro status signals.",
        role: "derived",
        as_of: "2026-03-10",
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
      {
        source_id: "sec_edgar",
        source_tier: "official_regulator",
        display_label: "SEC EDGAR Filing Archive",
        url: "https://www.sec.gov/edgar/search/",
        default_freshness_ttl_seconds: 21600,
        disclosure_note: "Official SEC filing archive used for filing metadata, ownership, governance, and event disclosures.",
        role: "primary",
        as_of: "2026-03-10",
        last_refreshed_at: "2026-03-10T00:00:00Z",
      },
    ],
    as_of: "2026-03-10",
    last_refreshed_at: "2026-03-10T00:00:00Z",
    source_mix: {
      source_ids: ["ft_activity_overview", "sec_edgar"],
      source_tiers: ["derived_from_official", "official_regulator"],
      primary_source_ids: ["sec_edgar"],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    market_context_status: {
      state: "partial",
      label: "Macro partial",
      observation_date: "2026-03-10",
      source: "U.S. Treasury Daily Par Yield Curve",
    },
    refresh: { triggered: false, reason: "none", ticker: "ACME", job_id: null },
    error: null,
  })),
}));

describe("CompanySecFeedPage", () => {
  it("renders SEC feed page panels and loading placeholders", () => {
    const html = renderToStaticMarkup(React.createElement(CompanySecFeedPage));

    expect(html).toContain("SEC Feed");
    expect(html).toContain("Unified SEC signal stream across filings");
    expect(html).toContain("Priority Alerts");
    expect(html).toContain("Chronological SEC Stream");
    expect(html).toContain("Source &amp; Freshness");
    expect(html).toContain("Loading alerts...");
    expect(html).toContain("Loading SEC feed...");
  });
});

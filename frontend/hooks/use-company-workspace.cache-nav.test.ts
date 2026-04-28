// @vitest-environment jsdom

import * as React from "react";
import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyLayoutProvider } from "@/components/layout/company-layout-context";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyWorkspaceBootstrap } from "@/lib/api";

const mockUseJobStream = vi.fn();

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: (...args: unknown[]) => mockUseJobStream(...args),
}));

vi.mock("@/lib/active-job", () => ({
  rememberActiveJob: vi.fn(),
}));

vi.mock("@/lib/recent-companies", () => ({
  recordRecentCompany: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFinancials: vi.fn(),
  getCompanyWorkspaceBootstrap: vi.fn(),
  getCompanyOverview: vi.fn(),
  getCompanyInsiderTrades: vi.fn(),
  getCompanyInstitutionalHoldings: vi.fn(),
  getCompanyEarningsSummary: vi.fn(),
  invalidateApiReadCacheForTicker: vi.fn(),
  refreshCompany: vi.fn(),
}));

function buildFinancialsResponse(overrides: Record<string, unknown> = {}) {
  return {
    company: null,
    financials: [],
    price_history: [],
    refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
    diagnostics: null,
    ...overrides,
  };
}

function buildBootstrapPayload() {
  return {
    company: { ticker: "RKLB", name: "Rocket Lab Corp", cache_state: "fresh" },
    financials: buildFinancialsResponse({
      company: {
        ticker: "RKLB",
        name: "Rocket Lab Corp",
        sector: "Space",
        market_sector: "Space",
        last_checked: "2026-03-31T00:00:00Z",
        cache_state: "fresh",
      },
      financials: [
        {
          filing_type: "10-K",
          period_end: "2025-12-31",
          revenue: 601800000,
          eps: null,
          free_cash_flow: -321810000,
        },
      ],
    }),
    brief: null,
    earnings_summary: {
      company: { ticker: "RKLB", name: "Rocket Lab Corp", cache_state: "fresh" },
      summary: {
        total_releases: 0,
        parsed_releases: 0,
        metadata_only_releases: 0,
        releases_with_guidance: 0,
        releases_with_buybacks: 0,
        releases_with_dividends: 0,
        latest_filing_date: null,
        latest_report_date: null,
        latest_reported_period_end: null,
        latest_revenue: null,
        latest_operating_income: null,
        latest_net_income: null,
        latest_diluted_eps: null,
      },
      refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
      diagnostics: null,
      error: null,
    },
    insider_trades: null,
    institutional_holdings: null,
    errors: { insider: null, institutional: null, earnings_summary: null },
  } as never;
}

function FinancialsWorkspaceProbe({ remountKey }: { remountKey: string }) {
  const workspace = useCompanyWorkspace("RKLB", {
    includeEarningsSummary: true,
    financialsView: "core_segments",
  });

  const phase = workspace.loading && !workspace.company && workspace.financials.length === 0 ? "skeleton" : "ready";

  return React.createElement(
    "div",
    { key: remountKey, "data-testid": "workspace-phase" },
    `${phase}:${workspace.company?.ticker ?? "none"}:${workspace.financials.length}`
  );
}

function FinancialsWorkspaceHost({ remountKey }: { remountKey: string }) {
  return React.createElement(
    CompanyLayoutProvider,
    null,
    React.createElement(FinancialsWorkspaceProbe, { remountKey, key: remountKey })
  );
}

describe("useCompanyWorkspace financials cache navigation", () => {
  beforeEach(() => {
    mockUseJobStream.mockReturnValue({
      consoleEntries: [],
      connectionState: "open",
      lastEvent: null,
    });
    vi.mocked(getCompanyWorkspaceBootstrap).mockResolvedValue(buildBootstrapPayload());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("uses initial workspace seed and skips workspace-bootstrap when the seed is fresh", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const initialWorkspaceData = {
      financialData: buildFinancialsResponse({
        company: {
          ticker: "RKLB",
          name: "Rocket Lab Corp",
          sector: "Space",
          market_sector: "Space",
          last_checked: "2026-03-31T00:00:00Z",
          cache_state: "fresh",
        },
        financials: [
          {
            filing_type: "10-K",
            period_end: "2025-12-31",
            revenue: 601800000,
            eps: null,
            free_cash_flow: -321810000,
          },
        ],
        refresh: { triggered: false, reason: "fresh", ticker: "RKLB", job_id: null },
      }) as never,
      briefData: null,
      earningsSummaryData: null,
      insiderData: null,
      institutionalData: null,
      insiderError: null,
      institutionalError: null,
      activeJobId: null,
    };

    const { result } = renderHook(
      () =>
        useCompanyWorkspace("RKLB", {
          includeEarningsSummary: true,
          financialsView: "core_segments",
          initialWorkspaceData,
        }),
      {
        wrapper: ({ children }) => React.createElement(CompanyLayoutProvider, null, children),
      }
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.company?.ticker).toBe("RKLB");
    expect(result.current.financials).toHaveLength(1);
    expect(fetchBootstrap).not.toHaveBeenCalled();
  });

  it("reuses fresh shared layout cache on financials remount without another workspace-bootstrap request", async () => {
    const fetchBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
    const { rerender } = render(React.createElement(FinancialsWorkspaceHost, { remountKey: "first" }));

    await waitFor(() => {
      expect(screen.getByTestId("workspace-phase").textContent).toBe("ready:RKLB:1");
    });

    expect(fetchBootstrap).toHaveBeenCalledTimes(1);

    rerender(React.createElement(FinancialsWorkspaceHost, { remountKey: "second" }));

    expect(screen.getByTestId("workspace-phase").textContent).toBe("ready:RKLB:1");
    expect(fetchBootstrap).toHaveBeenCalledTimes(1);
  });
});

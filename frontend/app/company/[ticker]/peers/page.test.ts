// @vitest-environment jsdom

import * as React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CompanyPeersPage from "@/app/company/[ticker]/peers/page";

const mockUseCompanyWorkspace = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ ticker: "acme" }),
}));

vi.mock("@/hooks/use-company-workspace", () => ({
  useCompanyWorkspace: (...args: unknown[]) => mockUseCompanyWorkspace(...args),
}));

vi.mock("@/components/layout/company-workspace-shell", () => ({
  CompanyWorkspaceShell: ({ rail, children }: { rail?: React.ReactNode; children?: React.ReactNode }) => React.createElement("div", null, rail, children),
}));

vi.mock("@/components/layout/company-utility-rail", () => ({
  CompanyUtilityRail: ({ children }: { children?: React.ReactNode }) => React.createElement("aside", null, children),
}));

vi.mock("@/components/ui/panel", () => ({
  Panel: ({ title, children }: { title: string; children?: React.ReactNode }) => React.createElement("section", null, React.createElement("h2", null, title), children),
}));

vi.mock("@/components/ui/status-pill", () => ({
  StatusPill: () => React.createElement("span", null, "status"),
}));

vi.mock("@/components/peers/peer-comparison-dashboard", () => ({
  PeerComparisonDashboard: ({ ticker }: { ticker: string }) => React.createElement("div", null, `peer-dashboard-${ticker}`),
}));

describe("CompanyPeersPage", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders loading state while company context loads", () => {
    mockUseCompanyWorkspace.mockReturnValue({
      company: null,
      financials: [],
      loading: true,
      refreshing: false,
      refreshState: null,
      consoleEntries: [],
      connectionState: "idle",
      queueRefresh: vi.fn(),
      reloadKey: "reload-1",
    });

    render(React.createElement(CompanyPeersPage));

    expect(screen.getByText("Loading company context...")).toBeTruthy();
    expect(screen.getByText("Loading peer comparison...")).toBeTruthy();
  });

  it("renders peer workspace metrics once company context is available", () => {
    mockUseCompanyWorkspace.mockReturnValue({
      company: { name: "Acme Corp", sector: "Technology", last_checked: "2026-03-22T00:00:00Z" },
      financials: [{ id: 1 }],
      loading: false,
      refreshing: false,
      refreshState: null,
      consoleEntries: [],
      connectionState: "idle",
      queueRefresh: vi.fn(),
      reloadKey: "reload-2",
    });

    render(React.createElement(CompanyPeersPage));

    expect(screen.getAllByText("Peer Workspace")[0]).toBeTruthy();
    expect(screen.getByText("4 selected peers")).toBeTruthy();
    expect(screen.getByText("peer-dashboard-ACME")).toBeTruthy();
  });
});

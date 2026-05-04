// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySubnav } from "@/components/layout/company-subnav";

const mockUsePathname = vi.fn();
const mockRouterPrefetch = vi.fn();
const mockUseCompanyLayoutContext = vi.fn();
const getCompanyFinancials = vi.fn();
const getCompanyOverview = vi.fn();
const prefetchCompanyWorkspaceTabs = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({
    prefetch: mockRouterPrefetch,
  }),
}));

vi.mock("@/components/layout/company-layout-context", () => ({
  useCompanyLayoutContext: () => mockUseCompanyLayoutContext(),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFinancials: (...args: unknown[]) => getCompanyFinancials(...args),
  getCompanyOverview: (...args: unknown[]) => getCompanyOverview(...args),
}));

vi.mock("@/lib/company-workspace-prefetch", () => ({
  prefetchCompanyWorkspaceTabs: (...args: unknown[]) => prefetchCompanyWorkspaceTabs(...args),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

describe("CompanySubnav", () => {
  beforeEach(() => {
    mockUsePathname.mockReset();
    mockRouterPrefetch.mockReset();
    mockUseCompanyLayoutContext.mockReset();
    getCompanyFinancials.mockReset();
    getCompanyOverview.mockReset();
    prefetchCompanyWorkspaceTabs.mockReset();
    mockUseCompanyLayoutContext.mockReturnValue(null);
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "unsupported" } });
    getCompanyOverview.mockResolvedValue({ company: { oil_support_status: "unsupported" }, financials: { company: { oil_support_status: "unsupported" } } });
  });

  it("shows primary tabs in desktop nav and marks charts tab active on charts route", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/charts");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    const chartsTab = within(desktopNav).getByRole("link", { name: "Charts" });
    expect(chartsTab.getAttribute("href")).toBe("/company/AAPL/charts");
    expect(chartsTab.getAttribute("aria-current")).toBe("page");
  });

  it("uses a More dropdown on desktop for specialist sections and keeps primary tabs visible directly", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/earnings");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    // Primary tabs are directly visible
    expect(within(desktopNav).getByRole("link", { name: "Brief" })).toBeTruthy();
    expect(within(desktopNav).getByRole("link", { name: "Financials" })).toBeTruthy();
    expect(within(desktopNav).getByRole("link", { name: "Charts" })).toBeTruthy();
    expect(within(desktopNav).getByRole("link", { name: "Models" })).toBeTruthy();
    expect(within(desktopNav).getByRole("link", { name: "Peers" })).toBeTruthy();

    // Specialist tabs are behind More dropdown
    const moreButton = within(desktopNav).getByRole("button", { name: "More" });
    expect(moreButton.className).toContain("is-active");

    // Open More and verify specialist tabs are present
    fireEvent.click(moreButton);
    expect(within(desktopNav).getByRole("link", { name: "Earnings" }).getAttribute("aria-current")).toBe("page");
    expect(within(desktopNav).getByRole("link", { name: "Filings" })).toBeTruthy();
    expect(within(desktopNav).getByRole("link", { name: "SEC Feed" })).toBeTruthy();
  });

  it("supports arrow-key focus movement across primary tabs and More button on desktop", () => {
    mockUsePathname.mockReturnValue("/company/AAPL");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    const briefTab = within(desktopNav).getByRole("link", { name: "Brief" });
    briefTab.focus();
    fireEvent.keyDown(briefTab, { key: "ArrowRight" });

    expect(document.activeElement?.textContent).toBe("Financials");
  });

  it("uses a mobile More menu for secondary sections and keeps Ownership & Stakes merged", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/ownership-changes");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const mobileNav = within(container).getByRole("navigation", { name: "Company workspace quick sections" });

    const moreButton = within(mobileNav).getByRole("button", { name: "More" });
    expect(moreButton.className).toContain("is-active");

    fireEvent.click(moreButton);

    const ownershipTab = within(mobileNav).getByRole("link", { name: "Ownership & Stakes" });
    expect(ownershipTab.getAttribute("href")).toBe("/company/AAPL/stakes");
    expect(ownershipTab.getAttribute("aria-current")).toBe("page");
  });

  it("shows Oil in the More menu for eligible tickers once company state resolves", async () => {
    mockUsePathname.mockReturnValue("/company/XOM/models");
    mockUseCompanyLayoutContext.mockReturnValue({
      company: null,
      publisherCount: 1,
      registerPublisher: () => () => undefined,
      setCompany: vi.fn(),
    });

    const { container, rerender } = render(React.createElement(CompanySubnav, { ticker: "XOM" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      expect(getCompanyFinancials).not.toHaveBeenCalled();
      expect(getCompanyOverview).not.toHaveBeenCalled();
    });

    mockUseCompanyLayoutContext.mockReturnValue({
      company: { ticker: "XOM", oil_support_status: "partial" },
      publisherCount: 1,
      registerPublisher: () => () => undefined,
      setCompany: vi.fn(),
    });
    rerender(React.createElement(CompanySubnav, { ticker: "XOM" }));

    const moreButton = within(desktopNav).getByRole("button", { name: "More" });
    fireEvent.click(moreButton);

    await waitFor(() => {
      const oilTab = within(desktopNav).getByRole("link", { name: "Oil" });
      expect(oilTab.getAttribute("href")).toBe("/company/XOM/oil");
    });
  });

  it("keeps the Oil tab hidden in the More menu for unsupported companies", async () => {
    mockUsePathname.mockReturnValue("/company/KMI/models");
    mockUseCompanyLayoutContext.mockReturnValue({
      company: null,
      publisherCount: 1,
      registerPublisher: () => () => undefined,
      setCompany: vi.fn(),
    });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "KMI" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      expect(getCompanyFinancials).not.toHaveBeenCalled();
      expect(getCompanyOverview).not.toHaveBeenCalled();
    });

    const moreButton = within(desktopNav).getByRole("button", { name: "More" });
    fireEvent.click(moreButton);

    expect(within(desktopNav).queryByRole("link", { name: "Oil" })).toBeNull();
  });

  it("reuses shared company context on the overview route when deciding Oil tab visibility", async () => {
    mockUsePathname.mockReturnValue("/company/XOM");
    mockUseCompanyLayoutContext.mockReturnValue({
      company: { ticker: "XOM", oil_support_status: "partial" },
      publisherCount: 1,
      registerPublisher: () => () => undefined,
      setCompany: vi.fn(),
    });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "XOM" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    const moreButton = within(desktopNav).getByRole("button", { name: "More" });
    fireEvent.click(moreButton);

    await waitFor(() => {
      expect(within(desktopNav).getByRole("link", { name: "Oil" }).getAttribute("href")).toBe("/company/XOM/oil");
    });
    expect(getCompanyOverview).not.toHaveBeenCalled();
    expect(getCompanyFinancials).not.toHaveBeenCalled();
  });

  it("triggers workspace prefetch on hover and focus of tab links", () => {
    mockUsePathname.mockReturnValue("/company/AAPL");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });
    const financialsLink = within(desktopNav).getByRole("link", { name: "Financials" });

    fireEvent.mouseEnter(financialsLink);
    fireEvent.focus(financialsLink);

    expect(prefetchCompanyWorkspaceTabs).toHaveBeenNthCalledWith(
      1,
      "AAPL",
      expect.objectContaining({
        trigger: "hover",
        pageRoute: "/company/[ticker]",
        scenario: "company_workspace_nav_prefetch",
      })
    );
    expect(prefetchCompanyWorkspaceTabs).toHaveBeenNthCalledWith(
      2,
      "AAPL",
      expect.objectContaining({
        trigger: "focus",
        pageRoute: "/company/[ticker]",
        scenario: "company_workspace_nav_prefetch",
      })
    );
    expect(mockRouterPrefetch).toHaveBeenCalledWith("/company/AAPL/financials");
  });
});

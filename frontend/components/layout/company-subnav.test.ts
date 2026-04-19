// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySubnav } from "@/components/layout/company-subnav";

const mockUsePathname = vi.fn();
const mockUseCompanyLayoutContext = vi.fn();
const getCompanyFinancials = vi.fn();
const getCompanyOverview = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

vi.mock("@/components/layout/company-layout-context", () => ({
  useCompanyLayoutContext: () => mockUseCompanyLayoutContext(),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFinancials: (...args: unknown[]) => getCompanyFinancials(...args),
  getCompanyOverview: (...args: unknown[]) => getCompanyOverview(...args),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

describe("CompanySubnav", () => {
  beforeEach(() => {
    mockUsePathname.mockReset();
    mockUseCompanyLayoutContext.mockReset();
    getCompanyFinancials.mockReset();
    getCompanyOverview.mockReset();
    mockUseCompanyLayoutContext.mockReturnValue(null);
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "unsupported" } });
    getCompanyOverview.mockResolvedValue({ company: { oil_support_status: "unsupported" }, financials: { company: { oil_support_status: "unsupported" } } });
  });

  it("includes charts tab and marks it active on charts route", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/charts");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    const chartsTab = within(desktopNav).getByRole("link", { name: "Charts" });
    expect(chartsTab.getAttribute("href")).toBe("/company/AAPL/charts");
    expect(chartsTab.getAttribute("aria-current")).toBe("page");
  });

  it("renders all company tabs directly on desktop without a More trigger", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/earnings");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    expect(within(desktopNav).queryByRole("button", { name: "More" })).toBeNull();

    const earningsTab = within(desktopNav).getByRole("link", { name: "Earnings" });
    expect(earningsTab.getAttribute("href")).toBe("/company/AAPL/earnings");
    expect(earningsTab.getAttribute("aria-current")).toBe("page");
  });

  it("renders a single primary row and supports arrow-key focus movement", () => {
    mockUsePathname.mockReturnValue("/company/AAPL");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    expect(within(container).queryByText("Core views")).toBeNull();
    expect(within(container).queryByText("Research feeds")).toBeNull();

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

  it("adds an Oil tab for supported or partial oil companies", async () => {
    mockUsePathname.mockReturnValue("/company/XOM/models");
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "partial" } });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "XOM" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      expect(getCompanyFinancials).toHaveBeenCalledWith("XOM", { view: "core" });
      const oilTab = within(desktopNav).getByRole("link", { name: "Oil" });
      expect(oilTab.getAttribute("href")).toBe("/company/XOM/oil");
    });
  });

  it("keeps the Oil tab hidden for unsupported companies", async () => {
    mockUsePathname.mockReturnValue("/company/KMI/models");
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "unsupported" } });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "KMI" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      expect(getCompanyFinancials).toHaveBeenCalledWith("KMI", { view: "core" });
    });
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

    await waitFor(() => {
      expect(within(desktopNav).getByRole("link", { name: "Oil" }).getAttribute("href")).toBe("/company/XOM/oil");
    });
    expect(getCompanyOverview).not.toHaveBeenCalled();
    expect(getCompanyFinancials).not.toHaveBeenCalled();
  });
});

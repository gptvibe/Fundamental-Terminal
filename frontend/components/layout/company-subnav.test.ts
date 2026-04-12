// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySubnav } from "@/components/layout/company-subnav";

const mockUsePathname = vi.fn();
const getCompanyFinancials = vi.fn();
const getCompanyOverview = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
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
    getCompanyFinancials.mockReset();
    getCompanyOverview.mockReset();
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "unsupported" } });
    getCompanyOverview.mockResolvedValue({ company: { oil_support_status: "unsupported" }, financials: { company: { oil_support_status: "unsupported" } } });
  });

  it("includes peers tab and marks it active on peers route", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/peers");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    const peersTab = within(desktopNav).getByRole("link", { name: "Peers" });
    expect(peersTab.getAttribute("href")).toBe("/company/AAPL/peers");
    expect(peersTab.getAttribute("aria-current")).toBe("page");
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
    mockUsePathname.mockReturnValue("/company/XOM/oil");
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "partial" } });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "XOM" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      const oilTab = within(desktopNav).getByRole("link", { name: "Oil" });
      expect(oilTab.getAttribute("href")).toBe("/company/XOM/oil");
      expect(oilTab.getAttribute("aria-current")).toBe("page");
    });
  });

  it("keeps the Oil tab hidden for unsupported companies", async () => {
    mockUsePathname.mockReturnValue("/company/KMI/models");
    getCompanyFinancials.mockResolvedValue({ company: { oil_support_status: "unsupported" } });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "KMI" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      expect(getCompanyFinancials).toHaveBeenCalledWith("KMI");
    });
    expect(within(desktopNav).queryByRole("link", { name: "Oil" })).toBeNull();
  });

  it("reuses the overview payload on the overview route when deciding Oil tab visibility", async () => {
    mockUsePathname.mockReturnValue("/company/XOM");
    getCompanyOverview.mockResolvedValue({
      company: { oil_support_status: "partial" },
      financials: { company: { oil_support_status: "partial" } },
    });

    const { container } = render(React.createElement(CompanySubnav, { ticker: "XOM" }));
    const desktopNav = within(container).getByRole("navigation", { name: "Company workspace sections" });

    await waitFor(() => {
      expect(getCompanyOverview).toHaveBeenCalledWith("XOM");
    });
    expect(getCompanyFinancials).not.toHaveBeenCalled();
    expect(within(desktopNav).getByRole("link", { name: "Oil" }).getAttribute("href")).toBe("/company/XOM/oil");
  });
});

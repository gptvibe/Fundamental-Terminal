// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySubnav } from "@/components/layout/company-subnav";

const mockUsePathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

describe("CompanySubnav", () => {
  beforeEach(() => {
    mockUsePathname.mockReset();
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

    const ownershipTab = within(mobileNav).getByRole("menuitem", { name: "Ownership & Stakes" });
    expect(ownershipTab.getAttribute("href")).toBe("/company/AAPL/stakes");
    expect(ownershipTab.getAttribute("aria-current")).toBe("page");
  });
});

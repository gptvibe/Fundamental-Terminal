// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CompanySubnav } from "@/components/layout/company-subnav";

const mockUsePathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

describe("CompanySubnav", () => {
  it("includes peers tab and marks it active on peers route", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/peers");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    const peersTab = within(container).getByRole("link", { name: "Peers" });
    expect(peersTab.getAttribute("href")).toBe("/company/AAPL/peers");
    expect(peersTab.getAttribute("aria-current")).toBe("page");
  });

  it("includes earnings tab and marks it active on earnings route", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/earnings");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    const earningsTab = within(container).getByRole("link", { name: "Earnings" });
    expect(earningsTab.getAttribute("href")).toBe("/company/AAPL/earnings");
    expect(earningsTab.getAttribute("aria-current")).toBe("page");
  });

  it("groups core and research views and supports arrow-key focus movement", () => {
    mockUsePathname.mockReturnValue("/company/AAPL");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    expect(within(container).getByText("Core views")).toBeTruthy();
    expect(within(container).getByText("Research feeds")).toBeTruthy();

    const overviewTab = within(container).getByRole("link", { name: "Overview" });
    overviewTab.focus();
    fireEvent.keyDown(overviewTab, { key: "ArrowRight" });

    expect(document.activeElement?.textContent).toBe("Financials");
  });
});

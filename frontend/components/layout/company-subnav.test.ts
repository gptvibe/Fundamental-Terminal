// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CompanySubnav } from "@/components/layout/company-subnav";

const mockUsePathname = vi.fn();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children?: React.ReactNode }) => React.createElement("a", { href, ...props }, children),
}));

describe("CompanySubnav", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockUsePathname.mockReset();
  });

  it("includes peers tab and marks it active on peers route", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/peers");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    const peersTab = within(container).getByRole("link", { name: "Peers" });
    expect(peersTab.getAttribute("href")).toBe("/company/AAPL/peers");
    expect(peersTab.getAttribute("aria-current")).toBe("page");
  });

  it("moves secondary routes into the More menu and marks the active entry", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/earnings");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    const moreButton = within(container).getByRole("button", { name: "More" });
    expect(moreButton.className).toContain("is-active");

    fireEvent.click(moreButton);

    const earningsTab = within(container).getByRole("menuitem", { name: "Earnings" });
    expect(earningsTab.getAttribute("href")).toBe("/company/AAPL/earnings");
    expect(earningsTab.getAttribute("aria-current")).toBe("page");
  });

  it("renders a single primary row and supports arrow-key focus movement", () => {
    mockUsePathname.mockReturnValue("/company/AAPL");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    expect(within(container).queryByText("Core views")).toBeNull();
    expect(within(container).queryByText("Research feeds")).toBeNull();

    const briefTab = within(container).getByRole("link", { name: "Brief" });
    briefTab.focus();
    fireEvent.keyDown(briefTab, { key: "ArrowRight" });

    expect(document.activeElement?.textContent).toBe("Financials");
  });

  it("maps the mobile picker to the merged Ownership & Stakes destination", () => {
    mockUsePathname.mockReturnValue("/company/AAPL/ownership-changes");

    const { container } = render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    const picker = within(container).getByLabelText("Section") as HTMLSelectElement;
    expect(picker.value).toBe("ownership-stakes");
    expect(within(container).getByRole("option", { name: "More · Ownership & Stakes" })).toBeTruthy();

    fireEvent.change(picker, { target: { value: "ownership-stakes" } });

    expect(mockPush).toHaveBeenCalledWith("/company/AAPL/stakes");
  });
});

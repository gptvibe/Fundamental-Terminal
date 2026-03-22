// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
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

    render(React.createElement(CompanySubnav, { ticker: "AAPL" }));

    const peersTab = screen.getByRole("link", { name: "Peers" });
    expect(peersTab.getAttribute("href")).toBe("/company/AAPL/peers");
    expect(peersTab.getAttribute("aria-current")).toBe("page");
  });
});

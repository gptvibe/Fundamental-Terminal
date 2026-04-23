// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChartsModeSwitch } from "./charts-mode-switch";

const useSearchParams = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/company/acme/charts",
  useSearchParams: () => useSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("ChartsModeSwitch", () => {
  it("keeps as_of when switching to studio", () => {
    useSearchParams.mockReturnValue(new URLSearchParams("as_of=2026-04-17"));

    render(React.createElement(ChartsModeSwitch, { activeMode: "outlook", studioEnabled: true }));

    expect(screen.getByRole("link", { name: "Growth Outlook" }).getAttribute("href")).toBe("/company/acme/charts?as_of=2026-04-17");
    expect(screen.getByRole("link", { name: "Projection Studio" }).getAttribute("href")).toBe("/company/acme/charts?as_of=2026-04-17&mode=studio");
  });

  it("disables Projection Studio when unavailable", () => {
    useSearchParams.mockReturnValue(new URLSearchParams("as_of=2026-04-17"));

    render(React.createElement(ChartsModeSwitch, { activeMode: "outlook", studioEnabled: false }));

    expect(screen.getByRole("link", { name: "Growth Outlook" })).toBeTruthy();
    expect(screen.getByText("Projection Studio").getAttribute("aria-disabled")).toBe("true");
  });
});
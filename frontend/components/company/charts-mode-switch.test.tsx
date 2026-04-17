// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChartsModeSwitch } from "./charts-mode-switch";

vi.mock("next/navigation", () => ({
  usePathname: () => "/company/acme/charts",
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

describe("ChartsModeSwitch", () => {
  it("disables Projection Studio when unavailable", () => {
    render(React.createElement(ChartsModeSwitch, { activeMode: "outlook", studioEnabled: false }));

    expect(screen.getByRole("link", { name: "Growth Outlook" })).toBeTruthy();
    expect(screen.getByText("Projection Studio").getAttribute("aria-disabled")).toBe("true");
  });
});
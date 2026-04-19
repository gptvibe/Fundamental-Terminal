// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyRouteError from "./error";

describe("CompanyRouteError", () => {
  it("renders a route-agnostic fallback and retries the current page", () => {
    const reset = vi.fn();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    render(<CompanyRouteError error={new Error("boom")} reset={reset} />);

    expect(screen.getByRole("heading", { name: "Company workspace failed to load" })).toBeTruthy();
    expect(screen.getByText(/retry this company page/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Retry page" }));

    expect(reset).toHaveBeenCalledTimes(1);
    expect(consoleError).toHaveBeenCalledWith("company route render error", expect.any(Error));

    consoleError.mockRestore();
  });
});
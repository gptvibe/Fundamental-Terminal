// @vitest-environment jsdom

import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppChrome } from "@/components/layout/app-chrome";

const push = vi.fn();
const mockUsePathname = vi.fn();
const mockUseLocalUserData = vi.fn();
const searchCompanies = vi.fn();
const resolveCompanyIdentifier = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => mockUsePathname(),
}));

vi.mock("@/hooks/use-local-user-data", () => ({
  useLocalUserData: () => mockUseLocalUserData(),
}));

vi.mock("@/lib/api", () => ({
  searchCompanies: (...args: unknown[]) => searchCompanies(...args),
  resolveCompanyIdentifier: (...args: unknown[]) => resolveCompanyIdentifier(...args),
}));

vi.mock("@/components/layout/app-logo", () => ({
  AppLogo: () => React.createElement("div", null, "Fundamental Terminal"),
}));

vi.mock("@/components/search/company-autocomplete-menu", () => ({
  CompanyAutocompleteMenu: () => null,
}));

describe("AppChrome", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    push.mockReset();
    mockUsePathname.mockReset();
    mockUseLocalUserData.mockReset();
    searchCompanies.mockReset();
    resolveCompanyIdentifier.mockReset();

    mockUsePathname.mockReturnValue("/company/O");
    mockUseLocalUserData.mockReturnValue({ savedCompanyCount: 0 });
    searchCompanies.mockResolvedValue({
      query: "O",
      results: [],
      refresh: { triggered: false, reason: "none", ticker: "O", job_id: null },
    });
    resolveCompanyIdentifier.mockResolvedValue({ resolved: false, ticker: null, name: null, error: "not_found" });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("does not auto-run autocomplete for the current company route ticker", async () => {
    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(searchCompanies).not.toHaveBeenCalled();
  });

  it("runs autocomplete after the user edits the search text", async () => {
    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    fireEvent.change(screen.getAllByLabelText("Search company or ticker")[0], { target: { value: "OA" } });

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(searchCompanies).toHaveBeenCalledWith("OA", { refresh: false });
  });
});
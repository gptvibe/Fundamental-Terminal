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

  it("runs an immediate autocomplete lookup before SEC resolve on fast submit", async () => {
    searchCompanies.mockResolvedValue({
      query: "MSFT",
      results: [
        {
          ticker: "MSFT",
          cik: "0000789019",
          name: "Microsoft Corp.",
          sector: "Technology",
          market_sector: "Technology",
          market_industry: "Software",
          regulated_entity: null,
          strict_official_mode: false,
          last_checked: null,
          last_checked_financials: null,
          last_checked_prices: null,
          last_checked_insiders: null,
          last_checked_institutional: null,
          last_checked_filings: null,
          earnings_last_checked: null,
          cache_state: "fresh",
        },
      ],
      refresh: { triggered: false, reason: "fresh", ticker: "MSFT", job_id: null },
    });

    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    const searchInput = screen.getAllByLabelText("Search company or ticker")[0];
    fireEvent.change(searchInput, { target: { value: "MSFT" } });
    const searchForm = searchInput.closest("form");
    expect(searchForm).toBeTruthy();

    await act(async () => {
      fireEvent.submit(searchForm as HTMLFormElement);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(searchCompanies).toHaveBeenCalledTimes(1);
    expect(resolveCompanyIdentifier).not.toHaveBeenCalled();
    expect(push).toHaveBeenCalledWith("/company/MSFT");
  });

  it("does not auto-select a fuzzy autocomplete result on fast submit", async () => {
    searchCompanies.mockResolvedValue({
      query: "NET",
      results: [
        {
          ticker: "NFLX",
          cik: "0001065280",
          name: "NETFLIX INC",
          sector: "Services-Video Tape Rental",
          market_sector: "Communication Services",
          market_industry: "Entertainment",
          regulated_entity: null,
          strict_official_mode: false,
          last_checked: null,
          last_checked_financials: null,
          last_checked_prices: null,
          last_checked_insiders: null,
          last_checked_institutional: null,
          last_checked_filings: null,
          earnings_last_checked: null,
          cache_state: "stale",
        },
      ],
      refresh: { triggered: false, reason: "none", ticker: "NET", job_id: null },
    });
    resolveCompanyIdentifier.mockResolvedValue({ resolved: true, ticker: "NET", name: "Cloudflare, Inc.", error: null });

    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    const searchInput = screen.getAllByLabelText("Search company or ticker")[0];
    fireEvent.change(searchInput, { target: { value: "NET" } });
    const searchForm = searchInput.closest("form");
    expect(searchForm).toBeTruthy();

    await act(async () => {
      fireEvent.submit(searchForm as HTMLFormElement);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(searchCompanies).toHaveBeenCalledTimes(1);
    expect(resolveCompanyIdentifier).toHaveBeenCalledWith("NET");
    expect(push).toHaveBeenCalledWith("/company/NET");
  });
});
// @vitest-environment jsdom

import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppChrome } from "@/components/layout/app-chrome";
import { COMMAND_PALETTE_REFRESH_EVENT } from "@/lib/command-palette-events";

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

    expect(searchCompanies).toHaveBeenCalledTimes(1);
    expect(searchCompanies).toHaveBeenCalledWith(
      "OA",
      expect.objectContaining({ refresh: false, signal: expect.any(AbortSignal) })
    );
  });

  it("reuses autocomplete results on submit without issuing a duplicate search", async () => {
    searchCompanies.mockResolvedValue({
      query: "MSFT",
      results: [buildCompanyPayload({ ticker: "MSFT", name: "Microsoft Corp.", cik: "0000789019" })],
      refresh: { triggered: false, reason: "fresh", ticker: "MSFT", job_id: null },
    });

    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    const searchInput = screen.getAllByLabelText("Search company or ticker")[0];
    fireEvent.change(searchInput, { target: { value: "MSFT" } });

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
      await Promise.resolve();
    });

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

  it("runs an immediate autocomplete lookup before SEC resolve on fast submit", async () => {
    searchCompanies.mockResolvedValue({
      query: "MSFT",
      results: [buildCompanyPayload({ ticker: "MSFT", name: "Microsoft Corp.", cik: "0000789019" })],
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
      results: [buildCompanyPayload({ ticker: "NFLX", name: "NETFLIX INC", cik: "0001065280", cache_state: "stale" })],
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

  it("falls back to resolve only when the latest autocomplete payload has no exact match", async () => {
    searchCompanies.mockResolvedValue({
      query: "NET",
      results: [buildCompanyPayload({ ticker: "NFLX", name: "NETFLIX INC", cik: "0001065280", cache_state: "stale" })],
      refresh: { triggered: false, reason: "none", ticker: "NET", job_id: null },
    });
    resolveCompanyIdentifier.mockResolvedValue({ resolved: true, ticker: "NET", name: "Cloudflare, Inc.", error: null });

    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    const searchInput = screen.getAllByLabelText("Search company or ticker")[0];
    fireEvent.change(searchInput, { target: { value: "NET" } });

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
      await Promise.resolve();
    });

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

  it("aborts stale autocomplete requests when the query changes", async () => {
    const requests = new Map<string, { signal: AbortSignal | undefined; resolve: (value: unknown) => void }>();
    searchCompanies.mockImplementation((query: string, options?: { signal?: AbortSignal }) => {
      return new Promise((resolve) => {
        requests.set(query, { signal: options?.signal, resolve });
      });
    });

    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    const searchInput = screen.getAllByLabelText("Search company or ticker")[0];
    fireEvent.change(searchInput, { target: { value: "M" } });

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });

    const firstRequest = requests.get("M");
    expect(firstRequest?.signal?.aborted).toBe(false);

    fireEvent.change(searchInput, { target: { value: "MS" } });

    await act(async () => {
      await Promise.resolve();
    });

    expect(firstRequest?.signal?.aborted).toBe(true);

    await act(async () => {
      vi.advanceTimersByTime(300);
      await Promise.resolve();
    });

    expect(requests.get("MS")?.signal?.aborted).toBe(false);
  });

  it("opens and closes the command palette with keyboard", () => {
    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();

    fireEvent.keyDown(screen.getByLabelText("Command search"), { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
  });

  it("supports fuzzy command search and executes route actions", () => {
    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByLabelText("Command search"), { target: { value: "gtw" } });
    fireEvent.keyDown(screen.getByLabelText("Command search"), { key: "Enter" });

    expect(push).toHaveBeenLastCalledWith("/watchlist");
  });

  it("supports keyboard navigation across command results", () => {
    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByLabelText("Command search"), { target: { value: "go to" } });
    fireEvent.keyDown(screen.getByLabelText("Command search"), { key: "ArrowDown" });
    fireEvent.keyDown(screen.getByLabelText("Command search"), { key: "Enter" });

    const lastRoute = push.mock.calls.at(-1)?.[0];
    expect(["/screener", "/watchlist"]).toContain(lastRoute);
  });

  it("handles ticker and filings command routes", () => {
    mockUsePathname.mockReturnValue("/company/MSFT");
    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    fireEvent.keyDown(window, { key: "k", metaKey: true });
    fireEvent.change(screen.getByLabelText("Command search"), { target: { value: "open ticker" } });
    fireEvent.click(screen.getByRole("button", { name: /Open ticker/ }));

    expect(push).toHaveBeenLastCalledWith("/company/MSFT");

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByLabelText("Command search"), { target: { value: "search filings" } });
    fireEvent.click(screen.getByRole("button", { name: /Search filings/ }));

    expect(push).toHaveBeenLastCalledWith("/company/MSFT/filings");
  });

  it("dispatches refresh events and toggles data source panel", () => {
    const refreshListener = vi.fn();
    window.addEventListener(COMMAND_PALETTE_REFRESH_EVENT, refreshListener as EventListener);

    render(React.createElement(AppChrome, null, React.createElement("div", null, "workspace")));

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByLabelText("Command search"), { target: { value: "refresh current company" } });
    fireEvent.keyDown(screen.getByLabelText("Command search"), { key: "Enter" });
    expect(refreshListener).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    fireEvent.change(screen.getByLabelText("Command search"), { target: { value: "toggle data source panel" } });
    fireEvent.keyDown(screen.getByLabelText("Command search"), { key: "Enter" });
    expect(screen.getByRole("complementary", { name: "Data source panel" })).toBeTruthy();

    window.removeEventListener(COMMAND_PALETTE_REFRESH_EVENT, refreshListener as EventListener);
  });
});

function buildCompanyPayload(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    ticker: "AAPL",
    cik: "0000320193",
    name: "Apple Inc.",
    sector: "Technology",
    market_sector: "Technology",
    market_industry: "Consumer Electronics",
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
    ...overrides,
  };
}

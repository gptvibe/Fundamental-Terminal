// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import {
  RECENT_COMPANIES_STORAGE_KEY,
  clearRecentCompanies,
  readRecentCompanies,
  recordRecentCompany,
} from "@/lib/recent-companies";

describe("recent company helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("records companies with normalized tickers and newest-first ordering", () => {
    recordRecentCompany({ ticker: "aapl", name: "Apple Inc.", sector: "Technology", openedAt: "2026-03-21T10:00:00Z" });
    recordRecentCompany({ ticker: "MSFT", name: "Microsoft", sector: "Technology", openedAt: "2026-03-22T10:00:00Z" });

    const recentCompanies = readRecentCompanies();

    expect(recentCompanies).toHaveLength(2);
    expect(recentCompanies[0]).toMatchObject({ ticker: "MSFT", name: "Microsoft" });
    expect(recentCompanies[1]).toMatchObject({ ticker: "AAPL", name: "Apple Inc." });
  });

  it("dedupes repeated companies and preserves known metadata", () => {
    recordRecentCompany({ ticker: "msft", name: "Microsoft" });
    recordRecentCompany({ ticker: "MSFT", sector: "Technology" });

    const recentCompanies = readRecentCompanies();

    expect(recentCompanies).toHaveLength(1);
    expect(recentCompanies[0]).toMatchObject({ ticker: "MSFT", name: "Microsoft", sector: "Technology" });
  });

  it("clears the recent company store", () => {
    recordRecentCompany({ ticker: "NVDA", name: "NVIDIA" });

    clearRecentCompanies();

    expect(readRecentCompanies()).toEqual([]);
    expect(window.localStorage.getItem(RECENT_COMPANIES_STORAGE_KEY)).toBe(JSON.stringify([]));
  });
});
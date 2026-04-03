// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import {
  LOCAL_COMPARE_SET_STORAGE_KEY,
  addCompareCompanies,
  buildCompareHref,
  clearCompareCompanies,
  readLocalCompareSet,
  removeCompareCompany,
} from "@/lib/local-compare-set";

describe("local compare set helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("normalizes and stores compare companies", () => {
    addCompareCompanies([
      { ticker: "aapl", name: "Apple" },
      { ticker: "msft", name: "Microsoft" },
    ]);

    expect(readLocalCompareSet().map((item) => item.ticker).sort()).toEqual(["AAPL", "MSFT"]);
    expect(window.localStorage.getItem(LOCAL_COMPARE_SET_STORAGE_KEY)).toContain("AAPL");
  });

  it("removes and clears compare companies", () => {
    addCompareCompanies([{ ticker: "AAPL" }, { ticker: "MSFT" }]);

    removeCompareCompany("AAPL");
    expect(readLocalCompareSet().map((item) => item.ticker)).toEqual(["MSFT"]);

    clearCompareCompanies();
    expect(readLocalCompareSet()).toEqual([]);
  });

  it("builds a capped compare href", () => {
    expect(buildCompareHref(["aapl", "msft", "nvda", "amzn", "meta", "goog"]))
      .toBe("/compare?tickers=AAPL%2CMSFT%2CNVDA%2CAMZN%2CMETA");
  });
});
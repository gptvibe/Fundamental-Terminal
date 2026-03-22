// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import {
  LOCAL_USER_DATA_STORAGE_KEY,
  clearAllLocalUserData,
  exportLocalUserData,
  importLocalUserData,
  readLocalUserData,
  saveCompanyNote,
  toggleWatchlistCompany,
} from "@/lib/local-user-data";

describe("local user data transfer helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("exports LocalUserData using the existing watchlist and notes contract", () => {
    toggleWatchlistCompany({ ticker: "aapl", name: "Apple", sector: "Technology" });
    saveCompanyNote({ ticker: "aapl", name: "Apple", sector: "Technology" }, "High-margin business");

    const exported = exportLocalUserData();

    expect(exported.watchlist[0]?.ticker).toBe("AAPL");
    expect(exported.notes.AAPL?.note).toBe("High-margin business");
  });

  it("imports LocalUserData JSON and normalizes ticker casing", () => {
    const imported = importLocalUserData(JSON.stringify({
      watchlist: [
        { ticker: "msft", name: "Microsoft", sector: "Technology", savedAt: "2026-03-01T00:00:00.000Z" },
      ],
      notes: {
        msft: {
          ticker: "msft",
          name: "Microsoft",
          sector: "Technology",
          note: "Cloud durability",
          updatedAt: "2026-03-02T00:00:00.000Z",
        },
      },
    }));

    expect(imported.watchlist[0]?.ticker).toBe("MSFT");
    expect(imported.notes.MSFT?.note).toBe("Cloud durability");
    expect(readLocalUserData().watchlist[0]?.ticker).toBe("MSFT");
  });

  it("clears all local user data", () => {
    toggleWatchlistCompany({ ticker: "NVDA" });

    clearAllLocalUserData();

    expect(readLocalUserData()).toEqual({ watchlist: [], notes: {} });
    expect(window.localStorage.getItem(LOCAL_USER_DATA_STORAGE_KEY)).toBe(JSON.stringify({ watchlist: [], notes: {} }));
  });

  it("throws a clear error on invalid import JSON", () => {
    expect(() => importLocalUserData("{not-json}")).toThrow("Import file is not valid JSON.");
  });
});

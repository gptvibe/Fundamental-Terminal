// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import {
  LOCAL_USER_DATA_VERSION,
  LOCAL_USER_DATA_STORAGE_KEY,
  clearAllLocalUserData,
  deleteWatchlistSavedView,
  exportLocalUserData,
  importLocalUserData,
  readLocalUserData,
  saveCompanyNote,
  saveWatchlistMonitoringEntry,
  saveWatchlistSavedView,
  toggleWatchlistCompany,
} from "@/lib/local-user-data";

describe("local user data transfer helpers", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("exports LocalUserData using the existing watchlist and notes contract", () => {
    toggleWatchlistCompany({ ticker: "aapl", name: "Apple", sector: "Technology" });
    saveCompanyNote({ ticker: "aapl", name: "Apple", sector: "Technology" }, "High-margin business");
    saveWatchlistMonitoringEntry({
      ticker: "AAPL",
      triageState: "reviewing",
      profileKey: "deep-dive",
      rationale: "Supply chain normalization can rerate margins.",
      triggers: {
        nextFiling: true,
        major8k: false,
        insiderActivity: false,
        ownershipChange: false,
        dilutionOrCapitalMarkets: false,
        valuationReview: true,
        customNote: "Revisit valuation after next filing.",
      },
      lastReviewedAt: null,
      nextReviewAt: "2026-04-15",
      snoozedUntil: null,
      holdUntil: null,
      updatedAt: "2026-04-08T00:00:00.000Z",
    });

    const exported = exportLocalUserData();

    expect(exported.watchlist[0]?.ticker).toBe("AAPL");
    expect(exported.version).toBe(LOCAL_USER_DATA_VERSION);
    expect(exported.notes.AAPL?.note).toBe("High-margin business");
    expect(exported.monitoring.AAPL?.triageState).toBe("reviewing");
    expect(exported.monitoring.AAPL?.triggers.nextFiling).toBe(true);
    expect(exported.monitoring.AAPL?.triggers.customNote).toBe("Revisit valuation after next filing.");
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
      monitoring: {
        msft: {
          ticker: "msft",
          triageState: "monitoring",
          profileKey: "quality-compounder",
          rationale: "Watch Azure bookings and capex efficiency.",
          triggers: {
            nextFiling: true,
            major8k: true,
            insiderActivity: false,
            ownershipChange: true,
            dilutionOrCapitalMarkets: false,
            valuationReview: false,
            customNote: "Track stake updates",
          },
          nextReviewAt: "2026-04-30",
          updatedAt: "2026-04-01T00:00:00.000Z",
        },
      },
      savedWatchlistViews: [
        {
          id: "due-view",
          name: "Due This Week",
          criteria: {
            primaryFilter: "review-due",
            triageStates: ["reviewing"],
            sortBy: "review",
            searchText: "",
            profileKey: null,
          },
          createdAt: "2026-04-02T00:00:00.000Z",
          updatedAt: "2026-04-02T00:00:00.000Z",
        },
      ],
    }));

    expect(imported.watchlist[0]?.ticker).toBe("MSFT");
    expect(imported.version).toBe(LOCAL_USER_DATA_VERSION);
    expect(imported.notes.MSFT?.note).toBe("Cloud durability");
    expect(imported.monitoring.MSFT?.profileKey).toBe("quality-compounder");
    expect(imported.monitoring.MSFT?.triggers.major8k).toBe(true);
    expect(imported.monitoring.MSFT?.triggers.customNote).toBe("Track stake updates");
    expect(imported.savedWatchlistViews[0]?.criteria.primaryFilter).toBe("review-due");
    expect(readLocalUserData().watchlist[0]?.ticker).toBe("MSFT");
  });

  it("imports legacy monitoring entries without triggers and keeps names and notes", () => {
    const imported = importLocalUserData(JSON.stringify({
      watchlist: [
        { ticker: "orcl", name: "Oracle", sector: "Technology", savedAt: "2026-03-01T00:00:00.000Z" },
      ],
      notes: {
        orcl: {
          ticker: "orcl",
          name: "Oracle",
          sector: "Technology",
          note: "Legacy import should keep this note",
          updatedAt: "2026-03-02T00:00:00.000Z",
        },
      },
      monitoring: {
        orcl: {
          ticker: "orcl",
          triageState: "monitoring",
          profileKey: "quality-compounder",
          rationale: "Legacy entry",
          nextReviewAt: "2026-04-30",
          updatedAt: "2026-04-01T00:00:00.000Z",
        },
      },
    }));

    expect(imported.watchlist[0]?.name).toBe("Oracle");
    expect(imported.notes.ORCL?.note).toBe("Legacy import should keep this note");
    expect(imported.monitoring.ORCL?.triggers.customNote).toBe("");
    expect(imported.monitoring.ORCL?.triggers.nextFiling).toBe(false);
  });

  it("saves and deletes custom watchlist views", () => {
    saveWatchlistSavedView({
      name: "Change Sweep",
      criteria: {
        primaryFilter: "material-change",
        triageStates: [],
        sortBy: "attention",
        searchText: "",
        profileKey: null,
      },
    });

    const saved = readLocalUserData().savedWatchlistViews;
    expect(saved).toHaveLength(1);

    deleteWatchlistSavedView(saved[0].id);
    expect(readLocalUserData().savedWatchlistViews).toEqual([]);
  });

  it("clears all local user data", () => {
    toggleWatchlistCompany({ ticker: "NVDA" });

    clearAllLocalUserData();

    expect(readLocalUserData()).toEqual({ version: LOCAL_USER_DATA_VERSION, watchlist: [], notes: {}, monitoring: {}, savedWatchlistViews: [] });
    expect(window.localStorage.getItem(LOCAL_USER_DATA_STORAGE_KEY)).toBe(JSON.stringify({ version: LOCAL_USER_DATA_VERSION, watchlist: [], notes: {}, monitoring: {}, savedWatchlistViews: [] }));
  });

  it("throws a clear error on invalid import JSON", () => {
    expect(() => importLocalUserData("{not-json}")).toThrow("Import file is not valid JSON.");
  });
});

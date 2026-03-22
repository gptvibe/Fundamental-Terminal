// @vitest-environment jsdom

import * as React from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomeSavedCompaniesPanel } from "@/components/personal/home-saved-companies-panel";

const push = vi.fn();
const mockUseLocalUserData = vi.fn();
const showAppToast = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/hooks/use-local-user-data", () => ({
  useLocalUserData: () => mockUseLocalUserData(),
}));

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

describe("HomeSavedCompaniesPanel", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    push.mockReset();
    showAppToast.mockReset();
    mockUseLocalUserData.mockReset();
  });

  it("shows transfer actions and runs export and clear-all handlers", () => {
    const exportData = vi.fn(() => ({ watchlist: [], notes: {} }));
    const clearAll = vi.fn();

    mockUseLocalUserData.mockReturnValue({
      savedCompanies: [
        {
          ticker: "AAPL",
          name: "Apple Inc.",
          sector: "Technology",
          savedAt: "2026-03-22T00:00:00Z",
          note: "Watch iPhone cycle",
          noteUpdatedAt: "2026-03-22T00:00:00Z",
          isInWatchlist: true,
          hasNote: true,
        },
      ],
      watchlistCount: 1,
      noteCount: 1,
      removeFromWatchlist: vi.fn(),
      clearNote: vi.fn(),
      exportData,
      importData: vi.fn(),
      clearAll,
    });

    const createObjectURL = vi.fn(() => "blob:url");
    const revokeObjectURL = vi.fn();
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;
    HTMLAnchorElement.prototype.click = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(React.createElement(HomeSavedCompaniesPanel));

    fireEvent.click(screen.getByRole("button", { name: "Export JSON" }));
    expect(exportData).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Clear All" }));
    expect(clearAll).toHaveBeenCalled();
  });

  it("imports LocalUserData JSON through hidden file input", async () => {
    const importData = vi.fn(() => ({ watchlist: [], notes: {} }));

    mockUseLocalUserData.mockReturnValue({
      savedCompanies: [
        {
          ticker: "MSFT",
          name: "Microsoft",
          sector: "Technology",
          savedAt: "2026-03-22T00:00:00Z",
          note: null,
          noteUpdatedAt: null,
          isInWatchlist: true,
          hasNote: false,
        },
      ],
      watchlistCount: 1,
      noteCount: 0,
      removeFromWatchlist: vi.fn(),
      clearNote: vi.fn(),
      exportData: vi.fn(() => ({ watchlist: [], notes: {} })),
      importData,
      clearAll: vi.fn(),
    });

    render(React.createElement(HomeSavedCompaniesPanel));

    const input = screen.getAllByLabelText("Import saved companies JSON")[0] as HTMLInputElement;
    const file = new File([JSON.stringify({ watchlist: [], notes: {} })], "local-user-data.json", { type: "application/json" });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(importData).toHaveBeenCalled();
    });
  });
});

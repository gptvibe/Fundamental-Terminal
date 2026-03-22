// @vitest-environment jsdom

import * as React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyDevicePanel } from "@/components/personal/company-device-panel";

const mockUseLocalUserData = vi.fn();
const showAppToast = vi.fn();

vi.mock("@/hooks/use-local-user-data", () => ({
  useLocalUserData: () => mockUseLocalUserData(),
}));

vi.mock("@/lib/app-toast", () => ({
  showAppToast: (...args: unknown[]) => showAppToast(...args),
}));

describe("CompanyDevicePanel", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockUseLocalUserData.mockReset();
    showAppToast.mockReset();
  });

  it("surfaces browser-only storage limitation clearly", () => {
    mockUseLocalUserData.mockReturnValue({
      isSaved: vi.fn(() => false),
      getNote: vi.fn(() => null),
      toggleWatchlist: vi.fn(() => true),
      clearNote: vi.fn(),
      saveNote: vi.fn(),
      syncMetadata: vi.fn(),
    });

    render(React.createElement(CompanyDevicePanel, { ticker: "AAPL", companyName: "Apple", sector: "Technology" }));

    expect(screen.getByText(/Browser-only storage:/)).toBeTruthy();
  });

  it("toggles watchlist and emits a toast", () => {
    const toggleWatchlist = vi.fn(() => true);

    mockUseLocalUserData.mockReturnValue({
      isSaved: vi.fn(() => false),
      getNote: vi.fn(() => null),
      toggleWatchlist,
      clearNote: vi.fn(),
      saveNote: vi.fn(),
      syncMetadata: vi.fn(),
    });

    render(React.createElement(CompanyDevicePanel, { ticker: "AAPL" }));

    fireEvent.click(screen.getAllByRole("button", { name: "Save to My Watchlist" })[0]);

    expect(toggleWatchlist).toHaveBeenCalled();
    expect(showAppToast).toHaveBeenCalled();
  });
});

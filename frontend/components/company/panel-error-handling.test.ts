// @vitest-environment jsdom

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import React, { ReactElement } from "react";

import { PanelErrorBoundary } from "@/components/company/brief-primitives";
import {
  getCompanyWorkspaceBootstrap,
  getCompanyFinancials,
  getCompanyOverview,
} from "@/lib/api";
import { CompanyLayoutProvider } from "@/components/layout/company-layout-context";

vi.mock("@/hooks/use-job-stream", () => ({
  useJobStream: () => ({
    consoleEntries: [],
    connectionState: "open",
    lastEvent: null,
  }),
}));

vi.mock("@/lib/active-job", () => ({
  rememberActiveJob: vi.fn(),
}));

vi.mock("@/lib/recent-companies", () => ({
  recordRecentCompany: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  getCompanyFinancials: vi.fn(),
  getCompanyWorkspaceBootstrap: vi.fn(),
  getCompanyOverview: vi.fn(),
  getCompanyInsiderTrades: vi.fn(),
  getCompanyInstitutionalHoldings: vi.fn(),
  invalidateApiReadCacheForTicker: vi.fn(),
  refreshCompany: vi.fn(),
}));

// Mock child component that simulates an error
function FailingPanelContent(): ReactElement {
  throw new Error("Failed to render panel content");
}

// Mock child component that renders successfully
function SuccessfulPanelContent(): ReactElement {
  return React.createElement("div", null, "Panel content loaded successfully");
}

describe("Panel Error Handling Integration", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("PanelErrorBoundary with failing children", () => {
    it("displays error fallback UI when child component throws", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement(PanelErrorBoundary, {
          kicker: "Test Panel",
          title: "Unable to load panel",
        }, React.createElement(FailingPanelContent))
      );

      expect(screen.getByText("Unable to load panel")).toBeDefined();
      expect(screen.getByText("Test Panel")).toBeDefined();
      expect(screen.getByText("Failed to render panel content")).toBeDefined();
      expect(screen.queryByText("Panel content loaded successfully")).toBeNull();

      consoleSpy.mockRestore();
    });

    it("isolates error to the boundary and doesn't crash sibling components", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement("div", null,
          React.createElement(PanelErrorBoundary, {
            kicker: "Broken Panel",
            title: "This panel broke",
          }, React.createElement(FailingPanelContent)),
          React.createElement("div", { "data-testid": "sibling" }, "I am still here")
        )
      );

      expect(screen.getByTestId("sibling")).toBeDefined();
      expect(screen.getByText("I am still here")).toBeDefined();
      expect(screen.getByText("This panel broke")).toBeDefined();

      consoleSpy.mockRestore();
    });

    it("renders successfully when no error is thrown", () => {
      render(
        React.createElement(PanelErrorBoundary, {
          kicker: "Success Panel",
          title: "Panel loaded",
        }, React.createElement(SuccessfulPanelContent))
      );

      expect(screen.getByText("Panel content loaded successfully")).toBeDefined();
      expect(screen.queryByText("Panel loaded")).toBeNull();
    });
  });

  describe("API Fetch Failure Scenarios", () => {
    it("handles 404 not found error in API call", async () => {
      const mockBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      mockBootstrap.mockRejectedValue(new Error("API request failed: 404 Not Found"));

      // Simulate fetching data and showing error
      const ComponentThatFetches = () => {
        const [error, setError] = React.useState<string | null>(null);
        const [loaded, setLoaded] = React.useState(false);

        React.useEffect(() => {
          getCompanyWorkspaceBootstrap("MISSING", { signal: new AbortController().signal }).catch((err) => {
            setError(err instanceof Error ? err.message : "Unknown error");
            setLoaded(true);
          });
        }, []);

        if (error) {
          throw new Error(`Failed to load data: ${error}`);
        }
        return React.createElement("div", null, "Data loaded");
      };

      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement(PanelErrorBoundary, {
          kicker: "Company Data",
          title: "Unable to load company information",
        }, React.createElement(ComponentThatFetches))
      );

      await waitFor(() => {
        expect(screen.getByText("Unable to load company information")).toBeDefined();
      });

      consoleSpy.mockRestore();
    });

    it("handles 500 server error in API call", async () => {
      const mockBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      mockBootstrap.mockRejectedValue(new Error("API request failed: 500 Internal Server Error"));

      const ComponentThatFetches = () => {
        const [error, setError] = React.useState<string | null>(null);

        React.useEffect(() => {
          getCompanyWorkspaceBootstrap("RKLB", { signal: new AbortController().signal }).catch((err) => {
            setError(err instanceof Error ? err.message : "Unknown error");
          });
        }, []);

        if (error) {
          throw new Error(error);
        }
        return React.createElement("div", null, "Data loaded");
      };

      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement(PanelErrorBoundary, {
          kicker: "Financial Data",
          title: "Server error loading data",
        }, React.createElement(ComponentThatFetches))
      );

      await waitFor(() => {
        expect(screen.getByText("Server error loading data")).toBeDefined();
      });

      consoleSpy.mockRestore();
    });

    it("handles network timeout errors", async () => {
      const mockBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      mockBootstrap.mockRejectedValue(new Error("Request timeout"));

      const ComponentThatFetches = () => {
        const [error, setError] = React.useState<string | null>(null);

        React.useEffect(() => {
          getCompanyWorkspaceBootstrap("RKLB", { signal: new AbortController().signal }).catch((err) => {
            setError(err instanceof Error ? err.message : "Unknown error");
          });
        }, []);

        if (error) {
          throw new Error(`Network error: ${error}`);
        }
        return React.createElement("div", null, "Data loaded");
      };

      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement(PanelErrorBoundary, {
          kicker: "Market Data",
          title: "Unable to fetch data",
        }, React.createElement(ComponentThatFetches))
      );

      await waitFor(() => {
        expect(screen.getByText("Unable to fetch data")).toBeDefined();
      });

      consoleSpy.mockRestore();
    });
  });

  describe("Multiple Panels with Selective Error Isolation", () => {
    it("allows one failing panel while others succeed", () => {
      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement("div", null,
          React.createElement(PanelErrorBoundary, {
            kicker: "Panel 1",
            title: "Failed to load",
          }, React.createElement(FailingPanelContent)),
          React.createElement(PanelErrorBoundary, {
            kicker: "Panel 2",
            title: "Loaded successfully",
          }, React.createElement(SuccessfulPanelContent)),
          React.createElement(PanelErrorBoundary, {
            kicker: "Panel 3",
            title: "Also loaded successfully",
          }, React.createElement(SuccessfulPanelContent))
        )
      );

      // Check that first panel shows error
      expect(screen.getByText("Failed to load")).toBeDefined();
      expect(screen.getByText("Failed to render panel content")).toBeDefined();

      // Check that other panels render successfully
      const successMessages = screen.getAllByText("Panel content loaded successfully");
      expect(successMessages).toHaveLength(2);

      consoleSpy.mockRestore();
    });
  });

  describe("Error Boundary with Use-Company-Workspace 404", () => {
    it("properly surfaces 404 error from hook through error boundary", async () => {
      const mockBootstrap = vi.mocked(getCompanyWorkspaceBootstrap);
      mockBootstrap.mockRejectedValue(new Error("API request failed: 404 Not Found"));

      // This simulates what happens when a company workspace hook tries to fetch a missing ticker
      const SimulatedWorkspacePanel = () => {
        const [error, setError] = React.useState<string | null>(null);

        React.useEffect(() => {
          getCompanyWorkspaceBootstrap("NONEXISTENT", { signal: new AbortController().signal }).catch((err) => {
            if (err instanceof Error && err.message.includes("404")) {
              setError("Company not found");
            }
          });
        }, []);

        if (error) {
          throw new Error(error);
        }

        return React.createElement("div", null, "Company data ready");
      };

      const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});

      render(
        React.createElement(PanelErrorBoundary, {
          kicker: "Company Workspace",
          title: "Could not load workspace",
        }, React.createElement(SimulatedWorkspacePanel))
      );

      await waitFor(() => {
        expect(screen.getByText("Could not load workspace")).toBeDefined();
        expect(screen.getByText("Company not found")).toBeDefined();
      });

      consoleSpy.mockRestore();
    });
  });
});

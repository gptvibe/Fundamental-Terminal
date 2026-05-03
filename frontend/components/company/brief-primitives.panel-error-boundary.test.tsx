// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PanelErrorBoundary, ResearchBriefStateBlock } from "@/components/company/brief-primitives";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ThrowingComponent({ shouldThrow }: { shouldThrow: boolean }): React.ReactElement {
  if (shouldThrow) {
    throw new Error("Panel render failure");
  }
  return React.createElement("div", null, "panel content rendered");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PanelErrorBoundary", () => {
  it("renders children when no error is thrown", () => {
    render(
      React.createElement(PanelErrorBoundary, {
        kicker: "Test",
        title: "Test panel error",
      }, React.createElement(ThrowingComponent, { shouldThrow: false }))
    );
    expect(screen.getByText("panel content rendered")).toBeDefined();
  });

  it("renders a ResearchBriefStateBlock error state when a child throws", () => {
    // React logs expected error output; suppress it for a clean test run
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      React.createElement(PanelErrorBoundary, {
        kicker: "Capital & risk",
        title: "Unable to render dilution tracker",
      }, React.createElement(ThrowingComponent, { shouldThrow: true }))
    );

    // The boundary should display the error fallback title
    expect(screen.getByText("Unable to render dilution tracker")).toBeDefined();
    // The kicker is also shown
    expect(screen.getByText("Capital & risk")).toBeDefined();
    // The error message from the thrown error should be shown
    expect(screen.getByText("Panel render failure")).toBeDefined();

    spy.mockRestore();
  });

  it("does not propagate the error to the parent tree", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(React.createElement("div", null,
        React.createElement(PanelErrorBoundary, {
          kicker: "Snapshot",
          title: "Unable to render chart",
        }, React.createElement(ThrowingComponent, { shouldThrow: true })),
        React.createElement("p", null, "sibling content still visible")
      )
    );

    // Sibling content outside the boundary must still render
    expect(screen.getByText("sibling content still visible")).toBeDefined();
    // Boundary shows the error fallback, not the broken child
    expect(screen.queryByText("panel content rendered")).toBeNull();

    spy.mockRestore();
  });

  it("shows a generic message when the thrown value is not an Error instance", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    function ThrowsString(): React.ReactElement {
      throw "string-error";
    }

    render(
      React.createElement(PanelErrorBoundary, {
        kicker: "Valuation",
        title: "Panel error",
      }, React.createElement(ThrowsString, null))
    );

    expect(screen.getByText("An unexpected error occurred in this panel.")).toBeDefined();

    spy.mockRestore();
  });
});

// Make vi globally available for the `vi.spyOn` calls above (vitest auto-imports it
// in the vitest global environment, but making the import explicit avoids lint warnings).
import { vi } from "vitest";

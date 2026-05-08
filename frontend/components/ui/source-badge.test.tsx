// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceBadge } from "@/components/ui/source-badge";

describe("SourceBadge", () => {
  it("renders source tier and label for a supported official source", () => {
    render(
      React.createElement(SourceBadge, {
        sourceTier: "official_regulator",
        sourceLabel: "SEC Company Facts (XBRL)",
        sourceId: "sec_companyfacts",
      })
    );

    const badge = screen.getByTestId("source-badge-official_regulator");
    expect(badge.textContent).toContain("Official regulator");
    expect(badge.textContent).toContain("SEC Company Facts (XBRL)");
  });

  it("renders source unavailable when provenance is missing", () => {
    render(React.createElement(SourceBadge, {}));
    expect(screen.getByTestId("source-badge-unavailable").textContent).toBe("Source unavailable");
  });
});

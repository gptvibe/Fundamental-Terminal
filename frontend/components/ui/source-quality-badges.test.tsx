// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceQualityBadges } from "@/components/ui/source-quality-badges";

describe("SourceQualityBadges", () => {
  it("renders official SEC and cached badges", () => {
    render(
      React.createElement(SourceQualityBadges, {
        sourceQuality: {
          source_type: "official_sec",
          freshness_time: "2026-05-10T12:00:00Z",
          stale: false,
          warnings: [],
          accession_number: "0000320193-26-000010",
          confidence_level: "high",
        },
      })
    );

    expect(screen.getByText("Official SEC")).toBeTruthy();
    expect(screen.getByText("Cached")).toBeTruthy();
  });

  it("renders fallback, stale, and experimental badges", () => {
    render(
      React.createElement(SourceQualityBadges, {
        sourceQuality: {
          source_type: "fallback_market",
          freshness_time: "2026-05-01T12:00:00Z",
          stale: true,
          warnings: ["fallback_market_source"],
          accession_number: null,
          confidence_level: "experimental",
        },
      })
    );

    expect(screen.getByText("Fallback")).toBeTruthy();
    expect(screen.getByText("Stale")).toBeTruthy();
    expect(screen.getByText("Experimental")).toBeTruthy();
  });
});

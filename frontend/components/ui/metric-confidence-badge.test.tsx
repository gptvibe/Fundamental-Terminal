// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricConfidenceBadge } from "@/components/ui/metric-confidence-badge";

describe("MetricConfidenceBadge", () => {
  it("renders key confidence chips when metadata exists", () => {
    render(
      React.createElement(MetricConfidenceBadge, {
        metadata: {
          freshness: "fresh",
          source: "sec_companyfacts",
          formulaVersion: "v3",
          missingInputsCount: 2,
          proxyUsed: true,
          fallbackUsed: true,
        },
      })
    );

    expect(screen.getAllByText("fresh").length).toBeGreaterThan(0);
    expect(screen.getByText("src sec_companyfacts")).toBeTruthy();
    expect(screen.getByText("formula v3")).toBeTruthy();
    expect(screen.getByText("missing 2")).toBeTruthy();
    expect(screen.getByText("proxy")).toBeTruthy();
    expect(screen.getByText("fallback")).toBeTruthy();
  });

  it("opens and closes the details popover on click", () => {
    render(
      React.createElement(MetricConfidenceBadge, {
        metadata: {
          freshness: "stale",
          source: "debt_to_equity",
          formulaVersion: "2026.04",
          missingInputs: ["shares_outstanding"],
          proxyUsed: false,
          fallbackUsed: false,
          qualityFlags: ["metrics_cache_stale"],
        },
      })
    );

    const trigger = screen.getByRole("button", { name: "Metric confidence details" });
    fireEvent.click(trigger);

    expect(screen.getByText("Quality flags")).toBeTruthy();
    expect(screen.getByText("metrics_cache_stale")).toBeTruthy();

    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  it("returns null when confidence metadata is not available", () => {
    const { container } = render(
      React.createElement(MetricConfidenceBadge, {
        metadata: {
          freshness: "unknown",
        },
      })
    );

    expect(container.textContent).toBe("");
  });
});

// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GovernanceFilingChart } from "@/components/charts/governance-filing-chart";

vi.mock("@/components/charts/chart-framework", () => ({
  ChartSourceBadges: () => React.createElement("div", null, "chart-source-badges"),
}));

vi.mock("@/components/charts/interactive-chart-frame", () => ({
  InteractiveChartFrame: ({ title, subtitle, stageState }: { title: string; subtitle?: string; stageState?: { title?: string; message?: string } }) =>
    React.createElement(
      "section",
      null,
      React.createElement("h2", null, title),
      subtitle ? React.createElement("p", null, subtitle) : null,
      stageState?.title ? React.createElement("div", null, stageState.title) : null,
      stageState?.message ? React.createElement("div", null, stageState.message) : null,
    ),
}));

describe("GovernanceFilingChart", () => {
  it("surfaces the foreign-issuer proxy-coverage caveat in the empty state", () => {
    render(React.createElement(GovernanceFilingChart, { filings: [] }));

    expect(screen.getByText(/Awaiting governance filings\. Many 20-F and 40-F issuers may have limited U\.S\. proxy coverage\./i)).toBeTruthy();
    expect(screen.getByText(/Many 20-F and 40-F issuers may have limited U\.S\. proxy coverage here\./i)).toBeTruthy();
  });
});
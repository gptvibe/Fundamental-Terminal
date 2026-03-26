// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CompanyResearchHeader } from "@/components/layout/company-research-header";

describe("CompanyResearchHeader", () => {
  it("renders company facts, source ribbon items, and summary cards", () => {
    render(
      React.createElement(CompanyResearchHeader, {
        ticker: "AAPL",
        title: "Overview",
        companyName: "Apple Inc.",
        sector: "Technology",
        cacheState: "fresh",
        description: "SEC-first company workspace.",
        facts: [
          { label: "Ticker", value: "AAPL" },
          { label: "CIK", value: "0000320193" }
        ],
        ribbonItems: [
          { label: "Sources", value: "SEC EDGAR/XBRL", tone: "green" },
          { label: "Prices", value: "Yahoo Finance", tone: "cyan" }
        ],
        summaries: [
          { label: "Revenue", value: "$391B", accent: "cyan" },
          { label: "Free Cash Flow", value: "$99B", accent: "green" }
        ]
      })
    );

    expect(screen.getByRole("heading", { name: "Overview" })).toBeTruthy();
    expect(screen.getByText("Apple Inc.")).toBeTruthy();
    expect(screen.getByText("SEC EDGAR/XBRL")).toBeTruthy();
    expect(screen.getByText("Yahoo Finance")).toBeTruthy();
    expect(screen.getByText("Revenue")).toBeTruthy();
    expect(screen.getByText("$99B")).toBeTruthy();
  });
});
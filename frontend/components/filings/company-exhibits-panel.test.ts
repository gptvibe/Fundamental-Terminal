import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CompanyExhibitsPanel } from "@/components/filings/company-exhibits-panel";
import type { CompanyExhibitsResponse, ExhibitPayload } from "@/lib/types";

function buildExhibit(overrides: Partial<ExhibitPayload> = {}): ExhibitPayload {
  return {
    exhibit_number: "EX-99.1",
    description: "Earnings Release",
    document: "ex99d1.htm",
    accession_number: "0000320193-26-000001",
    filing_type: "8-K",
    filing_date: "2026-02-01",
    tag: "earnings_release",
    tag_label: "Earnings Release",
    source_url: "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/ex99d1.htm",
    filing_index_url: "https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/index.html",
    ...overrides,
  };
}

function buildPayload(exhibits: ExhibitPayload[] = [buildExhibit()]): CompanyExhibitsResponse {
  return {
    company: null,
    exhibits,
    total: exhibits.length,
    provenance: ["SEC EDGAR filing directory index (official)"],
    source: "sec_edgar",
    error: null,
  };
}

describe("CompanyExhibitsPanel", () => {
  it("renders exhibits list when data is present", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, { payload: buildPayload() })
    );
    expect(html).toContain("EX-99.1");
    expect(html).toContain("Earnings Release");
  });

  it("shows loading state when no exhibits and loading", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, { payload: null, loading: true })
    );
    expect(html).toContain("Loading exhibit index");
  });

  it("shows empty state when not loading and no exhibits", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, {
        payload: buildPayload([]),
        loading: false,
      })
    );
    expect(html).toContain("No exhibits found");
  });

  it("shows error state when error and no exhibits", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, {
        payload: null,
        loading: false,
        error: "Unable to load exhibits",
      })
    );
    expect(html).toContain("Unable to load exhibits");
  });

  it("renders SEC source links for each exhibit", () => {
    const exhibit = buildExhibit();
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, { payload: buildPayload([exhibit]) })
    );
    expect(html).toContain(exhibit.source_url);
    expect(html).toContain(exhibit.filing_index_url);
  });

  it("renders provenance note from SEC EDGAR", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, { payload: buildPayload() })
    );
    expect(html).toContain("SEC EDGAR");
  });

  it("renders multiple exhibits", () => {
    const exhibits = [
      buildExhibit({ exhibit_number: "EX-99.1", document: "ex99d1.htm" }),
      buildExhibit({ exhibit_number: "EX-21", tag: "subsidiaries", tag_label: "List of Subsidiaries", document: "ex21.htm" }),
      buildExhibit({ exhibit_number: "EX-31.1", tag: "certification_302", tag_label: "SOX 302 Certification", document: "ex31d1.htm" }),
    ];
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, { payload: buildPayload(exhibits) })
    );
    expect(html).toContain("EX-99.1");
    expect(html).toContain("EX-21");
    expect(html).toContain("EX-31.1");
    expect(html).toContain("List of Subsidiaries");
    expect(html).toContain("SOX 302 Certification");
  });

  it("renders exhibit count", () => {
    const exhibits = [buildExhibit(), buildExhibit({ exhibit_number: "EX-21", document: "ex21.htm" })];
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, { payload: buildPayload(exhibits) })
    );
    expect(html).toContain("2 exhibits");
  });

  it("renders filter dropdowns", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, {
        payload: buildPayload(),
        exhibitTypeFilter: "",
        filingTypeFilter: "",
        onFilterChange: vi.fn(),
      })
    );
    expect(html).toContain("Exhibit type");
    expect(html).toContain("Filing form");
  });

  it("renders clear filters button when filter is active", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, {
        payload: buildPayload(),
        exhibitTypeFilter: "EX-99.1",
        filingTypeFilter: "",
        onFilterChange: vi.fn(),
      })
    );
    expect(html).toContain("Clear filters");
  });

  it("does not render clear filters when no filter is active", () => {
    const html = renderToStaticMarkup(
      React.createElement(CompanyExhibitsPanel, {
        payload: buildPayload(),
        exhibitTypeFilter: "",
        filingTypeFilter: "",
        onFilterChange: vi.fn(),
      })
    );
    expect(html).not.toContain("Clear filters");
  });
});

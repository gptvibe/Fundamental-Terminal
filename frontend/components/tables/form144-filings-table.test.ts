import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Form144FilingsTable } from "@/components/tables/form144-filings-table";
import type { Form144FilingPayload } from "@/lib/types";

function makeFiling(partial: Partial<Form144FilingPayload>): Form144FilingPayload {
  return {
    accession_number: partial.accession_number ?? "0001234567-26-000100",
    form: partial.form ?? "144",
    filing_date: partial.filing_date ?? "2026-03-10",
    filer_name: partial.filer_name ?? "Jane Smith",
    relationship_to_issuer: partial.relationship_to_issuer ?? "Director",
    issuer_name: partial.issuer_name ?? "Acme Corp",
    security_title: partial.security_title ?? "Common Stock",
    planned_sale_date: partial.planned_sale_date ?? "2026-03-20",
    shares_to_be_sold: partial.shares_to_be_sold ?? 5000,
    aggregate_market_value: partial.aggregate_market_value ?? 250000,
    shares_owned_after_sale: partial.shares_owned_after_sale ?? 45000,
    broker_name: partial.broker_name ?? "Goldman Sachs",
    source_url: partial.source_url ?? "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000100/form144.txt",
    summary: partial.summary ?? null,
  };
}

describe("Form144FilingsTable", () => {
  it("renders filer name and planned sale date", () => {
    const html = renderToStaticMarkup(
      React.createElement(Form144FilingsTable, {
        ticker: "ACME",
        filings: [makeFiling({})],
      })
    );

    expect(html).toContain("Jane Smith");
    expect(html).toContain("0001234567-26-000100");
  });

  it("renders the SEC source link when source_url is present", () => {
    const html = renderToStaticMarkup(
      React.createElement(Form144FilingsTable, {
        ticker: "ACME",
        filings: [makeFiling({})],
      })
    );

    expect(html).toContain("href=\"https://www.sec.gov/Archives/edgar/data/1234567/000123456726000100/form144.txt\"");
  });

  it("renders accession text without a link when source_url is null", () => {
    const html = renderToStaticMarkup(
      React.createElement(Form144FilingsTable, {
        ticker: "ACME",
        filings: [makeFiling({ source_url: null, accession_number: "0001234567-26-000999" })],
      })
    );

    expect(html).toContain("0001234567-26-000999");
    expect(html).not.toContain("href=\"0001234567-26-000999\"");
  });

  it("shows empty state when filings array is empty", () => {
    const html = renderToStaticMarkup(
      React.createElement(Form144FilingsTable, {
        ticker: "ACME",
        filings: [],
      })
    );

    expect(html).toContain("No Form 144 filings yet");
  });

  it("shows loading state when loading and no filings", () => {
    const html = renderToStaticMarkup(
      React.createElement(Form144FilingsTable, {
        ticker: "ACME",
        filings: [],
        loading: true,
      })
    );

    expect(html).toContain("Loading planned sales");
  });
});

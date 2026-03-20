import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { HedgeFundActivityTable } from "@/components/tables/hedge-fund-activity-table";
import type { InstitutionalHoldingPayload } from "@/lib/types";

function makeHolding(partial: Partial<InstitutionalHoldingPayload>): InstitutionalHoldingPayload {
  return {
    fund_name: partial.fund_name ?? "Sample Capital",
    fund_cik: partial.fund_cik ?? "0001234567",
    fund_manager: partial.fund_manager ?? "Alex Smith",
    manager_query: partial.manager_query ?? "Sample Capital",
    universe_source: partial.universe_source ?? "curated",
    fund_strategy: partial.fund_strategy ?? "Long-only",
    accession_number: partial.accession_number ?? "0001234567-26-000111",
    filing_form: partial.filing_form ?? "13F-HR",
    base_form: partial.base_form ?? "13F-HR",
    is_amendment: partial.is_amendment ?? false,
    reporting_date: partial.reporting_date ?? "2025-12-31",
    filing_date: partial.filing_date ?? "2026-02-14",
    shares_held: partial.shares_held ?? 120000,
    market_value: partial.market_value ?? 2400000,
    change_in_shares: partial.change_in_shares ?? 15000,
    percent_change: partial.percent_change ?? 0.1428,
    portfolio_weight: partial.portfolio_weight ?? 0.03,
    put_call: partial.put_call ?? null,
    investment_discretion: partial.investment_discretion ?? "SOLE",
    voting_authority_sole: partial.voting_authority_sole ?? 120000,
    voting_authority_shared: partial.voting_authority_shared ?? 0,
    voting_authority_none: partial.voting_authority_none ?? 0,
    source: partial.source ?? "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000111/primary_doc.xml",
  };
}

describe("HedgeFundActivityTable", () => {
  it("renders filing form, filing date, accession number, and SEC source link", () => {
    const html = renderToStaticMarkup(
      React.createElement(HedgeFundActivityTable, {
        ticker: "ACME",
        holdings: [makeHolding({})],
      })
    );

    expect(html).toContain(">13F-HR<");
    expect(html).toContain("0001234567-26-000111");
    expect(html).toContain("href=\"https://www.sec.gov/Archives/edgar/data/1234567/000123456726000111/primary_doc.xml\"");
  });

  it("renders amendment indicator when filing is an amendment", () => {
    const html = renderToStaticMarkup(
      React.createElement(HedgeFundActivityTable, {
        ticker: "ACME",
        holdings: [makeHolding({ is_amendment: true })],
      })
    );

    expect(html).toContain(">Amendment<");
  });
});

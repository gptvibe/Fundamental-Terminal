import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { InsiderTransactionsTable } from "@/components/tables/insider-transactions-table";
import type { InsiderTradePayload } from "@/lib/types";

function makeTrade(partial: Partial<InsiderTradePayload>): InsiderTradePayload {
  return {
    name: partial.name ?? "Jane Doe",
    role: partial.role ?? "CEO",
    date: partial.date ?? "2026-03-01",
    filing_date: partial.filing_date ?? "2026-03-02",
    filing_type: partial.filing_type ?? "4",
    accession_number: partial.accession_number ?? "0001234567-26-000001",
    source: partial.source ?? "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/xslF345X05/wk-form4_1.xml",
    action: partial.action ?? "buy",
    transaction_code: partial.transaction_code ?? "P",
    shares: partial.shares ?? 1000,
    price: partial.price ?? 10,
    value: partial.value ?? 10000,
    ownership_after: partial.ownership_after ?? 5000,
    security_title: partial.security_title ?? "Common Stock",
    is_derivative: partial.is_derivative ?? false,
    ownership_nature: partial.ownership_nature ?? "D",
    exercise_price: partial.exercise_price ?? null,
    expiration_date: partial.expiration_date ?? null,
    footnote_tags: partial.footnote_tags ?? null,
    is_10b5_1: partial.is_10b5_1 ?? false,
  };
}

describe("InsiderTransactionsTable", () => {
  it("renders filing metadata link when SEC source is present", () => {
    const html = renderToStaticMarkup(
      React.createElement(InsiderTransactionsTable, {
        ticker: "ACME",
        trades: [makeTrade({})],
      })
    );

    expect(html).toContain("0001234567-26-000001");
    expect(html).toContain("href=\"https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/xslF345X05/wk-form4_1.xml\"");
    expect(html).toContain(">4<");
  });

  it("renders accession text without a link when source is missing", () => {
    const html = renderToStaticMarkup(
      React.createElement(InsiderTransactionsTable, {
        ticker: "ACME",
        trades: [
          makeTrade({
            accession_number: "0001234567-26-000777",
            source: null,
          }),
        ],
      })
    );

    expect(html).toContain("0001234567-26-000777");
    expect(html).not.toContain("href=\"0001234567-26-000777\"");
  });
});

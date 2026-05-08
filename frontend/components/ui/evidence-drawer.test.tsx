// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { EvidenceDrawer } from "@/components/ui/evidence-drawer";

describe("EvidenceDrawer", () => {
  it("renders official source evidence", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(EvidenceDrawer, {
        title: "Business quality evidence",
        provenance: [
          {
            source_id: "sec_companyfacts",
            source_tier: "official_regulator",
            display_label: "SEC Company Facts (XBRL)",
            url: "https://data.sec.gov/api/xbrl/companyfacts/",
            default_freshness_ttl_seconds: 21600,
            disclosure_note: "Official SEC XBRL source",
            role: "primary",
            as_of: "2026-03-31",
            last_refreshed_at: "2026-04-02T00:00:00Z",
          },
        ],
        sourceMix: {
          source_ids: ["sec_companyfacts"],
          source_tiers: ["official_regulator"],
          primary_source_ids: ["sec_companyfacts"],
          fallback_source_ids: [],
          official_only: true,
        },
      })
    );

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    expect(screen.getByText("SEC Company Facts (XBRL)")).toBeTruthy();
    expect(screen.getByText("official_regulator")).toBeTruthy();
    expect(screen.getByText("sec_companyfacts")).toBeTruthy();
  });

  it("renders derived metric evidence with formula note", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(EvidenceDrawer, {
        title: "Valuation evidence",
        provenance: [
          {
            source_id: "ft_model_engine",
            source_tier: "derived_from_official",
            display_label: "Fundamental Terminal Model Engine",
            url: "https://github.com/gptvibe/Fundamental-Terminal",
            default_freshness_ttl_seconds: 21600,
            disclosure_note: "Derived analytics",
            role: "derived",
            as_of: "2026-03-31",
            last_refreshed_at: "2026-04-02T00:00:00Z",
          },
        ],
        sourceMix: {
          source_ids: ["ft_model_engine"],
          source_tiers: ["derived_from_official"],
          primary_source_ids: ["ft_model_engine"],
          fallback_source_ids: [],
          official_only: true,
        },
        metrics: [
          {
            label: "Discounted cash flow",
            source_id: "ft_model_engine",
            formula_note: "Calculation version: calc-v3",
          },
        ],
      })
    );

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    expect(screen.getByText("Discounted cash flow")).toBeTruthy();
    expect(screen.getByText("Calculation version: calc-v3")).toBeTruthy();
    expect(screen.getAllByText("derived_from_official").length).toBeGreaterThan(0);
  });

  it("makes commercial fallback obvious", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(EvidenceDrawer, {
        title: "Price evidence",
        provenance: [
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            url: "https://finance.yahoo.com/",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Commercial fallback",
            role: "fallback",
            as_of: "2026-03-31",
            last_refreshed_at: "2026-04-02T00:00:00Z",
          },
        ],
        sourceMix: {
          source_ids: ["yahoo_finance"],
          source_tiers: ["commercial_fallback"],
          primary_source_ids: [],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        },
      })
    );

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    expect(screen.getByText("Commercial fallback in use: Yahoo Finance")).toBeTruthy();
  });

  it("shows an unavailable message when evidence is missing", async () => {
    const user = userEvent.setup();
    render(React.createElement(EvidenceDrawer, { title: "Empty evidence" }));

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    expect(screen.getByText("Evidence unavailable for this field.")).toBeTruthy();
  });

  it("highlights strict official mode violations", async () => {
    const user = userEvent.setup();
    render(
      React.createElement(EvidenceDrawer, {
        title: "Strict official mode evidence",
        strictOfficialMode: true,
        provenance: [
          {
            source_id: "yahoo_finance",
            source_tier: "commercial_fallback",
            display_label: "Yahoo Finance",
            url: "https://finance.yahoo.com/",
            default_freshness_ttl_seconds: 3600,
            disclosure_note: "Commercial fallback",
            role: "fallback",
            as_of: "2026-03-31",
            last_refreshed_at: "2026-04-02T00:00:00Z",
          },
        ],
        sourceMix: {
          source_ids: ["yahoo_finance"],
          source_tiers: ["commercial_fallback"],
          primary_source_ids: [],
          fallback_source_ids: ["yahoo_finance"],
          official_only: false,
        },
      })
    );

    await user.click(screen.getByRole("button", { name: "View evidence" }));

    expect(screen.getByText("Strict official mode is enabled, but fallback evidence is still present: Yahoo Finance.")).toBeTruthy();
  });
});

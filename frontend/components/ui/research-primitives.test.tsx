// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  DataFreshnessBadge,
  EmptyState,
  ErrorState,
  EvidenceDrawer,
  KpiCard,
  KpiStrip,
  LoadingSkeleton,
  PageHeader,
  PageShell,
  PrimaryChartCard,
  PrimaryTableCard,
  SectionAccordion,
  SourceBadge,
  Toolbar,
  ToolbarGroup,
} from "@/components/ui/research-primitives";

describe("research primitives", () => {
  it("renders page scaffolding and core cards", () => {
    render(
      <PageShell>
        <PageHeader title="Research dashboard" subtitle="Reusable shell" actions={<button type="button">Refresh</button>} />
        <Toolbar>
          <ToolbarGroup title="Range">
            <button type="button">1Y</button>
          </ToolbarGroup>
        </Toolbar>
        <KpiStrip aria-label="Highlights">
          <KpiCard label="Revenue" value="$12.4B" delta="+6.2%" tone="positive" />
          <KpiCard label="FCF" value="$2.1B" detail="TTM" />
        </KpiStrip>
        <PrimaryChartCard title="Revenue trend" subtitle="GAAP filings">
          <div>Chart host</div>
        </PrimaryChartCard>
        <PrimaryTableCard title="Source table" subtitle="Latest pulls">
          <div>Table host</div>
        </PrimaryTableCard>
      </PageShell>
    );

    expect(screen.getByRole("heading", { level: 1, name: "Research dashboard" })).toBeTruthy();
    expect(screen.getByRole("toolbar", { name: "Page controls" })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Highlights" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Revenue trend" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Source table" })).toBeTruthy();
  });

  it("renders state and badge primitives accessibly", () => {
    render(
      <div>
        <DataFreshnessBadge freshness="fresh" asOf="2026-05-05" />
        <SourceBadge source="SEC CompanyFacts" kind="sec" />
        <LoadingSkeleton lines={2} label="Loading watchlist" />
        <EmptyState title="No filings yet" message="Queue a refresh to populate this panel." />
        <ErrorState title="Request failed" message="Try again in a few seconds." />
      </div>
    );

    expect(screen.getByLabelText("Data freshness Fresh as of 2026-05-05")).toBeTruthy();
    expect(screen.getByText("SEC CompanyFacts")).toBeTruthy();
    expect(screen.getByRole("status", { name: "Loading watchlist" })).toBeTruthy();
    expect(screen.getByText("No filings yet")).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("supports accordion and evidence drawer interactions", () => {
    render(
      <div>
        <SectionAccordion title="Methodology" subtitle="Assumptions" defaultOpen={false}>
          <p>Accordion body</p>
        </SectionAccordion>
        <EvidenceDrawer title="Source evidence" summaryLabel="Open evidence" defaultOpen={false}>
          <p>Drawer body</p>
        </EvidenceDrawer>
      </div>
    );

    const accordionSummary = screen.getByText("Methodology").closest("summary");
    expect(accordionSummary).toBeTruthy();
    if (accordionSummary) {
      fireEvent.click(accordionSummary);
    }
    expect(screen.getByText("Accordion body")).toBeTruthy();

    const drawerSummary = screen.getByText("Open evidence").closest("summary");
    expect(drawerSummary).toBeTruthy();
    if (drawerSummary) {
      fireEvent.click(drawerSummary);
    }
    expect(screen.getByText("Drawer body")).toBeTruthy();
  });
});

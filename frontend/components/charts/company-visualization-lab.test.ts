import { describe, expect, it } from "vitest";

import { applyDateRange, buildAnnotations, buildFilingHeatmapRows, computeValueMode } from "@/components/charts/company-visualization-lab";

describe("company visualization helpers", () => {
  it("computes margin, growth, and per-share modes", () => {
    expect(computeValueMode(120, 100, 400, 20, "absolute")).toBe(120);
    expect(computeValueMode(120, 100, 400, 20, "margin")).toBe(0.3);
    expect(computeValueMode(120, 100, 400, 20, "growth")).toBe(0.2);
    expect(computeValueMode(120, 100, 400, 20, "perShare")).toBe(6);
  });

  it("builds cross-source annotations in date order", () => {
    const rows = buildAnnotations({
      earnings: [{ filing_date: "2025-05-01", report_date: null } as never],
      events: [{ filing_date: "2025-04-20", report_date: null, category: "Financing" } as never],
      capitalFilings: [{ filing_date: "2025-04-25", report_date: null, event_type: "Registration" } as never],
      insiderTrades: [{ filing_date: "2025-04-10", date: null, action: "SELL" } as never],
      ownershipFilings: [{ filing_date: "2025-03-30", report_date: null, base_form: "SC 13D" } as never],
    });

    expect(rows.map((row) => row.kind)).toEqual(["ownership", "insider", "event", "capital", "earnings"]);
  });

  it("builds cadence heatmap rows with average lag", () => {
    const rows = buildFilingHeatmapRows([
      { filing_date: "2025-04-15", report_date: "2025-04-10" } as never,
      { filing_date: "2025-04-20", report_date: "2025-04-15" } as never,
      { filing_date: "2025-08-01", report_date: null } as never,
    ]);

    expect(rows[0].quarter).toBe("2025-Q2");
    expect(rows[0].filingCount).toBe(2);
    expect(rows[0].avgLagDays).toBeCloseTo(5, 1);
    expect(rows[1].quarter).toBe("2025-Q3");
  });

  it("filters rows by date range", () => {
    const rows = applyDateRange(
      [
        { periodEnd: "2018-12-31", value: 1 },
        { periodEnd: "2020-12-31", value: 2 },
        { periodEnd: "2024-12-31", value: 3 },
      ],
      "3y"
    );

    expect(rows).toHaveLength(1);
    expect(rows[0].periodEnd).toBe("2024-12-31");
  });
});

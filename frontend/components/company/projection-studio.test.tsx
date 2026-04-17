// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProjectionStudio } from "./projection-studio";

const { exportRowsToCsv } = vi.hoisted(() => ({
  exportRowsToCsv: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/company/acme/charts",
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("recharts", () => {
  const MockResponsiveContainer = ({ children }: { children: React.ReactNode }) => <div data-testid="recharts-responsive">{children}</div>;
  const MockChart = ({ children }: { children?: React.ReactNode }) => <div data-testid="recharts-chart">{children}</div>;
  const MockBar = ({ children }: { children?: React.ReactNode }) => <div data-testid="recharts-bar">{children}</div>;
  const MockCell = () => <div data-testid="recharts-cell" />;
  return {
    ResponsiveContainer: MockResponsiveContainer,
    BarChart: MockChart,
    Bar: MockBar,
    CartesianGrid: () => null,
    Cell: MockCell,
    ReferenceLine: () => null,
    Tooltip: () => null,
    XAxis: () => null,
    YAxis: () => null,
  };
});

vi.mock("@/lib/export", async () => {
  const actual = await vi.importActual<typeof import("@/lib/export")>("@/lib/export");
  return {
    ...actual,
    exportRowsToCsv,
  };
});

function buildPayload() {
  const revenueTrace = {
    line_item: "revenue",
    year: 2026,
    formula_label: "Revenue Growth",
    formula_template: "Prior Revenue × (1 + Growth)",
    formula_computation: "1100 × 1.10 = 1210",
    result_value: 1210,
    inputs: [
      {
        key: "prior_revenue",
        label: "Prior Revenue",
        value: 1100,
        formatted_value: "$1.10K",
        source_detail: "FY2025 SEC filing",
        source_kind: "sec-derived",
      },
    ],
    confidence: "high",
  };

  const operatingIncomeTrace = {
    line_item: "operating_income",
    year: 2026,
    formula_label: "Operating Income Build",
    formula_template: "Revenue - Variable - Semi-variable - Fixed",
    formula_computation: "1210 - 400 - 120 - 250 = 440",
    result_value: 440,
    inputs: [
      { key: "revenue", label: "Revenue", value: 1210, formatted_value: "$1.21K", source_detail: "Revenue schedule", source_kind: "derived" },
      { key: "variable_cost", label: "Variable Cost", value: 400, formatted_value: "$0.40K", source_detail: "Cost schedule", source_kind: "derived" },
      { key: "semi_variable_cost", label: "Semi-Variable Cost", value: 120, formatted_value: "$0.12K", source_detail: "Cost schedule", source_kind: "derived" },
      { key: "fixed_cost", label: "Fixed Cost", value: 250, formatted_value: "$0.25K", source_detail: "Cost schedule", source_kind: "derived" },
    ],
    confidence: "medium",
  };

  const freeCashFlowTrace = {
    line_item: "free_cash_flow",
    year: 2026,
    formula_label: "Free Cash Flow",
    formula_template: "Operating Cash Flow - Capex",
    formula_computation: "300 - 100 = 200",
    result_value: 200,
    inputs: [
      { key: "operating_cash_flow", label: "Operating Cash Flow", value: 300, formatted_value: "$0.30K", source_detail: "Cash flow schedule", source_kind: "derived" },
      { key: "capex", label: "Capex", value: 100, formatted_value: "$0.10K", source_detail: "Cash flow schedule", source_kind: "derived" },
    ],
    confidence: "high",
  };

  const studio = {
    methodology: null,
    schedule_sections: [
      {
        key: "income_statement",
        title: "Income Statement",
        rows: [
          {
            key: "revenue",
            label: "Revenue",
            unit: "usd",
            reported_values: { 2024: 1000, 2025: 1100 },
            projected_values: { 2026: 1210 },
            formula_traces: { 2026: revenueTrace },
            scenario_values: { base: 1210, bull: 1270, bear: 1150 },
            detail: "Driver-based top-line forecast",
          },
          {
            key: "operating_income",
            label: "Operating Income",
            unit: "usd",
            reported_values: { 2024: 350, 2025: 390 },
            projected_values: { 2026: 440 },
            formula_traces: { 2026: operatingIncomeTrace },
            scenario_values: { base: 440, bull: 500, bear: 360 },
            detail: "Contribution margin bridge",
          },
        ],
      },
      {
        key: "balance_sheet",
        title: "Balance Sheet",
        rows: [
          { key: "accounts_receivable", label: "Accounts Receivable", unit: "usd", reported_values: { 2025: 200 }, projected_values: { 2026: 210 }, formula_traces: {}, scenario_values: {}, detail: null },
          { key: "inventory", label: "Inventory", unit: "usd", reported_values: { 2025: 300 }, projected_values: { 2026: 315 }, formula_traces: {}, scenario_values: {}, detail: null },
          { key: "accounts_payable", label: "Accounts Payable", unit: "usd", reported_values: { 2025: 150 }, projected_values: { 2026: 160 }, formula_traces: {}, scenario_values: {}, detail: null },
          { key: "deferred_revenue", label: "Deferred Revenue", unit: "usd", reported_values: { 2025: 50 }, projected_values: { 2026: 55 }, formula_traces: {}, scenario_values: {}, detail: null },
          { key: "accrued_operating_liabilities", label: "Accrued Operating Liabilities", unit: "usd", reported_values: { 2025: 25 }, projected_values: { 2026: 30 }, formula_traces: {}, scenario_values: {}, detail: null },
        ],
      },
      {
        key: "cash_flow_statement",
        title: "Cash Flow Statement",
        rows: [
          { key: "operating_cash_flow", label: "Operating Cash Flow", unit: "usd", reported_values: { 2025: 260 }, projected_values: { 2026: 300 }, formula_traces: {}, scenario_values: {}, detail: null },
          { key: "capex", label: "Capex", unit: "usd", reported_values: { 2025: 90 }, projected_values: { 2026: 100 }, formula_traces: {}, scenario_values: {}, detail: null },
          { key: "free_cash_flow", label: "Free Cash Flow", unit: "usd", reported_values: { 2025: 170 }, projected_values: { 2026: 200 }, formula_traces: { 2026: freeCashFlowTrace }, scenario_values: { base: 200, bull: 245, bear: 155 }, detail: null },
        ],
      },
    ],
    drivers_used: [
      { key: "revenue_method", title: "Revenue Growth", value: "10%", detail: "Trend plus backlog", source_periods: ["FY2024", "FY2025"], default_markers: ["Recent trend"], fallback_markers: [] },
      { key: "operating_working_capital", title: "Receivables Days", value: "31d", detail: "Stable collection cadence", source_periods: ["FY2025"], default_markers: [], fallback_markers: ["Peer median"] },
      { key: "dilution", title: "Diluted Shares", value: "102M", detail: "Includes SBC offset", source_periods: ["FY2025"], default_markers: ["Treasury method"], fallback_markers: [] },
    ],
    scenarios_comparison: [
      { key: "revenue", label: "Revenue", unit: "usd", reported_values: {}, projected_values: {}, formula_traces: {}, scenario_values: { base: 1210, bull: 1270, bear: 1150 }, detail: null },
      { key: "free_cash_flow", label: "Free Cash Flow", unit: "usd", reported_values: {}, projected_values: {}, formula_traces: {}, scenario_values: { base: 200, bull: 245, bear: 155 }, detail: null },
    ],
    sensitivity_matrix: Array.from({ length: 5 }, (_, rowIndex) =>
      Array.from({ length: 5 }, (_, columnIndex) => ({
        row_index: rowIndex,
        column_index: columnIndex,
        revenue_growth: 0.06 + columnIndex * 0.02,
        operating_margin: 0.14 + rowIndex * 0.01,
        eps: 2.1 + rowIndex * 0.15 + columnIndex * 0.1,
        is_base: rowIndex === 2 && columnIndex === 2,
      }))
    ).flat(),
  };

  return {
    payload: {
      company: {
        ticker: "ACME",
        cik: "0000000001",
        name: "Acme Corporation",
        sector: "Technology",
        market_sector: "Technology",
        market_industry: "Application Software",
        oil_exposure_type: "non_oil",
        oil_support_status: "supported",
        oil_support_reasons: [],
        strict_official_mode: true,
        last_checked: null,
        last_checked_financials: null,
        last_checked_prices: null,
        last_checked_insiders: null,
        last_checked_institutional: null,
        last_checked_filings: null,
        earnings_last_checked: null,
        cache_state: "fresh",
      },
      forecast_methodology: {
        version: "company_charts_dashboard_v9",
        label: "Driver-based integrated forecast",
        summary: "Methodology summary",
        disclaimer: "Methodology disclaimer",
        forecast_horizon_years: 3,
        confidence_label: "High confidence",
      },
      projection_studio: studio,
    },
    studio,
  };
}

describe("ProjectionStudio", () => {
  it("renders grouped drivers, sensitivity matrix, bridges, scenarios, and schedules", () => {
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    expect(screen.getByText("Key Drivers")).toBeTruthy();
    expect(screen.getByText("Revenue Drivers")).toBeTruthy();
    expect(screen.getByText("Working Capital")).toBeTruthy();
    expect(screen.getByText("Shares & Dilution")).toBeTruthy();
    expect(screen.getByText("Sensitivity Matrix")).toBeTruthy();
    expect(screen.getByText("Scenarios Comparison")).toBeTruthy();
    expect(screen.getByText("Revenue Bridge")).toBeTruthy();
    expect(screen.getByText("Operating Income Bridge")).toBeTruthy();
    expect(screen.getByText("Free Cash Flow Bridge")).toBeTruthy();
    expect(screen.getByText("Income Statement")).toBeTruthy();
    expect(screen.getByText("Balance Check")).toBeTruthy();
    expect(screen.getByText("Cash Reconciliation")).toBeTruthy();
  });

  it("highlights the base sensitivity cell", () => {
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    expect(screen.getByTestId("studio-sensitivity-cell-2-2").className).toContain("is-base");
  });

  it("opens a formula popover from projected cells and bridge inspect actions", () => {
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    fireEvent.click(screen.getByRole("button", { name: "Revenue 2026 formula trace" }));

    let dialog = screen.getByRole("dialog", { name: "Formula trace details" });
    expect(within(dialog).getByText("Revenue Growth")).toBeTruthy();
    expect(within(dialog).getByText("Prior Revenue × (1 + Growth)")).toBeTruthy();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Formula trace details" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Inspect operating income bridge formula" }));
    dialog = screen.getByRole("dialog", { name: "Formula trace details" });
    expect(within(dialog).getByText("Operating Income Build")).toBeTruthy();
  });

  it("exports studio csv rows with schedule and trace metadata", () => {
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    fireEvent.click(screen.getByRole("button", { name: "Export Studio CSV" }));

    expect(exportRowsToCsv).toHaveBeenCalledTimes(1);
    const [fileName, rows] = exportRowsToCsv.mock.calls[0] as [string, Array<Record<string, unknown>>];
    expect(fileName).toBe("ACME-projection-studio.csv");
    expect(rows.some((row) => row.record_type === "schedule" && row.formula_label === "Revenue Growth")).toBe(true);
    expect(rows.some((row) => row.record_type === "driver" && row.driver_group === "Revenue Drivers")).toBe(true);
    expect(rows.some((row) => row.record_type === "sensitivity" && row.is_base === "true")).toBe(true);
  });

  it("links the valuation CTA to the models workspace", () => {
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    expect(screen.getByRole("link", { name: "Open in Models for Valuation" }).getAttribute("href")).toBe("/company/ACME/models");
  });
});

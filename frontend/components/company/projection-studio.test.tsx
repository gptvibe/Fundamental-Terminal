// @vitest-environment jsdom

import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ProjectionStudio } from "./projection-studio";
import { getCompanyChartsWhatIf } from "@/lib/api";

const { exportRowsToCsv } = vi.hoisted(() => ({
  exportRowsToCsv: vi.fn(),
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

vi.mock("@/lib/api", () => ({
  getCompanyChartsWhatIf: vi.fn(),
}));

function buildFormulaTrace({
  lineItem,
  label,
  formula,
  computation,
  resultValue,
  inputs,
  scenarioState = "baseline",
}: {
  lineItem: string;
  label: string;
  formula: string;
  computation: string;
  resultValue: number;
  inputs: Array<Record<string, unknown>>;
  scenarioState?: string;
}) {
  return {
    line_item: lineItem,
    year: 2026,
    formula_label: label,
    formula_template: formula,
    formula_computation: computation,
    result_value: resultValue,
    inputs,
    confidence: "high",
    scenario_state: scenarioState,
  };
}

function buildPayload(options?: {
  includeWhatIf?: boolean;
  revenue2026?: number;
  revenueScenarioState?: string;
  receivables2026?: number;
  dsoValue?: number;
  priceGrowthValue?: number;
  impactSummary?: boolean;
  appliedOverrides?: Array<Record<string, unknown>>;
}) {
  const revenue2026 = options?.revenue2026 ?? 1210;
  const receivables2026 = options?.receivables2026 ?? 210;
  const dsoValue = options?.dsoValue ?? 31;
  const priceGrowthValue = options?.priceGrowthValue ?? 0.04;
  const scenarioState = options?.revenueScenarioState ?? "baseline";

  const revenueTrace = buildFormulaTrace({
    lineItem: "revenue",
    label: "Revenue Growth",
    formula: "Prior Revenue × (1 + Growth)",
    computation: `1100 × 1.10 = ${revenue2026}`,
    resultValue: revenue2026,
    scenarioState,
    inputs: [
      {
        key: "prior_revenue",
        label: "Prior Revenue",
        value: 1100,
        formatted_value: "$1.10K",
        source_detail: "FY2025 SEC filing",
        source_kind: "sec-derived",
        is_override: false,
        original_value: null,
        original_source: null,
      },
      {
        key: "price_growth",
        label: "Price Growth",
        value: priceGrowthValue,
        formatted_value: `${Math.round(priceGrowthValue * 100)}.0%`,
        source_detail: scenarioState === "user_override" ? "User scenario override. Baseline source: SEC-derived pricing proxy." : "SEC-derived pricing proxy",
        source_kind: scenarioState === "user_override" ? "override" : "sec",
        is_override: scenarioState === "user_override",
        original_value: scenarioState === "user_override" ? 0.04 : null,
        original_source: scenarioState === "user_override" ? "SEC-derived pricing proxy" : null,
      },
    ],
  });

  const receivablesTrace = buildFormulaTrace({
    lineItem: "accounts_receivable",
    label: "Receivables Forecast",
    formula: "Revenue × DSO / 365",
    computation: `${revenue2026} × ${dsoValue} / 365 = ${receivables2026}`,
    resultValue: receivables2026,
    scenarioState,
    inputs: [
      {
        key: "revenue",
        label: "Revenue",
        value: revenue2026,
        formatted_value: `$${(revenue2026 / 1000).toFixed(2)}K`,
        source_detail: "Revenue schedule",
        source_kind: "derived",
        is_override: false,
        original_value: null,
        original_source: null,
      },
      {
        key: "accounts_receivable_days",
        label: "DSO",
        value: dsoValue,
        formatted_value: `${dsoValue}d`,
        source_detail: scenarioState === "user_override" ? "User scenario override. Baseline source: SEC-derived DSO." : "SEC-derived DSO",
        source_kind: scenarioState === "user_override" ? "override" : "sec",
        is_override: scenarioState === "user_override",
        original_value: scenarioState === "user_override" ? 31 : null,
        original_source: scenarioState === "user_override" ? "SEC-derived DSO" : null,
      },
    ],
  });

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
            projected_values: { 2026: revenue2026 },
            formula_traces: { 2026: revenueTrace },
            scenario_values: { base: revenue2026, bull: revenue2026 + 60, bear: revenue2026 - 60 },
            detail: "Driver-based top-line forecast",
          },
        ],
      },
      {
        key: "balance_sheet",
        title: "Balance Sheet",
        rows: [
          {
            key: "accounts_receivable",
            label: "Accounts Receivable",
            unit: "usd",
            reported_values: { 2025: 200 },
            projected_values: { 2026: receivables2026 },
            formula_traces: { 2026: receivablesTrace },
            scenario_values: {},
            detail: null,
          },
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
          { key: "free_cash_flow", label: "Free Cash Flow", unit: "usd", reported_values: { 2025: 170 }, projected_values: { 2026: 200 }, formula_traces: {}, scenario_values: { base: 200, bull: 245, bear: 155 }, detail: null },
        ],
      },
    ],
    drivers_used: [
      { key: "revenue_method", title: "Revenue Growth", value: "10%", detail: "Trend plus backlog", source_periods: ["FY2024", "FY2025"], default_markers: ["Recent trend"], fallback_markers: [] },
      { key: "operating_working_capital", title: "Receivables Days", value: "31d", detail: "Stable collection cadence", source_periods: ["FY2025"], default_markers: [], fallback_markers: ["Peer median"] },
    ],
    scenarios_comparison: [
      { key: "revenue", label: "Revenue", unit: "usd", reported_values: {}, projected_values: {}, formula_traces: {}, scenario_values: { base: revenue2026, bull: revenue2026 + 60, bear: revenue2026 - 60 }, detail: null },
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

  const payload = {
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
    title: "Growth Outlook",
    build_state: "ready",
    build_status: "Charts dashboard ready.",
    summary: {
      headline: "Growth Outlook",
      primary_score: { key: "growth", label: "Growth", score: 84, tone: "positive", detail: null },
      secondary_badges: [],
      thesis: "Studio baseline view.",
      unavailable_notes: [],
      freshness_badges: [],
      source_badges: [],
    },
    factors: { primary: null, supporting: [] },
    legend: { title: "Actual vs Forecast", items: [] },
    cards: {
      revenue: { key: "revenue", title: "Revenue", subtitle: null, metric_label: "Revenue", unit_label: "USD", empty_state: null, highlights: [], series: [] },
      revenue_growth: { key: "revenue_growth", title: "Revenue Growth", subtitle: null, metric_label: "Revenue Growth", unit_label: "%", empty_state: null, highlights: [], series: [] },
      profit_metric: { key: "profit_metric", title: "Profit Metric", subtitle: null, metric_label: "Profit", unit_label: "USD", empty_state: null, highlights: [], series: [] },
      cash_flow_metric: { key: "cash_flow_metric", title: "Cash Flow Metric", subtitle: null, metric_label: "Cash Flow", unit_label: "USD", empty_state: null, highlights: [], series: [] },
      eps: { key: "eps", title: "EPS", subtitle: null, metric_label: "EPS", unit_label: "USD/share", empty_state: null, highlights: [], series: [] },
      growth_summary: { key: "growth_summary", title: "Growth Summary", subtitle: null, empty_state: null, comparisons: [] },
      forecast_assumptions: null,
      forecast_calculations: null,
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
    what_if: options?.includeWhatIf
      ? {
          impact_summary: options?.impactSummary
            ? {
                forecast_year: 2026,
                metrics: [
                  {
                    key: "revenue",
                    label: "Revenue",
                    unit: "usd",
                    baseline_value: 1210,
                    scenario_value: revenue2026,
                    delta_value: revenue2026 - 1210,
                    delta_percent: (revenue2026 - 1210) / 1210,
                  },
                ],
              }
            : null,
          overrides_applied: options?.appliedOverrides ?? [],
          overrides_clipped: [],
          driver_control_metadata: [
            {
              key: "price_growth",
              label: "Price Growth",
              unit: "percent",
              baseline_value: 0.04,
              current_value: priceGrowthValue,
              min_value: -0.05,
              max_value: 0.15,
              step: 0.005,
              source_detail: "SEC-derived pricing proxy",
              source_kind: "sec",
            },
            {
              key: "dso",
              label: "Days Sales Outstanding",
              unit: "days",
              baseline_value: 31,
              current_value: dsoValue,
              min_value: 5,
              max_value: 150,
              step: 1,
              source_detail: "SEC-derived DSO",
              source_kind: "sec",
            },
          ],
        }
      : null,
    payload_version: "company_charts_dashboard_v9",
    refresh: { triggered: false, reason: "fresh", ticker: "ACME", job_id: null },
    diagnostics: { coverage_ratio: 1, fallback_ratio: 0, stale_flags: [], parser_confidence: 1, missing_field_flags: [], reconciliation_penalty: null, reconciliation_disagreement_count: 0 },
    provenance: [],
    as_of: null,
    last_refreshed_at: null,
    source_mix: { source_ids: [], source_tiers: [], primary_source_ids: [], fallback_source_ids: [], official_only: true },
    confidence_flags: [],
  };

  return {
    payload,
    studio,
  };
}

describe("ProjectionStudio", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("opens and collapses the what-if sidebar and uses backend-provided limits", async () => {
    vi.mocked(getCompanyChartsWhatIf).mockResolvedValueOnce(buildPayload({ includeWhatIf: true }).payload as never);
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    await waitFor(() => expect(getCompanyChartsWhatIf).toHaveBeenCalledWith("ACME", { overrides: {} }, expect.anything()));
    const dsoSlider = await waitFor(() => screen.getByTestId("studio-what-if-slider-dso"));
    expect(dsoSlider.getAttribute("min")).toBe("5");
    expect(dsoSlider.getAttribute("max")).toBe("150");
    expect(dsoSlider.getAttribute("step")).toBe("1");

    const toggle = screen.getByRole("button", { name: "Hide What-If Sidebar" });
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Show What-If Sidebar" }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: "Show What-If Sidebar" }));
    expect(screen.getByRole("button", { name: "Hide What-If Sidebar" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("debounces recomputation, updates the impact strip, and renders delta indicators", async () => {
    vi.mocked(getCompanyChartsWhatIf)
      .mockResolvedValueOnce(
        buildPayload({
          includeWhatIf: true,
          impactSummary: true,
          revenue2026: 1300,
          receivables2026: 278,
          dsoValue: 78,
          priceGrowthValue: 0.08,
          revenueScenarioState: "user_override",
          appliedOverrides: [
            { key: "price_growth", label: "Price Growth", unit: "percent", requested_value: 0.08, applied_value: 0.08, baseline_value: 0.04, min_value: -0.05, max_value: 0.15, clipped: false, source_detail: "SEC-derived pricing proxy", source_kind: "sec" },
          ],
        }).payload as never
      );

    const { payload, studio } = buildPayload({ includeWhatIf: true });
    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    await waitFor(() => expect(screen.getByTestId("studio-what-if-input-price_growth")).toBeTruthy());

    fireEvent.change(screen.getByTestId("studio-what-if-input-price_growth"), { target: { value: "0.08", valueAsNumber: 0.08 } });
    expect(getCompanyChartsWhatIf).toHaveBeenCalledTimes(0);
    expect(screen.queryByLabelText("What-if impact summary")).toBeNull();

    await new Promise((resolve) => setTimeout(resolve, 350));

    await waitFor(() => expect(getCompanyChartsWhatIf).toHaveBeenCalledTimes(1));
    expect(vi.mocked(getCompanyChartsWhatIf).mock.calls[0][1]).toEqual({ overrides: { price_growth: 0.08 } });
    expect(screen.getByLabelText("What-if impact summary")).toBeTruthy();

    const revenueCell = screen.getByRole("button", { name: "Revenue 2026 formula trace" });
    expect(within(revenueCell).getByText("+90")).toBeTruthy();
  });

  it("shows override metadata in formula popovers and reset returns to the base case", async () => {
    vi.mocked(getCompanyChartsWhatIf)
      .mockResolvedValueOnce(
        buildPayload({
          includeWhatIf: true,
          impactSummary: true,
          revenue2026: 1300,
          receivables2026: 278,
          dsoValue: 78,
          priceGrowthValue: 0.08,
          revenueScenarioState: "user_override",
          appliedOverrides: [
            { key: "price_growth", label: "Price Growth", unit: "percent", requested_value: 0.08, applied_value: 0.08, baseline_value: 0.04, min_value: -0.05, max_value: 0.15, clipped: false, source_detail: "SEC-derived pricing proxy", source_kind: "sec" },
          ],
        }).payload as never
      );

    const { payload, studio } = buildPayload({ includeWhatIf: true });
    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    await waitFor(() => expect(screen.getByTestId("studio-what-if-input-price_growth")).toBeTruthy());
    fireEvent.change(screen.getByTestId("studio-what-if-input-price_growth"), { target: { value: "0.08", valueAsNumber: 0.08 } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    await waitFor(() => expect(getCompanyChartsWhatIf).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Revenue 2026 formula trace" }));
    const dialog = screen.getByRole("dialog", { name: "Formula trace details" });
    expect(within(dialog).getByText("User scenario")).toBeTruthy();
    expect(within(dialog).getByText("Override")).toBeTruthy();
    expect(within(dialog).getByText(/Baseline 0.04/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Reset All" }));

    await waitFor(() => expect(screen.queryByLabelText("What-if impact summary")).toBeNull());
    expect(screen.queryByText("+90")).toBeNull();
    expect((screen.getByTestId("studio-what-if-input-price_growth") as HTMLInputElement).value).toBe("0.04");
  });

  it("preserves the current Studio view when recomputation fails", async () => {
    vi.mocked(getCompanyChartsWhatIf)
      .mockResolvedValueOnce(
        buildPayload({
          includeWhatIf: true,
          impactSummary: true,
          revenue2026: 1300,
          receivables2026: 278,
          dsoValue: 78,
          priceGrowthValue: 0.08,
          revenueScenarioState: "user_override",
          appliedOverrides: [
            { key: "price_growth", label: "Price Growth", unit: "percent", requested_value: 0.08, applied_value: 0.08, baseline_value: 0.04, min_value: -0.05, max_value: 0.15, clipped: false, source_detail: "SEC-derived pricing proxy", source_kind: "sec" },
          ],
        }).payload as never
      )
      .mockRejectedValueOnce(new Error("Scenario recompute failed"));

    const { payload, studio } = buildPayload({ includeWhatIf: true });
    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    await waitFor(() => expect(screen.getByTestId("studio-what-if-input-price_growth")).toBeTruthy());

    fireEvent.change(screen.getByTestId("studio-what-if-input-price_growth"), { target: { value: "0.08", valueAsNumber: 0.08 } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    await waitFor(() => expect(getCompanyChartsWhatIf).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText("What-if impact summary")).toBeTruthy();
    expect(within(screen.getByRole("button", { name: "Revenue 2026 formula trace" })).getByText("+90")).toBeTruthy();

    fireEvent.change(screen.getByTestId("studio-what-if-input-dso"), { target: { value: "90", valueAsNumber: 90 } });
    await new Promise((resolve) => setTimeout(resolve, 350));
    await waitFor(() => expect(getCompanyChartsWhatIf).toHaveBeenCalledTimes(2));

    expect(screen.getByRole("alert").textContent).toContain("Scenario recompute failed");
    expect(screen.getByLabelText("What-if impact summary")).toBeTruthy();
    expect(within(screen.getByRole("button", { name: "Revenue 2026 formula trace" })).getByText("+90")).toBeTruthy();
  });

  it("still exports studio csv rows with schedule metadata", async () => {
    vi.mocked(getCompanyChartsWhatIf).mockResolvedValueOnce(buildPayload({ includeWhatIf: true }).payload as never);
    const { payload, studio } = buildPayload();

    render(React.createElement(ProjectionStudio, { payload: payload as never, studio: studio as never }));

    await waitFor(() => expect(screen.getByText("Key Drivers")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Export Studio CSV" }));

    expect(exportRowsToCsv).toHaveBeenCalledTimes(1);
    const [fileName] = exportRowsToCsv.mock.calls[0] as [string, Array<Record<string, unknown>>];
    expect(fileName).toBe("ACME-projection-studio.csv");
  });
});
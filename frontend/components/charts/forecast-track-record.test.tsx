// @vitest-environment jsdom

import * as React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ForecastTrackRecord } from "./forecast-track-record";
import type { CompanyChartsForecastAccuracyResponse } from "@/lib/types";

vi.mock("recharts", () => {
  const MockResponsiveContainer = ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-responsive">{children}</div>
  );
  const MockChart = ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="recharts-chart">{children}</div>
  );
  return {
    ResponsiveContainer: MockResponsiveContainer,
    LineChart: MockChart,
    CartesianGrid: () => null,
    Line: () => null,
    Tooltip: () => null,
    XAxis: () => null,
    YAxis: () => null,
  };
});

function buildResponse(
  overrides: Partial<CompanyChartsForecastAccuracyResponse> = {}
): CompanyChartsForecastAccuracyResponse {
  return {
    company: null,
    status: "ok",
    insufficient_history_reason: null,
    max_backtests: 6,
    metrics: [
      {
        key: "revenue",
        label: "Revenue",
        unit: "usd",
        sample_count: 2,
        directional_sample_count: 2,
        mean_absolute_error: 8,
        mean_absolute_percentage_error: 0.06,
        directional_accuracy: 1,
      },
      {
        key: "eps",
        label: "Diluted EPS",
        unit: "usd_per_share",
        sample_count: 2,
        directional_sample_count: 2,
        mean_absolute_error: 0.4,
        mean_absolute_percentage_error: 0.19,
        directional_accuracy: 0.5,
      },
    ],
    aggregate: {
      snapshot_count: 2,
      sample_count: 4,
      directional_sample_count: 4,
      mean_absolute_percentage_error: 0.12,
      directional_accuracy: 0.75,
    },
    samples: [
      {
        metric_key: "revenue",
        metric_label: "Revenue",
        unit: "usd",
        anchor_fiscal_year: 2023,
        target_fiscal_year: 2024,
        cutoff_as_of: "2024-02-10T00:00:00+00:00",
        predicted_value: 110,
        actual_value: 120,
        absolute_error: 10,
        absolute_percentage_error: 0.0833,
        directionally_correct: true,
      },
      {
        metric_key: "revenue",
        metric_label: "Revenue",
        unit: "usd",
        anchor_fiscal_year: 2024,
        target_fiscal_year: 2025,
        cutoff_as_of: "2025-02-10T00:00:00+00:00",
        predicted_value: 126,
        actual_value: 133,
        absolute_error: 7,
        absolute_percentage_error: 0.0526,
        directionally_correct: true,
      },
      {
        metric_key: "eps",
        metric_label: "Diluted EPS",
        unit: "usd_per_share",
        anchor_fiscal_year: 2023,
        target_fiscal_year: 2024,
        cutoff_as_of: "2024-02-10T00:00:00+00:00",
        predicted_value: 1.6,
        actual_value: 2,
        absolute_error: 0.4,
        absolute_percentage_error: 0.2,
        directionally_correct: true,
      },
      {
        metric_key: "eps",
        metric_label: "Diluted EPS",
        unit: "usd_per_share",
        anchor_fiscal_year: 2024,
        target_fiscal_year: 2025,
        cutoff_as_of: "2025-02-10T00:00:00+00:00",
        predicted_value: 1.8,
        actual_value: 2.2,
        absolute_error: 0.4,
        absolute_percentage_error: 0.1818,
        directionally_correct: false,
      },
    ],
    refresh: {
      triggered: false,
      reason: "fresh",
      ticker: "ACME",
      job_id: null,
    },
    diagnostics: {
      coverage_ratio: 0.8,
      fallback_ratio: 0,
      stale_flags: [],
      parser_confidence: null,
      missing_field_flags: [],
      reconciliation_penalty: null,
      reconciliation_disagreement_count: 0,
    },
    provenance: [],
    as_of: "2025-12-31",
    last_refreshed_at: "2026-04-19T00:00:00Z",
    source_mix: {
      source_ids: [],
      source_tiers: [],
      primary_source_ids: [],
      fallback_source_ids: [],
      official_only: true,
    },
    confidence_flags: [],
    ...overrides,
  };
}

describe("ForecastTrackRecord", () => {
  it("renders summary strip metrics", () => {
    render(React.createElement(ForecastTrackRecord, { data: buildResponse() }));

    const summary = screen.getByTestId("forecast-track-record-summary");
    expect(within(summary).getByText(/Snapshots 2/)).toBeTruthy();
    expect(within(summary).getByText(/Samples 4/)).toBeTruthy();
    expect(within(summary).getByText(/Aggregate MAPE 12.00%/)).toBeTruthy();
    expect(within(summary).getByText(/Directional Accuracy 75.00%/)).toBeTruthy();
  });

  it("switches metrics from selector", () => {
    render(React.createElement(ForecastTrackRecord, { data: buildResponse() }));

    const select = screen.getByTestId("forecast-track-record-metric-select") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "eps" } });

    const table = screen.getByTestId("forecast-track-record-table");
    expect(within(table).getByText("Miss")).toBeTruthy();
    expect(within(table).getByText("20.00%")).toBeTruthy();
  });

  it("supports sorting and row expansion", () => {
    render(React.createElement(ForecastTrackRecord, { data: buildResponse() }));

    const table = screen.getByTestId("forecast-track-record-table");
    const absErrorSort = within(table).getByRole("button", { name: "Abs Error" });
    fireEvent.click(absErrorSort);
    fireEvent.click(absErrorSort);

    const bodyRows = within(table).getAllByRole("row").slice(1);
    expect(within(bodyRows[0]).getByText("2025")).toBeTruthy();

    const expandButtons = within(table).getAllByRole("button", { name: "Expand" });
    fireEvent.click(expandButtons[0]);
    expect(screen.getByText(/Anchor FY/)).toBeTruthy();
  });

  it("shows insufficient-history state without fabricated output", () => {
    render(
      React.createElement(ForecastTrackRecord, {
        data: buildResponse({
          status: "insufficient_history",
          insufficient_history_reason: "Need more annual history.",
          aggregate: {
            snapshot_count: 0,
            sample_count: 0,
            directional_sample_count: 0,
            mean_absolute_percentage_error: null,
            directional_accuracy: null,
          },
          samples: [],
        }),
      })
    );

    const insufficient = screen.getByTestId("forecast-track-record-insufficient");
    expect(within(insufficient).getByText("Need more annual history.")).toBeTruthy();
    expect(within(insufficient).getByText(/does not fabricate forecast outcomes/i)).toBeTruthy();
  });
});

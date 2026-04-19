"use client";

import Link from "next/link";
import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartsModeSwitch } from "@/components/company/charts-mode-switch";
import { ForecastTrackRecord } from "@/components/charts/forecast-track-record";
import { ForecastTrustCue } from "@/components/ui/forecast-trust-cue";
import { SourceStateBadge } from "@/components/ui/source-state-badge";
import { useForecastAccuracy } from "@/hooks/use-forecast-accuracy";
import { getCompanyChartsWhatIf } from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { exportRowsToCsv, type ExportRow, normalizeExportFileStem } from "@/lib/export";
import { FORECAST_HANDOFF_QUERY_PARAM, encodeForecastHandoffPayload, type ForecastHandoffMetric, type ForecastHandoffPayload } from "@/lib/forecast-handoff";
import { getForecastSourceStateDescriptor, resolveProjectionForecastSourceState, resolveSavedScenarioSourceState, type ForecastSourceState } from "@/lib/forecast-source-state";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import type {
  CompanyChartsDashboardResponse,
  CompanyChartsDriverCardPayload,
  CompanyChartsDriverControlMetadataPayload,
  CompanyChartsForecastAccuracyResponse,
  CompanyChartsFormulaInputPayload,
  CompanyChartsFormulaTracePayload,
  CompanyChartsProjectedRowPayload,
  CompanyChartsScheduleSectionPayload,
  CompanyChartsSensitivityCellPayload,
  CompanyChartsWhatIfImpactMetricPayload,
  CompanyChartsWhatIfOverridePayload,
} from "@/lib/types";

import { FormulaTracePopover } from "./formula-trace-popover";

interface ProjectionStudioProps {
  payload: CompanyChartsDashboardResponse;
  studio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>;
  requestedAsOf?: string | null;
}

interface DriverGroup {
  key: string;
  title: string;
  drivers: CompanyChartsDriverCardPayload[];
}

interface DriverControlGroup {
  key: string;
  title: string;
  controls: CompanyChartsDriverControlMetadataPayload[];
}

interface SensitivityGrid {
  rowIndexes: number[];
  columnIndexes: number[];
  rowLabels: Map<number, number>;
  columnLabels: Map<number, number>;
  cells: Map<string, CompanyChartsSensitivityCellPayload>;
  baseCell: CompanyChartsSensitivityCellPayload | null;
}

interface BridgeStep {
  key: string;
  label: string;
  amount: number;
  kind: "total" | "delta";
}

interface BridgeChartRow extends BridgeStep {
  offset: number;
  magnitude: number;
}

interface BridgeCard {
  key: string;
  title: string;
  trace: CompanyChartsFormulaTracePayload;
  unit: string;
  rows: BridgeChartRow[];
}

interface CellDelta {
  label: string;
  tone: "up" | "down";
}

const DRIVER_GROUP_TITLES: Record<string, string> = {
  revenue: "Revenue Drivers",
  cost: "Cost Structure",
  working_capital: "Working Capital",
  reinvestment: "Reinvestment",
  below_line: "Below-The-Line",
  dilution: "Shares & Dilution",
  other: "Other Inputs",
};

const WHAT_IF_DEBOUNCE_MS = 320;
const SCENARIO_STORAGE_VERSION = 1;
const MAX_COMPARE_SCENARIOS = 2;
const EMPTY_DRIVER_CONTROLS: CompanyChartsDriverControlMetadataPayload[] = [];
const EMPTY_WHAT_IF_IMPACT_METRICS: CompanyChartsWhatIfImpactMetricPayload[] = [];
const FORECAST_METRIC_SPECS = [
  { key: "revenue", label: "Revenue", unit: "usd" },
  { key: "operating_income", label: "Operating Income", unit: "usd" },
  { key: "net_income", label: "Net Income", unit: "usd" },
  { key: "free_cash_flow", label: "Free Cash Flow", unit: "usd" },
  { key: "eps", label: "EPS", unit: "usd_per_share" },
] as const;

interface SavedStudioScenarioMetric {
  key: string;
  label: string;
  unit: string;
  value: number | null;
}

interface SavedStudioScenario {
  version: 1;
  id: string;
  name: string;
  createdAt: string;
  overrideCount: number;
  source: "sec_base_forecast" | "user_scenario";
  overrides: Record<string, number>;
  metrics: SavedStudioScenarioMetric[];
}

type SavedScenarioPersistenceResult =
  | { status: "ok"; persistedCount: number }
  | { status: "trimmed"; persistedCount: number }
  | { status: "failed"; persistedCount: 0 };

function isSubtotalRow(key: string): boolean {
  return key.includes("_subtotal") || key.includes("_total") || key === "balance_check" || key === "reconciliation";
}

function formatValue(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return "—";
  }
  if (unit === "percent") {
    return formatPercent(value);
  }
  return formatCompactNumber(value);
}

function formatDriverValue(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return "—";
  }
  if (unit === "percent") {
    return formatPercent(value);
  }
  if (unit === "days") {
    return `${formatCompactNumber(value)}d`;
  }
  if (unit === "multiple") {
    return `${value.toFixed(2)}x`;
  }
  return formatCompactNumber(value);
}

function formatSignedDelta(value: number, unit: string): string {
  const prefix = value > 0 ? "+" : "-";
  return `${prefix}${formatDriverValue(Math.abs(value), unit)}`;
}

function readYearValue(values: Record<number, number | null>, year: number): number | null {
  const value = values[year];
  return typeof value === "number" ? value : null;
}

function buildBalanceCheckRow(section: CompanyChartsScheduleSectionPayload): CompanyChartsProjectedRowPayload | null {
  if (section.key !== "balance_sheet") {
    return null;
  }

  const accountsReceivable = section.rows.find((row) => row.key === "accounts_receivable");
  const inventory = section.rows.find((row) => row.key === "inventory");
  const accountsPayable = section.rows.find((row) => row.key === "accounts_payable");
  const deferredRevenue = section.rows.find((row) => row.key === "deferred_revenue");
  const accruedLiabilities = section.rows.find((row) => row.key === "accrued_operating_liabilities");
  if (!accountsReceivable || !inventory || !accountsPayable || !deferredRevenue || !accruedLiabilities) {
    return null;
  }

  const years = new Set<number>();
  [accountsReceivable, inventory, accountsPayable, deferredRevenue, accruedLiabilities].forEach((row) => {
    Object.keys(row.reported_values).forEach((year) => years.add(Number(year)));
    Object.keys(row.projected_values).forEach((year) => years.add(Number(year)));
  });

  const reportedValues: Record<number, number | null> = {};
  const projectedValues: Record<number, number | null> = {};
  Array.from(years).forEach((year) => {
    const calc =
      (readYearValue(accountsReceivable.reported_values, year) ?? readYearValue(accountsReceivable.projected_values, year) ?? 0) +
      (readYearValue(inventory.reported_values, year) ?? readYearValue(inventory.projected_values, year) ?? 0) -
      (readYearValue(accountsPayable.reported_values, year) ?? readYearValue(accountsPayable.projected_values, year) ?? 0) -
      (readYearValue(deferredRevenue.reported_values, year) ?? readYearValue(deferredRevenue.projected_values, year) ?? 0) -
      (readYearValue(accruedLiabilities.reported_values, year) ?? readYearValue(accruedLiabilities.projected_values, year) ?? 0);

    if (year in accountsReceivable.reported_values || year in inventory.reported_values) {
      reportedValues[year] = calc;
      return;
    }

    projectedValues[year] = calc;
  });

  return {
    key: "balance_check",
    label: "Balance Check",
    unit: "usd",
    reported_values: reportedValues,
    projected_values: projectedValues,
    formula_traces: {},
    scenario_values: {},
    detail: "AR + Inventory - AP - Deferred Revenue - Accrued Liabilities",
  };
}

function buildCashReconciliationRow(section: CompanyChartsScheduleSectionPayload): CompanyChartsProjectedRowPayload | null {
  if (section.key !== "cash_flow_statement") {
    return null;
  }

  const operatingCashFlow = section.rows.find((row) => row.key === "operating_cash_flow");
  const capex = section.rows.find((row) => row.key === "capex");
  const freeCashFlow = section.rows.find((row) => row.key === "free_cash_flow");
  if (!operatingCashFlow || !capex || !freeCashFlow) {
    return null;
  }

  const years = new Set<number>();
  [operatingCashFlow, capex, freeCashFlow].forEach((row) => {
    Object.keys(row.reported_values).forEach((year) => years.add(Number(year)));
    Object.keys(row.projected_values).forEach((year) => years.add(Number(year)));
  });

  const reportedValues: Record<number, number | null> = {};
  const projectedValues: Record<number, number | null> = {};
  Array.from(years).forEach((year) => {
    const calc =
      (readYearValue(operatingCashFlow.reported_values, year) ?? readYearValue(operatingCashFlow.projected_values, year) ?? 0) -
      (readYearValue(capex.reported_values, year) ?? readYearValue(capex.projected_values, year) ?? 0) -
      (readYearValue(freeCashFlow.reported_values, year) ?? readYearValue(freeCashFlow.projected_values, year) ?? 0);

    if (year in operatingCashFlow.reported_values || year in capex.reported_values) {
      reportedValues[year] = calc;
      return;
    }

    projectedValues[year] = calc;
  });

  return {
    key: "reconciliation",
    label: "Cash Reconciliation",
    unit: "usd",
    reported_values: reportedValues,
    projected_values: projectedValues,
    formula_traces: {},
    scenario_values: {},
    detail: "Operating Cash Flow - Capex - Free Cash Flow",
  };
}

function withCheckRows(section: CompanyChartsScheduleSectionPayload): CompanyChartsScheduleSectionPayload {
  const syntheticRow = buildBalanceCheckRow(section) ?? buildCashReconciliationRow(section);
  if (!syntheticRow) {
    return section;
  }

  return {
    ...section,
    rows: [...section.rows, syntheticRow],
  };
}

function getDriverGroupKey(driver: { key: string; title?: string; label?: string }): string {
  const normalizedKey = `${driver.key} ${driver.title ?? driver.label ?? ""}`.toLowerCase();

  if (normalizedKey.includes("revenue") || normalizedKey.includes("growth") || normalizedKey.includes("price") || normalizedKey.includes("volume") || normalizedKey.includes("demand")) {
    return "revenue";
  }
  if (normalizedKey.includes("cost") || normalizedKey.includes("margin") || normalizedKey.includes("opex") || normalizedKey.includes("sga") || normalizedKey.includes("r&d")) {
    return "cost";
  }
  if (normalizedKey.includes("working_capital") || normalizedKey.includes("receivable") || normalizedKey.includes("inventory") || normalizedKey.includes("payable") || normalizedKey.includes("days")) {
    return "working_capital";
  }
  if (normalizedKey.includes("reinvestment") || normalizedKey.includes("capex") || normalizedKey.includes("depreciation") || normalizedKey.includes("capital")) {
    return "reinvestment";
  }
  if (normalizedKey.includes("below_line") || normalizedKey.includes("interest") || normalizedKey.includes("tax") || normalizedKey.includes("other income")) {
    return "below_line";
  }
  if (normalizedKey.includes("dilution") || normalizedKey.includes("share")) {
    return "dilution";
  }
  return "other";
}

function groupDrivers(drivers: CompanyChartsDriverCardPayload[]): DriverGroup[] {
  const grouped = new Map<string, CompanyChartsDriverCardPayload[]>();

  drivers.forEach((driver) => {
    const key = getDriverGroupKey(driver);
    grouped.set(key, [...(grouped.get(key) ?? []), driver]);
  });

  return Array.from(grouped.entries()).map(([key, groupedDrivers]) => ({
    key,
    title: DRIVER_GROUP_TITLES[key] ?? DRIVER_GROUP_TITLES.other,
    drivers: groupedDrivers,
  }));
}

function groupDriverControls(controls: CompanyChartsDriverControlMetadataPayload[]): DriverControlGroup[] {
  const grouped = new Map<string, CompanyChartsDriverControlMetadataPayload[]>();

  controls.forEach((control) => {
    const key = getDriverGroupKey({ key: control.key, label: control.label });
    grouped.set(key, [...(grouped.get(key) ?? []), control]);
  });

  return Array.from(grouped.entries()).map(([key, groupedControls]) => ({
    key,
    title: DRIVER_GROUP_TITLES[key] ?? DRIVER_GROUP_TITLES.other,
    controls: groupedControls,
  }));
}

function sensitivityCellKey(rowIndex: number, columnIndex: number): string {
  return `${rowIndex}:${columnIndex}`;
}

function buildSensitivityGrid(cells: CompanyChartsSensitivityCellPayload[]): SensitivityGrid {
  const rowIndexes = Array.from(new Set(cells.map((cell) => cell.row_index))).sort((left, right) => left - right);
  const columnIndexes = Array.from(new Set(cells.map((cell) => cell.column_index))).sort((left, right) => left - right);
  const rowLabels = new Map<number, number>();
  const columnLabels = new Map<number, number>();
  const cellMap = new Map<string, CompanyChartsSensitivityCellPayload>();

  cells.forEach((cell) => {
    cellMap.set(sensitivityCellKey(cell.row_index, cell.column_index), cell);
    if (cell.operating_margin != null && !rowLabels.has(cell.row_index)) {
      rowLabels.set(cell.row_index, cell.operating_margin);
    }
    if (cell.revenue_growth != null && !columnLabels.has(cell.column_index)) {
      columnLabels.set(cell.column_index, cell.revenue_growth);
    }
  });

  return {
    rowIndexes,
    columnIndexes,
    rowLabels,
    columnLabels,
    cells: cellMap,
    baseCell: cells.find((cell) => cell.is_base) ?? null,
  };
}

function getTraceInput(trace: CompanyChartsFormulaTracePayload, key: string): CompanyChartsFormulaInputPayload | null {
  return trace.inputs.find((input) => input.key === key) ?? null;
}

function findRowByKey(sections: CompanyChartsScheduleSectionPayload[], rowKey: string): CompanyChartsProjectedRowPayload | null {
  for (const section of sections) {
    const row = section.rows.find((candidate) => candidate.key === rowKey);
    if (row) {
      return row;
    }
  }
  return null;
}

function buildBridgeRows(steps: BridgeStep[]): BridgeChartRow[] {
  let runningValue = 0;

  return steps.map((step) => {
    if (step.kind === "total") {
      runningValue = step.amount;
      return {
        ...step,
        offset: 0,
        magnitude: Math.abs(step.amount),
      };
    }

    const nextValue = runningValue + step.amount;
    const bridgeRow = {
      ...step,
      offset: Math.min(runningValue, nextValue),
      magnitude: Math.abs(step.amount),
    };
    runningValue = nextValue;
    return bridgeRow;
  });
}

function buildRevenueBridge(trace: CompanyChartsFormulaTracePayload): BridgeCard | null {
  const priorRevenue = getTraceInput(trace, "prior_revenue")?.value ?? getTraceInput(trace, "previous_revenue")?.value;
  const projectedRevenue = trace.result_value;
  if (priorRevenue == null || projectedRevenue == null) {
    return null;
  }

  return {
    key: "revenue-bridge",
    title: "Revenue Bridge",
    trace,
    unit: "usd",
    rows: buildBridgeRows([
      { key: "prior", label: "Prior Revenue", amount: priorRevenue, kind: "total" },
      { key: "growth", label: "Growth Delta", amount: projectedRevenue - priorRevenue, kind: "delta" },
      { key: "projected", label: `${trace.year} Revenue`, amount: projectedRevenue, kind: "total" },
    ]),
  };
}

function buildOperatingIncomeBridge(trace: CompanyChartsFormulaTracePayload): BridgeCard | null {
  const revenue = getTraceInput(trace, "revenue")?.value;
  const variableCost = getTraceInput(trace, "variable_cost")?.value;
  const semiVariableCost = getTraceInput(trace, "semi_variable_cost")?.value;
  const fixedCost = getTraceInput(trace, "fixed_cost")?.value;
  const projectedOperatingIncome = trace.result_value;
  if (revenue == null || variableCost == null || semiVariableCost == null || fixedCost == null || projectedOperatingIncome == null) {
    return null;
  }

  return {
    key: "operating-income-bridge",
    title: "Operating Income Bridge",
    trace,
    unit: "usd",
    rows: buildBridgeRows([
      { key: "revenue", label: "Revenue", amount: revenue, kind: "total" },
      { key: "variable", label: "Variable Costs", amount: -variableCost, kind: "delta" },
      { key: "semi-variable", label: "Semi-Variable Costs", amount: -semiVariableCost, kind: "delta" },
      { key: "fixed", label: "Fixed Costs", amount: -fixedCost, kind: "delta" },
      { key: "result", label: `${trace.year} Operating Income`, amount: projectedOperatingIncome, kind: "total" },
    ]),
  };
}

function buildFreeCashFlowBridge(trace: CompanyChartsFormulaTracePayload): BridgeCard | null {
  const operatingCashFlow = getTraceInput(trace, "operating_cash_flow")?.value;
  const capex = getTraceInput(trace, "capex")?.value;
  const freeCashFlow = trace.result_value;
  if (operatingCashFlow == null || capex == null || freeCashFlow == null) {
    return null;
  }

  return {
    key: "free-cash-flow-bridge",
    title: "Free Cash Flow Bridge",
    trace,
    unit: "usd",
    rows: buildBridgeRows([
      { key: "operating-cash-flow", label: "Operating Cash Flow", amount: operatingCashFlow, kind: "total" },
      { key: "capex", label: "Capex", amount: -capex, kind: "delta" },
      { key: "free-cash-flow", label: `${trace.year} Free Cash Flow`, amount: freeCashFlow, kind: "total" },
    ]),
  };
}

function buildBridgeCards(sections: CompanyChartsScheduleSectionPayload[], firstProjectedYear: number | null): BridgeCard[] {
  if (firstProjectedYear == null) {
    return [];
  }

  const revenueTrace = findRowByKey(sections, "revenue")?.formula_traces[firstProjectedYear];
  const operatingIncomeTrace = findRowByKey(sections, "operating_income")?.formula_traces[firstProjectedYear];
  const freeCashFlowTrace = findRowByKey(sections, "free_cash_flow")?.formula_traces[firstProjectedYear];

  return [
    revenueTrace ? buildRevenueBridge(revenueTrace) : null,
    operatingIncomeTrace ? buildOperatingIncomeBridge(operatingIncomeTrace) : null,
    freeCashFlowTrace ? buildFreeCashFlowBridge(freeCashFlowTrace) : null,
  ].filter((card): card is BridgeCard => card !== null);
}

function formatTraceInputs(trace: CompanyChartsFormulaTracePayload | undefined): string {
  if (!trace) {
    return "";
  }

  return trace.inputs
    .map((input) => `${input.label}=${input.formatted_value} [${input.source_kind}${input.source_detail ? ` | ${input.source_detail}` : ""}]`)
    .join("; ");
}

function buildExportRows(
  scheduleSections: CompanyChartsScheduleSectionPayload[],
  driverGroups: DriverGroup[],
  scenarios: CompanyChartsProjectedRowPayload[],
  sensitivityCells: CompanyChartsSensitivityCellPayload[],
  impactMetrics: CompanyChartsWhatIfImpactMetricPayload[],
  comparedScenarios: SavedStudioScenario[],
  sourceState: ForecastSourceState,
  forecastAccuracy: CompanyChartsForecastAccuracyResponse | null
): ExportRow[] {
  const sourceDescriptor = getForecastSourceStateDescriptor(sourceState);
  const metadataRows: ExportRow[] = [
    {
      record_type: "source_state_meta",
      source_state: sourceDescriptor.key,
      source_state_label: sourceDescriptor.label,
      source_state_description: sourceDescriptor.description,
    },
  ];

  if (forecastAccuracy) {
    metadataRows.push({
      record_type: "forecast_accuracy_meta",
      forecast_accuracy_status: forecastAccuracy.status,
      insufficient_history_reason: forecastAccuracy.status === "insufficient_history" ? (forecastAccuracy.insufficient_history_reason ?? "") : "",
      snapshot_count: forecastAccuracy.status === "ok" ? forecastAccuracy.aggregate.snapshot_count : "",
      sample_count: forecastAccuracy.status === "ok" ? forecastAccuracy.aggregate.sample_count : "",
      mean_absolute_percentage_error: forecastAccuracy.status === "ok" ? (forecastAccuracy.aggregate.mean_absolute_percentage_error ?? "") : "",
      directional_accuracy: forecastAccuracy.status === "ok" ? (forecastAccuracy.aggregate.directional_accuracy ?? "") : "",
    });
  }

  const scheduleRows = scheduleSections.flatMap((section) =>
    section.rows.flatMap((row) => {
      const years = Array.from(new Set([...Object.keys(row.reported_values).map(Number), ...Object.keys(row.projected_values).map(Number)])).sort(
        (left, right) => left - right
      );

      return years.map((year) => {
        const trace = row.formula_traces[year];
        return {
          record_type: "schedule",
          section_key: section.key,
          section_title: section.title,
          row_key: row.key,
          row_label: row.label,
          row_detail: row.detail ?? "",
          unit: row.unit,
          year,
          reported_value: row.reported_values[year] ?? "",
          projected_value: row.projected_values[year] ?? "",
          formula_label: trace?.formula_label ?? "",
          formula_template: trace?.formula_template ?? "",
          formula_computation: trace?.formula_computation ?? "",
          formula_confidence: trace?.confidence ?? "",
          formula_result_value: trace?.result_value ?? "",
          formula_inputs: formatTraceInputs(trace),
        } satisfies ExportRow;
      });
    })
  );

  const driverRows = driverGroups.flatMap((group) =>
    group.drivers.map(
      (driver) =>
        ({
          record_type: "driver",
          driver_group: group.title,
          driver_key: driver.key,
          driver_title: driver.title,
          driver_value: driver.value,
          driver_detail: driver.detail ?? "",
          source_periods: driver.source_periods.join(" | "),
          default_markers: driver.default_markers.join(" | "),
          fallback_markers: driver.fallback_markers.join(" | "),
        }) satisfies ExportRow
    )
  );

  const scenarioRows = scenarios.map(
    (row) =>
      ({
        record_type: "scenario",
        row_key: row.key,
        row_label: row.label,
        unit: row.unit,
        base: row.scenario_values.base ?? "",
        bull: row.scenario_values.bull ?? "",
        bear: row.scenario_values.bear ?? "",
      }) satisfies ExportRow
  );

  const sensitivityRows = sensitivityCells.map(
    (cell) =>
      ({
        record_type: "sensitivity",
        row_index: cell.row_index,
        column_index: cell.column_index,
        revenue_growth: cell.revenue_growth ?? "",
        operating_margin: cell.operating_margin ?? "",
        eps: cell.eps ?? "",
        is_base: cell.is_base ? "true" : "false",
      }) satisfies ExportRow
  );

  const impactRows = impactMetrics.map(
    (metric) =>
      ({
        record_type: "scenario_impact",
        metric_key: metric.key,
        metric_label: metric.label,
        unit: metric.unit,
        baseline_value: metric.baseline_value ?? "",
        scenario_value: metric.scenario_value ?? "",
        delta_value: metric.delta_value ?? "",
        delta_percent: metric.delta_percent ?? "",
      }) satisfies ExportRow
  );

  const comparedScenarioRows =
    comparedScenarios.length === MAX_COMPARE_SCENARIOS
      ? buildComparedScenarioRows(comparedScenarios[0], comparedScenarios[1])
      : [];

  return [...metadataRows, ...scheduleRows, ...driverRows, ...scenarioRows, ...sensitivityRows, ...impactRows, ...comparedScenarioRows];
}

function buildComparedScenarioRows(left: SavedStudioScenario, right: SavedStudioScenario): ExportRow[] {
  const leftMetricMap = new Map(left.metrics.map((metric) => [metric.key, metric]));
  const rightMetricMap = new Map(right.metrics.map((metric) => [metric.key, metric]));
  const metricKeys = Array.from(new Set([...leftMetricMap.keys(), ...rightMetricMap.keys()]));

  return metricKeys.map((metricKey) => {
    const leftMetric = leftMetricMap.get(metricKey) ?? null;
    const rightMetric = rightMetricMap.get(metricKey) ?? null;
    const delta =
      leftMetric?.value != null && rightMetric?.value != null
        ? rightMetric.value - leftMetric.value
        : "";

    return {
      record_type: "scenario_compare",
      metric_key: metricKey,
      metric_label: leftMetric?.label ?? rightMetric?.label ?? metricKey,
      unit: leftMetric?.unit ?? rightMetric?.unit ?? "",
      left_scenario: left.name,
      left_value: leftMetric?.value ?? "",
      right_scenario: right.name,
      right_value: rightMetric?.value ?? "",
      delta,
    } satisfies ExportRow;
  });
}

function normalizeScenarioName(name: string | null | undefined): string | null {
  const trimmed = (name ?? "").trim();
  return trimmed ? trimmed : null;
}

function storageKeyForTicker(ticker: string): string {
  return `ft:projection-studio:scenarios:${ticker.toUpperCase()}`;
}

function isQuotaExceededStorageError(error: unknown): boolean {
  if (error instanceof DOMException) {
    return error.name === "QuotaExceededError" || error.name === "NS_ERROR_DOM_QUOTA_REACHED" || error.code === 22 || error.code === 1014;
  }

  return false;
}

function tryPersistSavedScenarios(storageKey: string, savedScenarios: SavedStudioScenario[]): boolean {
  try {
    if (!savedScenarios.length) {
      window.localStorage.removeItem(storageKey);
      return true;
    }

    window.localStorage.setItem(storageKey, JSON.stringify(savedScenarios));
    return true;
  } catch (error) {
    if (isQuotaExceededStorageError(error)) {
      return false;
    }

    throw error;
  }
}

function persistSavedScenariosForTicker(ticker: string, savedScenarios: SavedStudioScenario[]): SavedScenarioPersistenceResult {
  const storageKey = storageKeyForTicker(ticker);

  if (tryPersistSavedScenarios(storageKey, savedScenarios)) {
    return {
      status: "ok",
      persistedCount: savedScenarios.length,
    };
  }

  for (let keepCount = savedScenarios.length - 1; keepCount >= 1; keepCount -= 1) {
    if (tryPersistSavedScenarios(storageKey, savedScenarios.slice(0, keepCount))) {
      return {
        status: "trimmed",
        persistedCount: keepCount,
      };
    }
  }

  try {
    window.localStorage.removeItem(storageKey);
  } catch {
    // Ignore remove failures after quota issues. The current in-memory scenarios still remain usable.
  }

  return {
    status: "failed",
    persistedCount: 0,
  };
}

function parseSavedScenarios(raw: string | null): SavedStudioScenario[] {
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .map((entry): SavedStudioScenario | null => {
        if (!entry || typeof entry !== "object") {
          return null;
        }
        const candidate = entry as Partial<SavedStudioScenario>;
        if (
          candidate.version !== SCENARIO_STORAGE_VERSION ||
          typeof candidate.id !== "string" ||
          typeof candidate.name !== "string" ||
          typeof candidate.createdAt !== "string" ||
          typeof candidate.overrides !== "object" ||
          !candidate.overrides ||
          !Array.isArray(candidate.metrics)
        ) {
          return null;
        }

        const normalizedOverrides: Record<string, number> = {};
        Object.entries(candidate.overrides).forEach(([key, value]) => {
          if (typeof value === "number" && Number.isFinite(value)) {
            normalizedOverrides[key] = value;
          }
        });

        const metrics = candidate.metrics
          .map((metric): SavedStudioScenarioMetric | null => {
            if (!metric || typeof metric !== "object") {
              return null;
            }
            const nextMetric = metric as Partial<SavedStudioScenarioMetric>;
            if (typeof nextMetric.key !== "string" || typeof nextMetric.label !== "string" || typeof nextMetric.unit !== "string") {
              return null;
            }
            return {
              key: nextMetric.key,
              label: nextMetric.label,
              unit: nextMetric.unit,
              value: typeof nextMetric.value === "number" && Number.isFinite(nextMetric.value) ? nextMetric.value : null,
            };
          })
          .filter((metric): metric is SavedStudioScenarioMetric => metric !== null);

        return {
          version: 1,
          id: candidate.id,
          name: candidate.name,
          createdAt: candidate.createdAt,
          overrideCount: typeof candidate.overrideCount === "number" && Number.isFinite(candidate.overrideCount) ? candidate.overrideCount : Object.keys(normalizedOverrides).length,
          source: candidate.source === "user_scenario" ? "user_scenario" : "sec_base_forecast",
          overrides: normalizedOverrides,
          metrics,
        };
      })
      .filter((entry): entry is SavedStudioScenario => entry !== null)
      .sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime());
  } catch {
    return [];
  }
}

function readProjectedValueByKey(studio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>, rowKey: string, year: number): number | null {
  for (const section of studio.schedule_sections) {
    const row = section.rows.find((candidate) => candidate.key === rowKey);
    if (!row) {
      continue;
    }
    const value = row.projected_values[year];
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  return null;
}

function collectScenarioMetrics(studio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>, forecastYear: number | null): SavedStudioScenarioMetric[] {
  if (forecastYear == null) {
    return [];
  }

  return FORECAST_METRIC_SPECS.map((metricSpec) => ({
    key: metricSpec.key,
    label: metricSpec.label,
    unit: metricSpec.unit,
    value: readProjectedValueByKey(studio, metricSpec.key, forecastYear),
  }));
}

function buildForecastHandoffMetrics(
  baseStudio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>,
  visibleStudio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>,
  forecastYear: number | null
): ForecastHandoffMetric[] {
  if (forecastYear == null) {
    return [];
  }

  return FORECAST_METRIC_SPECS.map((metricSpec) => ({
    key: metricSpec.key,
    label: metricSpec.label,
    unit: metricSpec.unit,
    base: readProjectedValueByKey(baseStudio, metricSpec.key, forecastYear),
    scenario: readProjectedValueByKey(visibleStudio, metricSpec.key, forecastYear),
  })).filter((metric) => metric.base != null || metric.scenario != null);
}

function formatScenarioTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown";
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function getSensitivityTone(cell: CompanyChartsSensitivityCellPayload | undefined, baseCell: CompanyChartsSensitivityCellPayload | null): string {
  if (!cell) {
    return "is-empty";
  }
  if (cell.is_base) {
    return "is-base";
  }
  if (baseCell?.eps == null || cell.eps == null) {
    return "is-neutral";
  }
  if (cell.eps > baseCell.eps) {
    return "is-upside";
  }
  if (cell.eps < baseCell.eps) {
    return "is-downside";
  }
  return "is-neutral";
}

function getBridgeFill(row: BridgeChartRow): string {
  if (row.kind === "total") {
    return "var(--accent)";
  }
  return row.amount >= 0 ? "var(--positive)" : "var(--negative)";
}

function nearlyEqual(left: number | null | undefined, right: number | null | undefined): boolean {
  if (left == null || right == null) {
    return left == null && right == null;
  }
  return Math.abs(left - right) <= 1e-9;
}

function clampValue(value: number, control: CompanyChartsDriverControlMetadataPayload): number {
  const minimum = control.min_value ?? value;
  const maximum = control.max_value ?? value;
  return Math.min(maximum, Math.max(minimum, value));
}

function materialityThreshold(unit: string, baselineValue: number): number {
  if (unit === "percent") {
    return 0.005;
  }
  if (unit === "days") {
    return 1;
  }
  if (unit === "multiple") {
    return 0.05;
  }
  if (unit === "usd_per_share") {
    return 0.05;
  }
  return Math.max(Math.abs(baselineValue) * 0.01, 1);
}

function buildCellDelta(baselineValue: number | null, scenarioValue: number | null, unit: string): CellDelta | null {
  if (baselineValue == null || scenarioValue == null || nearlyEqual(baselineValue, scenarioValue)) {
    return null;
  }

  const deltaValue = scenarioValue - baselineValue;
  if (Math.abs(deltaValue) < materialityThreshold(unit, baselineValue)) {
    return null;
  }

  return {
    label: formatSignedDelta(deltaValue, unit),
    tone: deltaValue >= 0 ? "up" : "down",
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function asErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function ScheduleTable({
  section,
  baselineSection,
  reportedYears,
  projectedYears,
  hasScenarioOverrides,
  onCellClick,
}: {
  section: CompanyChartsScheduleSectionPayload;
  baselineSection: CompanyChartsScheduleSectionPayload | null;
  reportedYears: number[];
  projectedYears: number[];
  hasScenarioOverrides: boolean;
  onCellClick: (trace: CompanyChartsFormulaTracePayload) => void;
}) {
  const allYears = [...reportedYears, ...projectedYears];
  const baselineRowsByKey = useMemo(() => new Map((baselineSection?.rows ?? []).map((row) => [row.key, row])), [baselineSection]);

  return (
    <div className="studio-schedule-table">
      <h3 className="studio-schedule-title">{section.title}</h3>
      <div className="studio-table-wrapper">
        <table className="studio-table">
          <thead>
            <tr className="studio-table-header-row">
              <th className="studio-table-label-cell">Metric</th>
              {allYears.map((year) => {
                const isProjected = projectedYears.includes(year);
                return (
                  <th key={year} className={`studio-table-year-cell ${isProjected ? "is-projected" : "is-reported"}`}>
                    <span className="studio-table-year">{year}</span>
                    <span className="studio-table-year-marker">{isProjected ? "P" : "R"}</span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {section.rows.map((row) => {
              const isSubtotal = isSubtotalRow(row.key);
              const baselineRow = baselineRowsByKey.get(row.key) ?? null;
              return (
                <tr key={row.key} className={`studio-table-body-row ${isSubtotal ? "is-subtotal" : ""}`}>
                  <td className="studio-table-label-cell">
                    <div className="studio-row-label">{row.label}</div>
                    {row.detail ? <div className="studio-row-detail">{row.detail}</div> : null}
                  </td>
                  {allYears.map((year) => {
                    const isProjected = projectedYears.includes(year);
                    const value = isProjected ? row.projected_values[year] : row.reported_values[year];
                    const trace = isProjected ? row.formula_traces[year] : null;
                    const isClickable = Boolean(isProjected && trace);
                    const delta =
                      isProjected && hasScenarioOverrides
                        ? buildCellDelta(baselineRow?.projected_values[year] ?? null, value ?? null, row.unit)
                        : null;

                    const cellContent = (
                      <span className="studio-table-value-stack">
                        <span className="studio-table-main-value">{formatValue(value, row.unit)}</span>
                        {delta ? <span className={`studio-table-delta-badge is-${delta.tone}`}>{delta.label}</span> : null}
                      </span>
                    );

                    return (
                      <td
                        key={`${row.key}-${year}`}
                        className={`studio-table-value-cell ${isProjected ? "is-projected" : "is-reported"} ${isClickable ? "is-clickable" : ""} ${delta ? `has-delta is-${delta.tone}` : ""}`}
                        data-projected={isProjected ? "true" : "false"}
                      >
                        {isClickable && trace ? (
                          <button
                            type="button"
                            className="studio-table-value-button"
                            onClick={() => onCellClick(trace)}
                            aria-label={`${row.label} ${year} formula trace`}
                          >
                            {cellContent}
                          </button>
                        ) : (
                          cellContent
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SensitivityMatrix({ grid }: { grid: SensitivityGrid }) {
  if (!grid.rowIndexes.length || !grid.columnIndexes.length) {
    return null;
  }

  return (
    <section className="studio-panel" aria-label="Sensitivity matrix">
      <div className="studio-panel-header">
        <div>
          <h2 className="studio-panel-title">Sensitivity Matrix</h2>
          <p className="studio-panel-subtitle">Five-by-five EPS surface across revenue growth and operating margin assumptions.</p>
        </div>
      </div>
      <div className="studio-table-wrapper">
        <table className="studio-sensitivity-table">
          <thead>
            <tr>
              <th>Operating Margin \ Revenue Growth</th>
              {grid.columnIndexes.map((columnIndex) => (
                <th key={columnIndex}>{formatValue(grid.columnLabels.get(columnIndex), "percent")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.rowIndexes.map((rowIndex) => (
              <tr key={rowIndex}>
                <th>{formatValue(grid.rowLabels.get(rowIndex), "percent")}</th>
                {grid.columnIndexes.map((columnIndex) => {
                  const cell = grid.cells.get(sensitivityCellKey(rowIndex, columnIndex));
                  return (
                    <td
                      key={columnIndex}
                      className={`studio-sensitivity-cell ${getSensitivityTone(cell, grid.baseCell)}`}
                      data-testid={`studio-sensitivity-cell-${rowIndex}-${columnIndex}`}
                    >
                      {cell?.eps == null ? "—" : formatCompactNumber(cell.eps)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BridgeChartCard({ card, onInspect }: { card: BridgeCard; onInspect: (trace: CompanyChartsFormulaTracePayload) => void }) {
  return (
    <section className="studio-panel studio-bridge-card" aria-label={card.title}>
      <div className="studio-panel-header studio-bridge-header">
        <div>
          <h2 className="studio-panel-title">{card.title}</h2>
          <p className="studio-panel-subtitle">{card.trace.formula_template}</p>
        </div>
        <button
          type="button"
          className="studio-secondary-button"
          onClick={() => onInspect(card.trace)}
          aria-label={`Inspect ${card.title.toLowerCase()} formula`}
        >
          Inspect Formula
        </button>
      </div>
      <div className="studio-bridge-chart-shell">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={card.rows} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(10)} interval={0} angle={-12} textAnchor="end" height={56} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(10)} tickFormatter={(value) => formatCompactNumber(Number(value))} width={64} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(_value, _name, props) => {
                const payload = props?.payload as BridgeChartRow | undefined;
                if (!payload) {
                  return ["—", "Value"];
                }
                return [formatValue(payload.amount, card.unit), payload.label];
              }}
            />
            <ReferenceLine y={0} stroke="var(--panel-border)" />
            <Bar dataKey="offset" stackId="bridge" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="magnitude" stackId="bridge" radius={[8, 8, 0, 0]} isAnimationActive={false}>
              {card.rows.map((row) => (
                <Cell key={row.key} fill={getBridgeFill(row)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="studio-bridge-footer">
        <span className={`formula-trace-confidence formula-trace-confidence-${card.trace.confidence}`}>{card.trace.confidence}</span>
        <span className="studio-bridge-footnote">Projected year {card.trace.year}</span>
      </div>
    </section>
  );
}

function ImpactMetricCard({ metric }: { metric: CompanyChartsWhatIfImpactMetricPayload }) {
  return (
    <article className="studio-impact-card">
      <div className="studio-impact-card-topline">
        <div className="studio-impact-card-label">{metric.label}</div>
        {metric.delta_value != null ? (
          <div className={`studio-impact-card-delta ${metric.delta_value >= 0 ? "is-up" : "is-down"}`}>{formatSignedDelta(metric.delta_value, metric.unit)}</div>
        ) : null}
      </div>
      <div className="studio-impact-card-values">
        <span>Base {formatDriverValue(metric.baseline_value, metric.unit)}</span>
        <span>Scenario {formatDriverValue(metric.scenario_value, metric.unit)}</span>
      </div>
      {metric.delta_percent != null ? (
        <div className="studio-impact-card-detail">{metric.delta_percent >= 0 ? "+" : ""}{formatPercent(metric.delta_percent)} vs base</div>
      ) : null}
    </article>
  );
}

function ImpactSummaryStrip({
  payload,
  activeOverrideCount,
}: {
  payload: CompanyChartsDashboardResponse;
  activeOverrideCount: number;
}) {
  const impactSummary = payload.what_if?.impact_summary;
  const metrics = impactSummary?.metrics ?? [];
  if (!activeOverrideCount || !metrics.length) {
    return null;
  }

  return (
    <section className="studio-impact-strip" aria-label="What-if impact summary">
      <div className="studio-impact-strip-copy">
        <div className="studio-impact-strip-eyebrow">User Scenario</div>
        <h2 className="studio-impact-strip-title">Forecast impact for {impactSummary?.forecast_year ?? "next forecast year"}</h2>
        <p className="studio-impact-strip-subtitle">Live deltas against the baseline forecast remain visible while the rest of Studio updates in place.</p>
      </div>
      <div className="studio-impact-strip-grid">
        {metrics.map((metric) => (
          <ImpactMetricCard key={metric.key} metric={metric} />
        ))}
      </div>
    </section>
  );
}

function WhatIfSidebar({
  controls,
  draftOverrides,
  appliedOverrides,
  clippedOverrides,
  isOpen,
  controlsLoading,
  recomputing,
  error,
  onToggle,
  onResetAll,
  onRetry,
  onControlChange,
}: {
  controls: CompanyChartsDriverControlMetadataPayload[];
  draftOverrides: Record<string, number>;
  appliedOverrides: Map<string, CompanyChartsWhatIfOverridePayload>;
  clippedOverrides: Set<string>;
  isOpen: boolean;
  controlsLoading: boolean;
  recomputing: boolean;
  error: string | null;
  onToggle: () => void;
  onResetAll: () => void;
  onRetry: () => void;
  onControlChange: (key: string, value: number) => void;
}) {
  const groupedControls = useMemo(() => groupDriverControls(controls), [controls]);
  const activeOverrideCount = Object.keys(draftOverrides).length;

  return (
    <aside id="studio-what-if-sidebar" className={`studio-what-if-sidebar ${isOpen ? "is-open" : "is-collapsed"}`} aria-label="Projection Studio what-if sidebar">
      <div className="studio-panel studio-what-if-shell">
        <div className="studio-panel-header studio-what-if-header">
          <div>
            <h2 className="studio-panel-title">What-If Controls</h2>
            <p className="studio-panel-subtitle">Backend-provided operating assumptions for live scenario recomputation.</p>
          </div>
          <div className="studio-what-if-actions">
            <button type="button" className="studio-secondary-button" onClick={onToggle} aria-controls="studio-what-if-sidebar">
              {isOpen ? "Collapse Sidebar" : "Open Sidebar"}
            </button>
            <button type="button" className="studio-secondary-button" onClick={onResetAll} disabled={!activeOverrideCount && !recomputing}>
              Reset All
            </button>
          </div>
        </div>

        {controlsLoading && !controls.length ? <div className="studio-what-if-state">Loading backend control limits...</div> : null}
        {recomputing ? <div className="studio-what-if-state">Recomputing scenario. The current Studio view stays visible until fresh results land.</div> : null}
        {error ? (
          <div className="studio-what-if-error" role="alert">
            <div>{error}</div>
            <button type="button" className="studio-secondary-button" onClick={onRetry}>
              Retry
            </button>
          </div>
        ) : null}
        {clippedOverrides.size ? <div className="studio-what-if-state">One or more overrides were clipped by backend limits before the scenario was applied.</div> : null}

        {!controlsLoading && !controls.length ? (
          <div className="studio-what-if-empty">
            <p>Controls are not available yet.</p>
            <button type="button" className="studio-secondary-button" onClick={onRetry}>
              Load Controls
            </button>
          </div>
        ) : null}

        {controls.length ? (
          <>
            <div className="studio-what-if-summary-row">
              <span className="studio-marker-chip is-default">Active overrides: {activeOverrideCount}</span>
              <span className="studio-marker-chip is-default">Backend limits: live</span>
            </div>

            <div className="studio-what-if-group-stack">
              {groupedControls.map((group) => (
                <section key={group.key} className="studio-what-if-group">
                  <div className="studio-driver-group-title">{group.title}</div>
                  <div className="studio-what-if-control-grid">
                    {group.controls.map((control) => {
                      const controlValue = draftOverrides[control.key] ?? control.baseline_value ?? control.current_value ?? 0;
                      const appliedOverride = appliedOverrides.get(control.key) ?? null;
                      const isActive = control.key in draftOverrides;
                      return (
                        <article key={control.key} className={`studio-driver-card studio-what-if-card ${isActive ? "is-active" : ""}`} data-testid={`studio-what-if-control-${control.key}`}>
                          <div className="studio-driver-topline">
                            <div>
                              <div className="studio-driver-title">{control.label}</div>
                              <div className="studio-driver-detail">{control.source_detail}</div>
                            </div>
                            <div className="studio-driver-value">{formatDriverValue(controlValue, control.unit)}</div>
                          </div>

                          <div className="studio-what-if-range-row">
                            <span>{formatDriverValue(control.min_value, control.unit)}</span>
                            <input
                              data-testid={`studio-what-if-slider-${control.key}`}
                              className="studio-what-if-range"
                              type="range"
                              min={control.min_value ?? undefined}
                              max={control.max_value ?? undefined}
                              step={control.step ?? "any"}
                              value={controlValue}
                              onChange={(event) => onControlChange(control.key, event.currentTarget.valueAsNumber)}
                              aria-label={`${control.label} slider`}
                            />
                            <span>{formatDriverValue(control.max_value, control.unit)}</span>
                          </div>

                          <label className="studio-what-if-input-shell">
                            <span className="studio-what-if-input-label">Manual value</span>
                            <input
                              data-testid={`studio-what-if-input-${control.key}`}
                              className="studio-what-if-number"
                              type="number"
                              min={control.min_value ?? undefined}
                              max={control.max_value ?? undefined}
                              step={control.step ?? "any"}
                              value={controlValue}
                              onChange={(event) => onControlChange(control.key, event.currentTarget.valueAsNumber)}
                            />
                          </label>

                          <div className="studio-what-if-meta-row">
                            <span>Baseline {formatDriverValue(control.baseline_value, control.unit)}</span>
                            {appliedOverride ? <span>Applied {formatDriverValue(appliedOverride.applied_value, control.unit)}</span> : <span>{control.source_kind}</span>}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}

export function ProjectionStudio({ payload, studio, requestedAsOf = null }: ProjectionStudioProps) {
  const ticker = payload.company?.ticker ?? "company";
  const forecastAccuracy = useForecastAccuracy(ticker, {
    asOf: requestedAsOf,
    enabled: Boolean(payload.company?.ticker),
  });
  const [selectedTrace, setSelectedTrace] = useState<CompanyChartsFormulaTracePayload | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [basePayload, setBasePayload] = useState<CompanyChartsDashboardResponse>(payload);
  const [visiblePayload, setVisiblePayload] = useState<CompanyChartsDashboardResponse>(payload);
  const [draftOverrides, setDraftOverrides] = useState<Record<string, number>>({});
  const [controlsLoading, setControlsLoading] = useState(!payload.what_if);
  const [recomputing, setRecomputing] = useState(false);
  const [recomputeError, setRecomputeError] = useState<string | null>(null);
  const [controlsRetryTick, setControlsRetryTick] = useState(0);
  const [recomputeRetryTick, setRecomputeRetryTick] = useState(0);
  const [savedScenarios, setSavedScenarios] = useState<SavedStudioScenario[]>([]);
  const [savedScenarioPersistenceMessage, setSavedScenarioPersistenceMessage] = useState<string | null>(null);
  const [loadedScenarioId, setLoadedScenarioId] = useState<string | null>(null);
  const [compareScenarioIds, setCompareScenarioIds] = useState<string[]>([]);
  const [loadedSavedScenarioTicker, setLoadedSavedScenarioTicker] = useState<string | null>(null);
  const recomputeAbortRef = useRef<AbortController | null>(null);
  const persistedSavedScenarioSnapshotRef = useRef<string | null>(null);

  useEffect(() => {
    setBasePayload(payload);
    setVisiblePayload(payload);
    setDraftOverrides({});
    setControlsLoading(!payload.what_if);
    setRecomputing(false);
    setRecomputeError(null);
    setSelectedTrace(null);
    setLoadedScenarioId(null);
    setCompareScenarioIds([]);
  }, [payload]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const nextSavedScenarios = parseSavedScenarios(window.localStorage.getItem(storageKeyForTicker(ticker)));
    persistedSavedScenarioSnapshotRef.current = JSON.stringify(nextSavedScenarios);
    setSavedScenarios(nextSavedScenarios);
    setSavedScenarioPersistenceMessage(null);
    setLoadedSavedScenarioTicker(ticker);
  }, [ticker]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (loadedSavedScenarioTicker !== ticker) {
      return;
    }

    const savedScenarioSnapshot = JSON.stringify(savedScenarios);
    if (savedScenarioSnapshot === persistedSavedScenarioSnapshotRef.current) {
      return;
    }

    const persistenceResult = persistSavedScenariosForTicker(ticker, savedScenarios);
    if (persistenceResult.status === "ok") {
      persistedSavedScenarioSnapshotRef.current = savedScenarioSnapshot;
      setSavedScenarioPersistenceMessage(null);
      return;
    }

    if (persistenceResult.status === "trimmed") {
      persistedSavedScenarioSnapshotRef.current = JSON.stringify(savedScenarios.slice(0, persistenceResult.persistedCount));
      const plural = persistenceResult.persistedCount === 1 ? "" : "s";
      setSavedScenarioPersistenceMessage(
        `Browser storage is full. Projection Studio kept this tab live, but only the newest ${persistenceResult.persistedCount.toLocaleString()} saved scenario${plural} will persist on this device.`
      );
      return;
    }

    persistedSavedScenarioSnapshotRef.current = null;
    setSavedScenarioPersistenceMessage(
      "Browser storage is full. Projection Studio will keep scenario changes in this tab, but saved scenarios cannot persist on this device."
    );
  }, [loadedSavedScenarioTicker, savedScenarios, ticker]);

  useEffect(() => {
    return () => {
      recomputeAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (payload.what_if) {
      setControlsLoading(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setControlsLoading(true);

    void getCompanyChartsWhatIf(ticker, { overrides: {} }, { asOf: requestedAsOf, signal: controller.signal })
      .then((response) => {
        if (cancelled) {
          return;
        }
        startTransition(() => {
          setBasePayload(response);
          setVisiblePayload(response);
        });
      })
      .catch((error) => {
        if (!cancelled && !isAbortError(error)) {
          setRecomputeError(asErrorMessage(error, "Unable to load what-if controls"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setControlsLoading(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [controlsRetryTick, payload, requestedAsOf, ticker]);

  const baseStudio = basePayload.projection_studio ?? studio;
  const visibleStudio = visiblePayload.projection_studio ?? studio;
  const baseWhatIf = basePayload.what_if;
  const visibleWhatIf = visiblePayload.what_if;
  const baseControls = baseWhatIf?.driver_control_metadata ?? EMPTY_DRIVER_CONTROLS;
  const baseControlMap = useMemo(() => new Map(baseControls.map((control) => [control.key, control])), [baseControls]);
  const appliedOverrides = useMemo(
    () => new Map((visibleWhatIf?.overrides_applied ?? []).map((override) => [override.key, override])),
    [visibleWhatIf?.overrides_applied]
  );
  const clippedOverrides = useMemo(() => new Set((visibleWhatIf?.overrides_clipped ?? []).map((override) => override.key)), [visibleWhatIf?.overrides_clipped]);
  const overrideSignature = useMemo(() => JSON.stringify(draftOverrides), [draftOverrides]);
  const activeOverrideCount = Object.keys(draftOverrides).length;

  useEffect(() => {
    if (!baseControls.length) {
      return;
    }

    if (!activeOverrideCount) {
      recomputeAbortRef.current?.abort();
      setRecomputeError(null);
      setRecomputing(false);
      startTransition(() => {
        setVisiblePayload(basePayload);
      });
      return;
    }

    const controller = new AbortController();
    recomputeAbortRef.current?.abort();
    recomputeAbortRef.current = controller;
    setRecomputing(true);
    setRecomputeError(null);

    const timeoutId = window.setTimeout(() => {
      void getCompanyChartsWhatIf(ticker, { overrides: draftOverrides }, { asOf: requestedAsOf, signal: controller.signal })
        .then((response) => {
          if (controller.signal.aborted) {
            return;
          }
          startTransition(() => {
            setVisiblePayload(response);
            setSelectedTrace(null);
          });
        })
        .catch((error) => {
          if (!controller.signal.aborted && !isAbortError(error)) {
            setRecomputeError(asErrorMessage(error, "Unable to recompute the what-if scenario"));
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setRecomputing(false);
          }
        });
    }, WHAT_IF_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
      if (recomputeAbortRef.current === controller) {
        recomputeAbortRef.current = null;
      }
    };
  }, [activeOverrideCount, baseControls.length, basePayload, draftOverrides, overrideSignature, recomputeRetryTick, requestedAsOf, ticker]);

  const scheduleSections = useMemo(() => visibleStudio.schedule_sections.map((section) => withCheckRows(section)), [visibleStudio.schedule_sections]);
  const baselineScheduleSections = useMemo(() => baseStudio.schedule_sections.map((section) => withCheckRows(section)), [baseStudio.schedule_sections]);
  const baselineSectionsByKey = useMemo(() => new Map(baselineScheduleSections.map((section) => [section.key, section])), [baselineScheduleSections]);
  const driverGroups = useMemo(() => groupDrivers(visibleStudio.drivers_used), [visibleStudio.drivers_used]);
  const sensitivityGrid = useMemo(() => buildSensitivityGrid(visibleStudio.sensitivity_matrix), [visibleStudio.sensitivity_matrix]);

  const allYears = useMemo(() => {
    const years = new Set<number>();
    scheduleSections.forEach((section) => {
      section.rows.forEach((row) => {
        Object.keys(row.reported_values).forEach((year) => years.add(Number(year)));
        Object.keys(row.projected_values).forEach((year) => years.add(Number(year)));
      });
    });
    return Array.from(years).sort((left, right) => left - right);
  }, [scheduleSections]);

  const reportedYears = useMemo(
    () => allYears.filter((year) => scheduleSections.some((section) => section.rows.some((row) => row.reported_values[year] != null))),
    [allYears, scheduleSections]
  );
  const projectedYears = useMemo(() => allYears.filter((year) => !reportedYears.includes(year)), [allYears, reportedYears]);
  const firstProjectedYear = projectedYears[0] ?? null;
  const bridgeCards = useMemo(() => buildBridgeCards(scheduleSections, projectedYears[0] ?? null), [projectedYears, scheduleSections]);
  const scenarioImpactMetrics = visibleWhatIf?.impact_summary?.metrics ?? EMPTY_WHAT_IF_IMPACT_METRICS;
  const comparedScenarios = useMemo(
    () => compareScenarioIds.map((id) => savedScenarios.find((scenario) => scenario.id === id) ?? null).filter((scenario): scenario is SavedStudioScenario => scenario !== null),
    [compareScenarioIds, savedScenarios]
  );

  const loadedScenario = useMemo(
    () => (loadedScenarioId ? savedScenarios.find((scenario) => scenario.id === loadedScenarioId) ?? null : null),
    [loadedScenarioId, savedScenarios]
  );

  const forecastHandoffPayload = useMemo<ForecastHandoffPayload | null>(() => {
    const metrics = buildForecastHandoffMetrics(baseStudio, visibleStudio, firstProjectedYear);
    if (!metrics.length) {
      return null;
    }

    return {
      version: 1,
      ticker,
      asOf: requestedAsOf,
      forecastYear: firstProjectedYear,
      source: activeOverrideCount > 0 ? "user_scenario" : "sec_base_forecast",
      scenarioName: loadedScenario?.name ?? null,
      overrideCount: activeOverrideCount,
      metrics,
      createdAt: new Date().toISOString(),
    };
  }, [activeOverrideCount, baseStudio, firstProjectedYear, loadedScenario?.name, requestedAsOf, ticker, visibleStudio]);

  const valuationImpactHref = useMemo(() => {
    const baseHref = `/company/${encodeURIComponent(ticker)}/models`;
    if (!forecastHandoffPayload) {
      return baseHref;
    }

    return `${baseHref}?${FORECAST_HANDOFF_QUERY_PARAM}=${encodeForecastHandoffPayload(forecastHandoffPayload)}`;
  }, [forecastHandoffPayload, ticker]);
  const sourceState = useMemo(
    () => resolveProjectionForecastSourceState(visiblePayload, activeOverrideCount),
    [activeOverrideCount, visiblePayload]
  );

  const exportRows = useMemo(
    () => buildExportRows(scheduleSections, driverGroups, visibleStudio.scenarios_comparison, visibleStudio.sensitivity_matrix, scenarioImpactMetrics, comparedScenarios, sourceState, forecastAccuracy.data),
    [comparedScenarios, driverGroups, forecastAccuracy.data, scenarioImpactMetrics, scheduleSections, sourceState, visibleStudio.scenarios_comparison, visibleStudio.sensitivity_matrix]
  );

  function handleExportCsv() {
    exportRowsToCsv(`${normalizeExportFileStem(`${ticker}-projection-studio`, "projection-studio")}.csv`, exportRows);
  }

  function handleControlChange(key: string, rawValue: number) {
    const control = baseControlMap.get(key);
    if (!control || Number.isNaN(rawValue)) {
      return;
    }

    const clampedValue = clampValue(rawValue, control);
    setLoadedScenarioId(null);
    setDraftOverrides((current) => {
      if (nearlyEqual(clampedValue, control.baseline_value)) {
        if (!(key in current)) {
          return current;
        }
        const next = { ...current };
        delete next[key];
        return next;
      }
      return {
        ...current,
        [key]: clampedValue,
      };
    });
  }

  function handleResetAll() {
    setDraftOverrides({});
    setRecomputeError(null);
    setRecomputing(false);
    recomputeAbortRef.current?.abort();
    startTransition(() => {
      setVisiblePayload(basePayload);
      setSelectedTrace(null);
    });
    setLoadedScenarioId(null);
  }

  function handleRetry() {
    if (!baseControls.length) {
      setControlsRetryTick((current) => current + 1);
      return;
    }
    setRecomputeRetryTick((current) => current + 1);
  }

  function handleSaveScenario() {
    const suggestedName = loadedScenario?.name ?? `Scenario ${savedScenarios.length + 1}`;
    const inputName = normalizeScenarioName(window.prompt("Name this scenario", suggestedName));
    if (!inputName) {
      return;
    }

    const nextScenario: SavedStudioScenario = {
      version: 1,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: inputName,
      createdAt: new Date().toISOString(),
      overrideCount: activeOverrideCount,
      source: activeOverrideCount > 0 ? "user_scenario" : "sec_base_forecast",
      overrides: { ...draftOverrides },
      metrics: collectScenarioMetrics(visibleStudio, firstProjectedYear),
    };

    setSavedScenarios((current) => [nextScenario, ...current]);
    setLoadedScenarioId(nextScenario.id);
  }

  function handleLoadScenario(scenario: SavedStudioScenario) {
    setDraftOverrides({ ...scenario.overrides });
    setLoadedScenarioId(scenario.id);
  }

  function handleDeleteScenario(id: string) {
    setSavedScenarios((current) => current.filter((scenario) => scenario.id !== id));
    setCompareScenarioIds((current) => current.filter((scenarioId) => scenarioId !== id));
    setLoadedScenarioId((current) => (current === id ? null : current));
  }

  function handleToggleCompare(id: string) {
    setCompareScenarioIds((current) => {
      if (current.includes(id)) {
        return current.filter((scenarioId) => scenarioId !== id);
      }
      if (current.length >= MAX_COMPARE_SCENARIOS) {
        return [...current.slice(1), id];
      }
      return [...current, id];
    });
  }

  const compareRows =
    comparedScenarios.length === MAX_COMPARE_SCENARIOS
      ? buildComparedScenarioRows(comparedScenarios[0], comparedScenarios[1])
      : [];

  return (
    <div className="charts-page-shell">
      <header className="charts-page-hero">
        <div className="charts-page-hero-copy">
          <div className="charts-page-kicker-row">
            <span className="charts-page-chip">Charts</span>
            <span className="charts-page-chip charts-page-chip-subtle">Projection Studio</span>
          </div>
          <ChartsModeSwitch activeMode="studio" studioEnabled />
          <h1 className="charts-page-title">{payload.company?.name ?? "Projection Studio"}</h1>
          <div className="charts-page-meta-row">
            <span className="charts-page-meta-pill">{ticker}</span>
            {payload.company?.market_sector ? <span className="charts-page-meta-pill">{payload.company.market_sector}</span> : null}
            {payload.forecast_methodology.confidence_label ? <span className="charts-page-meta-pill">{payload.forecast_methodology.confidence_label}</span> : null}
          </div>
          <ForecastTrustCue
            sourceState={sourceState}
            accuracy={forecastAccuracy.data}
            loading={forecastAccuracy.loading}
            error={forecastAccuracy.error}
          />
          <p className="charts-page-hero-thesis">Inspection of projected values, sensitivities, waterfall bridges, and traceable formulas.</p>
        </div>
        <div className="studio-hero-actions">
          <button type="button" className="studio-primary-button" onClick={handleExportCsv}>
            Export Studio CSV
          </button>
          <button type="button" className="studio-secondary-button" onClick={handleSaveScenario}>
            Save Scenario
          </button>
          <button type="button" className="studio-secondary-button" onClick={() => setSidebarOpen((current) => !current)} aria-controls="studio-what-if-sidebar">
            {sidebarOpen ? "Hide What-If Sidebar" : "Show What-If Sidebar"}
          </button>
          <Link href={valuationImpactHref} className="studio-secondary-link">
            See Valuation Impact
          </Link>
        </div>
      </header>

      <div className={`studio-layout-shell ${sidebarOpen ? "has-sidebar" : "is-sidebar-collapsed"}`}>
        <div className="studio-layout-main">
          <ImpactSummaryStrip payload={visiblePayload} activeOverrideCount={activeOverrideCount} />

          <div className="workspace-card-stack workspace-card-stack-tight" data-testid="projection-studio-track-record-section">
            <div className="workspace-pill-row">
              <SourceStateBadge state={sourceState} compact={false} />
            </div>
            <ForecastTrackRecord data={forecastAccuracy.data} loading={forecastAccuracy.loading} error={forecastAccuracy.error} />
          </div>

          <section className="studio-panel" aria-label="Saved scenarios">
            <div className="studio-panel-header">
              <div>
                <h2 className="studio-panel-title">Scenario Library</h2>
                <p className="studio-panel-subtitle">Saved locally in this browser. Compare up to two scenarios with simple deltas.</p>
              </div>
            </div>

            {savedScenarioPersistenceMessage ? (
              <div className="studio-what-if-error" role="alert">
                <div>{savedScenarioPersistenceMessage}</div>
              </div>
            ) : null}

            {!savedScenarios.length ? <div className="studio-what-if-state">No saved scenarios yet. Save the current forecast setup to reuse it later.</div> : null}

            {savedScenarios.length ? (
              <div className="studio-scenario-library">
                {savedScenarios.map((scenario) => (
                  <article key={scenario.id} className={`studio-driver-card studio-scenario-card ${loadedScenarioId === scenario.id ? "is-active" : ""}`}>
                    <div className="studio-driver-topline">
                      <div>
                        <div className="studio-driver-title">{scenario.name}</div>
                        <div className="studio-driver-detail">Saved {formatScenarioTimestamp(scenario.createdAt)}</div>
                      </div>
                      <span className="studio-marker-chip is-default">{scenario.overrideCount} overrides</span>
                    </div>
                    <div className="studio-scenario-meta-row">
                      <SourceStateBadge state={resolveSavedScenarioSourceState(scenario.source)} />
                      <label className="studio-scenario-compare-toggle">
                        <input
                          type="checkbox"
                          checked={compareScenarioIds.includes(scenario.id)}
                          onChange={() => handleToggleCompare(scenario.id)}
                        />
                        Compare
                      </label>
                    </div>
                    <div className="studio-scenario-action-row">
                      <button type="button" className="studio-secondary-button" onClick={() => handleLoadScenario(scenario)}>
                        Load
                      </button>
                      <button type="button" className="studio-secondary-button" onClick={() => handleDeleteScenario(scenario.id)}>
                        Delete
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}

            {compareRows.length ? (
              <div className="studio-table-wrapper">
                <table className="studio-scenarios-table" data-testid="studio-scenario-compare-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>{comparedScenarios[0].name}</th>
                      <th>{comparedScenarios[1].name}</th>
                      <th>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {compareRows.map((row) => (
                      <tr key={String(row.metric_key)}>
                        <td>{String(row.metric_label)}</td>
                        <td>{formatValue(typeof row.left_value === "number" ? row.left_value : null, String(row.unit ?? "usd"))}</td>
                        <td>{formatValue(typeof row.right_value === "number" ? row.right_value : null, String(row.unit ?? "usd"))}</td>
                        <td>{typeof row.delta === "number" ? formatSignedDelta(row.delta, String(row.unit ?? "usd")) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>

          <section className="studio-panel" aria-label="Key drivers">
            <div className="studio-panel-header">
              <div>
                <h2 className="studio-panel-title">Key Drivers</h2>
                <p className="studio-panel-subtitle">Grouped assumption cards with source periods and fallback markers.</p>
              </div>
            </div>
            <div className="studio-driver-groups">
              {driverGroups.map((group) => (
                <div key={group.key} className="studio-driver-group">
                  <div className="studio-driver-group-title">{group.title}</div>
                  <div className="studio-driver-group-grid">
                    {group.drivers.map((driver) => (
                      <article key={driver.key} className="studio-driver-card">
                        <div className="studio-driver-topline">
                          <div className="studio-driver-title">{driver.title}</div>
                          <div className="studio-driver-value">{driver.value}</div>
                        </div>
                        {driver.detail ? <div className="studio-driver-detail">{driver.detail}</div> : null}
                        {driver.source_periods.length ? <div className="studio-driver-periods">Source periods: {driver.source_periods.join(" · ")}</div> : null}
                        <div className="studio-driver-marker-row">
                          {driver.default_markers.map((marker) => (
                            <span key={`${driver.key}-default-${marker}`} className="studio-marker-chip is-default">
                              Default: {marker}
                            </span>
                          ))}
                          {driver.fallback_markers.map((marker) => (
                            <span key={`${driver.key}-fallback-${marker}`} className="studio-marker-chip is-fallback">
                              Fallback: {marker}
                            </span>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="studio-analytics-grid">
            <SensitivityMatrix grid={sensitivityGrid} />

            <section className="studio-panel" aria-label="Scenarios comparison">
              <div className="studio-panel-header">
                <div>
                  <h2 className="studio-panel-title">Scenarios Comparison</h2>
                  <p className="studio-panel-subtitle">Base, bull, and bear outputs from the backend projection payload.</p>
                </div>
              </div>
              <div className="studio-table-wrapper">
                <table className="studio-scenarios-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Base</th>
                      <th>Bull</th>
                      <th>Bear</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleStudio.scenarios_comparison.map((row) => (
                      <tr key={row.key}>
                        <td>
                          <div className="studio-row-label">{row.label}</div>
                        </td>
                        <td>{formatValue(row.scenario_values.base, row.unit)}</td>
                        <td>{formatValue(row.scenario_values.bull, row.unit)}</td>
                        <td>{formatValue(row.scenario_values.bear, row.unit)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </section>

          {bridgeCards.length ? (
            <section className="studio-bridge-grid" aria-label="Bridge charts">
              {bridgeCards.map((card) => (
                <BridgeChartCard key={card.key} card={card} onInspect={setSelectedTrace} />
              ))}
            </section>
          ) : null}

          <section className="studio-schedule-stack" aria-label="Projection studio schedules">
            {scheduleSections.map((section) => (
              <ScheduleTable
                key={section.key}
                section={section}
                baselineSection={baselineSectionsByKey.get(section.key) ?? null}
                reportedYears={reportedYears}
                projectedYears={projectedYears}
                hasScenarioOverrides={activeOverrideCount > 0}
                onCellClick={setSelectedTrace}
              />
            ))}
          </section>
        </div>

        <WhatIfSidebar
          controls={baseControls}
          draftOverrides={draftOverrides}
          appliedOverrides={appliedOverrides}
          clippedOverrides={clippedOverrides}
          isOpen={sidebarOpen}
          controlsLoading={controlsLoading}
          recomputing={recomputing}
          error={recomputeError}
          onToggle={() => setSidebarOpen((current) => !current)}
          onResetAll={handleResetAll}
          onRetry={handleRetry}
          onControlChange={handleControlChange}
        />
      </div>

      <FormulaTracePopover trace={selectedTrace} isOpen={Boolean(selectedTrace)} onClose={() => setSelectedTrace(null)} />
    </div>
  );
}
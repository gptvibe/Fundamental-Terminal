"use client";

import Link from "next/link";
import { startTransition, useEffect, useMemo, useRef, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartsModeSwitch } from "@/components/company/charts-mode-switch";
import { ChartShareActions } from "@/components/company/chart-share-actions";
import { ForecastTrackRecord } from "@/components/charts/forecast-track-record";
import { ForecastTrustCue } from "@/components/ui/forecast-trust-cue";
import { SourceStateBadge } from "@/components/ui/source-state-badge";
import { useForecastAccuracy } from "@/hooks/use-forecast-accuracy";
import { buildChartsSourcePath, buildStudioChartShareSnapshot } from "@/lib/chart-share";
import { getCompanyChartsStudioSpec } from "@/lib/chart-spec";
import {
  cloneCompanyChartsScenario,
  createCompanyChartsScenario,
  getCompanyChartsScenario,
  getCompanyChartsWhatIf,
  listCompanyChartsScenarios,
  updateCompanyChartsScenario,
} from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { copyTextToClipboard, exportRowsToCsv, type ExportRow, normalizeExportFileStem } from "@/lib/export";
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
  CompanyChartsScenarioPayload,
  CompanyChartsScenarioUpsertRequest,
  CompanyChartsScenarioViewerPayload,
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
  requestedScenarioId?: string | null;
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

interface ScenarioDecompositionContribution {
  kind: "assumption" | "intermediate";
  key: string;
  label: string;
  unit: string;
  leftValue: number | null;
  rightValue: number | null;
  deltaValue: number | null;
  contributionValue: number | null;
  sourceNote: string | null;
}

interface ScenarioOutputDecomposition {
  metricKey: string;
  metricLabel: string;
  unit: string;
  leftValue: number | null;
  rightValue: number | null;
  deltaValue: number | null;
  contributions: ScenarioDecompositionContribution[];
}

interface ScenarioDiffSummary {
  leftScenarioName: string;
  rightScenarioName: string;
  forecastYear: number | null;
  assumptionContributions: ScenarioDecompositionContribution[];
  intermediateContributions: ScenarioDecompositionContribution[];
  outputDecompositions: ScenarioOutputDecomposition[];
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
const OUTPUT_DECOMPOSITION_METRICS = [
  { key: "eps", label: "EPS", unit: "usd_per_share" },
  { key: "revenue", label: "Revenue", unit: "usd" },
  { key: "free_cash_flow", label: "Free Cash Flow", unit: "usd" },
  { key: "operating_income", label: "Operating Income", unit: "usd" },
  { key: "net_income", label: "Net Income", unit: "usd" },
] as const;
const INTERMEDIATE_LINE_ITEM_KEYS = [
  "revenue",
  "operating_income",
  "net_income",
  "operating_cash_flow",
  "capex",
  "free_cash_flow",
  "eps",
] as const;
const INTERMEDIATE_LINE_ITEM_LABELS: Record<string, string> = {
  revenue: "Revenue",
  operating_income: "Operating Income",
  net_income: "Net Income",
  operating_cash_flow: "Operating Cash Flow",
  capex: "Capex",
  free_cash_flow: "Free Cash Flow",
  eps: "EPS",
};

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
  updatedAt: string | null;
  overrideCount: number;
  source: "sec_base_forecast" | "user_scenario";
  visibility: "public" | "private";
  storage: "local" | "remote";
  overrides: Record<string, number>;
  metrics: SavedStudioScenarioMetric[];
  sharePath: string | null;
  editable: boolean;
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
  compareDiffSummary: ScenarioDiffSummary | null,
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

  const decompositionRows: ExportRow[] = compareDiffSummary
    ? [
        {
          record_type: "scenario_decomposition_meta",
          left_scenario: compareDiffSummary.leftScenarioName,
          right_scenario: compareDiffSummary.rightScenarioName,
          forecast_year: compareDiffSummary.forecastYear ?? "",
        },
        ...compareDiffSummary.outputDecompositions.map((output) => ({
          record_type: "scenario_decomposition_output",
          metric_key: output.metricKey,
          metric_label: output.metricLabel,
          unit: output.unit,
          left_value: output.leftValue ?? "",
          right_value: output.rightValue ?? "",
          delta_value: output.deltaValue ?? "",
        })),
        ...compareDiffSummary.outputDecompositions.flatMap((output) =>
          output.contributions.map((contribution) => ({
            record_type: "scenario_decomposition_contribution",
            output_metric_key: output.metricKey,
            output_metric_label: output.metricLabel,
            contribution_kind: contribution.kind,
            contribution_key: contribution.key,
            contribution_label: contribution.label,
            contribution_unit: contribution.unit,
            left_value: contribution.leftValue ?? "",
            right_value: contribution.rightValue ?? "",
            delta_value: contribution.deltaValue ?? "",
            contribution_value: contribution.contributionValue ?? "",
            source_note: contribution.sourceNote ?? "",
          }))
        ),
      ]
    : [];

  return [...metadataRows, ...scheduleRows, ...driverRows, ...scenarioRows, ...sensitivityRows, ...impactRows, ...comparedScenarioRows, ...decompositionRows];
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

function extractNumericSuffix(value: string): number | null {
  const match = value.match(/-?\d+(?:\.\d+)?$/);
  if (!match) {
    return null;
  }
  const parsed = Number(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function inferInputUnit(input: CompanyChartsFormulaInputPayload): string {
  const text = `${input.formatted_value} ${input.label}`.toLowerCase();
  if (input.formatted_value.includes("%") || text.includes("growth") || text.includes("margin") || text.includes("rate")) {
    return "percent";
  }
  if (input.formatted_value.toLowerCase().includes("d") || text.includes("days") || text.includes("dso") || text.includes("dio") || text.includes("dpo")) {
    return "days";
  }
  if (input.formatted_value.includes("$") && text.includes("share")) {
    return "usd_per_share";
  }
  if (input.formatted_value.includes("$") || text.includes("revenue") || text.includes("income") || text.includes("cash")) {
    return "usd";
  }
  return "count";
}

function normalizeInputValue(input: CompanyChartsFormulaInputPayload | undefined): number | null {
  if (!input) {
    return null;
  }
  if (typeof input.value === "number" && Number.isFinite(input.value)) {
    return input.value;
  }
  return extractNumericSuffix(input.formatted_value);
}

function humanizeKey(value: string): string {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function firstProjectedYearFromStudio(studioPayload: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>): number | null {
  const years = new Set<number>();
  studioPayload.schedule_sections.forEach((section) => {
    section.rows.forEach((row) => {
      Object.keys(row.projected_values).forEach((year) => {
        years.add(Number(year));
      });
    });
  });
  const sorted = Array.from(years).sort((left, right) => left - right);
  return sorted[0] ?? null;
}

function readProjectedRowValue(
  studioPayload: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>,
  rowKey: string,
  year: number
): { value: number | null; unit: string; label: string; trace: CompanyChartsFormulaTracePayload | null } {
  const row = findRowByKey(studioPayload.schedule_sections, rowKey);
  if (!row) {
    return { value: null, unit: "count", label: humanizeKey(rowKey), trace: null };
  }
  const rawValue = row.projected_values[year];
  return {
    value: typeof rawValue === "number" && Number.isFinite(rawValue) ? rawValue : null,
    unit: row.unit,
    label: row.label,
    trace: row.formula_traces[year] ?? null,
  };
}

function topByMagnitude<T>(values: T[], readMagnitude: (value: T) => number, limit: number): T[] {
  return [...values].sort((left, right) => readMagnitude(right) - readMagnitude(left)).slice(0, limit);
}

function buildAssumptionDiffContributions(left: SavedStudioScenario, right: SavedStudioScenario): ScenarioDecompositionContribution[] {
  const keys = Array.from(new Set([...Object.keys(left.overrides), ...Object.keys(right.overrides)]));
  return topByMagnitude(
    keys
      .map((key): ScenarioDecompositionContribution | null => {
        const leftValue = key in left.overrides ? left.overrides[key] : null;
        const rightValue = key in right.overrides ? right.overrides[key] : null;
        if (leftValue == null || rightValue == null) {
          return null;
        }
        const deltaValue = rightValue - leftValue;
        if (Math.abs(deltaValue) <= 1e-9) {
          return null;
        }
        return {
          kind: "assumption",
          key,
          label: humanizeKey(key),
          unit: key.includes("growth") || key.includes("margin") ? "percent" : key.includes("day") || key.includes("dso") ? "days" : "count",
          leftValue,
          rightValue,
          deltaValue,
          contributionValue: null,
          sourceNote: "Scenario override",
        };
      })
      .filter((entry): entry is ScenarioDecompositionContribution => entry !== null),
    (entry) => Math.abs(entry.deltaValue ?? 0),
    8
  );
}

function buildTraceInputContributions(
  leftTrace: CompanyChartsFormulaTracePayload | null,
  rightTrace: CompanyChartsFormulaTracePayload | null,
  outputDelta: number | null
): ScenarioDecompositionContribution[] {
  if (!leftTrace || !rightTrace) {
    return [];
  }

  const leftByKey = new Map(leftTrace.inputs.map((input) => [input.key, input]));
  const rightByKey = new Map(rightTrace.inputs.map((input) => [input.key, input]));
  const keys = Array.from(new Set([...leftByKey.keys(), ...rightByKey.keys()]));

  const rawContributions = keys
    .map((key): ScenarioDecompositionContribution | null => {
      const leftInput = leftByKey.get(key);
      const rightInput = rightByKey.get(key);
      const leftValue = normalizeInputValue(leftInput);
      const rightValue = normalizeInputValue(rightInput);
      if (leftValue == null || rightValue == null) {
        return null;
      }
      const deltaValue = rightValue - leftValue;
      if (Math.abs(deltaValue) <= 1e-9) {
        return null;
      }

      return {
        kind: "assumption",
        key,
        label: rightInput?.label ?? leftInput?.label ?? humanizeKey(key),
        unit: inferInputUnit(
          rightInput ??
            leftInput ?? {
              key,
              label: humanizeKey(key),
              value: null,
              formatted_value: "",
              source_detail: "",
              source_kind: "derived",
              is_override: false,
              original_value: null,
              original_source: null,
            }
        ),
        leftValue,
        rightValue,
        deltaValue,
        contributionValue: null,
        sourceNote: rightInput?.source_detail ?? leftInput?.source_detail ?? null,
      };
    })
    .filter((entry): entry is ScenarioDecompositionContribution => entry !== null);

  const denominator = rawContributions.reduce((sum, entry) => sum + Math.abs(entry.deltaValue ?? 0), 0);
  return topByMagnitude(
    rawContributions.map((entry) => ({
      ...entry,
      contributionValue:
        denominator > 0 && outputDelta != null
          ? outputDelta * (Math.abs(entry.deltaValue ?? 0) / denominator) * ((entry.deltaValue ?? 0) >= 0 ? 1 : -1)
          : null,
    })),
    (entry) => Math.abs(entry.contributionValue ?? entry.deltaValue ?? 0),
    6
  );
}

function buildIntermediateLineItemContributions(
  leftStudio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>,
  rightStudio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>,
  year: number
): ScenarioDecompositionContribution[] {
  return topByMagnitude(
    INTERMEDIATE_LINE_ITEM_KEYS
      .map((rowKey): ScenarioDecompositionContribution | null => {
        const left = readProjectedRowValue(leftStudio, rowKey, year);
        const right = readProjectedRowValue(rightStudio, rowKey, year);
        if (left.value == null || right.value == null) {
          return null;
        }
        const deltaValue = right.value - left.value;
        if (Math.abs(deltaValue) <= 1e-9) {
          return null;
        }
        return {
          kind: "intermediate",
          key: rowKey,
          label: right.label || left.label || INTERMEDIATE_LINE_ITEM_LABELS[rowKey] || humanizeKey(rowKey),
          unit: right.unit || left.unit || "count",
          leftValue: left.value,
          rightValue: right.value,
          deltaValue,
          contributionValue: deltaValue,
          sourceNote: "Projected line item",
        };
      })
      .filter((entry): entry is ScenarioDecompositionContribution => entry !== null),
    (entry) => Math.abs(entry.deltaValue ?? 0),
    8
  );
}

function buildScenarioDiffSummary(
  leftScenario: SavedStudioScenario,
  rightScenario: SavedStudioScenario,
  leftPayload: CompanyChartsDashboardResponse,
  rightPayload: CompanyChartsDashboardResponse
): ScenarioDiffSummary | null {
  const leftStudio = getCompanyChartsStudioSpec(leftPayload)?.projection_studio ?? leftPayload.projection_studio;
  const rightStudio = getCompanyChartsStudioSpec(rightPayload)?.projection_studio ?? rightPayload.projection_studio;
  if (!leftStudio || !rightStudio) {
    return null;
  }

  const forecastYear = firstProjectedYearFromStudio(rightStudio) ?? firstProjectedYearFromStudio(leftStudio);
  if (forecastYear == null) {
    return null;
  }

  const assumptionContributions = buildAssumptionDiffContributions(leftScenario, rightScenario);
  const intermediateContributions = buildIntermediateLineItemContributions(leftStudio, rightStudio, forecastYear);

  const outputDecompositions: ScenarioOutputDecomposition[] = OUTPUT_DECOMPOSITION_METRICS.map((metric) => {
    const left = readProjectedRowValue(leftStudio, metric.key, forecastYear);
    const right = readProjectedRowValue(rightStudio, metric.key, forecastYear);
    const deltaValue =
      left.value != null && right.value != null
        ? right.value - left.value
        : null;

    const traceContributions = buildTraceInputContributions(left.trace, right.trace, deltaValue);
    const outputSpecificIntermediates = intermediateContributions.filter((entry) => entry.key !== metric.key).slice(0, 4);

    return {
      metricKey: metric.key,
      metricLabel: metric.label,
      unit: right.unit || left.unit || metric.unit,
      leftValue: left.value,
      rightValue: right.value,
      deltaValue,
      contributions: [...traceContributions, ...outputSpecificIntermediates],
    };
  });

  return {
    leftScenarioName: leftScenario.name,
    rightScenarioName: rightScenario.name,
    forecastYear,
    assumptionContributions,
    intermediateContributions,
    outputDecompositions,
  };
}

function buildScenarioDiffShareSummary(summary: ScenarioDiffSummary): string {
  const lines: string[] = [];
  lines.push(`Why did this change? ${summary.leftScenarioName} -> ${summary.rightScenarioName}`);
  lines.push(`Forecast year: ${summary.forecastYear ?? "n/a"}`);

  summary.outputDecompositions.slice(0, 4).forEach((output) => {
    lines.push(
      `${output.metricLabel}: ${formatValue(output.leftValue, output.unit)} -> ${formatValue(output.rightValue, output.unit)} (${output.deltaValue == null ? "—" : formatSignedDelta(output.deltaValue, output.unit)})`
    );
  });

  lines.push("Top assumption shifts:");
  summary.assumptionContributions.slice(0, 3).forEach((entry) => {
    lines.push(
      `- ${entry.label}: ${formatValue(entry.leftValue, entry.unit)} -> ${formatValue(entry.rightValue, entry.unit)} (${entry.deltaValue == null ? "—" : formatSignedDelta(entry.deltaValue, entry.unit)})`
    );
  });

  lines.push("Top intermediate deltas:");
  summary.intermediateContributions.slice(0, 3).forEach((entry) => {
    lines.push(`- ${entry.label}: ${entry.deltaValue == null ? "—" : formatSignedDelta(entry.deltaValue, entry.unit)}`);
  });

  return lines.join("\n");
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
  const localOnlyScenarios = savedScenarios.filter((scenario) => scenario.storage === "local");

  if (tryPersistSavedScenarios(storageKey, localOnlyScenarios)) {
    return {
      status: "ok",
      persistedCount: localOnlyScenarios.length,
    };
  }

  for (let keepCount = localOnlyScenarios.length - 1; keepCount >= 1; keepCount -= 1) {
    if (tryPersistSavedScenarios(storageKey, localOnlyScenarios.slice(0, keepCount))) {
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
          updatedAt: typeof candidate.updatedAt === "string" ? candidate.updatedAt : null,
          overrideCount: typeof candidate.overrideCount === "number" && Number.isFinite(candidate.overrideCount) ? candidate.overrideCount : Object.keys(normalizedOverrides).length,
          source: candidate.source === "user_scenario" ? "user_scenario" : "sec_base_forecast",
          visibility: candidate.visibility === "public" ? "public" : "private",
          storage: "local",
          overrides: normalizedOverrides,
          metrics,
          sharePath: typeof candidate.sharePath === "string" ? candidate.sharePath : null,
          editable: true,
        };
      })
      .filter((entry): entry is SavedStudioScenario => entry !== null)
      .sort((left, right) => new Date(right.updatedAt ?? right.createdAt).getTime() - new Date(left.updatedAt ?? left.createdAt).getTime());
  } catch {
    return [];
  }
}

function mapRemoteScenario(candidate: CompanyChartsScenarioPayload): SavedStudioScenario {
  return {
    version: 1,
    id: candidate.id,
    name: candidate.name,
    createdAt: candidate.created_at ?? new Date().toISOString(),
    updatedAt: candidate.updated_at,
    overrideCount: candidate.override_count,
    source: candidate.source,
    visibility: candidate.visibility,
    storage: "remote",
    overrides: { ...candidate.overrides },
    metrics: candidate.metrics.map((metric) => ({
      key: metric.key,
      label: metric.label,
      unit: metric.unit,
      value: metric.value,
    })),
    sharePath: candidate.share_path,
    editable: candidate.editable,
  };
}

function mergeSavedScenarios(remoteScenarios: SavedStudioScenario[], localScenarios: SavedStudioScenario[]): SavedStudioScenario[] {
  const merged = new Map<string, SavedStudioScenario>();
  [...remoteScenarios, ...localScenarios].forEach((scenario) => {
    if (!merged.has(scenario.id)) {
      merged.set(scenario.id, scenario);
    }
  });
  return Array.from(merged.values()).sort(
    (left, right) => new Date(right.updatedAt ?? right.createdAt).getTime() - new Date(left.updatedAt ?? left.createdAt).getTime()
  );
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

function ScenarioDiffPanel({
  summary,
  loading,
  error,
  onCopy,
}: {
  summary: ScenarioDiffSummary | null;
  loading: boolean;
  error: string | null;
  onCopy: () => void;
}) {
  if (!loading && !error && !summary) {
    return null;
  }

  return (
    <section className="studio-panel" aria-label="Why did this change">
      <div className="studio-panel-header">
        <div>
          <h2 className="studio-panel-title">Why did this change?</h2>
          <p className="studio-panel-subtitle">Decomposition between two scenarios using changed assumptions, formula traces, and major intermediate line items.</p>
        </div>
        {summary ? (
          <button type="button" className="studio-secondary-button" onClick={onCopy}>
            Copy Summary
          </button>
        ) : null}
      </div>

      {loading ? <div className="studio-what-if-state">Building scenario decomposition...</div> : null}
      {error ? <div className="studio-what-if-error" role="alert">{error}</div> : null}

      {summary ? (
        <div className="studio-diff-shell" data-testid="studio-scenario-diff-panel">
          <div className="studio-diff-summary-card" data-testid="studio-scenario-diff-summary-card">
            <div className="studio-diff-summary-title">{summary.leftScenarioName} -&gt; {summary.rightScenarioName}</div>
            <div className="studio-diff-summary-subtitle">Forecast Year {summary.forecastYear ?? "n/a"}</div>
            <div className="studio-diff-summary-grid">
              {summary.outputDecompositions.slice(0, 4).map((output) => (
                <div key={output.metricKey} className="studio-diff-summary-metric">
                  <span>{output.metricLabel}</span>
                  <strong>{output.deltaValue == null ? "—" : formatSignedDelta(output.deltaValue, output.unit)}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="studio-diff-columns">
            <div className="studio-diff-column">
              <h3 className="studio-panel-title">Top Assumption Changes</h3>
              {!summary.assumptionContributions.length ? <div className="studio-what-if-state">No assumption deltas detected.</div> : null}
              <div className="studio-diff-list">
                {summary.assumptionContributions.slice(0, 6).map((entry) => (
                  <article key={`assumption-${entry.key}`} className="studio-driver-card studio-diff-item">
                    <div className="studio-driver-topline">
                      <div className="studio-driver-title">{entry.label}</div>
                      <div className="studio-driver-value">{entry.deltaValue == null ? "—" : formatSignedDelta(entry.deltaValue, entry.unit)}</div>
                    </div>
                    <div className="studio-driver-detail">
                      {formatValue(entry.leftValue, entry.unit)} -&gt; {formatValue(entry.rightValue, entry.unit)}
                    </div>
                  </article>
                ))}
              </div>
            </div>

            <div className="studio-diff-column">
              <h3 className="studio-panel-title">Major Intermediate Deltas</h3>
              {!summary.intermediateContributions.length ? <div className="studio-what-if-state">No intermediate line-item deltas detected.</div> : null}
              <div className="studio-diff-list">
                {summary.intermediateContributions.slice(0, 6).map((entry) => (
                  <article key={`intermediate-${entry.key}`} className="studio-driver-card studio-diff-item">
                    <div className="studio-driver-topline">
                      <div className="studio-driver-title">{entry.label}</div>
                      <div className="studio-driver-value">{entry.deltaValue == null ? "—" : formatSignedDelta(entry.deltaValue, entry.unit)}</div>
                    </div>
                    <div className="studio-driver-detail">
                      {formatValue(entry.leftValue, entry.unit)} -&gt; {formatValue(entry.rightValue, entry.unit)}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>

          <div className="studio-diff-output-grid">
            {summary.outputDecompositions.map((output) => (
              <article key={output.metricKey} className="studio-driver-card studio-diff-output-card">
                <div className="studio-driver-topline">
                  <div className="studio-driver-title">{output.metricLabel}</div>
                  <div className="studio-driver-value">{output.deltaValue == null ? "—" : formatSignedDelta(output.deltaValue, output.unit)}</div>
                </div>
                <div className="studio-driver-detail">
                  {formatValue(output.leftValue, output.unit)} -&gt; {formatValue(output.rightValue, output.unit)}
                </div>
                <div className="studio-diff-contribution-list">
                  {output.contributions.slice(0, 4).map((contribution) => (
                    <div key={`${output.metricKey}-${contribution.kind}-${contribution.key}`} className="studio-diff-contribution-row">
                      <span>{contribution.label}</span>
                      <strong>
                        {contribution.contributionValue == null
                          ? contribution.deltaValue == null
                            ? "—"
                            : formatSignedDelta(contribution.deltaValue, contribution.unit)
                          : formatSignedDelta(contribution.contributionValue, output.unit)}
                      </strong>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function ProjectionStudio({ payload, studio, requestedAsOf = null, requestedScenarioId = null }: ProjectionStudioProps) {
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
  const [localSavedScenarios, setLocalSavedScenarios] = useState<SavedStudioScenario[]>([]);
  const [remoteSavedScenarios, setRemoteSavedScenarios] = useState<SavedStudioScenario[]>([]);
  const [scenarioViewer, setScenarioViewer] = useState<CompanyChartsScenarioViewerPayload>({
    kind: "anonymous",
    signed_in: false,
    sync_enabled: false,
    can_create_private: false,
  });
  const [savedScenarioPersistenceMessage, setSavedScenarioPersistenceMessage] = useState<string | null>(null);
  const [scenarioSyncMessage, setScenarioSyncMessage] = useState<string | null>(null);
  const [loadedScenarioId, setLoadedScenarioId] = useState<string | null>(null);
  const [compareScenarioIds, setCompareScenarioIds] = useState<string[]>([]);
  const [compareDiffSummary, setCompareDiffSummary] = useState<ScenarioDiffSummary | null>(null);
  const [compareDiffLoading, setCompareDiffLoading] = useState(false);
  const [compareDiffError, setCompareDiffError] = useState<string | null>(null);
  const [loadedSavedScenarioTicker, setLoadedSavedScenarioTicker] = useState<string | null>(null);
  const recomputeAbortRef = useRef<AbortController | null>(null);
  const persistedSavedScenarioSnapshotRef = useRef<string | null>(null);
  const shareCaptureRef = useRef<HTMLDivElement | null>(null);

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
    setCompareDiffSummary(null);
    setCompareDiffLoading(false);
    setCompareDiffError(null);
  }, [payload]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const nextSavedScenarios = parseSavedScenarios(window.localStorage.getItem(storageKeyForTicker(ticker)));
    persistedSavedScenarioSnapshotRef.current = JSON.stringify(nextSavedScenarios);
    setLocalSavedScenarios(nextSavedScenarios);
    setRemoteSavedScenarios([]);
    setSavedScenarioPersistenceMessage(null);
    setScenarioSyncMessage(null);
    setLoadedSavedScenarioTicker(ticker);
  }, [ticker]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (loadedSavedScenarioTicker !== ticker) {
      return;
    }

    const savedScenarioSnapshot = JSON.stringify(localSavedScenarios);
    if (savedScenarioSnapshot === persistedSavedScenarioSnapshotRef.current) {
      return;
    }

    const persistenceResult = persistSavedScenariosForTicker(ticker, localSavedScenarios);
    if (persistenceResult.status === "ok") {
      persistedSavedScenarioSnapshotRef.current = savedScenarioSnapshot;
      setSavedScenarioPersistenceMessage(null);
      return;
    }

    if (persistenceResult.status === "trimmed") {
      persistedSavedScenarioSnapshotRef.current = JSON.stringify(localSavedScenarios.slice(0, persistenceResult.persistedCount));
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
  }, [loadedSavedScenarioTicker, localSavedScenarios, ticker]);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    void listCompanyChartsScenarios(ticker, { signal: controller.signal })
      .then((response) => {
        if (cancelled) {
          return;
        }
        setScenarioViewer(response.viewer);
        setRemoteSavedScenarios(response.scenarios.map(mapRemoteScenario));
      })
      .catch((error) => {
        if (!cancelled && !isAbortError(error)) {
          setScenarioSyncMessage(asErrorMessage(error, "Unable to sync Projection Studio scenarios right now"));
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [ticker]);

  const savedScenarios = useMemo(
    () => mergeSavedScenarios(remoteSavedScenarios, localSavedScenarios),
    [localSavedScenarios, remoteSavedScenarios]
  );

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

  const baseStudioSpec = useMemo(() => getCompanyChartsStudioSpec(basePayload), [basePayload]);
  const visibleStudioSpec = useMemo(() => getCompanyChartsStudioSpec(visiblePayload), [visiblePayload]);
  const baseStudio = baseStudioSpec?.projection_studio ?? basePayload.projection_studio ?? studio;
  const visibleStudio = visibleStudioSpec?.projection_studio ?? visiblePayload.projection_studio ?? studio;
  const baseWhatIf = baseStudioSpec?.what_if ?? basePayload.what_if;
  const visibleWhatIf = visibleStudioSpec?.what_if ?? visiblePayload.what_if;
  const loadedScenario = useMemo(
    () => (loadedScenarioId ? savedScenarios.find((scenario) => scenario.id === loadedScenarioId) ?? null : null),
    [loadedScenarioId, savedScenarios]
  );
  const shareSourcePath = useMemo(() => {
    if (loadedScenario?.storage === "remote" && loadedScenario.sharePath) {
      return loadedScenario.sharePath;
    }
    return buildChartsSourcePath(ticker, "studio");
  }, [loadedScenario?.sharePath, loadedScenario?.storage, ticker]);
  const baseControls = baseWhatIf?.driver_control_metadata ?? EMPTY_DRIVER_CONTROLS;
  const baseControlMap = useMemo(() => new Map(baseControls.map((control) => [control.key, control])), [baseControls]);
  const appliedOverrides = useMemo(
    () => new Map((visibleWhatIf?.overrides_applied ?? []).map((override) => [override.key, override])),
    [visibleWhatIf?.overrides_applied]
  );
  const clippedOverrides = useMemo(() => new Set((visibleWhatIf?.overrides_clipped ?? []).map((override) => override.key)), [visibleWhatIf?.overrides_clipped]);
  const overrideSignature = useMemo(() => JSON.stringify(draftOverrides), [draftOverrides]);
  const activeOverrideCount = Object.keys(draftOverrides).length;
  const shareSnapshot = useMemo(
    () =>
      buildStudioChartShareSnapshot(visiblePayload, {
        sourcePath: shareSourcePath,
        scenarioName: loadedScenario?.name ?? null,
        overrideCount: activeOverrideCount,
      }),
    [activeOverrideCount, loadedScenario?.name, shareSourcePath, visiblePayload]
  );

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

  useEffect(() => {
    if (comparedScenarios.length !== MAX_COMPARE_SCENARIOS) {
      setCompareDiffSummary(null);
      setCompareDiffLoading(false);
      setCompareDiffError(null);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    setCompareDiffLoading(true);
    setCompareDiffError(null);

    const [leftScenario, rightScenario] = comparedScenarios;
    void Promise.all([
      getCompanyChartsWhatIf(ticker, { overrides: leftScenario.overrides }, { asOf: requestedAsOf, signal: controller.signal }),
      getCompanyChartsWhatIf(ticker, { overrides: rightScenario.overrides }, { asOf: requestedAsOf, signal: controller.signal }),
    ])
      .then(([leftPayload, rightPayload]) => {
        if (cancelled) {
          return;
        }
        setCompareDiffSummary(buildScenarioDiffSummary(leftScenario, rightScenario, leftPayload, rightPayload));
      })
      .catch((error) => {
        if (!cancelled && !isAbortError(error)) {
          setCompareDiffError(asErrorMessage(error, "Unable to build scenario decomposition"));
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCompareDiffLoading(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [comparedScenarios, requestedAsOf, ticker]);

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
    () =>
      buildExportRows(
        scheduleSections,
        driverGroups,
        visibleStudio.scenarios_comparison,
        visibleStudio.sensitivity_matrix,
        scenarioImpactMetrics,
        comparedScenarios,
        compareDiffSummary,
        sourceState,
        forecastAccuracy.data
      ),
    [compareDiffSummary, comparedScenarios, driverGroups, forecastAccuracy.data, scenarioImpactMetrics, scheduleSections, sourceState, visibleStudio.scenarios_comparison, visibleStudio.sensitivity_matrix]
  );

  function handleExportCsv() {
    exportRowsToCsv(`${normalizeExportFileStem(`${ticker}-projection-studio`, "projection-studio")}.csv`, exportRows);
  }

  async function handleCopyCompareSummary() {
    if (!compareDiffSummary) {
      return;
    }
    await copyTextToClipboard(buildScenarioDiffShareSummary(compareDiffSummary));
    setScenarioSyncMessage("Scenario diff summary copied.");
  }

  function buildScenarioRequest(name: string, visibility: "public" | "private"): CompanyChartsScenarioUpsertRequest {
    return {
      name,
      visibility,
      source: activeOverrideCount > 0 ? "user_scenario" : "sec_base_forecast",
      override_count: activeOverrideCount,
      forecast_year: firstProjectedYear,
      as_of: requestedAsOf,
      overrides: { ...draftOverrides },
      metrics: collectScenarioMetrics(visibleStudio, firstProjectedYear),
    };
  }

  function buildScenarioRequestFromSavedScenario(
    scenario: SavedStudioScenario,
    name: string,
    visibility: "public" | "private"
  ): CompanyChartsScenarioUpsertRequest {
    return {
      name,
      visibility,
      source: scenario.source,
      override_count: scenario.overrideCount,
      forecast_year: firstProjectedYear,
      as_of: requestedAsOf,
      overrides: { ...scenario.overrides },
      metrics: scenario.metrics,
    };
  }

  function upsertLocalScenario(name: string, visibility: "public" | "private", replaceScenarioId: string | null = null): SavedStudioScenario {
    const now = new Date().toISOString();
    const nextScenario: SavedStudioScenario = {
      version: 1,
      id: replaceScenarioId ?? `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name,
      createdAt: replaceScenarioId && loadedScenario ? loadedScenario.createdAt : now,
      updatedAt: now,
      overrideCount: activeOverrideCount,
      source: activeOverrideCount > 0 ? "user_scenario" : "sec_base_forecast",
      visibility,
      storage: "local",
      overrides: { ...draftOverrides },
      metrics: collectScenarioMetrics(visibleStudio, firstProjectedYear),
      sharePath: null,
      editable: true,
    };

    setLocalSavedScenarios((current) => [nextScenario, ...current.filter((scenario) => scenario.id !== nextScenario.id)]);
    setLoadedScenarioId(nextScenario.id);
    return nextScenario;
  }

  function upsertRemoteScenarioInState(nextScenario: SavedStudioScenario) {
    setRemoteSavedScenarios((current) => [nextScenario, ...current.filter((scenario) => scenario.id !== nextScenario.id)]);
    setLoadedScenarioId(nextScenario.id);
  }

  function promptForScenarioVisibility(defaultVisibility: "public" | "private"): "public" | "private" | null {
    const fallbackVisibility = scenarioViewer.can_create_private ? defaultVisibility : "public";
    const rawValue = window.prompt("Visibility: public or private", fallbackVisibility);
    if (rawValue == null) {
      return null;
    }
    const normalized = rawValue.trim().toLowerCase();
    if (normalized === "public") {
      return "public";
    }
    if (normalized === "private") {
      if (!scenarioViewer.can_create_private) {
        window.alert("Private scenarios need a local viewer identity in this browser.");
        return null;
      }
      return "private";
    }
    window.alert("Enter either 'public' or 'private'.");
    return null;
  }

  async function copyScenarioLink(sharePath: string): Promise<void> {
    const fallbackUrl =
      typeof window !== "undefined"
        ? new URL(sharePath, window.location.origin).toString()
        : sharePath;

    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(fallbackUrl);
      setScenarioSyncMessage("Scenario link copied.");
      return;
    }

    window.prompt("Copy this Projection Studio link", fallbackUrl);
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const url = new URL(window.location.href);
    url.searchParams.set("mode", "studio");
    if (loadedScenario?.storage === "remote") {
      url.searchParams.set("scenario", loadedScenario.id);
    } else {
      url.searchParams.delete("scenario");
    }
    window.history.replaceState({}, "", url.toString());
  }, [loadedScenario?.id, loadedScenario?.storage]);

  useEffect(() => {
    if (!requestedScenarioId) {
      return;
    }

    const existingScenario = savedScenarios.find((scenario) => scenario.id === requestedScenarioId) ?? null;
    if (existingScenario) {
      setDraftOverrides({ ...existingScenario.overrides });
      setLoadedScenarioId(existingScenario.id);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    void getCompanyChartsScenario(ticker, requestedScenarioId, { signal: controller.signal })
      .then((response) => {
        if (cancelled) {
          return;
        }
        const nextScenario = mapRemoteScenario(response.scenario);
        setScenarioViewer(response.viewer);
        setRemoteSavedScenarios((current) => [nextScenario, ...current.filter((scenario) => scenario.id !== nextScenario.id)]);
        setDraftOverrides({ ...nextScenario.overrides });
        setLoadedScenarioId(nextScenario.id);
      })
      .catch((error) => {
        if (!cancelled && !isAbortError(error)) {
          setScenarioSyncMessage(asErrorMessage(error, "Unable to load the requested shared scenario"));
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [requestedScenarioId, savedScenarios, ticker]);

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

  async function handleSaveScenario() {
    setScenarioSyncMessage(null);
    if (loadedScenario?.storage === "remote" && loadedScenario.editable) {
      const response = await updateCompanyChartsScenario(
        ticker,
        loadedScenario.id,
        buildScenarioRequest(loadedScenario.name, loadedScenario.visibility)
      ).catch((error) => {
        setScenarioSyncMessage(asErrorMessage(error, "Unable to update the saved scenario"));
        return null;
      });

      if (response) {
        upsertRemoteScenarioInState(mapRemoteScenario(response.scenario));
        setScenarioViewer(response.viewer);
      }
      return;
    }

    const suggestedName = loadedScenario?.name ?? `Scenario ${savedScenarios.length + 1}`;
    const inputName = normalizeScenarioName(window.prompt("Name this scenario", suggestedName));
    if (!inputName) {
      return;
    }
    const visibility = promptForScenarioVisibility(loadedScenario?.visibility ?? "private");
    if (!visibility) {
      return;
    }

    const response = await createCompanyChartsScenario(ticker, buildScenarioRequest(inputName, visibility)).catch((error) => {
      setScenarioSyncMessage(asErrorMessage(error, "Unable to save to the backend. Keeping a local scenario copy instead."));
      return null;
    });

    if (response) {
      upsertRemoteScenarioInState(mapRemoteScenario(response.scenario));
      setScenarioViewer(response.viewer);
      if (loadedScenario?.storage === "local") {
        setLocalSavedScenarios((current) => current.filter((scenario) => scenario.id !== loadedScenario.id));
      }
      return;
    }

    upsertLocalScenario(inputName, visibility, loadedScenario?.storage === "local" ? loadedScenario.id : null);
  }

  async function handleSaveAsScenario() {
    setScenarioSyncMessage(null);
    const suggestedName = loadedScenario ? `${loadedScenario.name} Copy` : `Scenario ${savedScenarios.length + 1}`;
    const inputName = normalizeScenarioName(window.prompt("Save this scenario as", suggestedName));
    if (!inputName) {
      return;
    }
    const visibility = promptForScenarioVisibility(loadedScenario?.visibility ?? "private");
    if (!visibility) {
      return;
    }

    const response = await createCompanyChartsScenario(ticker, buildScenarioRequest(inputName, visibility)).catch(() => null);
    if (response) {
      upsertRemoteScenarioInState(mapRemoteScenario(response.scenario));
      setScenarioViewer(response.viewer);
      return;
    }

    upsertLocalScenario(inputName, visibility);
  }

  async function handleDuplicateScenario(scenario: SavedStudioScenario | null = loadedScenario) {
    const sourceScenario = scenario ?? loadedScenario;
    if (!sourceScenario) {
      return;
    }

    setScenarioSyncMessage(null);
    const inputName = normalizeScenarioName(window.prompt("Duplicate scenario as", `${sourceScenario.name} Copy`));
    if (!inputName) {
      return;
    }
    const visibility = promptForScenarioVisibility(sourceScenario.visibility);
    if (!visibility) {
      return;
    }

    if (sourceScenario.storage === "remote") {
      const response = await cloneCompanyChartsScenario(ticker, sourceScenario.id, { name: inputName, visibility }).catch((error) => {
        setScenarioSyncMessage(asErrorMessage(error, "Unable to duplicate the saved scenario"));
        return null;
      });
      if (response) {
        upsertRemoteScenarioInState(mapRemoteScenario(response.scenario));
        setScenarioViewer(response.viewer);
        return;
      }
    }

    const now = new Date().toISOString();
    const duplicatedScenario: SavedStudioScenario = {
      ...sourceScenario,
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      name: inputName,
      visibility,
      storage: "local",
      sharePath: null,
      editable: true,
      createdAt: now,
      updatedAt: now,
    };
    setLocalSavedScenarios((current) => [duplicatedScenario, ...current]);
    setLoadedScenarioId(duplicatedScenario.id);
  }

  async function handleShareScenarioLink(scenario: SavedStudioScenario | null = loadedScenario) {
    const currentScenario = scenario ?? loadedScenario;
    setScenarioSyncMessage(null);

    if (currentScenario?.storage === "remote" && currentScenario.sharePath) {
      if (currentScenario.visibility === "private") {
        const response = await updateCompanyChartsScenario(
          ticker,
          currentScenario.id,
          buildScenarioRequestFromSavedScenario(currentScenario, currentScenario.name, "public")
        ).catch((error) => {
          setScenarioSyncMessage(asErrorMessage(error, "Unable to publish the saved scenario"));
          return null;
        });
        if (!response) {
          return;
        }
        const nextScenario = mapRemoteScenario(response.scenario);
        upsertRemoteScenarioInState(nextScenario);
        setScenarioViewer(response.viewer);
        await copyScenarioLink(nextScenario.sharePath ?? response.scenario.share_path);
        return;
      }

      await copyScenarioLink(currentScenario.sharePath);
      return;
    }

    const suggestedName = currentScenario?.name ?? `Scenario ${savedScenarios.length + 1}`;
    const inputName = normalizeScenarioName(window.prompt("Create a public share link for", suggestedName));
    if (!inputName) {
      return;
    }

    const response = await createCompanyChartsScenario(
      ticker,
      currentScenario ? buildScenarioRequestFromSavedScenario(currentScenario, inputName, "public") : buildScenarioRequest(inputName, "public")
    ).catch((error) => {
      setScenarioSyncMessage(asErrorMessage(error, "Unable to create a public share link"));
      return null;
    });
    if (!response) {
      return;
    }

    const nextScenario = mapRemoteScenario(response.scenario);
    upsertRemoteScenarioInState(nextScenario);
    setScenarioViewer(response.viewer);
    await copyScenarioLink(response.scenario.share_path);
  }

  function handleLoadScenario(scenario: SavedStudioScenario) {
    setDraftOverrides({ ...scenario.overrides });
    setLoadedScenarioId(scenario.id);
  }

  function handleDeleteScenario(id: string) {
    setLocalSavedScenarios((current) => current.filter((scenario) => scenario.id !== id));
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
    <div ref={shareCaptureRef} className="charts-page-shell">
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
          <p className="charts-page-hero-thesis">{visibleStudioSpec?.summary ?? "Inspection of projected values, sensitivities, waterfall bridges, and traceable formulas."}</p>
        </div>
        <div className="studio-hero-actions">
          <button type="button" className="studio-primary-button" onClick={handleExportCsv}>
            Export Studio CSV
          </button>
          <ChartShareActions
            ticker={ticker}
            snapshot={shareSnapshot}
            fileStem={`${ticker.toLowerCase()}-projection-studio`}
            className="chart-share-action-bar-inline"
            captureTargetRef={shareCaptureRef}
          />
          <button type="button" className="studio-secondary-button" onClick={() => void handleSaveScenario()}>
            Save
          </button>
          <button type="button" className="studio-secondary-button" onClick={() => void handleSaveAsScenario()}>
            Save As
          </button>
          <button type="button" className="studio-secondary-button" onClick={() => void handleShareScenarioLink()}>
            Share Link
          </button>
          <button type="button" className="studio-secondary-button" onClick={() => void handleDuplicateScenario()}>
            Duplicate
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
                <p className="studio-panel-subtitle">
                  {scenarioViewer.sync_enabled
                    ? "Local drafts stay in this browser while synced scenarios can be reopened and shared with public or private visibility."
                    : "Saved locally in this browser. Compare up to two scenarios with simple deltas."}
                </p>
              </div>
            </div>

            {savedScenarioPersistenceMessage ? (
              <div className="studio-what-if-error" role="alert">
                <div>{savedScenarioPersistenceMessage}</div>
              </div>
            ) : null}

            {scenarioSyncMessage ? (
              <div className="studio-what-if-state" role="status">
                {scenarioSyncMessage}
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
                        <div className="studio-driver-detail">
                          {scenario.updatedAt ? `Updated ${formatScenarioTimestamp(scenario.updatedAt)}` : `Saved ${formatScenarioTimestamp(scenario.createdAt)}`}
                        </div>
                      </div>
                      <span className="studio-marker-chip is-default">{scenario.overrideCount} overrides</span>
                    </div>
                    <div className="studio-scenario-meta-row">
                      <SourceStateBadge state={resolveSavedScenarioSourceState(scenario.source)} />
                      <span className="studio-marker-chip is-default">{scenario.visibility}</span>
                      <span className="studio-marker-chip is-default">{scenario.storage === "remote" ? "Synced" : "Local"}</span>
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
                      <button type="button" className="studio-secondary-button" onClick={() => void handleShareScenarioLink(scenario)}>
                        Share Link
                      </button>
                      <button type="button" className="studio-secondary-button" onClick={() => void handleDuplicateScenario(scenario)}>
                        Duplicate
                      </button>
                      {scenario.storage === "local" ? (
                        <button type="button" className="studio-secondary-button" onClick={() => handleDeleteScenario(scenario.id)}>
                          Delete
                        </button>
                      ) : null}
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

            <ScenarioDiffPanel
              summary={compareDiffSummary}
              loading={compareDiffLoading}
              error={compareDiffError}
              onCopy={() => {
                void handleCopyCompareSummary();
              }}
            />
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

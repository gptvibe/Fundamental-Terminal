"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartsModeSwitch } from "@/components/company/charts-mode-switch";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { exportRowsToCsv, type ExportRow, normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import type {
  CompanyChartsDashboardResponse,
  CompanyChartsDriverCardPayload,
  CompanyChartsFormulaInputPayload,
  CompanyChartsFormulaTracePayload,
  CompanyChartsProjectedRowPayload,
  CompanyChartsScheduleSectionPayload,
  CompanyChartsSensitivityCellPayload,
} from "@/lib/types";

import { FormulaTracePopover } from "./formula-trace-popover";

interface ProjectionStudioProps {
  payload: CompanyChartsDashboardResponse;
  studio: NonNullable<CompanyChartsDashboardResponse["projection_studio"]>;
}

interface DriverGroup {
  key: string;
  title: string;
  drivers: CompanyChartsDriverCardPayload[];
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

const DRIVER_GROUP_TITLES: Record<string, string> = {
  revenue: "Revenue Drivers",
  cost: "Cost Structure",
  working_capital: "Working Capital",
  reinvestment: "Reinvestment",
  below_line: "Below-The-Line",
  dilution: "Shares & Dilution",
  other: "Other Inputs",
};

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

function getDriverGroupKey(driver: CompanyChartsDriverCardPayload): string {
  const normalizedKey = `${driver.key} ${driver.title}`.toLowerCase();

  if (normalizedKey.includes("revenue") || normalizedKey.includes("growth") || normalizedKey.includes("price") || normalizedKey.includes("volume")) {
    return "revenue";
  }
  if (normalizedKey.includes("cost") || normalizedKey.includes("margin") || normalizedKey.includes("opex") || normalizedKey.includes("sga") || normalizedKey.includes("r&d")) {
    return "cost";
  }
  if (normalizedKey.includes("working_capital") || normalizedKey.includes("receivable") || normalizedKey.includes("inventory") || normalizedKey.includes("payable")) {
    return "working_capital";
  }
  if (normalizedKey.includes("reinvestment") || normalizedKey.includes("capex") || normalizedKey.includes("depreciation")) {
    return "reinvestment";
  }
  if (normalizedKey.includes("below_line") || normalizedKey.includes("interest") || normalizedKey.includes("tax") || normalizedKey.includes("other income")) {
    return "below_line";
  }
  if (normalizedKey.includes("dilution") || normalizedKey.includes("share") || normalizedKey.includes("buyback")) {
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
  sensitivityCells: CompanyChartsSensitivityCellPayload[]
): ExportRow[] {
  const scheduleRows = scheduleSections.flatMap((section) =>
    section.rows.flatMap((row) => {
      const years = Array.from(
        new Set([...Object.keys(row.reported_values).map(Number), ...Object.keys(row.projected_values).map(Number)])
      ).sort((left, right) => left - right);

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

  return [...scheduleRows, ...driverRows, ...scenarioRows, ...sensitivityRows];
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

function ScheduleTable({
  section,
  reportedYears,
  projectedYears,
  onCellClick,
}: {
  section: CompanyChartsScheduleSectionPayload;
  reportedYears: number[];
  projectedYears: number[];
  onCellClick: (trace: CompanyChartsFormulaTracePayload) => void;
}) {
  const allYears = [...reportedYears, ...projectedYears];

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

                    return (
                      <td
                        key={`${row.key}-${year}`}
                        className={`studio-table-value-cell ${isProjected ? "is-projected" : "is-reported"} ${isClickable ? "is-clickable" : ""}`}
                        data-projected={isProjected ? "true" : "false"}
                      >
                        {isClickable && trace ? (
                          <button
                            type="button"
                            className="studio-table-value-button"
                            onClick={() => onCellClick(trace)}
                            aria-label={`${row.label} ${year} formula trace`}
                          >
                            {formatValue(value, row.unit)}
                          </button>
                        ) : (
                          formatValue(value, row.unit)
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

export function ProjectionStudio({ payload, studio }: ProjectionStudioProps) {
  const [selectedTrace, setSelectedTrace] = useState<CompanyChartsFormulaTracePayload | null>(null);

  const scheduleSections = useMemo(() => studio.schedule_sections.map((section) => withCheckRows(section)), [studio.schedule_sections]);
  const driverGroups = useMemo(() => groupDrivers(studio.drivers_used), [studio.drivers_used]);
  const sensitivityGrid = useMemo(() => buildSensitivityGrid(studio.sensitivity_matrix), [studio.sensitivity_matrix]);

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
  const bridgeCards = useMemo(() => buildBridgeCards(scheduleSections, projectedYears[0] ?? null), [projectedYears, scheduleSections]);
  const exportRows = useMemo(
    () => buildExportRows(scheduleSections, driverGroups, studio.scenarios_comparison, studio.sensitivity_matrix),
    [driverGroups, scheduleSections, studio.scenarios_comparison, studio.sensitivity_matrix]
  );

  const ticker = payload.company?.ticker ?? "company";

  function handleExportCsv() {
    exportRowsToCsv(`${normalizeExportFileStem(`${ticker}-projection-studio`, "projection-studio")}.csv`, exportRows);
  }

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
          <p className="charts-page-hero-thesis">Inspection of projected values, sensitivities, waterfall bridges, and traceable formulas.</p>
        </div>
        <div className="studio-hero-actions">
          <button type="button" className="studio-primary-button" onClick={handleExportCsv}>
            Export Studio CSV
          </button>
          <Link href={`/company/${encodeURIComponent(ticker)}/models`} className="studio-secondary-link">
            Open in Models for Valuation
          </Link>
        </div>
      </header>

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
                {studio.scenarios_comparison.map((row) => (
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
            reportedYears={reportedYears}
            projectedYears={projectedYears}
            onCellClick={setSelectedTrace}
          />
        ))}
      </section>

      <FormulaTracePopover trace={selectedTrace} isOpen={Boolean(selectedTrace)} onClose={() => setSelectedTrace(null)} />
    </div>
  );
}

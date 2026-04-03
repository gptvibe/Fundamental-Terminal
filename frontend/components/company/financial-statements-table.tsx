"use client";

import type { CSSProperties } from "react";
import { useMemo } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";

import { MetricLabel } from "@/components/ui/metric-label";
import { difference, formatSignedCompactDelta } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);

type StatementMetricConfig = {
  key: string;
  label: string;
  selectValue: (statement: FinancialPayload) => number | null | undefined;
  formatValue: (value: number | null | undefined) => string;
  formatDelta?: (value: number | null | undefined) => string;
};

const STATEMENT_METRICS: StatementMetricConfig[] = [
  { key: "revenue", label: "Revenue", selectValue: (statement) => statement.revenue, formatValue: formatCompactNumber },
  { key: "gross_profit", label: "Gross Profit", selectValue: (statement) => statement.gross_profit, formatValue: formatCompactNumber },
  { key: "operating_income", label: "Operating Income", selectValue: (statement) => statement.operating_income, formatValue: formatCompactNumber },
  { key: "net_income", label: "Net Income", selectValue: (statement) => statement.net_income, formatValue: formatCompactNumber },
  { key: "eps", label: "EPS", selectValue: (statement) => statement.eps, formatValue: formatPerShareValue, formatDelta: formatPerShareDelta },
  { key: "operating_cash_flow", label: "Operating Cash Flow", selectValue: (statement) => statement.operating_cash_flow, formatValue: formatCompactNumber },
  { key: "free_cash_flow", label: "Free Cash Flow", selectValue: (statement) => statement.free_cash_flow, formatValue: formatCompactNumber },
  { key: "total_assets", label: "Total Assets", selectValue: (statement) => statement.total_assets, formatValue: formatCompactNumber },
  { key: "total_liabilities", label: "Total Liabilities", selectValue: (statement) => statement.total_liabilities, formatValue: formatCompactNumber },
];

interface FinancialStatementsTableProps {
  financials: FinancialPayload[];
  ticker: string;
  showComparison?: boolean;
  selectedPeriodKey?: string | null;
  comparisonPeriodKey?: string | null;
  selectedFinancial?: FinancialPayload | null;
  comparisonFinancial?: FinancialPayload | null;
}

export function FinancialStatementsTable({
  financials,
  ticker,
  showComparison = false,
  selectedPeriodKey = null,
  comparisonPeriodKey = null,
  selectedFinancial = null,
  comparisonFinancial = null,
}: FinancialStatementsTableProps) {
  const metricTrends = useMemo(() => buildMetricTrendRows(financials), [financials]);
  const activeFinancial = selectedFinancial ?? findFinancialByKey(financials, selectedPeriodKey) ?? financials[0] ?? null;
  const activeComparisonFinancial = showComparison
    ? comparisonFinancial ?? findFinancialByKey(financials, comparisonPeriodKey)
    : null;
  const exportedFinancials = useMemo(
    () => buildVisibleStatements(activeFinancial, activeComparisonFinancial),
    [activeComparisonFinancial, activeFinancial]
  );
  const jsonPayload = useMemo(() => JSON.stringify(exportedFinancials, null, 2), [exportedFinancials]);
  const csvPayload = useMemo(() => buildFinancialsCsv(exportedFinancials), [exportedFinancials]);

  return (
    <div className="financial-statements-stack">
      <div className="financial-export-row">
        <div className="financial-trend-table-note">Download the currently focused statement view for spreadsheet or model work.</div>
        <div className="financial-export-actions">
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={() => triggerDownload(`${ticker}-financial-statements.csv`, csvPayload, "text/csv;charset=utf-8")}
          >
            Download CSV
          </button>
          <button
            type="button"
            className="ticker-button financial-export-button"
            onClick={() => triggerDownload(`${ticker}-financial-statements.json`, jsonPayload, "application/json;charset=utf-8")}
          >
            Download JSON
          </button>
        </div>
      </div>

      {(activeFinancial || activeComparisonFinancial) ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {activeFinancial ? <span className="pill tone-cyan">Focus {formatStatementLabel(activeFinancial)}</span> : null}
          {activeComparisonFinancial ? <span className="pill tone-gold">Compare {formatStatementLabel(activeComparisonFinancial)}</span> : null}
          {showComparison && !activeComparisonFinancial ? <span className="pill tone-red">No comparison period is available in the current view</span> : null}
        </div>
      ) : null}

      <div className="financial-trend-table-shell">
        <div className="financial-trend-table-note">Hover a sparkline to inspect values across the currently selected cadence and range.</div>
        <div className="financial-trend-table-scroll">
          <table className="financial-trend-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Latest + Trend</th>
              </tr>
            </thead>
            <tbody>
              {metricTrends.map((metric) => (
                <tr key={metric.key}>
                  <td>
                    <div className="financial-trend-label">
                      <MetricLabel label={metric.label} metricKey={metric.key} />
                    </div>
                    <div className="financial-trend-subtitle">{metric.historyLabel}</div>
                  </td>
                  <td>
                    <div className="financial-trend-inline">
                      <div className="financial-trend-value-block">
                        <div className="financial-trend-value" style={{ color: metric.color }}>
                          {metric.displayValue}
                        </div>
                        <div className="financial-trend-direction">{metric.directionLabel}</div>
                      </div>
                      <MetricSparkline row={metric} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="financial-table-shell">
        <table className="financial-table" style={{ minWidth: 860 }}>
          <thead>
            <tr>
              <th>Metric</th>
              <th>{activeFinancial ? formatStatementHeader(activeFinancial) : "Selected Period"}</th>
              {activeComparisonFinancial ? <th>{formatStatementHeader(activeComparisonFinancial)}</th> : null}
              {activeComparisonFinancial ? <th>Absolute Change</th> : null}
              {activeComparisonFinancial ? <th>Percent Change</th> : null}
            </tr>
          </thead>
          <tbody>
            {STATEMENT_METRICS.map((metric) => {
              const activeValue = activeFinancial ? metric.selectValue(activeFinancial) : null;
              const comparisonValue = activeComparisonFinancial ? metric.selectValue(activeComparisonFinancial) : null;
              const absoluteChange = activeComparisonFinancial ? difference(activeValue, comparisonValue) : null;
              const relativeChange = activeComparisonFinancial ? calculateRelativeChange(activeValue, comparisonValue) : null;
              const toneStyle = resolveDeltaStyle(absoluteChange);

              return (
                <tr key={metric.key}>
                  <td>
                    <MetricLabel label={metric.label} metricKey={metric.key} />
                  </td>
                  <td>{metric.formatValue(activeValue)}</td>
                  {activeComparisonFinancial ? <td>{metric.formatValue(comparisonValue)}</td> : null}
                  {activeComparisonFinancial ? <td style={toneStyle}>{formatMetricDelta(metric, absoluteChange)}</td> : null}
                  {activeComparisonFinancial ? <td style={toneStyle}>{formatPercent(relativeChange)}</td> : null}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type TrendDirection = "up" | "down" | "flat";

type SparklineTooltipEntry = {
  color?: string;
  payload?: Record<string, unknown>;
  value?: number | null;
};

interface MetricTrendPoint {
  label: string;
  fullDate: string;
  value: number | null;
}

interface MetricTrendRow {
  key: string;
  label: string;
  displayValue: string;
  historyLabel: string;
  directionLabel: string;
  color: string;
  valueLabel: string;
  points: MetricTrendPoint[];
  formatValue: (value: number | null) => string;
}

function MetricSparkline({ row }: { row: MetricTrendRow }) {
  const hasValues = row.points.some((point) => point.value !== null && Number.isFinite(point.value));

  if (!hasValues) {
    return <div className="financial-trend-empty">No cached history</div>;
  }

  return (
    <div className="financial-trend-sparkline-shell">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={row.points} margin={{ top: 6, right: 4, left: 4, bottom: 6 }}>
          <Tooltip content={<MetricSparklineTooltip metricLabel={row.label} color={row.color} valueLabel={row.valueLabel} formatValue={row.formatValue} />} />
          <Line
            type="monotone"
            dataKey="value"
            stroke={row.color}
            strokeWidth={2.4}
            dot={false}
            connectNulls
            isAnimationActive={false}
            activeDot={{ r: 4, fill: row.color, stroke: "var(--panel)", strokeWidth: 2 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function MetricSparklineTooltip({
  active,
  payload,
  label,
  metricLabel,
  color,
  valueLabel,
  formatValue
}: {
  active?: boolean;
  payload?: SparklineTooltipEntry[];
  label?: string;
  metricLabel: string;
  color: string;
  valueLabel: string;
  formatValue: (value: number | null) => string;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload ?? {};
  const value = asFiniteNumber(point.value);
  const periodEnd = typeof point.fullDate === "string" ? formatDate(point.fullDate) : "--";

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">
        {metricLabel}
        {label ? ` - ${label}` : ""}
      </div>
      <TooltipRow label={valueLabel} value={formatValue(value)} color={color} />
      <TooltipRow label="Period End" value={periodEnd} color="var(--warning)" />
    </div>
  );
}

function TooltipRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="chart-tooltip-row">
      <span className="chart-tooltip-key">
        <span className="chart-tooltip-dot" style={{ background: color }} />
        {label}
      </span>
      <span className="chart-tooltip-value">{value}</span>
    </div>
  );
}

function buildMetricTrendRows(financials: FinancialPayload[]): MetricTrendRow[] {
  const history = selectTrendHistory(financials);

  return [
    createMetricTrendRow({
      key: "revenue",
      label: "Revenue",
      history,
      valueLabel: "Revenue",
      selectValue: (statement) => statement.revenue,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "eps",
      label: "EPS",
      history,
      valueLabel: "EPS",
      selectValue: (statement) => statement.eps,
      formatValue: (value) => (value === null ? "--" : value.toFixed(2))
    }),
    createMetricTrendRow({
      key: "free-cash-flow",
      label: "Free Cash Flow",
      history,
      valueLabel: "Free Cash Flow",
      selectValue: (statement) => statement.free_cash_flow,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "net-margin",
      label: "Net Margin",
      history,
      valueLabel: "Net Margin",
      selectValue: (statement) => computeNetMargin(statement),
      formatValue: (value) => formatPercent(value)
    }),
    createMetricTrendRow({
      key: "sga",
      label: "SG&A",
      history,
      valueLabel: "SG&A",
      selectValue: (statement) => statement.sga,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "rnd",
      label: "R&D",
      history,
      valueLabel: "R&D",
      selectValue: (statement) => statement.research_and_development,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "interest-expense",
      label: "Interest Expense",
      history,
      valueLabel: "Interest Expense",
      selectValue: (statement) => statement.interest_expense,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "income-tax-expense",
      label: "Income Tax Expense",
      history,
      valueLabel: "Income Tax Expense",
      selectValue: (statement) => statement.income_tax_expense,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "long-term-debt",
      label: "Long-Term Debt",
      history,
      valueLabel: "Long-Term Debt",
      selectValue: (statement) => statement.long_term_debt,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "lease-liabilities",
      label: "Lease Liabilities",
      history,
      valueLabel: "Lease Liabilities",
      selectValue: (statement) => statement.lease_liabilities,
      formatValue: (value) => formatCompactNumber(value)
    }),
    createMetricTrendRow({
      key: "stock-based-compensation",
      label: "Stock-Based Comp",
      history,
      valueLabel: "Stock-Based Compensation",
      selectValue: (statement) => statement.stock_based_compensation,
      formatValue: (value) => formatCompactNumber(value)
    })
  ];
}

function createMetricTrendRow({
  key,
  label,
  history,
  valueLabel,
  selectValue,
  formatValue
}: {
  key: string;
  label: string;
  history: FinancialPayload[];
  valueLabel: string;
  selectValue: (statement: FinancialPayload) => number | null;
  formatValue: (value: number | null) => string;
}): MetricTrendRow {
  const points = history.map((statement) => ({
    label: new Intl.DateTimeFormat("en-US", { year: "numeric" }).format(new Date(statement.period_end)),
    fullDate: statement.period_end,
    value: selectValue(statement)
  }));

  const firstValue = points.find((point) => point.value !== null)?.value ?? null;
  const latestPoint = [...points].reverse().find((point) => point.value !== null) ?? null;
  const latestValue = latestPoint?.value ?? null;
  const direction = determineTrendDirection(firstValue, latestValue);

  return {
    key,
    label,
    displayValue: formatValue(latestValue),
    historyLabel: history.length >= 2 ? `${points[0]?.label ?? "--"} to ${points.at(-1)?.label ?? "--"}` : "Latest cached period",
    directionLabel: directionCopy(direction),
    color: trendColor(direction),
    valueLabel,
    points,
    formatValue
  };
}

function selectTrendHistory(financials: FinancialPayload[]): FinancialPayload[] {
  const annualStatements = financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
  const source = annualStatements.length >= 2 ? annualStatements : financials;

  return [...source].sort((left, right) => Date.parse(left.period_end) - Date.parse(right.period_end));
}

function computeNetMargin(statement: FinancialPayload): number | null {
  if (statement.net_income === null || statement.revenue === null || statement.revenue === 0) {
    return null;
  }

  return statement.net_income / statement.revenue;
}

function determineTrendDirection(firstValue: number | null, latestValue: number | null): TrendDirection {
  if (firstValue === null || latestValue === null) {
    return "flat";
  }

  const delta = latestValue - firstValue;
  const threshold = Math.max(Math.abs(firstValue) * 0.02, 0.0001);
  if (delta > threshold) {
    return "up";
  }
  if (delta < -threshold) {
    return "down";
  }
  return "flat";
}

function directionCopy(direction: TrendDirection): string {
  switch (direction) {
    case "up":
      return "Improving trend";
    case "down":
      return "Softening trend";
    default:
      return "Stable trend";
  }
}

function trendColor(direction: TrendDirection): string {
  switch (direction) {
    case "up":
      return "var(--positive)";
    case "down":
      return "var(--negative)";
    default:
      return "var(--warning)";
  }
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function findFinancialByKey(financials: FinancialPayload[], key: string | null): FinancialPayload | null {
  if (!key) {
    return null;
  }
  return financials.find((statement) => buildStatementKey(statement) === key) ?? null;
}

function buildVisibleStatements(
  activeFinancial: FinancialPayload | null,
  comparisonFinancial: FinancialPayload | null
): FinancialPayload[] {
  const visibleStatements = [activeFinancial, comparisonFinancial].filter((statement): statement is FinancialPayload => Boolean(statement));
  const seenKeys = new Set<string>();
  return visibleStatements.filter((statement) => {
    const statementKey = buildStatementKey(statement);
    if (seenKeys.has(statementKey)) {
      return false;
    }
    seenKeys.add(statementKey);
    return true;
  });
}

function buildStatementKey(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.period_end}|${statement.filing_type}`;
}

function formatStatementLabel(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

function formatStatementHeader(statement: Pick<FinancialPayload, "period_end" | "filing_type">): string {
  return `${statement.filing_type} ${formatDate(statement.period_end)}`;
}

function formatPerShareValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  return value.toFixed(2);
}

function formatPerShareDelta(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}

function formatMetricDelta(metric: StatementMetricConfig, value: number | null): string {
  if (metric.formatDelta) {
    return metric.formatDelta(value);
  }
  return formatSignedCompactDelta(value);
}

function calculateRelativeChange(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current == null || previous == null || Number.isNaN(current) || Number.isNaN(previous) || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

function resolveDeltaStyle(value: number | null): CSSProperties | undefined {
  if (value == null || Number.isNaN(value)) {
    return { color: "var(--text-muted)", fontWeight: 600 };
  }
  if (value > 0) {
    return { color: "var(--positive)", fontWeight: 700 };
  }
  if (value < 0) {
    return { color: "var(--negative)", fontWeight: 700 };
  }
  return { color: "var(--text-muted)", fontWeight: 600 };
}

function triggerDownload(filename: string, payload: string, contentType: string) {
  const blob = new Blob([payload], { type: contentType });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

function buildFinancialsCsv(financials: FinancialPayload[]): string {
  const headers = [
    "period_start",
    "period_end",
    "filing_type",
    "statement_type",
    "source",
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "eps",
    "operating_cash_flow",
    "free_cash_flow",
    "total_assets",
    "current_assets",
    "total_liabilities",
    "current_liabilities",
    "retained_earnings",
    "sga",
    "research_and_development",
    "interest_expense",
    "income_tax_expense",
    "inventory",
    "accounts_receivable",
    "goodwill_and_intangibles",
    "long_term_debt",
    "lease_liabilities",
    "shares_outstanding",
    "weighted_average_diluted_shares",
    "stock_based_compensation",
    "capex",
    "acquisitions",
    "debt_changes",
    "dividends",
    "share_buybacks"
  ];
  const rows = financials.map((statement) =>
    [
      statement.period_start,
      statement.period_end,
      statement.filing_type,
      statement.statement_type,
      statement.source,
      statement.revenue,
      statement.gross_profit,
      statement.operating_income,
      statement.net_income,
      statement.eps,
      statement.operating_cash_flow,
      statement.free_cash_flow,
      statement.total_assets,
      statement.current_assets,
      statement.total_liabilities,
      statement.current_liabilities,
      statement.retained_earnings,
      statement.sga,
      statement.research_and_development,
      statement.interest_expense,
      statement.income_tax_expense,
      statement.inventory,
      statement.accounts_receivable,
      statement.goodwill_and_intangibles,
      statement.long_term_debt,
      statement.lease_liabilities,
      statement.shares_outstanding,
      statement.weighted_average_diluted_shares,
      statement.stock_based_compensation,
      statement.capex,
      statement.acquisitions,
      statement.debt_changes,
      statement.dividends,
      statement.share_buybacks
    ].map(csvCell)
  );

  return [headers.join(","), ...rows.map((row) => row.join(","))].join("\n");
}

function csvCell(value: string | number | null): string {
  if (value === null) {
    return "";
  }

  const text = String(value);
  if (/[",\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

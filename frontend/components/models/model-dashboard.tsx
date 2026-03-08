"use client";

import type { ReactNode } from "react";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import {
  CHART_AXIS_COLOR,
  CHART_GRID_COLOR,
  RECHARTS_TOOLTIP_PROPS,
  chartLegendStyle,
  chartTick
} from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { ModelPayload } from "@/lib/types";

const MODEL_ORDER = ["dcf", "dupont", "piotroski", "altman_z", "ratios"];
const CHART_COLORS = ["#00FF41", "#00E5FF", "#FFD700", "#7CFFB2", "#64D2FF", "#F6C945"];

export function ModelDashboard({ models }: { models: ModelPayload[] }) {
  const sortedModels = [...models].sort((left, right) => {
    const leftIndex = MODEL_ORDER.indexOf(left.model_name);
    const rightIndex = MODEL_ORDER.indexOf(right.model_name);
    return (leftIndex === -1 ? MODEL_ORDER.length : leftIndex) - (rightIndex === -1 ? MODEL_ORDER.length : rightIndex);
  });

  if (!sortedModels.length) {
    return <div className="text-muted">No cached model outputs yet.</div>;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      {sortedModels.map((model) => (
        <ModelSection key={`${model.model_name}-${model.model_version}-${model.created_at}`} model={model} />
      ))}
    </div>
  );
}

function ModelSection({ model }: { model: ModelPayload }) {
  return (
    <section
      style={{
        display: "grid",
        gap: 14,
        padding: 16,
        borderRadius: 14,
        border: "1px solid var(--panel-border)",
        background: "var(--panel-alt)"
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "#00E5FF" }}>
            {titleCase(model.model_name)}
          </div>
          <div style={{ marginTop: 6, fontSize: 13, color: "var(--text-muted)" }}>
            v{model.model_version} · computed {formatDate(model.created_at)}
          </div>
        </div>
        <span className="pill">{String(model.result.status ?? "ready")}</span>
      </div>
      {renderModelContent(model)}
    </section>
  );
}

function renderModelContent(model: ModelPayload) {
  switch (model.model_name) {
    case "dcf":
      return <DcfModelView model={model} />;
    case "dupont":
      return <DupontModelView model={model} />;
    case "piotroski":
      return <PiotroskiModelView model={model} />;
    case "altman_z":
      return <AltmanModelView model={model} />;
    case "ratios":
      return <RatiosModelView model={model} />;
    default:
      return <FallbackModelView model={model} />;
  }
}

function DcfModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  if (result.status !== "ok") {
    return <StateMessage result={result} />;
  }

  const assumptions = asRecord(result.assumptions);
  const historical = asArray(result.historical_free_cash_flow).map((entry) => ({
    period: String(entry.period_end ?? "—"),
    freeCashFlow: asNumber(entry.free_cash_flow)
  }));
  const projected = asArray(result.projected_free_cash_flow).map((entry) => ({
    period: `Y${String(entry.year ?? "?")}`,
    growthRate: asNumber(entry.growth_rate),
    freeCashFlow: asNumber(entry.free_cash_flow),
    presentValue: asNumber(entry.present_value)
  }));
  const chartData = [
    ...historical.map((entry) => ({ label: entry.period, historicalFcf: entry.freeCashFlow, projectedFcf: null, presentValue: null })),
    ...projected.map((entry) => ({ label: entry.period, historicalFcf: null, projectedFcf: entry.freeCashFlow, presentValue: entry.presentValue }))
  ];

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Enterprise Value", value: formatCompactNumber(asNumber(result.enterprise_value_proxy)) },
          { label: "PV Cash Flows", value: formatCompactNumber(asNumber(result.present_value_of_cash_flows)) },
          { label: "Terminal PV", value: formatCompactNumber(asNumber(result.terminal_value_present_value)) },
          { label: "Discount Rate", value: formatPercent(asNumber(assumptions.discount_rate)) }
        ]}
      />

      <ChartShell title="Historical + Projected Free Cash Flow">
        <ResponsiveContainer>
          <LineChart data={chartData}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(value: number | string | Array<number | string>) => {
                if (typeof value === "number") {
                  return formatCompactNumber(value);
                }
                return value;
              }}
            />
            <Legend wrapperStyle={chartLegendStyle()} />
            <Line type="monotone" dataKey="historicalFcf" name="Historical FCF" stroke="#00E5FF" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} />
            <Line type="monotone" dataKey="projectedFcf" name="Projected FCF" stroke="#00FF41" strokeWidth={2} dot={{ r: 2 }} connectNulls={false} />
            <Line type="monotone" dataKey="presentValue" name="Discounted PV" stroke="#FFD700" strokeWidth={2} dot={false} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </ChartShell>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 0.85fr) minmax(420px, 1.15fr)", gap: 14 }}>
        <CompactTable
          title="Assumptions"
          columns={[
            { key: "metric", label: "Metric" },
            { key: "value", label: "Value", align: "right" }
          ]}
          rows={[
            { metric: "Base Period End", value: String(result.base_period_end ?? "—") },
            { metric: "Discount Rate", value: formatPercent(asNumber(assumptions.discount_rate)) },
            { metric: "Terminal Growth", value: formatPercent(asNumber(assumptions.terminal_growth_rate)) },
            { metric: "Starting FCF Growth", value: formatPercent(asNumber(assumptions.starting_growth_rate)) },
            { metric: "Projection Years", value: String(assumptions.projection_years ?? "—") }
          ]}
        />
        <CompactTable
          title="Projection Table"
          columns={[
            { key: "period", label: "Period" },
            { key: "growthRate", label: "Growth", align: "right" },
            { key: "freeCashFlow", label: "FCF", align: "right" },
            { key: "presentValue", label: "PV", align: "right" }
          ]}
          rows={projected.map((entry) => ({
            period: entry.period,
            growthRate: formatPercent(entry.growthRate),
            freeCashFlow: formatCompactNumber(entry.freeCashFlow),
            presentValue: formatCompactNumber(entry.presentValue)
          }))}
        />
      </div>
    </div>
  );
}

function DupontModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  const chartData = [
    { label: "Net Margin", value: asNumber(result.net_profit_margin), formatted: formatPercent(asNumber(result.net_profit_margin)) },
    { label: "Asset Turnover", value: asNumber(result.asset_turnover), formatted: formatMultiple(asNumber(result.asset_turnover)) },
    { label: "Equity Multiplier", value: asNumber(result.equity_multiplier), formatted: formatMultiple(asNumber(result.equity_multiplier)) },
    { label: "ROE", value: asNumber(result.return_on_equity), formatted: formatPercent(asNumber(result.return_on_equity)) }
  ];

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Net Margin", value: formatPercent(asNumber(result.net_profit_margin)) },
          { label: "Asset Turnover", value: formatMultiple(asNumber(result.asset_turnover)) },
          { label: "Equity Multiplier", value: formatMultiple(asNumber(result.equity_multiplier)) },
          { label: "ROE", value: formatPercent(asNumber(result.return_on_equity)) }
        ]}
      />

      <ChartShell title="DuPont Components">
        <ResponsiveContainer>
          <BarChart data={chartData}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(_value, _name, item) => item.payload.formatted}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={entry.label} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartShell>

      <CompactTable
        title="DuPont Number Table"
        columns={[
          { key: "metric", label: "Metric" },
          { key: "value", label: "Value", align: "right" }
        ]}
        rows={[
          { metric: "Period End", value: String(result.period_end ?? "—") },
          { metric: "Filing Type", value: String(result.filing_type ?? "—") },
          { metric: "Net Profit Margin", value: formatPercent(asNumber(result.net_profit_margin)) },
          { metric: "Asset Turnover", value: formatMultiple(asNumber(result.asset_turnover)) },
          { metric: "Equity Multiplier", value: formatMultiple(asNumber(result.equity_multiplier)) },
          { metric: "Return on Equity", value: formatPercent(asNumber(result.return_on_equity)) },
          { metric: "Average Assets", value: formatCompactNumber(asNumber(result.average_assets)) },
          { metric: "Average Equity", value: formatCompactNumber(asNumber(result.average_equity)) }
        ]}
      />
    </div>
  );
}

function PiotroskiModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  const criteria = Object.entries(asRecord(result.criteria)).map(([key, value]) => ({
    label: titleCase(key),
    raw: value,
    value: typeof value === "boolean" ? (value ? 1 : 0) : null,
    display: typeof value === "boolean" ? (value ? "Pass" : "Fail") : "Unavailable"
  }));
  const piotroskiState = resolvePiotroskiScoreState(result);
  const availableCriteria = asNumber(result.available_criteria);
  const score = piotroskiState.rawScore;
  const normalizedScore = piotroskiState.score;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Reported Score", value: formatPiotroskiDisplay(piotroskiState) },
          { label: "Available Signals", value: availableCriteria === null ? "—" : `${availableCriteria}/9` },
          { label: "Comparison Score", value: formatScore9(normalizedScore) },
          { label: "Equity Proxy", value: formatCompactNumber(asNumber(result.equity_proxy)) }
        ]}
      />

      <ChartShell title="Piotroski Criteria">
        <ResponsiveContainer>
          <BarChart data={criteria}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} interval={0} angle={-18} textAnchor="end" height={70} />
            <YAxis domain={[0, 1]} ticks={[0, 1]} stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(_value, _name, item) => item.payload.display}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {criteria.map((entry) => (
                <Cell key={entry.label} fill={entry.value === 1 ? "#00FF41" : entry.value === 0 ? "#ff4d6d" : "#8b949e"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartShell>

      <CompactTable
        title="Piotroski Number Table"
        columns={[
          { key: "criterion", label: "Criterion" },
          { key: "value", label: "Result", align: "right" }
        ]}
        rows={criteria.map((entry) => ({ criterion: entry.label, value: entry.display }))}
      />
    </div>
  );
}

function AltmanModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  const factors = Object.entries(asRecord(result.factors)).map(([key, value]) => ({
    label: titleCase(key),
    value: asNumber(value),
    formatted: formatPercent(asNumber(value))
  }));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Altman Proxy", value: formatSigned(asNumber(result.z_score_approximate)) },
          { label: "Status", value: String(result.status ?? "—") },
          { label: "Filing Type", value: String(result.filing_type ?? "—") },
          { label: "Period End", value: String(result.period_end ?? "—") }
        ]}
      />

      <ChartShell title="Altman Proxy Factors">
        <ResponsiveContainer>
          <BarChart data={factors}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} interval={0} angle={-12} textAnchor="end" height={60} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(_value, _name, item) => item.payload.formatted}
            />
            <ReferenceLine y={0} stroke="var(--panel-border)" />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {factors.map((entry, index) => (
                <Cell key={entry.label} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartShell>

      <CompactTable
        title="Altman Number Table"
        columns={[
          { key: "metric", label: "Metric" },
          { key: "value", label: "Value", align: "right" }
        ]}
        rows={[
          { metric: "Altman Proxy", value: formatSigned(asNumber(result.z_score_approximate)) },
          ...factors.map((entry) => ({ metric: entry.label, value: entry.formatted })),
          {
            metric: "Missing Factors",
            value: asArray(result.missing_factors)
              .map((entry) => titleCase(String(entry)))
              .join(", ") || "—"
          }
        ]}
      />
    </div>
  );
}

function RatiosModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  const values = asRecord(result.values);
  const chartKeys = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "return_on_assets",
    "return_on_equity",
    "free_cash_flow_margin"
  ];
  const chartData = chartKeys.map((key) => ({
    label: titleCase(key),
    value: asNumber(values[key]),
    formatted: formatPercent(asNumber(values[key]))
  }));
  const tableRows = Object.entries(values).map(([key, value]) => ({
    metric: titleCase(key),
    value: formatRatioMetric(key, asNumber(value))
  }));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Period End", value: String(result.period_end ?? "—") },
          { label: "Previous Period", value: String(result.previous_period_end ?? "—") },
          { label: "Net Margin", value: formatPercent(asNumber(values.net_margin)) },
          { label: "ROE", value: formatPercent(asNumber(values.return_on_equity)) }
        ]}
      />

      <ChartShell title="Core Ratio Snapshot">
        <ResponsiveContainer>
          <BarChart data={chartData}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} interval={0} angle={-12} textAnchor="end" height={60} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(_value, _name, item) => item.payload.formatted}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {chartData.map((entry, index) => (
                <Cell key={entry.label} fill={CHART_COLORS[index % CHART_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartShell>

      <CompactTable
        title="Ratio Number Table"
        columns={[
          { key: "metric", label: "Metric" },
          { key: "value", label: "Value", align: "right" }
        ]}
        rows={tableRows}
      />
    </div>
  );
}

function FallbackModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  return (
    <CompactTable
      title="Model Output"
      columns={[
        { key: "metric", label: "Metric" },
        { key: "value", label: "Value", align: "right" }
      ]}
      rows={Object.entries(result).map(([key, value]) => ({ metric: titleCase(key), value: formatUnknown(value) }))}
    />
  );
}

function StateMessage({ result }: { result: Record<string, unknown> }) {
  return (
    <div className="text-muted" style={{ lineHeight: 1.6 }}>
      {String(result.reason ?? "This model does not have enough normalized financial data yet.")}
    </div>
  );
}

function MetricStrip({ metrics }: { metrics: Array<{ label: string; value: string }> }) {
  return (
    <div className="metric-grid">
      {metrics.map((metric) => (
        <div key={metric.label} className="metric-card">
          <div className="metric-label">{metric.label}</div>
          <div className="metric-value">{metric.value}</div>
        </div>
      ))}
    </div>
  );
}

function ChartShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gap: 12,
        minHeight: 320,
        padding: 12,
        borderRadius: 12,
        border: "1px solid var(--panel-border)",
        background: "var(--panel)"
      }}
    >
      <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-muted)" }}>{title}</div>
      <div style={{ width: "100%", height: 260 }}>{children}</div>
    </div>
  );
}

type TableColumn = { key: string; label: string; align?: "left" | "right" };

function CompactTable({
  title,
  columns,
  rows
}: {
  title: string;
  columns: TableColumn[];
  rows: Array<Record<string, string>>;
}) {
  return (
    <div
      style={{
        borderRadius: 12,
        border: "1px solid var(--panel-border)",
        overflow: "hidden",
        background: "var(--panel)"
      }}
    >
      <div style={{ padding: "12px 14px", fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--text-muted)" }}>
        {title}
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={{
                  textAlign: column.align ?? "left",
                  padding: "10px 14px",
                  color: "var(--text-muted)",
                  borderTop: "1px solid var(--panel-border)",
                  borderBottom: "1px solid var(--panel-border)",
                  fontWeight: 600
                }}
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  style={{
                    textAlign: column.align ?? "left",
                    padding: "10px 14px",
                    borderBottom: rowIndex === rows.length - 1 ? "none" : "1px solid var(--panel-border)",
                    color: column.align === "right" ? "var(--text)" : "var(--text-soft)",
                    fontVariantNumeric: column.align === "right" ? "tabular-nums" : undefined
                  }}
                >
                  {row[column.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((entry): entry is Record<string, unknown> => Boolean(entry) && typeof entry === "object" && !Array.isArray(entry));
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatMultiple(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(2)}x`;
}

function formatScore9(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return `${value.toFixed(1)}/9`;
}

function formatSigned(value: number | null): string {
  if (value === null) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2, signDisplay: "exceptZero" }).format(value);
}

function formatRatioMetric(metric: string, value: number | null): string {
  if (value === null) {
    return "—";
  }

  if (metric === "asset_turnover") {
    return formatMultiple(value);
  }

  return formatPercent(value);
}

function formatUnknown(value: unknown): string {
  if (typeof value === "number") {
    return Math.abs(value) >= 1000 ? formatCompactNumber(value) : String(value);
  }
  if (typeof value === "boolean") {
    return value ? "True" : "False";
  }
  if (typeof value === "string") {
    return value;
  }
  return JSON.stringify(value);
}




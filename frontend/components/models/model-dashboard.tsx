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
  CHART_SERIES_COLORS,
  RECHARTS_TOOLTIP_PROPS,
  chartLegendStyle,
  chartTick
} from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { ModelPayload } from "@/lib/types";

const MODEL_ORDER = ["dcf", "reverse_dcf", "residual_income", "roic", "capital_allocation", "dupont", "piotroski", "altman_z", "ratios"];
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
  const status = String(model.result.model_status ?? model.result.status ?? "supported");
  const explanation = String(model.result.explanation ?? "View discount rate, terminal assumptions, and data provenance used in this result.");
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
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <StatusBadge status={status} />
          <span className="pill" title="View discount rate, terminal assumptions, and data provenance used in this result.">
            Assumptions visible
          </span>
        </div>
      </div>
      {status !== "supported" ? <div className="text-muted">{explanation}</div> : null}
      {renderModelContent(model)}
    </section>
  );
}

function renderModelContent(model: ModelPayload) {
  switch (model.model_name) {
    case "dcf":
      return <DcfModelView model={model} />;
    case "reverse_dcf":
      return <ReverseDcfModelView model={model} />;
    case "residual_income":
      return <ResidualIncomeModelView model={model} />;
    case "roic":
      return <RoicModelView model={model} />;
    case "capital_allocation":
      return <CapitalAllocationModelView model={model} />;
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
  if (isUnavailableStatus(result)) {
    return <StateMessage result={result} />;
  }

  const assumptions = asRecord(result.assumptions);
  const priceSnapshot = asRecord(result.price_snapshot);
  const applicability = asRecord(result.applicability);
  const inputQuality = asRecord(result.input_quality);
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
          { label: "Enterprise Value", value: formatCompactNumber(asNumber(result.enterprise_value)) },
          { label: "Equity Value", value: formatCompactNumber(asNumber(result.equity_value)) },
          { label: "Fair Value / Share", value: formatCompactNumber(asNumber(result.fair_value_per_share)) },
          { label: "Net Debt", value: formatCompactNumber(asNumber(result.net_debt)) },
          { label: "PV Cash Flows", value: formatCompactNumber(asNumber(result.present_value_of_cash_flows)) },
          { label: "Terminal PV", value: formatCompactNumber(asNumber(result.terminal_value_present_value)) },
          { label: "Discount Rate", value: formatPercent(asNumber(assumptions.discount_rate)) },
          { label: "Confidence", value: String(result.confidence_summary ?? "—") }
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
            { metric: "Projection Years", value: String(assumptions.projection_years ?? "—") },
            { metric: "Confidence Summary", value: String(result.confidence_summary ?? "—") },
            { metric: "Applicable", value: applicability.is_supported === false ? "No" : "Yes" },
            { metric: "Price Source", value: String(priceSnapshot.price_source ?? "—") },
            { metric: "Price Date", value: String(priceSnapshot.price_date ?? "—") },
            { metric: "Starting FCF Proxied", value: inputQuality.starting_cash_flow_proxied ? "Yes" : "No" },
            { metric: "Capital Structure Proxied", value: inputQuality.capital_structure_proxied ? "Yes" : "No" }
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

      <AssumptionProvenanceTable provenance={asRecord(result.assumption_provenance)} />
    </div>
  );
}

function ReverseDcfModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  if (isUnavailableStatus(result)) {
    return <StateMessage result={result} />;
  }

  const priceSnapshot = asRecord(result.price_snapshot);
  const solveMetadata = asRecord(result.solve_metadata);
  const heatmap = asArray(result.heatmap).map((item) => ({
    label: `${formatPercent(asNumber(item.growth))} / ${formatPercent(asNumber(item.margin))}`,
    value: asNumber(item.value_gap),
  }));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Implied Growth", value: formatPercent(asNumber(result.implied_growth)) },
          { label: "Implied Margin", value: formatPercent(asNumber(result.implied_margin)) },
          { label: "Current Operating Margin", value: formatPercent(asNumber(result.current_operating_margin)) },
          { label: "Price Date", value: String(priceSnapshot.price_date ?? "—") },
          { label: "Price Source", value: String(priceSnapshot.price_source ?? "—") },
          { label: "Solve Method", value: String(solveMetadata.method ?? "—") },
          { label: "Confidence", value: String(result.confidence_summary ?? "—") },
        ]}
      />

      <ChartShell title="Reverse DCF Heatmap (Growth / Margin)">
        <ResponsiveContainer>
          <BarChart data={heatmap}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(10)} interval={0} angle={-24} textAnchor="end" height={86} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number | string) => typeof value === "number" ? value.toFixed(3) : value} />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {heatmap.map((entry, index) => (
                <Cell key={`${entry.label}-${index}`} fill={CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartShell>

      <AssumptionProvenanceTable provenance={asRecord(result.assumption_provenance)} />
    </div>
  );
}

function ResidualIncomeModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  if (isUnavailableStatus(result)) {
    return <StateMessage result={result} />;
  }

  const inputs = asRecord(result.inputs);
  const intrinsic = asRecord(result.intrinsic_value);
  const projections = asArray(result.projections).map((item) => ({
    year: String(item.year ?? "—"),
    bookEquity: formatCompactNumber(asNumber(item.book_equity)),
    roe: formatPercent(asNumber(item.roe)),
    residualIncome: formatCompactNumber(asNumber(item.residual_income)),
    pvResidualIncome: formatCompactNumber(asNumber(item.pv_residual_income)),
  }));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Intrinsic Value / Share", value: formatCompactNumber(asNumber(intrinsic.intrinsic_value_per_share)) },
          { label: "Book Equity / Share", value: formatCompactNumber(asNumber(intrinsic.book_equity_per_share)) },
          { label: "PV Residual Income / Share", value: formatCompactNumber(asNumber(intrinsic.pv_residual_income_per_share)) },
          { label: "Terminal Value / Share", value: formatCompactNumber(asNumber(intrinsic.terminal_value_per_share)) },
          { label: "Upside vs Price", value: formatPercent(asNumber(intrinsic.upside_vs_price)) },
          { label: "Cost of Equity", value: formatPercent(asNumber(inputs.cost_of_equity)) },
          { label: "Average ROE", value: formatPercent(asNumber(inputs.avg_roe_5y)) },
          { label: "Trust Summary", value: String(result.trust_summary ?? "—") },
        ]}
      />

      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 0.85fr) minmax(420px, 1.15fr)", gap: 14 }}>
        <CompactTable
          title="Residual Income Inputs"
          columns={[
            { key: "metric", label: "Metric" },
            { key: "value", label: "Value", align: "right" },
          ]}
          rows={[
            { metric: "Book Equity", value: formatCompactNumber(asNumber(inputs.book_equity)) },
            { metric: "Net Income", value: formatCompactNumber(asNumber(inputs.net_income)) },
            { metric: "ROE", value: formatPercent(asNumber(inputs.roe)) },
            { metric: "Average ROE (5Y)", value: formatPercent(asNumber(inputs.avg_roe_5y)) },
            { metric: "Cost of Equity", value: formatPercent(asNumber(inputs.cost_of_equity)) },
            { metric: "Terminal Growth", value: formatPercent(asNumber(inputs.terminal_growth_rate)) },
            { metric: "Payout Ratio", value: formatPercent(asNumber(inputs.payout_ratio_assumed)) },
            { metric: "Primary For Sector", value: result.primary_for_sector ? "Yes" : "No" },
          ]}
        />
        <CompactTable
          title="Projection Table"
          columns={[
            { key: "year", label: "Year" },
            { key: "bookEquity", label: "Book Equity", align: "right" },
            { key: "roe", label: "ROE", align: "right" },
            { key: "residualIncome", label: "Residual Income", align: "right" },
            { key: "pvResidualIncome", label: "PV RI", align: "right" },
          ]}
          rows={projections}
        />
      </div>

      <AssumptionProvenanceTable provenance={asRecord(result.assumption_provenance)} />
    </div>
  );
}

function RoicModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  if (isUnavailableStatus(result)) {
    return <StateMessage result={result} />;
  }
  const trend = asArray(result.trend).map((item) => ({
    period: String(item.period_end ?? "—"),
    roic: asNumber(item.roic),
    reinvestment: asNumber(item.reinvestment_rate),
    spread: asNumber(item.spread_vs_capital_cost),
  }));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "ROIC", value: formatPercent(asNumber(result.roic)) },
          { label: "Incremental ROIC", value: formatPercent(asNumber(result.incremental_roic)) },
          { label: "Reinvestment", value: formatPercent(asNumber(result.reinvestment_rate)) },
          { label: "Spread", value: formatPercent(asNumber(result.spread_vs_capital_cost_proxy)) },
        ]}
      />
      <ChartShell title="ROIC Trend">
        <ResponsiveContainer>
          <LineChart data={trend}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(v) => formatPercent(Number(v))} />
            <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number | string) => typeof value === "number" ? formatPercent(value) : value} />
            <Legend wrapperStyle={chartLegendStyle()} />
            <Line dataKey="roic" name="ROIC" stroke="#00FF41" strokeWidth={2} dot={{ r: 2 }} />
            <Line dataKey="reinvestment" name="Reinvestment" stroke="#00E5FF" strokeWidth={2} dot={{ r: 2 }} />
            <Line dataKey="spread" name="Spread" stroke="#FFD700" strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </ChartShell>
      <AssumptionProvenanceTable provenance={asRecord(result.assumption_provenance)} />
    </div>
  );
}

function CapitalAllocationModelView({ model }: { model: ModelPayload }) {
  const result = asRecord(model.result);
  if (isUnavailableStatus(result)) {
    return <StateMessage result={result} />;
  }
  const series = asArray(result.series).map((item) => ({
    period: String(item.period_end ?? "—"),
    dividends: asNumber(item.dividends),
    buybacks: asNumber(item.buybacks),
    sbc: asNumber(item.stock_based_compensation),
  }));

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <MetricStrip
        metrics={[
          { label: "Shareholder Yield", value: formatPercent(asNumber(result.shareholder_yield)) },
          { label: "Net Distribution", value: formatCompactNumber(asNumber(result.net_shareholder_distribution)) },
          { label: "Debt Financing Signal", value: formatCompactNumber(asNumber(result.debt_financing_signal)) },
          { label: "Confidence", value: String(result.confidence_summary ?? "—") },
        ]}
      />
      <ChartShell title="Capital Allocation Stack">
        <ResponsiveContainer>
          <BarChart data={series}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(v) => formatCompactNumber(Number(v))} />
            <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number | string) => typeof value === "number" ? formatCompactNumber(value) : value} />
            <Legend wrapperStyle={chartLegendStyle()} />
            <Bar dataKey="dividends" stackId="cap" name="Dividends" fill="#00FF41" />
            <Bar dataKey="buybacks" stackId="cap" name="Buybacks" fill="#00E5FF" />
            <Bar dataKey="sbc" stackId="cap" name="SBC" fill="#FF6B6B" />
          </BarChart>
        </ResponsiveContainer>
      </ChartShell>
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
                <Cell key={entry.label} fill={CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length]} />
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
                <Cell key={entry.label} fill={CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length]} />
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
                <Cell key={entry.label} fill={CHART_SERIES_COLORS[index % CHART_SERIES_COLORS.length]} />
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
  const applicability = asRecord(result.applicability);
  const matches = asArray(applicability.matches)
    .map((item) => {
      const field = typeof item.field === "string" ? item.field : "field";
      const keyword = typeof item.keyword === "string" ? item.keyword : "keyword";
      return `${field}: ${keyword}`;
    })
    .filter(Boolean);

  return (
    <div className="text-muted" style={{ lineHeight: 1.6 }}>
      {String(result.reason ?? "This model does not have enough normalized financial data yet.")}
      {matches.length ? <div style={{ marginTop: 8 }}>Applicability flags: {matches.join(", ")}</div> : null}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  if (status === "partial") {
    return <span className="pill" title="This model used incomplete financial inputs; results are directional only.">Partial inputs</span>;
  }
  if (status === "proxy") {
    return <span className="pill" title="This model used approximation logic where direct inputs were unavailable.">Proxy output</span>;
  }
  if (status === "insufficient_data") {
    return <span className="pill">Insufficient data</span>;
  }
  if (status === "unsupported") {
    return <span className="pill">Unsupported</span>;
  }
  return <span className="pill">Supported</span>;
}

function isUnavailableStatus(result: Record<string, unknown>): boolean {
  const status = String(result.model_status ?? result.status ?? "supported");
  return status === "insufficient_data" || status === "unsupported";
}

function AssumptionProvenanceTable({ provenance }: { provenance: Record<string, unknown> }) {
  const riskFree = asRecord(provenance.risk_free_rate);
  const discountInputs = asRecord(provenance.discount_rate_inputs);
  const terminal = asRecord(provenance.terminal_assumptions);
  if (!Object.keys(riskFree).length && !Object.keys(discountInputs).length && !Object.keys(terminal).length) {
    return null;
  }
  return (
    <CompactTable
      title="Assumption Provenance"
      columns={[
        { key: "metric", label: "Metric" },
        { key: "value", label: "Value", align: "right" },
      ]}
      rows={[
        { metric: "Risk-free source", value: String(riskFree.source_name ?? "—") },
        { metric: "Observation date", value: String(riskFree.observation_date ?? "—") },
        { metric: "Tenor", value: String(riskFree.tenor ?? "—") },
        { metric: "Risk-free rate", value: formatPercent(asNumber(riskFree.rate_used)) },
        { metric: "Discount input", value: formatPercent(asNumber(discountInputs.discount_rate ?? discountInputs.risk_free_rate)) },
        { metric: "Terminal growth", value: formatPercent(asNumber(terminal.terminal_growth_rate ?? discountInputs.terminal_growth)) },
      ]}
    />
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

  if (metric === "asset_turnover" || metric === "interest_coverage" || metric === "net_debt_to_fcf") {
    return formatMultiple(value);
  }

  if (metric === "cash_conversion") {
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




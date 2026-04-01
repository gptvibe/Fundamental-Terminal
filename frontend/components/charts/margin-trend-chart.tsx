"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { difference, findPointForStatement, formatSignedPointDelta, formatStatementAxisLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);

type PeriodView = "annual" | "quarterly";

type MarginDatum = {
  period: string;
  periodEnd: string;
  filingType: string;
  grossMargin: number | null;
  operatingMargin: number | null;
  netMargin: number | null;
  fcfMargin: number | null;
};

function pct(num: number | null, denom: number | null): number | null {
  if (num == null || denom == null || denom === 0) return null;
  return Math.round((num / denom) * 10000) / 100; // two-decimal percent
}

function buildMarginSeries(statements: FinancialPayload[], cadence: "annual" | "quarterly" | "ttm" | "reported"): MarginDatum[] {
  return [...statements]
    .sort((a, b) => a.period_end.localeCompare(b.period_end))
    .map((s) => ({
      period: formatStatementAxisLabel(s, cadence),
      periodEnd: s.period_end,
      filingType: s.filing_type,
      grossMargin: pct(s.gross_profit, s.revenue),
      operatingMargin: pct(s.operating_income, s.revenue),
      netMargin: pct(s.net_income, s.revenue),
      fcfMargin: pct(s.free_cash_flow, s.revenue),
    }));
}

interface MarginTrendChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function MarginTrendChart({ financials, chartState }: MarginTrendChartProps) {
  const [periodView, setPeriodView] = useState<PeriodView>("annual");
  const selectedFinancial = chartState?.selectedFinancial ?? null;
  const comparisonFinancial = chartState?.comparisonFinancial ?? null;
  const useSharedState = Boolean(chartState);

  const annualStatements = useMemo(
    () => financials.filter((s) => ANNUAL_FORMS.has(s.filing_type)),
    [financials]
  );
  const quarterlyStatements = useMemo(
    () => financials.filter((s) => QUARTERLY_FORMS.has(s.filing_type)),
    [financials]
  );

  useEffect(() => {
    if (useSharedState) {
      return;
    }
    if (periodView === "annual" && annualStatements.length > 0) return;
    if (periodView === "quarterly" && quarterlyStatements.length > 0) return;
    if (annualStatements.length > 0) {
      setPeriodView("annual");
      return;
    }
    if (quarterlyStatements.length > 0) setPeriodView("quarterly");
  }, [annualStatements.length, periodView, quarterlyStatements.length, useSharedState]);

  const activeCadence: "annual" | "quarterly" | "ttm" | "reported" = useSharedState
    ? chartState?.effectiveCadence ?? chartState?.cadence ?? "annual"
    : periodView;
  const source = useSharedState ? financials : periodView === "annual" ? annualStatements : quarterlyStatements;
  const data = useMemo(() => buildMarginSeries(source, activeCadence), [activeCadence, source]);
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const latest = data.at(-1) ?? null;
  const summaryPoint = focusPoint ?? latest;
  const exportRows = useMemo(
    () => data.map((row) => ({ period: row.period, period_end: row.periodEnd, gross_margin: row.grossMargin, operating_margin: row.operatingMargin, net_margin: row.netMargin, fcf_margin: row.fcfMargin })),
    [data]
  );
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Periods", value: String(data.length) },
        { label: "Cadence", value: activeCadence.toUpperCase() },
        { label: "Source", value: "Cached filing history" },
      ]}
    />
  ) : null;

  return (
    <InteractiveChartFrame
      title="Margin trends"
      subtitle={data.length ? `${data.length} visible periods of margin history.` : "Awaiting margin history"}
      inspectorTitle="Margin trends"
      inspectorSubtitle="Gross, operating, net, and free-cash-flow margins across the visible filing history."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{ datasetKind: "time_series" }}
      annotations={[
        { label: "Gross Margin", color: "var(--positive)" },
        { label: "Operating Margin", color: "var(--accent)" },
        { label: "Net Margin", color: "var(--warning)" },
        { label: "FCF Margin", color: "#A855F7" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Visible periods {data.length}</span>
            <span className="pill">Cadence {activeCadence.toUpperCase()}</span>
            <span className="pill">Source: cached filing history</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Margin trends",
              title: "No revenue data is available yet to compute margin trends",
              message: "Margin trend charts appear once cached filings include revenue and the relevant margin components.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("margin-trends", "financials")}.png`,
        csvFileName: `${normalizeExportFileStem("margin-trends", "financials")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div className="cash-waterfall-shell">
            {chartState ? (
              <FinancialChartStateBar state={chartState} />
            ) : (
              <div className="cash-waterfall-toolbar">
                <div className="cash-waterfall-toggle-group">
                  <button
                    type="button"
                    className={`chart-chip${periodView === "annual" ? " chart-chip-active" : ""}`}
                    onClick={() => setPeriodView("annual")}
                    disabled={!annualStatements.length}
                  >
                    Annual
                  </button>
                  <button
                    type="button"
                    className={`chart-chip${periodView === "quarterly" ? " chart-chip-active" : ""}`}
                    onClick={() => setPeriodView("quarterly")}
                    disabled={!quarterlyStatements.length}
                  >
                    Quarterly
                  </button>
                </div>
                <span className="pill">{source.length} cached {periodView} filings</span>
              </div>
            )}

            {summaryPoint ? (
              <div className="cash-waterfall-meta">
                <span className="pill">Period {summaryPoint.period}</span>
                <span className="pill">Gross {formatMargin(summaryPoint.grossMargin)}</span>
                <span className="pill">Operating {formatMargin(summaryPoint.operatingMargin)}</span>
                <span className="pill">Net {formatMargin(summaryPoint.netMargin)}</span>
                <span className="pill">FCF {formatMargin(summaryPoint.fcfMargin)}</span>
              </div>
            ) : null}

            {summaryPoint && comparisonPoint ? (
              <div className="cash-waterfall-meta">
                <span className="pill tone-gold">Gross Δ {formatSignedPointDelta(difference(summaryPoint.grossMargin, comparisonPoint.grossMargin))}</span>
                <span className="pill tone-gold">Operating Δ {formatSignedPointDelta(difference(summaryPoint.operatingMargin, comparisonPoint.operatingMargin))}</span>
                <span className="pill tone-gold">Net Δ {formatSignedPointDelta(difference(summaryPoint.netMargin, comparisonPoint.netMargin))}</span>
                <span className="pill tone-gold">FCF Δ {formatSignedPointDelta(difference(summaryPoint.fcfMargin, comparisonPoint.fcfMargin))}</span>
              </div>
            ) : null}

            <div style={{ width: "100%", height: expanded ? 420 : 340 }}>
              <ResponsiveContainer>
                <LineChart data={data} margin={{ top: 10, right: expanded ? 20 : 14, left: 4, bottom: 8 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                  <YAxis
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick(expanded ? 11 : 10)}
                    tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
                    width={52}
                  />
                  <ReferenceLine y={0} stroke={CHART_AXIS_COLOR} strokeDasharray="4 2" />
                  {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} stroke="var(--warning)" strokeDasharray="4 3" /> : null}
                  {focusPoint ? <ReferenceLine x={focusPoint.period} stroke="var(--accent)" strokeDasharray="4 3" /> : null}
                  <Tooltip
                    {...RECHARTS_TOOLTIP_PROPS}
                    formatter={(value: number) => `${value.toFixed(1)}%`}
                  />
                  <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
                  <Line type="monotone" dataKey="grossMargin" name="Gross Margin" stroke="var(--positive)" strokeWidth={expanded ? 2.6 : 2.2} dot={false} connectNulls isAnimationActive={false} />
                  <Line type="monotone" dataKey="operatingMargin" name="Operating Margin" stroke="var(--accent)" strokeWidth={expanded ? 2.6 : 2.2} dot={false} connectNulls isAnimationActive={false} />
                  <Line type="monotone" dataKey="netMargin" name="Net Margin" stroke="var(--warning)" strokeWidth={expanded ? 2.6 : 2.2} dot={false} connectNulls isAnimationActive={false} />
                  <Line type="monotone" dataKey="fcfMargin" name="FCF Margin" stroke="#A855F7" strokeWidth={expanded ? 2.6 : 2.2} dot={false} connectNulls isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <PanelEmptyState message="No revenue data is available yet to compute margin trends." />
        )
      }
    />
  );
}

function formatMargin(value: number | null): string {
  if (value === null || Number.isNaN(value)) {
    return "\u2014";
  }
  return `${value.toFixed(1)}%`;
}

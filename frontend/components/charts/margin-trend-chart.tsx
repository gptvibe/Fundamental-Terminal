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

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatDate } from "@/lib/format";
import type { FinancialPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);

type PeriodView = "annual" | "quarterly";

type MarginDatum = {
  period: string;
  grossMargin: number | null;
  operatingMargin: number | null;
  netMargin: number | null;
  fcfMargin: number | null;
};

function pct(num: number | null, denom: number | null): number | null {
  if (num == null || denom == null || denom === 0) return null;
  return Math.round((num / denom) * 10000) / 100; // two-decimal percent
}

function buildMarginSeries(statements: FinancialPayload[]): MarginDatum[] {
  return [...statements]
    .sort((a, b) => a.period_end.localeCompare(b.period_end))
    .map((s) => ({
      period: formatDate(s.period_end),
      grossMargin: pct(s.gross_profit, s.revenue),
      operatingMargin: pct(s.operating_income, s.revenue),
      netMargin: pct(s.net_income, s.revenue),
      fcfMargin: pct(s.free_cash_flow, s.revenue),
    }));
}

export function MarginTrendChart({ financials }: { financials: FinancialPayload[] }) {
  const [periodView, setPeriodView] = useState<PeriodView>("annual");

  const annualStatements = useMemo(
    () => financials.filter((s) => ANNUAL_FORMS.has(s.filing_type)),
    [financials]
  );
  const quarterlyStatements = useMemo(
    () => financials.filter((s) => QUARTERLY_FORMS.has(s.filing_type)),
    [financials]
  );

  useEffect(() => {
    if (periodView === "annual" && annualStatements.length > 0) return;
    if (periodView === "quarterly" && quarterlyStatements.length > 0) return;
    if (annualStatements.length > 0) {
      setPeriodView("annual");
      return;
    }
    if (quarterlyStatements.length > 0) setPeriodView("quarterly");
  }, [annualStatements.length, periodView, quarterlyStatements.length]);

  const source = periodView === "annual" ? annualStatements : quarterlyStatements;
  const data = useMemo(() => buildMarginSeries(source), [source]);
  const latest = data.at(-1) ?? null;

  if (!data.length) {
    return <PanelEmptyState message="No revenue data is available yet to compute margin trends." />;
  }

  return (
    <div className="cost-structure-shell">
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

      {latest ? (
        <div className="cash-waterfall-meta">
          <span className="pill">Period {latest.period}</span>
          {latest.grossMargin != null && <span className="pill">Gross {latest.grossMargin.toFixed(1)}%</span>}
          {latest.operatingMargin != null && <span className="pill">Operating {latest.operatingMargin.toFixed(1)}%</span>}
          {latest.netMargin != null && <span className="pill">Net {latest.netMargin.toFixed(1)}%</span>}
          {latest.fcfMargin != null && <span className="pill">FCF {latest.fcfMargin.toFixed(1)}%</span>}
        </div>
      ) : null}

      <div style={{ width: "100%", height: 340 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 14, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis
              stroke={CHART_AXIS_COLOR}
              tick={chartTick()}
              tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
              width={52}
            />
            <ReferenceLine y={0} stroke={CHART_AXIS_COLOR} strokeDasharray="4 2" />
            <Tooltip
              {...RECHARTS_TOOLTIP_PROPS}
              formatter={(value: number) => `${value.toFixed(1)}%`}
            />
            <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
            <Line type="monotone" dataKey="grossMargin" name="Gross Margin" stroke="#00FF41" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="operatingMargin" name="Operating Margin" stroke="#00E5FF" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="netMargin" name="Net Margin" stroke="#FFD700" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="fcfMargin" name="FCF Margin" stroke="#A855F7" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

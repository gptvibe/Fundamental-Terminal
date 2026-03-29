"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import type { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { buildOperatingCostSeries } from "@/lib/financial-chart-transforms";
import { formatCompactNumber, formatDate } from "@/lib/format";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);

type PeriodView = "annual" | "quarterly";

export function OperatingCostStructureChart({ financials }: { financials: FinancialPayload[] }) {
  const [periodView, setPeriodView] = useState<PeriodView>("annual");

  const annualStatements = useMemo(
    () => financials.filter((statement) => ANNUAL_FORMS.has(statement.filing_type)),
    [financials]
  );
  const quarterlyStatements = useMemo(
    () => financials.filter((statement) => QUARTERLY_FORMS.has(statement.filing_type)),
    [financials]
  );

  useEffect(() => {
    if (periodView === "annual" && annualStatements.length > 0) {
      return;
    }
    if (periodView === "quarterly" && quarterlyStatements.length > 0) {
      return;
    }
    if (annualStatements.length > 0) {
      setPeriodView("annual");
      return;
    }
    if (quarterlyStatements.length > 0) {
      setPeriodView("quarterly");
    }
  }, [annualStatements.length, periodView, quarterlyStatements.length]);

  const source = periodView === "annual" ? annualStatements : quarterlyStatements;
  const data = useMemo(() => buildOperatingCostSeries(source), [source]);
  const latest = data.at(-1) ?? null;

  if (!data.length) {
    return <PanelEmptyState message="No SG&A, R&D, stock-based compensation, interest, or tax expense history is available yet." />;
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
          <span className="pill">Period {formatDate(latest.periodEnd)}</span>
          <span className="pill">SG&A {formatCompactNumber(latest.sga)}</span>
          <span className="pill">R&D {formatCompactNumber(latest.researchAndDevelopment)}</span>
          <span className="pill">SBC {formatCompactNumber(latest.stockBasedCompensation)}</span>
        </div>
      ) : null}

      <div style={{ width: "100%", height: 340 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 14, left: 4, bottom: 8 }}>
            <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
            <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} width={82} />
            <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
            <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
            <Line type="monotone" dataKey="sga" name="SG&A" stroke="var(--accent)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="researchAndDevelopment" name="R&D" stroke="var(--warning)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="stockBasedCompensation" name="Stock-Based Comp" stroke="var(--positive)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="interestExpense" name="Interest Expense" stroke="var(--negative)" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
            <Line type="monotone" dataKey="incomeTaxExpense" name="Income Tax Expense" stroke="#A855F7" strokeWidth={2.2} dot={false} connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}


"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { FinancialChartStateBar } from "@/components/charts/financial-chart-state-bar";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { FinancialPayload } from "@/lib/types";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber } from "@/lib/format";
import { difference, findPointForStatement, formatSignedCompactDelta, formatStatementAxisLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";

interface BalanceSheetChartProps {
  financials: FinancialPayload[];
  chartState?: SharedFinancialChartState;
}

export function BalanceSheetChart({ financials, chartState }: BalanceSheetChartProps) {
  const selectedFinancial = chartState?.selectedFinancial ?? null;
  const comparisonFinancial = chartState?.comparisonFinancial ?? null;
  const data = useMemo(
    () =>
      [...financials]
        .reverse()
        .map((item) => ({
          period: formatStatementAxisLabel(item, chartState?.effectiveCadence ?? chartState?.cadence),
          periodEnd: item.period_end,
          filingType: item.filing_type,
          assets: item.total_assets,
          liabilities: item.total_liabilities,
          equity:
            item.total_assets != null && item.total_liabilities != null
              ? item.total_assets - item.total_liabilities
              : null,
        })),
    [chartState?.cadence, chartState?.effectiveCadence, financials]
  );
  const focusPoint = useMemo(() => findPointForStatement(data, selectedFinancial), [data, selectedFinancial]);
  const comparisonPoint = useMemo(() => findPointForStatement(data, comparisonFinancial), [comparisonFinancial, data]);
  const latest = data.at(-1) ?? null;
  const summaryPoint = focusPoint ?? latest;
  const exportRows = useMemo(
    () => data.map((row) => ({ period: row.period, period_end: row.periodEnd, assets: row.assets, liabilities: row.liabilities, equity: row.equity })),
    [data]
  );
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Periods", value: String(data.length) },
        { label: "Focus", value: summaryPoint?.period ?? "Latest" },
        { label: "Source", value: "Cached balance-sheet filings" },
      ]}
    />
  ) : null;

  return (
    <InteractiveChartFrame
      title="Balance sheet history"
      subtitle={data.length ? `${data.length} reported balance-sheet periods.` : "Awaiting balance-sheet history"}
      inspectorTitle="Balance sheet history"
      inspectorSubtitle="Assets, liabilities, and net assets across the visible filing history."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{ datasetKind: "time_series" }}
      annotations={[
        { label: "Assets", color: "var(--accent)" },
        { label: "Liabilities", color: "var(--warning)" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Visible periods {data.length}</span>
            <span className="pill">Source: cached balance-sheet filings</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Balance sheet",
              title: "No balance-sheet history yet",
              message: "This chart fills in once cached filings include balance-sheet history.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("balance-sheet-history", "financials")}.png`,
        csvFileName: `${normalizeExportFileStem("balance-sheet-history", "financials")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div className="cash-waterfall-shell">
            {chartState ? <FinancialChartStateBar state={chartState} /> : null}

            {summaryPoint ? (
              <div className="cash-waterfall-meta">
                <span className="pill">Assets {formatCompactNumber(summaryPoint.assets)}</span>
                <span className="pill">Liabilities {formatCompactNumber(summaryPoint.liabilities)}</span>
                <span className="pill">Net Assets {formatCompactNumber(summaryPoint.equity)}</span>
              </div>
            ) : null}

            {summaryPoint && comparisonPoint ? (
              <div className="cash-waterfall-meta">
                <span className="pill tone-gold">Assets Δ {formatSignedCompactDelta(difference(summaryPoint.assets, comparisonPoint.assets))}</span>
                <span className="pill tone-gold">Liabilities Δ {formatSignedCompactDelta(difference(summaryPoint.liabilities, comparisonPoint.liabilities))}</span>
                <span className="pill tone-gold">Net Assets Δ {formatSignedCompactDelta(difference(summaryPoint.equity, comparisonPoint.equity))}</span>
              </div>
            ) : null}

            <div style={{ width: "100%", height: expanded ? 400 : 320 }}>
              <ResponsiveContainer>
                <BarChart data={data}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatCompactNumber(Number(value))} />
                  {comparisonPoint ? <ReferenceLine x={comparisonPoint.period} stroke="var(--warning)" strokeDasharray="4 3" /> : null}
                  {focusPoint ? <ReferenceLine x={focusPoint.period} stroke="var(--accent)" strokeDasharray="4 3" /> : null}
                  <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
                  <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
                  <Bar dataKey="assets" fill="var(--accent)" radius={[2, 2, 0, 0]} />
                  <Bar dataKey="liabilities" fill="var(--warning)" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <PanelEmptyState message="No balance-sheet history is available yet." />
        )
      }
    />
  );
}

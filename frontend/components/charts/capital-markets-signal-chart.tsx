"use client";

import { useMemo } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { buildCapitalMarketsSignalSeries } from "@/lib/financial-chart-transforms";
import { normalizeExportFileStem } from "@/lib/export";
import { formatCompactNumber } from "@/lib/format";
import type { FilingEventPayload, FinancialPayload } from "@/lib/types";

export function CapitalMarketsSignalChart({ financials, events }: { financials: FinancialPayload[]; events: FilingEventPayload[] }) {
  const data = useMemo(() => buildCapitalMarketsSignalSeries(financials, events), [events, financials]);
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Periods", value: String(data.length) },
        { label: "Events", value: String(events.length) },
        { label: "Source", value: "Filings + current reports" },
      ]}
    />
  ) : null;
  const exportRows = useMemo(
    () => data.map((row) => ({ period: row.period, financing_events: row.financingEvents, debt_changes: row.debtChanges })),
    [data]
  );

  return (
    <InteractiveChartFrame
      title="Financing signal tracker"
      subtitle={data.length ? `${data.length} periods of debt-change and financing-event history.` : "Awaiting financing signal history"}
      inspectorTitle="Financing signal tracker"
      inspectorSubtitle="Debt-change history from filings overlaid with financing and capital-markets current reports."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{ datasetKind: "time_series" }}
      annotations={[
        { label: "Financing Events", color: "var(--warning)" },
        { label: "Debt Changes", color: "var(--accent)" },
      ]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Visible periods {data.length}</span>
            <span className="pill">Current reports {events.length}</span>
            <span className="pill">Source: financial filings plus financing events</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Capital markets",
              title: "No financing signal history yet",
              message: "This chart fills in once the cache includes debt-change fields or financing-related current reports.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("capital-markets-signal", "capital-markets")}.png`,
        csvFileName: `${normalizeExportFileStem("capital-markets-signal", "capital-markets")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div style={{ width: "100%", height: expanded ? 400 : 320 }}>
            <ResponsiveContainer>
              <ComposedChart data={data} margin={{ top: 8, right: expanded ? 24 : 16, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                <YAxis yAxisId="events" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} allowDecimals={false} width={46} />
                <YAxis yAxisId="debt" orientation="right" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} tickFormatter={(value) => formatCompactNumber(Number(value))} width={72} />
                <Tooltip
                  {...RECHARTS_TOOLTIP_PROPS}
                  formatter={(value: number, name: string) => (name === "Financing Events" ? String(value) : formatCompactNumber(value))}
                />
                <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}>{value}</span>} />
                <Bar yAxisId="events" dataKey="financingEvents" name="Financing Events" fill="var(--warning)" radius={[2, 2, 0, 0]} />
                <Line yAxisId="debt" type="monotone" dataKey="debtChanges" name="Debt Changes" stroke="var(--accent)" strokeWidth={expanded ? 2.8 : 2.4} dot={{ r: expanded ? 4 : 3, fill: "var(--accent)" }} connectNulls isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Capital markets</div>
            <div className="grid-empty-title">No financing signal history yet</div>
            <div className="grid-empty-copy">This chart fills in once the cache includes debt-change fields or financing-related current reports.</div>
          </div>
        )
      }
    />
  );
}

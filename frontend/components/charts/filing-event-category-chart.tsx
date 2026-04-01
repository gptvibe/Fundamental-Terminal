"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import type { FilingEventPayload } from "@/lib/types";

const CATEGORY_COLORS: Record<string, string> = {
  Earnings: "var(--accent)",
  Accounting: "#F97316",
  Leadership: "var(--warning)",
  Deal: "var(--negative)",
  Financing: "var(--positive)",
  "Capital Markets": "var(--positive)",
  "General Update": "#94A3B8",
  Other: "#C084FC"
};

export function FilingEventCategoryChart({ events }: { events: FilingEventPayload[] }) {
  const data = useMemo(() => buildChartData(events), [events]);
  const exportRows = useMemo(() => data.map((row) => ({ category: row.category, events: row.count })), [data]);
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Categories", value: String(data.length) },
        { label: "Events", value: String(events.length) },
        { label: "Source", value: "SEC current reports" },
      ]}
    />
  ) : null;

  return (
    <InteractiveChartFrame
      title="8-K event categories"
      subtitle={data.length ? `${events.length} current reports across ${data.length} categories.` : "Awaiting 8-K events"}
      inspectorTitle="8-K event categories"
      inspectorSubtitle="Category distribution for the currently cached current-report event stream."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{ datasetKind: "categorical_snapshot" }}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Source: SEC current reports</span>
            <span className="pill">Visible categories {data.length}</span>
            <span className="pill">Visible events {events.length}</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Event intelligence",
              title: "No 8-K events yet",
              message: "This chart fills in once SEC submissions include current reports for the company.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("filing-event-category-mix", "events")}.png`,
        csvFileName: `${normalizeExportFileStem("filing-event-category-mix", "events")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div style={{ width: "100%", height: expanded ? 380 : 300 }}>
            <ResponsiveContainer>
              <BarChart data={data} margin={{ top: 8, right: expanded ? 24 : 16, left: 0, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="category" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} interval={0} angle={-14} textAnchor="end" height={62} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} allowDecimals={false} width={48} />
                <Tooltip {...RECHARTS_TOOLTIP_PROPS} />
                <Bar dataKey="count" name="Events" radius={[2, 2, 0, 0]}>
                  {data.map((entry) => (
                    <Cell key={entry.category} fill={CATEGORY_COLORS[entry.category] ?? CATEGORY_COLORS.Other} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Event intelligence</div>
            <div className="grid-empty-title">No 8-K events yet</div>
            <div className="grid-empty-copy">This chart fills in once SEC submissions include current reports for the company.</div>
          </div>
        )
      }
    />
  );
}

function buildChartData(events: FilingEventPayload[]) {
  const grouped = new Map<string, number>();
  for (const event of events) {
    grouped.set(event.category, (grouped.get(event.category) ?? 0) + 1);
  }
  return [...grouped.entries()]
    .map(([category, count]) => ({ category, count }))
    .sort((left, right) => right.count - left.count || left.category.localeCompare(right.category));
}
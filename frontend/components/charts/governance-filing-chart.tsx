"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ChartSourceBadges } from "@/components/charts/chart-framework";
import { InteractiveChartFrame } from "@/components/charts/interactive-chart-frame";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { normalizeExportFileStem } from "@/lib/export";
import type { GovernanceFilingPayload } from "@/lib/types";

export function GovernanceFilingChart({ filings }: { filings: GovernanceFilingPayload[] }) {
  const data = useMemo(() => buildChartData(filings), [filings]);
  const exportRows = useMemo(() => data.map((row) => ({ form: row.label, filings: row.count })), [data]);
  const badgeArea = data.length ? (
    <ChartSourceBadges
      badges={[
        { label: "Forms", value: String(data.length) },
        { label: "Filings", value: String(filings.length) },
        { label: "Source", value: "SEC proxy materials" },
      ]}
    />
  ) : null;

  return (
    <InteractiveChartFrame
      title="Proxy filing mix"
      subtitle={data.length ? `${filings.length} filings across ${data.length} proxy forms.` : "Awaiting governance filings"}
      inspectorTitle="Proxy filing mix"
      inspectorSubtitle="Governance filings grouped by proxy form across the cached filing record."
      hideInlineHeader
      badgeArea={badgeArea}
      controlState={{ datasetKind: "categorical_snapshot" }}
      annotations={[{ label: "Filings", color: "var(--positive)" }]}
      footer={(
        <div className="chart-inspector-footer-stack">
          <div className="chart-inspector-footer-pill-row">
            <span className="pill">Source: SEC proxy and proxy-related materials</span>
            <span className="pill">Visible forms {data.length}</span>
            <span className="pill">Visible filings {filings.length}</span>
          </div>
        </div>
      )}
      stageState={
        data.length
          ? undefined
          : {
              kind: "empty",
              kicker: "Governance",
              title: "No proxy filings yet",
              message: "This chart activates when SEC submissions include proxy statements or related proxy materials for the company.",
            }
      }
      exportState={{
        pngFileName: `${normalizeExportFileStem("governance-filing-mix", "governance")}.png`,
        csvFileName: `${normalizeExportFileStem("governance-filing-mix", "governance")}.csv`,
        csvRows: exportRows,
      }}
      renderChart={({ expanded }) =>
        data.length ? (
          <div style={{ width: "100%", height: expanded ? 360 : 280 }}>
            <ResponsiveContainer>
              <BarChart data={data} margin={{ top: 8, right: expanded ? 24 : 16, left: 0, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(expanded ? 11 : 10)} allowDecimals={false} width={48} />
                <Tooltip {...RECHARTS_TOOLTIP_PROPS} />
                <Bar dataKey="count" name="Filings" fill="var(--positive)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="grid-empty-state" style={{ minHeight: 220 }}>
            <div className="grid-empty-kicker">Governance</div>
            <div className="grid-empty-title">No proxy filings yet</div>
            <div className="grid-empty-copy">This chart activates when SEC submissions include proxy statements or related proxy materials for the company.</div>
          </div>
        )
      }
    />
  );
}

function buildChartData(filings: GovernanceFilingPayload[]) {
  const grouped = new Map<string, number>();
  for (const filing of filings) {
    grouped.set(filing.form, (grouped.get(filing.form) ?? 0) + 1);
  }
  return [...grouped.entries()].map(([label, count]) => ({ label, count }));
}
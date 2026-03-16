"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import type { GovernanceFilingPayload } from "@/lib/types";

export function GovernanceFilingChart({ filings }: { filings: GovernanceFilingPayload[] }) {
  const data = useMemo(() => buildChartData(filings), [filings]);

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Governance</div>
        <div className="grid-empty-title">No proxy filings yet</div>
        <div className="grid-empty-copy">This chart activates when SEC submissions include proxy statements or related proxy materials for the company.</div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} allowDecimals={false} width={48} />
          <Tooltip {...RECHARTS_TOOLTIP_PROPS} />
          <Bar dataKey="count" name="Filings" fill="#7CFFCB" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function buildChartData(filings: GovernanceFilingPayload[]) {
  const grouped = new Map<string, number>();
  for (const filing of filings) {
    grouped.set(filing.form, (grouped.get(filing.form) ?? 0) + 1);
  }
  return [...grouped.entries()].map(([label, count]) => ({ label, count }));
}
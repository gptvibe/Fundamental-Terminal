"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import type { BeneficialOwnershipFilingPayload } from "@/lib/types";

export function BeneficialOwnershipFormChart({ filings }: { filings: BeneficialOwnershipFilingPayload[] }) {
  const data = useMemo(() => buildChartData(filings), [filings]);

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Beneficial ownership</div>
        <div className="grid-empty-title">No 13D or 13G filings yet</div>
        <div className="grid-empty-copy">This chart fills in once SEC submissions include major beneficial ownership disclosures for the company.</div>
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
          <Bar dataKey="initial" name="Initial filings" fill="#00E5FF" radius={[6, 6, 0, 0]} />
          <Bar dataKey="amendments" name="Amendments" fill="#FFD700" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function buildChartData(filings: BeneficialOwnershipFilingPayload[]) {
  const grouped = new Map<string, { label: string; initial: number; amendments: number }>();
  for (const filing of filings) {
    const row = grouped.get(filing.base_form) ?? { label: filing.base_form.replace("SC ", ""), initial: 0, amendments: 0 };
    if (filing.is_amendment) {
      row.amendments += 1;
    } else {
      row.initial += 1;
    }
    grouped.set(filing.base_form, row);
  }
  return [...grouped.values()];
}
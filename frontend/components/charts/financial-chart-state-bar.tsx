"use client";

import { formatFinancialCadenceLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";

export function FinancialChartStateBar({ state }: { state: SharedFinancialChartState }) {
  return (
    <div className="cash-waterfall-toolbar">
      <div className="cash-waterfall-meta">
        <span className="pill tone-cyan">{formatFinancialCadenceLabel(state.cadence)} view</span>
        <span className="pill">{state.visiblePeriodCount} periods</span>
        {state.selectedPeriodLabel ? <span className="pill tone-cyan">Focus {state.selectedPeriodLabel}</span> : null}
        {state.comparisonPeriodLabel ? <span className="pill tone-gold">Compare {state.comparisonPeriodLabel}</span> : null}
      </div>
    </div>
  );
}
"use client";

import { formatFinancialCadenceLabel, formatRenderedFinancialCadenceLabel, type SharedFinancialChartState } from "@/lib/financial-chart-state";

export function FinancialChartStateBar({ state }: { state: SharedFinancialChartState }) {
  return (
    <div className="cash-waterfall-toolbar">
      <div className="cash-waterfall-meta">
        <span className="pill tone-cyan">{formatRenderedFinancialCadenceLabel(state.effectiveCadence)} view</span>
        {state.requestedCadence !== state.effectiveCadence ? <span className="pill">Requested {formatFinancialCadenceLabel(state.requestedCadence)}</span> : null}
        <span className="pill">{state.visiblePeriodCount} periods</span>
        {state.selectedPeriodLabel ? <span className="pill tone-cyan">Focus {state.selectedPeriodLabel}</span> : null}
        {state.comparisonPeriodLabel ? <span className="pill tone-gold">Compare {state.comparisonPeriodLabel}</span> : null}
      </div>
      {state.cadenceNote ? <div className="financial-period-toolbar-note">{state.cadenceNote}</div> : null}
    </div>
  );
}
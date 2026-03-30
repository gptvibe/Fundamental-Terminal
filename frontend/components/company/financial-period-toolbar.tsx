"use client";

import type { ReactNode } from "react";

import type {
  FinancialCadence,
  FinancialCompareMode,
  FinancialPeriodOption,
  FinancialRangePreset,
} from "@/hooks/use-period-selection";

interface FinancialPeriodToolbarProps {
  cadence: FinancialCadence;
  rangePreset: FinancialRangePreset;
  compareMode: FinancialCompareMode;
  selectedPeriodKey: string | null;
  customComparePeriodKey: string | null;
  activeComparisonPeriodKey: string | null;
  periodOptions: FinancialPeriodOption[];
  comparisonOptions: FinancialPeriodOption[];
  visiblePeriodCount: number;
  totalFinancialCount: number;
  cadenceNote?: string | null;
  selectedPeriodLabel?: string | null;
  comparisonPeriodLabel?: string | null;
  onCadenceChange: (next: FinancialCadence) => void;
  onRangePresetChange: (next: FinancialRangePreset) => void;
  onCompareModeChange: (next: FinancialCompareMode) => void;
  onSelectedPeriodChange: (next: string | null) => void;
  onCustomComparePeriodChange: (next: string | null) => void;
}

const CADENCE_OPTIONS: Array<{ value: FinancialCadence; label: string }> = [
  { value: "annual", label: "Annual" },
  { value: "quarterly", label: "Quarterly" },
  { value: "ttm", label: "TTM" },
];

const RANGE_OPTIONS: Array<{ value: FinancialRangePreset; label: string }> = [
  { value: "3Y", label: "3Y" },
  { value: "5Y", label: "5Y" },
  { value: "10Y", label: "10Y" },
  { value: "All", label: "All" },
];

const COMPARE_OPTIONS: Array<{ value: FinancialCompareMode; label: string }> = [
  { value: "off", label: "Off" },
  { value: "previous", label: "Previous Period" },
  { value: "custom", label: "Custom Period" },
];

export function FinancialPeriodToolbar({
  cadence,
  rangePreset,
  compareMode,
  selectedPeriodKey,
  customComparePeriodKey,
  activeComparisonPeriodKey,
  periodOptions,
  comparisonOptions,
  visiblePeriodCount,
  totalFinancialCount,
  cadenceNote = null,
  selectedPeriodLabel = null,
  comparisonPeriodLabel = null,
  onCadenceChange,
  onRangePresetChange,
  onCompareModeChange,
  onSelectedPeriodChange,
  onCustomComparePeriodChange,
}: FinancialPeriodToolbarProps) {
  const canCompare = comparisonOptions.length > 0;

  return (
    <div className="financial-period-toolbar">
      <div className="financial-period-toolbar-grid">
        <ToolbarGroup label="Cadence">
          {CADENCE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`chart-chip${cadence === option.value ? " chart-chip-active" : ""}`}
              onClick={() => onCadenceChange(option.value)}
              aria-pressed={cadence === option.value}
            >
              {option.label}
            </button>
          ))}
        </ToolbarGroup>

        <ToolbarGroup label="Range">
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`chart-chip${rangePreset === option.value ? " chart-chip-active" : ""}`}
              onClick={() => onRangePresetChange(option.value)}
              aria-pressed={rangePreset === option.value}
            >
              {option.label}
            </button>
          ))}
        </ToolbarGroup>

        <ToolbarGroup label="Compare">
          {COMPARE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`chart-chip${compareMode === option.value ? " chart-chip-active" : ""}`}
              onClick={() => onCompareModeChange(option.value)}
              aria-pressed={compareMode === option.value}
              disabled={option.value !== "off" && !canCompare}
            >
              {option.label}
            </button>
          ))}
        </ToolbarGroup>
      </div>

      <div className="financial-period-toolbar-grid secondary-grid">
        <label className="financial-period-toolbar-select">
          <span className="financial-period-toolbar-select-label">Focus Period</span>
          <select
            aria-label="Focus period"
            value={selectedPeriodKey ?? ""}
            onChange={(event) => onSelectedPeriodChange(event.target.value || null)}
            disabled={!periodOptions.length}
          >
            {periodOptions.map((option) => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        {compareMode === "custom" ? (
          <label className="financial-period-toolbar-select">
            <span className="financial-period-toolbar-select-label">Compare With</span>
            <select
              aria-label="Custom comparison period"
              value={customComparePeriodKey ?? ""}
              onChange={(event) => onCustomComparePeriodChange(event.target.value || null)}
              disabled={!comparisonOptions.length}
            >
              {comparisonOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <div className="financial-period-toolbar-meta">
        <span className="pill">Visible {visiblePeriodCount.toLocaleString()} of {totalFinancialCount.toLocaleString()} periods</span>
        {selectedPeriodLabel ? <span className="pill tone-cyan">Focus {selectedPeriodLabel}</span> : null}
        {compareMode !== "off" && comparisonPeriodLabel ? (
          <span className="pill tone-gold">Compare {comparisonPeriodLabel}</span>
        ) : null}
        {compareMode === "previous" && activeComparisonPeriodKey == null ? (
          <span className="pill tone-red">No earlier period is available in the current range</span>
        ) : null}
      </div>

      {cadenceNote ? <div className="financial-period-toolbar-note">{cadenceNote}</div> : null}
    </div>
  );
}

function ToolbarGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="financial-period-toolbar-group">
      <div className="financial-period-toolbar-group-label">{label}</div>
      <div className="financial-period-toolbar-chip-row">{children}</div>
    </div>
  );
}
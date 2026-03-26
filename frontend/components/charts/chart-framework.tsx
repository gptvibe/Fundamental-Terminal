"use client";

import { useId } from "react";

export type ControlOption = {
  key: string;
  label: string;
  disabled?: boolean;
};

export type SourceBadge = {
  label: string;
  value: string;
};

type ChartControlGroupProps = {
  label: string;
  value: string;
  options: ControlOption[];
  onChange: (value: string) => void;
};

export function ChartControlGroup({ label, value, options, onChange }: ChartControlGroupProps) {
  return (
    <div className="viz-control-group" role="group" aria-label={label}>
      <span className="viz-control-label">{label}</span>
      <div className="viz-control-buttons">
        {options.map((option) => (
          <button
            key={option.key}
            type="button"
            className={`chart-chip${value === option.key ? " chart-chip-active" : ""}`}
            onClick={() => onChange(option.key)}
            disabled={option.disabled}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}

type ComparePickerProps = {
  label: string;
  options: ControlOption[];
  selectedKeys: string[];
  onToggle: (key: string) => void;
  maxSelections: number;
};

export function ChartComparePicker({ label, options, selectedKeys, onToggle, maxSelections }: ComparePickerProps) {
  const id = useId();
  return (
    <div className="viz-control-group" role="group" aria-labelledby={id}>
      <span className="viz-control-label" id={id}>{label}</span>
      <div className="viz-control-buttons">
        {options.map((option) => {
          const active = selectedKeys.includes(option.key);
          const maxedOut = selectedKeys.length >= maxSelections && !active;
          return (
            <button
              key={option.key}
              type="button"
              className={`chart-chip${active ? " chart-chip-active" : ""}`}
              onClick={() => onToggle(option.key)}
              disabled={option.disabled || maxedOut}
              title={maxedOut ? `Select up to ${maxSelections} metrics` : undefined}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ChartSourceBadges({ badges }: { badges: SourceBadge[] }) {
  if (!badges.length) {
    return null;
  }
  return (
    <div className="viz-badge-row">
      {badges.map((badge) => (
        <span className="pill" key={`${badge.label}-${badge.value}`}>
          {badge.label}: {badge.value}
        </span>
      ))}
    </div>
  );
}

export function ChartStateBlock({
  title,
  subtitle,
  detail,
}: {
  title: string;
  subtitle: string;
  detail: string;
}) {
  return (
    <div className="grid-empty-state" style={{ minHeight: 240 }}>
      <div className="grid-empty-kicker">{title}</div>
      <div className="grid-empty-title">{subtitle}</div>
      <div className="grid-empty-copy">{detail}</div>
    </div>
  );
}

export function exportRowsToCsv(fileName: string, rows: Array<Record<string, string | number | null | undefined>>) {
  if (!rows.length) {
    return;
  }

  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  const lines = [
    keys.join(","),
    ...rows.map((row) => keys.map((key) => csvCell(row[key])).join(",")),
  ];

  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(href);
}

function csvCell(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return "";
  }
  const text = String(value);
  if (!/[",\n]/.test(text)) {
    return text;
  }
  return `"${text.replaceAll('"', '""')}"`;
}

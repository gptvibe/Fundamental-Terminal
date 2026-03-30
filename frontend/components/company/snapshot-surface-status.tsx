"use client";

import type { SnapshotSurfaceCapabilities, SnapshotSurfaceMode, SnapshotSurfaceWarning } from "@/lib/snapshot-surface";

interface SnapshotSurfaceStatusProps {
  capabilities: SnapshotSurfaceCapabilities;
  mode: SnapshotSurfaceMode;
  warnings?: SnapshotSurfaceWarning[];
}

const CAPABILITY_LABELS: Array<keyof SnapshotSurfaceCapabilities> = [
  "supports_selected_period",
  "supports_compare_mode",
  "supports_trend_mode",
];

export function SnapshotSurfaceStatus({
  capabilities,
  mode,
  warnings = [],
}: SnapshotSurfaceStatusProps) {
  return (
    <div className="snapshot-surface-status">
      <div className="snapshot-surface-pill-row">
        {CAPABILITY_LABELS.map((capability) => (
          <span
            key={capability}
            className={`pill${capabilities[capability] ? " tone-cyan" : " tone-red"}`}
          >
            {capability}
          </span>
        ))}
        <span className={`pill${mode === "compare" ? " tone-gold" : mode === "trend" ? " tone-cyan" : ""}`}>
          mode_{mode}
        </span>
      </div>

      {warnings.length ? (
        <div className="snapshot-surface-warning-grid">
          {warnings.map((warning) => (
            <div
              key={warning.code}
              className={`snapshot-surface-warning-card tone-${warning.tone}`}
            >
              <div className="snapshot-surface-warning-title">{warning.label}</div>
              <div className="snapshot-surface-warning-copy">{warning.detail}</div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
export interface SnapshotSurfaceCapabilities {
  supports_selected_period: boolean;
  supports_compare_mode: boolean;
  supports_trend_mode: boolean;
}

export type SnapshotSurfaceMode = "selected" | "compare" | "trend";

export type SnapshotSurfaceWarningTone = "info" | "warning" | "danger";

export interface SnapshotSurfaceWarning {
  code: string;
  label: string;
  detail: string;
  tone: SnapshotSurfaceWarningTone;
}

export function resolveSnapshotSurfaceMode({
  comparisonAvailable,
  trendAvailable,
  capabilities,
}: {
  comparisonAvailable: boolean;
  trendAvailable: boolean;
  capabilities: SnapshotSurfaceCapabilities;
}): SnapshotSurfaceMode {
  if (comparisonAvailable && capabilities.supports_compare_mode) {
    return "compare";
  }
  if (trendAvailable && capabilities.supports_trend_mode) {
    return "trend";
  }
  return "selected";
}

export function dedupeSnapshotSurfaceWarnings(warnings: SnapshotSurfaceWarning[]): SnapshotSurfaceWarning[] {
  const seenCodes = new Set<string>();
  const output: SnapshotSurfaceWarning[] = [];
  for (const warning of warnings) {
    if (seenCodes.has(warning.code)) {
      continue;
    }
    seenCodes.add(warning.code);
    output.push(warning);
  }
  return output;
}
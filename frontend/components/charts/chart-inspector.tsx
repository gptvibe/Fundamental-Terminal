"use client";

import type { ReactNode } from "react";
import { useId, useMemo, useRef, useState } from "react";
import { clsx } from "clsx";

import { ChartControlGroup } from "@/components/charts/chart-framework";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { Dialog } from "@/components/ui/dialog";
import {
  formatChartCadenceLabel,
  formatChartTimeframeLabel,
  formatChartTypeLabel,
  getAllowedCadenceModes,
  getAllowedChartTypes,
  getAllowedTimeframeModes,
  resolveChartType,
  type ChartCadenceMode,
  type ChartDatasetKind,
  type ChartTimeframeMode,
  type ChartType,
} from "@/lib/chart-capabilities";
import { exportElementToPng, exportRowsToCsv, type ExportRow } from "@/lib/export";

export interface ChartInspectorAction {
  label: string;
  onClick: () => void | Promise<void>;
  disabled?: boolean;
  variant?: "primary" | "secondary";
}

export interface ChartInspectorAnnotation {
  label: string;
  tone?: "neutral" | "accent" | "positive" | "warning";
  color?: string;
}

export interface ChartInspectorResetState {
  onReset: () => void;
  disabled?: boolean;
  label?: string;
}

export interface ChartInspectorExportState {
  pngFileName?: string;
  csvFileName?: string;
  csvRows?: ExportRow[];
}

export interface ChartInspectorStageState {
  kind: "ready" | "loading" | "empty" | "error";
  kicker?: string;
  title?: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
}

export interface ChartInspectorControlState {
  datasetKind: ChartDatasetKind;
  chartType?: ChartType;
  chartTypeOptions?: readonly ChartType[];
  onChartTypeChange?: (chartType: ChartType) => void;
  chartTypeLabel?: string;
  timeframeMode?: ChartTimeframeMode;
  timeframeModeOptions?: readonly ChartTimeframeMode[];
  onTimeframeModeChange?: (timeframeMode: ChartTimeframeMode) => void;
  timeframeLabel?: string;
  cadenceMode?: ChartCadenceMode;
  cadenceModeOptions?: readonly ChartCadenceMode[];
  onCadenceModeChange?: (cadenceMode: ChartCadenceMode) => void;
  cadenceLabel?: string;
}

interface ChartInspectorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle?: string;
  badgeArea?: ReactNode;
  controls?: ReactNode;
  controlState?: ChartInspectorControlState;
  annotations?: ChartInspectorAnnotation[];
  footer?: ReactNode;
  stageState?: ChartInspectorStageState;
  resetState?: ChartInspectorResetState;
  exportState?: ChartInspectorExportState;
  exportActions?: ChartInspectorAction[];
  renderChart: (context: { expanded: boolean }) => ReactNode;
  className?: string;
}

export function ChartInspector({
  open,
  onOpenChange,
  title,
  subtitle,
  badgeArea,
  controls,
  controlState,
  annotations,
  footer,
  stageState,
  resetState,
  exportState,
  exportActions,
  renderChart,
  className,
}: ChartInspectorProps) {
  const titleId = useId();
  const subtitleId = useId();
  const stageRef = useRef<HTMLDivElement>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [pngExportPending, setPngExportPending] = useState(false);
  const chartTypeOptions = controlState ? getAllowedChartTypes(controlState.datasetKind, controlState.chartTypeOptions) : [];
  const timeframeModeOptions = controlState ? getAllowedTimeframeModes(controlState.datasetKind, controlState.timeframeModeOptions) : [];
  const cadenceModeOptions = controlState ? getAllowedCadenceModes(controlState.datasetKind, controlState.cadenceModeOptions) : [];
  const selectedChartType = controlState ? resolveChartType(controlState.datasetKind, controlState.chartType) : null;
  const resolvedStageState = stageState ?? null;
  const selectedAnnotations = useMemo<ChartInspectorAnnotation[]>(() => {
    const chartTypeAnnotation: ChartInspectorAnnotation[] = selectedChartType
      ? [{ label: formatChartTypeLabel(selectedChartType), tone: "accent" }]
      : [];
    return [...chartTypeAnnotation, ...(annotations ?? [])];
  }, [annotations, selectedChartType]);
  const csvRows = exportState?.csvRows ?? [];
  const hasFooter = Boolean(footer);
  const hasDefaultExportActions = Boolean(exportState?.pngFileName || exportState?.csvFileName);
  const hasInspectorControls = Boolean(
    controls ||
      (controlState?.onChartTypeChange && chartTypeOptions.length > 1) ||
      (controlState?.onTimeframeModeChange && timeframeModeOptions.length > 1) ||
      (controlState?.onCadenceModeChange && cadenceModeOptions.length > 1)
  );
  const hasActions = Boolean(resetState || hasDefaultExportActions || exportActions?.length);

  async function runInspectorAction(action: () => void | Promise<void>, successMessage?: string) {
    setActionMessage(null);
    try {
      await action();
      if (successMessage) {
        setActionMessage(successMessage);
      }
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "The chart action could not be completed.");
    }
  }

  async function handleExportPng() {
    if (!exportState?.pngFileName || resolvedStageState?.kind === "loading" || resolvedStageState?.kind === "empty" || resolvedStageState?.kind === "error") {
      return;
    }

    const stageElement = stageRef.current;
    if (!stageElement) {
      setActionMessage("The chart is not ready to export yet.");
      return;
    }

    setPngExportPending(true);
    await runInspectorAction(
      () => exportElementToPng(stageElement, { fileName: exportState.pngFileName as string }),
      "PNG exported."
    );
    setPngExportPending(false);
  }

  function handleExportCsv() {
    if (!exportState?.csvFileName || !csvRows.length) {
      return;
    }

    exportRowsToCsv(exportState.csvFileName, csvRows);
    setActionMessage("CSV exported.");
  }

  return (
    <Dialog
      open={open}
      onClose={() => onOpenChange(false)}
      labelledBy={titleId}
      describedBy={subtitle ? subtitleId : undefined}
      contentClassName={clsx("chart-inspector-dialog", className)}
    >
      <div className="chart-inspector-shell">
        <div className="chart-inspector-header">
          <div className="chart-inspector-title-block">
            <div className="chart-inspector-kicker">Chart inspector</div>
            <h2 id={titleId} className="chart-inspector-title">{title}</h2>
            {subtitle ? <p id={subtitleId} className="chart-inspector-subtitle">{subtitle}</p> : null}
          </div>

          <button type="button" className="ticker-button chart-inspector-close-button" onClick={() => onOpenChange(false)}>
            Close
          </button>
        </div>

        {badgeArea ? <div className="chart-inspector-badge-row">{badgeArea}</div> : null}

        {selectedAnnotations.length ? (
          <div className="chart-inspector-annotation-row" aria-label="Selected series and chart settings">
            {selectedAnnotations.map((annotation) => (
              <span
                key={`${annotation.label}-${annotation.color ?? annotation.tone ?? "neutral"}`}
                className={clsx(
                  "chart-inspector-annotation-pill",
                  annotation.tone === "accent" && "is-accent",
                  annotation.tone === "positive" && "is-positive",
                  annotation.tone === "warning" && "is-warning"
                )}
              >
                {annotation.color ? <span className="chart-inspector-annotation-swatch" style={{ backgroundColor: annotation.color }} aria-hidden="true" /> : null}
                {annotation.label}
              </span>
            ))}
          </div>
        ) : null}

        {(hasInspectorControls || hasActions) ? (
          <div className="chart-inspector-toolbar">
            {hasInspectorControls ? (
              <div className="chart-inspector-controls">
                {controlState?.onChartTypeChange && selectedChartType && chartTypeOptions.length > 1 ? (
                  <ChartControlGroup
                    label={controlState.chartTypeLabel ?? "Chart type"}
                    value={selectedChartType}
                    options={chartTypeOptions.map((chartType) => ({ key: chartType, label: formatChartTypeLabel(chartType) }))}
                    onChange={(value) => controlState.onChartTypeChange?.(value as ChartType)}
                  />
                ) : null}

                {controlState?.onTimeframeModeChange && controlState.timeframeMode && timeframeModeOptions.length > 1 ? (
                  <ChartControlGroup
                    label={controlState.timeframeLabel ?? "Window"}
                    value={timeframeModeOptions.includes(controlState.timeframeMode) ? controlState.timeframeMode : timeframeModeOptions[0]}
                    options={timeframeModeOptions.map((timeframeMode) => ({ key: timeframeMode, label: formatChartTimeframeLabel(timeframeMode) }))}
                    onChange={(value) => controlState.onTimeframeModeChange?.(value as ChartTimeframeMode)}
                  />
                ) : null}

                {controlState?.onCadenceModeChange && controlState.cadenceMode && cadenceModeOptions.length > 1 ? (
                  <ChartControlGroup
                    label={controlState.cadenceLabel ?? "Cadence"}
                    value={cadenceModeOptions.includes(controlState.cadenceMode) ? controlState.cadenceMode : cadenceModeOptions[0]}
                    options={cadenceModeOptions.map((cadenceMode) => ({ key: cadenceMode, label: formatChartCadenceLabel(cadenceMode) }))}
                    onChange={(value) => controlState.onCadenceModeChange?.(value as ChartCadenceMode)}
                  />
                ) : null}

                {controls}
              </div>
            ) : (
              <div className="chart-inspector-controls" aria-hidden="true" />
            )}

            {hasActions ? (
              <div className="chart-inspector-actions">
                {resetState ? (
                  <button
                    type="button"
                    className="ticker-button chart-inspector-action-button chart-inspector-action-button-secondary"
                    onClick={resetState.onReset}
                    disabled={resetState.disabled}
                  >
                    {resetState.label ?? "Reset view"}
                  </button>
                ) : null}

                {exportState?.pngFileName ? (
                  <button
                    type="button"
                    className="ticker-button chart-inspector-action-button chart-inspector-action-button-secondary"
                    onClick={() => void handleExportPng()}
                    disabled={pngExportPending || resolvedStageState?.kind === "loading" || resolvedStageState?.kind === "empty" || resolvedStageState?.kind === "error"}
                  >
                    {pngExportPending ? "Exporting PNG..." : "Export PNG"}
                  </button>
                ) : null}

                {exportState?.csvFileName ? (
                  <button
                    type="button"
                    className="ticker-button chart-inspector-action-button chart-inspector-action-button-secondary"
                    onClick={handleExportCsv}
                    disabled={!csvRows.length}
                  >
                    Export CSV
                  </button>
                ) : null}

                {(exportActions ?? []).map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    className={clsx(
                      "ticker-button chart-inspector-action-button",
                      action.variant === "primary" ? "chart-inspector-action-button-primary" : "chart-inspector-action-button-secondary"
                    )}
                    onClick={() => void runInspectorAction(action.onClick)}
                    disabled={action.disabled}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}

        {actionMessage ? <div className="chart-inspector-status" role="status" aria-live="polite">{actionMessage}</div> : null}

        <div className={clsx("chart-inspector-stage", resolvedStageState && `is-${resolvedStageState.kind}`)}>
          <div ref={stageRef} className="chart-inspector-stage-content">
            {resolvedStageState && resolvedStageState.kind !== "ready" ? (
              <ChartInspectorStageBlock state={resolvedStageState} />
            ) : (
              renderChart({ expanded: true })
            )}
          </div>
        </div>

        {hasFooter ? <div className="chart-inspector-footer">{footer}</div> : null}
      </div>
    </Dialog>
  );
}

function ChartInspectorStageBlock({ state }: { state: ChartInspectorStageState }) {
  if (state.kind === "loading") {
    return (
      <div className="chart-inspector-stage-block chart-inspector-stage-block-loading">
        <PanelEmptyState
          kicker={state.kicker ?? "Loading chart"}
          title={state.title ?? "Preparing chart inspector"}
          message={state.message}
          minHeight={320}
          loading
        />
        <div className="chart-inspector-stage-skeleton" aria-hidden="true">
          <span className="workspace-skeleton chart-inspector-stage-skeleton-header" />
          <span className="workspace-skeleton chart-inspector-stage-skeleton-body" />
          <span className="workspace-skeleton chart-inspector-stage-skeleton-body is-short" />
        </div>
      </div>
    );
  }

  return (
    <div className="chart-inspector-stage-block">
      <PanelEmptyState
        kicker={state.kicker ?? (state.kind === "error" ? "Chart unavailable" : "No chart data")}
        title={state.title ?? (state.kind === "error" ? "Unable to render the expanded chart" : "Nothing to show in the inspector")}
        message={state.message}
        minHeight={320}
      />
      {state.onAction ? (
        <div className="chart-inspector-stage-block-action-row">
          <button type="button" className="ticker-button" onClick={state.onAction}>
            {state.actionLabel ?? (state.kind === "error" ? "Retry" : "Refresh view")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
"use client";

import type { MouseEvent, ReactNode } from "react";
import { useState } from "react";
import { clsx } from "clsx";

import {
  ChartInspector,
  type ChartInspectorAction,
  type ChartInspectorAnnotation,
  type ChartInspectorControlState,
  type ChartInspectorExportState,
  type ChartInspectorResetState,
  type ChartInspectorStageState,
} from "@/components/charts/chart-inspector";

const CARD_OPEN_IGNORE_SELECTOR = [
  "button",
  "a",
  "input",
  "select",
  "textarea",
  "summary",
  "[role='button']",
  "[role='link']",
  "[data-chart-frame-ignore-open]",
].join(",");

interface InteractiveChartFrameProps {
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
  headerClassName?: string;
  titleClassName?: string;
  subtitleClassName?: string;
  bodyClassName?: string;
  inspectorTitle?: string;
  inspectorSubtitle?: string;
  expandLabel?: string;
}

export function InteractiveChartFrame({
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
  headerClassName,
  titleClassName,
  subtitleClassName,
  bodyClassName,
  inspectorTitle,
  inspectorSubtitle,
  expandLabel = "Expand",
}: InteractiveChartFrameProps) {
  const [open, setOpen] = useState(false);

  function handleCardClick(event: MouseEvent<HTMLElement>) {
    if (shouldIgnoreCardOpen(event.target)) {
      return;
    }
    setOpen(true);
  }

  return (
    <section className={clsx("interactive-chart-frame", className)} onClick={handleCardClick}>
      <div className={clsx("interactive-chart-frame-header", headerClassName)}>
        <div className="interactive-chart-frame-heading">
          <div className={clsx("interactive-chart-frame-title", titleClassName)}>{title}</div>
          {subtitle ? <div className={clsx("interactive-chart-frame-subtitle", subtitleClassName)}>{subtitle}</div> : null}
        </div>
      </div>

      <button
        type="button"
        className="ticker-button interactive-chart-expand-button"
        onClick={() => setOpen(true)}
        aria-label={`${expandLabel} ${title}`}
        data-chart-frame-ignore-open
      >
        {expandLabel}
      </button>

      <div className={clsx("interactive-chart-frame-body", bodyClassName)}>{renderChart({ expanded: false })}</div>

      <ChartInspector
        open={open}
        onOpenChange={setOpen}
        title={inspectorTitle ?? title}
        subtitle={inspectorSubtitle ?? subtitle}
        badgeArea={badgeArea}
        controls={controls}
        controlState={controlState}
        annotations={annotations}
        footer={footer}
        stageState={stageState}
        resetState={resetState}
        exportState={exportState}
        exportActions={exportActions}
        renderChart={renderChart}
      />
    </section>
  );
}

function shouldIgnoreCardOpen(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(CARD_OPEN_IGNORE_SELECTOR) !== null;
}
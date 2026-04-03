import { clsx } from "clsx";

import { buildMetricTooltip } from "@/lib/metric-glossary";

interface MetricLabelProps {
  label: string;
  metricKey?: string | null;
  className?: string;
}

export function MetricLabel({ label, metricKey, className }: MetricLabelProps) {
  const tooltip = buildMetricTooltip(metricKey, label);

  return (
    <span
      className={clsx(className, tooltip && "metric-label-tooltip-target")}
      title={tooltip ?? undefined}
      aria-label={tooltip ? `${label}. ${tooltip.replace(/\n+/g, " ")}` : undefined}
      tabIndex={tooltip ? 0 : undefined}
    >
      {label}
    </span>
  );
}
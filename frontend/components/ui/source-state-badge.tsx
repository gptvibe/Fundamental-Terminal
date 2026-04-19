import { getForecastSourceStateDescriptor, type ForecastSourceState } from "@/lib/forecast-source-state";

interface SourceStateBadgeProps {
  state: ForecastSourceState;
  compact?: boolean;
}

export function SourceStateBadge({ state, compact = true }: SourceStateBadgeProps) {
  const descriptor = getForecastSourceStateDescriptor(state);

  return (
    <span
      className={`pill forecast-source-state-badge tone-${descriptor.tone}`}
      title={descriptor.description}
      data-testid={`source-state-badge-${state}`}
    >
      {compact ? descriptor.compactLabel : descriptor.label}
    </span>
  );
}

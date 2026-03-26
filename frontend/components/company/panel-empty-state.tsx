import { clsx } from "clsx";

interface PanelEmptyStateProps {
  message: string;
  kicker?: string;
  title?: string;
  minHeight?: number;
  className?: string;
}

export function PanelEmptyState({ message, kicker = "Current view", title = "Nothing to show yet", minHeight = 220, className }: PanelEmptyStateProps) {
  return (
    <div className={clsx("grid-empty-state", className)} style={{ minHeight }}>
      <div className="grid-empty-kicker">{kicker}</div>
      <div className="grid-empty-title">{title}</div>
      <div className="grid-empty-copy">{message}</div>
    </div>
  );
}

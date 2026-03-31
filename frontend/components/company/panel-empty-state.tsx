import { clsx } from "clsx";

interface PanelEmptyStateProps {
  message: string;
  kicker?: string;
  title?: string;
  minHeight?: number;
  className?: string;
  loading?: boolean;
  loadingMessage?: string;
}

export function PanelEmptyState({
  message,
  kicker = "Current view",
  title = "Nothing to show yet",
  minHeight = 220,
  className,
  loading = false,
  loadingMessage,
}: PanelEmptyStateProps) {
  const resolvedKicker = loading ? "Loading" : kicker;
  const resolvedTitle = loading ? "Preparing this panel" : title;
  const resolvedMessage = loading ? loadingMessage ?? message : message;

  return (
    <div
      className={clsx("grid-empty-state", loading && "grid-empty-state-loading", className)}
      style={{ minHeight }}
      role={loading ? "status" : undefined}
      aria-live={loading ? "polite" : undefined}
    >
      {loading ? <div className="workspace-skeleton grid-empty-loading-line" aria-hidden="true" /> : null}
      <div className="grid-empty-kicker">{resolvedKicker}</div>
      <div className="grid-empty-title">{resolvedTitle}</div>
      <div className="grid-empty-copy">{resolvedMessage}</div>
    </div>
  );
}

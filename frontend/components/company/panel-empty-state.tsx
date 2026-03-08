interface PanelEmptyStateProps {
  message: string;
}

export function PanelEmptyState({ message }: PanelEmptyStateProps) {
  return (
    <div className="grid-empty-state" style={{ minHeight: 220 }}>
      <div className="grid-empty-kicker">Current view</div>
      <div className="grid-empty-title">Nothing to show yet</div>
      <div className="grid-empty-copy">{message}</div>
    </div>
  );
}

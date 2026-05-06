"use client";

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div
      aria-hidden="true"
      style={{ height, minHeight: height }}
      className="skeleton-block"
    />
  );
}

export function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div aria-hidden="true" className="skeleton-table">
      <div className="skeleton-table-header skeleton-block" style={{ height: 32, marginBottom: 4 }} />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-block" style={{ height: 28, marginBottom: 2 }} />
      ))}
    </div>
  );
}

export function GridSkeleton({ height = 420 }: { height?: number }) {
  return (
    <div
      aria-hidden="true"
      style={{ height, minHeight: height }}
      className="skeleton-block"
    />
  );
}

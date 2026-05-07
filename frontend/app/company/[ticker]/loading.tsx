export default function CompanyRouteLoading() {
  return (
    <div className="company-workspace-stack company-route-loading research-brief-loading" aria-busy="true" aria-label="Loading research brief">
      <div className="research-brief-hero-loading" role="status" aria-live="polite">
        Building the Research Brief from persisted filing and fundamentals caches.
      </div>
      {/* Header skeleton */}
      <div className="panel workspace-skeleton workspace-skeleton-header" />
      {/* Section nav skeleton */}
      <div className="research-brief-loading-nav" aria-hidden="true">
        {Array.from({ length: 7 }).map((_, index) => (
          <div key={index} className="workspace-skeleton workspace-skeleton-nav-chip" />
        ))}
      </div>
      {/* Snapshot section skeleton — above-fold content */}
      <div className="research-brief-loading-section">
        <div className="workspace-skeleton workspace-skeleton-section-title" />
        <div className="workspace-skeleton workspace-skeleton-section-summary" />
        <div className="research-brief-loading-grid">
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card workspace-skeleton-card-wide" />
        </div>
      </div>
      {/* Second section skeleton — below-fold placeholder */}
      <div className="research-brief-loading-section">
        <div className="workspace-skeleton workspace-skeleton-section-title" />
        <div className="workspace-skeleton workspace-skeleton-section-summary" />
        <div className="research-brief-loading-grid">
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
        </div>
      </div>
      {/* Third section skeleton */}
      <div className="research-brief-loading-section">
        <div className="workspace-skeleton workspace-skeleton-section-title" />
        <div className="workspace-skeleton workspace-skeleton-section-summary" />
        <div className="research-brief-loading-grid">
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
        </div>
      </div>
    </div>
  );
}

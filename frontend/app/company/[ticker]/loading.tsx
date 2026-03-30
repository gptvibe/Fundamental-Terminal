export default function CompanyRouteLoading() {
  return (
    <div className="company-workspace-stack company-route-loading research-brief-loading">
      <div className="panel workspace-skeleton workspace-skeleton-header" />
      <div className="research-brief-loading-nav" aria-hidden="true">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="workspace-skeleton workspace-skeleton-nav-chip" />
        ))}
      </div>
      <div className="research-brief-loading-section">
        <div className="workspace-skeleton workspace-skeleton-section-title" />
        <div className="workspace-skeleton workspace-skeleton-section-summary" />
        <div className="research-brief-loading-grid">
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card workspace-skeleton-card-wide" />
        </div>
      </div>
      <div className="research-brief-loading-section">
        <div className="workspace-skeleton workspace-skeleton-section-title" />
        <div className="workspace-skeleton workspace-skeleton-section-summary" />
        <div className="research-brief-loading-grid">
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
          <div className="panel workspace-skeleton workspace-skeleton-card" />
        </div>
      </div>
    </div>
  );
}

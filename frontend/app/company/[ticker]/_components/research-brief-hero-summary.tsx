"use client";

export function ResearchBriefHeroSummary({
  summary,
  metrics,
  metaItems,
  fallbackLabels,
  loading = false,
  loadingMessage = null,
}: {
  summary: string;
  metrics: Array<{ label: string; value: string | null }>;
  metaItems: Array<string | null>;
  fallbackLabels: string[];
  loading?: boolean;
  loadingMessage?: string | null;
}) {
  const visibleMetaItems = metaItems.filter((item): item is string => Boolean(item));

  return (
    <div className="research-brief-hero">
      {loadingMessage ? (
        <div className="research-brief-hero-loading" role="status" aria-live="polite">
          {loadingMessage}
        </div>
      ) : null}
      <div className="research-brief-hero-main">
        <div className="research-brief-hero-copy">
          <p className="research-brief-hero-summary">{summary}</p>
          {visibleMetaItems.length ? (
            <div className="research-brief-hero-meta" aria-label="Brief metadata">
              {visibleMetaItems.map((item) => (
                <span key={item} className="research-brief-hero-meta-item">
                  {item}
                </span>
              ))}
            </div>
          ) : null}
          {fallbackLabels.length ? (
            <div className="research-brief-hero-note">
              Price history and market profile context includes a labeled commercial fallback from {fallbackLabels.join(", ")}. Core fundamentals remain sourced from official filings and public datasets.
            </div>
          ) : null}
        </div>

        <div className="research-brief-hero-metrics">
          {metrics.map((item, index) => (
            <div key={item.label} className={`research-brief-hero-metric${index < 2 ? " is-primary" : " is-secondary"}`}>
              <div className="research-brief-hero-metric-label">{item.label}</div>
              <div className="research-brief-hero-metric-value">
                {loading ? (
                  <span aria-hidden="true" className={`workspace-skeleton research-brief-hero-metric-skeleton skeleton-${index % 4}`} />
                ) : (
                  item.value ?? "\u2014"
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

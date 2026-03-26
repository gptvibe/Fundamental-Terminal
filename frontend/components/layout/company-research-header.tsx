import type { ReactNode } from "react";
import { clsx } from "clsx";

type AccentTone = "green" | "cyan" | "gold" | "red";

export interface CompanyFactItem {
  label: string;
  value: string | null;
}

export interface CompanySummaryItem {
  label: string;
  value: string;
  accent?: AccentTone;
}

export interface CompanyRibbonItem {
  label: string;
  value: string;
  tone?: AccentTone;
}

interface CompanyResearchHeaderProps {
  ticker: string;
  title: string;
  companyName?: string | null;
  sector?: string | null;
  cacheState?: string | null;
  description?: string;
  aside?: ReactNode;
  facts?: CompanyFactItem[];
  ribbonItems?: CompanyRibbonItem[];
  summaries?: CompanySummaryItem[];
  className?: string;
  children?: ReactNode;
}

export function CompanyResearchHeader({
  ticker,
  title,
  companyName,
  sector,
  cacheState,
  description,
  aside,
  facts = [],
  ribbonItems = [],
  summaries = [],
  className,
  children,
}: CompanyResearchHeaderProps) {
  return (
    <section className={clsx("company-research-header", className)}>
      <div className="company-research-header-top">
        <div className="company-research-header-copy">
          <div className="company-research-header-kicker-row">
            <span className="company-research-header-kicker">{ticker}</span>
            {sector ? <span className="company-research-header-tag">{sector}</span> : null}
            {cacheState ? (
              <span className={clsx("company-research-header-tag", `tone-${cacheState}`)}>
                {cacheState}
              </span>
            ) : null}
          </div>
          <div className="company-research-header-title-row">
            <div>
              <h1 className="company-research-header-title">{title}</h1>
              <p className="company-research-header-subtitle">{companyName ?? ticker}</p>
            </div>
            {aside ? <div className="company-research-header-aside">{aside}</div> : null}
          </div>
          {description ? <p className="company-research-header-description">{description}</p> : null}
        </div>
      </div>

      {ribbonItems.length ? (
        <div className="company-source-ribbon" aria-label="Data sources and freshness">
          {ribbonItems.map((item) => (
            <div key={`${item.label}:${item.value}`} className={clsx("company-source-chip", item.tone && `tone-${item.tone}`)}>
              <span className="company-source-chip-label">{item.label}</span>
              <span className="company-source-chip-value">{item.value}</span>
            </div>
          ))}
        </div>
      ) : null}

      {facts.length ? <CompanyMetricGrid items={facts} /> : null}
      {summaries.length ? <CompanySummaryStrip items={summaries} /> : null}
      {children ? <div className="company-research-header-extra">{children}</div> : null}
    </section>
  );
}

export function CompanyMetricGrid({ items }: { items: CompanyFactItem[] }) {
  return (
    <div className="metric-grid">
      {items.map((item) => (
        <div key={item.label} className="metric-card">
          <div className="metric-label">{item.label}</div>
          <div className="metric-value">{item.value ?? "?"}</div>
        </div>
      ))}
    </div>
  );
}

export function CompanySummaryStrip({ items, className }: { items: CompanySummaryItem[]; className?: string }) {
  return (
    <div className={clsx("company-summary-strip", className)}>
      {items.map((item) => (
        <div key={item.label} className={clsx("summary-card", `accent-${item.accent ?? "cyan"}`)}>
          <div className="summary-card-label">{item.label}</div>
          <div className="summary-card-value">{item.value}</div>
        </div>
      ))}
    </div>
  );
}
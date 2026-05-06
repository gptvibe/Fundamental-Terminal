import { useId, type HTMLAttributes, type ReactNode } from "react";
import { clsx } from "clsx";

type Tone = "neutral" | "positive" | "warning" | "danger";

type Freshness = "fresh" | "stale" | "delayed" | "unknown";

type SourceKind = "sec" | "market" | "model" | "derived" | "internal" | "external";

interface PrimitiveProps {
  className?: string;
  children?: ReactNode;
}

interface HeaderBlockProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
}

export function PageShell({ className, children }: PrimitiveProps) {
  return <main className={clsx("rd-page-shell", className)}>{children}</main>;
}

export function PageHeader({ title, subtitle, actions, eyebrow }: HeaderBlockProps) {
  return (
    <header className="rd-page-header">
      <div className="rd-page-header-copy">
        {eyebrow ? <p className="rd-page-header-eyebrow">{eyebrow}</p> : null}
        <h1 className="rd-page-header-title">{title}</h1>
        {subtitle ? <p className="rd-page-header-subtitle">{subtitle}</p> : null}
      </div>
      {actions ? <div className="rd-page-header-actions">{actions}</div> : null}
    </header>
  );
}

export function KpiStrip({ className, children, ...rest }: HTMLAttributes<HTMLUListElement>) {
  return (
    <ul className={clsx("rd-kpi-strip", className)} {...rest}>
      {children}
    </ul>
  );
}

interface KpiCardProps {
  label: ReactNode;
  value: ReactNode;
  delta?: ReactNode;
  detail?: ReactNode;
  tone?: Tone;
  className?: string;
}

export function KpiCard({ label, value, delta, detail, tone = "neutral", className }: KpiCardProps) {
  return (
    <li className="rd-kpi-item">
      <article className={clsx("rd-kpi-card", `rd-tone-${tone}`, className)}>
        <p className="rd-kpi-label">{label}</p>
        <p className="rd-kpi-value">{value}</p>
        {delta ? <p className="rd-kpi-delta">{delta}</p> : null}
        {detail ? <p className="rd-kpi-detail">{detail}</p> : null}
      </article>
    </li>
  );
}

interface DataFreshnessBadgeProps {
  freshness: Freshness;
  asOf?: string;
  detail?: string;
  className?: string;
}

const FRESHNESS_COPY: Record<Freshness, string> = {
  fresh: "Fresh",
  stale: "Stale",
  delayed: "Delayed",
  unknown: "Unknown",
};

export function DataFreshnessBadge({ freshness, asOf, detail, className }: DataFreshnessBadgeProps) {
  const text = FRESHNESS_COPY[freshness];
  const ariaLabel = ["Data freshness", text, asOf ? `as of ${asOf}` : ""].filter(Boolean).join(" ");

  return (
    <span className={clsx("rd-badge", `rd-freshness-${freshness}`, className)} aria-label={ariaLabel}>
      <span className="rd-badge-label">{text}</span>
      {asOf ? <span className="rd-badge-value">{asOf}</span> : null}
      {detail ? <span className="rd-badge-detail">{detail}</span> : null}
    </span>
  );
}

interface SourceBadgeProps {
  source: string;
  kind?: SourceKind;
  className?: string;
}

export function SourceBadge({ source, kind = "external", className }: SourceBadgeProps) {
  const kindLabel = kind === "sec" ? "SEC" : kind;
  return (
    <span className={clsx("rd-badge", "rd-source-badge", `rd-source-${kind}`, className)}>
      <span className="rd-badge-label">{kindLabel}</span>
      <span className="rd-badge-value">{source}</span>
    </span>
  );
}

interface PrimaryCardProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  footer?: ReactNode;
}

function PrimaryCardContainer({ title, subtitle, actions, children, className, footer, variant }: PrimaryCardProps & { variant: "chart" | "table" }) {
  return (
    <section className={clsx("rd-primary-card", `rd-primary-${variant}`, className)}>
      <div className="rd-primary-card-header">
        <div>
          <h2 className="rd-primary-card-title">{title}</h2>
          {subtitle ? <p className="rd-primary-card-subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="rd-primary-card-actions">{actions}</div> : null}
      </div>
      <div className="rd-primary-card-body">{children}</div>
      {footer ? <div className="rd-primary-card-footer">{footer}</div> : null}
    </section>
  );
}

export function PrimaryChartCard(props: PrimaryCardProps) {
  return <PrimaryCardContainer {...props} variant="chart" />;
}

export function PrimaryTableCard(props: PrimaryCardProps) {
  return <PrimaryCardContainer {...props} variant="table" />;
}

interface SectionAccordionProps {
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  aside?: ReactNode;
}

export function SectionAccordion({ title, subtitle, children, defaultOpen = false, className, aside }: SectionAccordionProps) {
  return (
    <details className={clsx("rd-section-accordion", className)} open={defaultOpen}>
      <summary className="rd-section-accordion-trigger">
        <span className="rd-section-accordion-title-wrap">
          <span className="rd-section-accordion-title">{title}</span>
          {subtitle ? <span className="rd-section-accordion-subtitle">{subtitle}</span> : null}
        </span>
        {aside ? <span className="rd-section-accordion-aside">{aside}</span> : null}
      </summary>
      <div className="rd-section-accordion-content">{children}</div>
    </details>
  );
}

interface EvidenceDrawerProps {
  title: ReactNode;
  children: ReactNode;
  summaryLabel?: string;
  defaultOpen?: boolean;
  className?: string;
}

export function EvidenceDrawer({ title, children, summaryLabel = "Evidence", defaultOpen = false, className }: EvidenceDrawerProps) {
  const drawerId = useId();

  return (
    <details className={clsx("rd-evidence-drawer", className)} open={defaultOpen}>
      <summary className="rd-evidence-drawer-trigger" aria-controls={drawerId}>
        {summaryLabel}
      </summary>
      <aside id={drawerId} className="rd-evidence-drawer-content" aria-label="Evidence panel">
        <div className="rd-evidence-drawer-header">
          <h3 className="rd-evidence-drawer-title">{title}</h3>
        </div>
        <div className="rd-evidence-drawer-body">{children}</div>
      </aside>
    </details>
  );
}

interface EmptyStateProps {
  title: ReactNode;
  message: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, message, action, className }: EmptyStateProps) {
  return (
    <div className={clsx("rd-state", "rd-empty-state", className)}>
      <p className="rd-state-kicker">No records</p>
      <h3 className="rd-state-title">{title}</h3>
      <p className="rd-state-message">{message}</p>
      {action ? <div className="rd-state-action">{action}</div> : null}
    </div>
  );
}

interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
  label?: string;
}

export function LoadingSkeleton({ lines = 3, className, label = "Loading content" }: LoadingSkeletonProps) {
  const resolvedLines = Math.max(1, Math.min(lines, 8));

  return (
    <div className={clsx("rd-state", "rd-loading-skeleton", className)} role="status" aria-live="polite" aria-label={label}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: resolvedLines }, (_, index) => (
        <span className="rd-loading-line" key={`rd-loading-line-${index}`} aria-hidden="true" />
      ))}
    </div>
  );
}

interface ErrorStateProps {
  title: ReactNode;
  message: ReactNode;
  retryAction?: ReactNode;
  className?: string;
}

export function ErrorState({ title, message, retryAction, className }: ErrorStateProps) {
  return (
    <div className={clsx("rd-state", "rd-error-state", className)} role="alert">
      <p className="rd-state-kicker">Error</p>
      <h3 className="rd-state-title">{title}</h3>
      <p className="rd-state-message">{message}</p>
      {retryAction ? <div className="rd-state-action">{retryAction}</div> : null}
    </div>
  );
}

interface ToolbarProps {
  children: ReactNode;
  className?: string;
  label?: string;
}

export function Toolbar({ children, className, label = "Page controls" }: ToolbarProps) {
  return (
    <div className={clsx("rd-toolbar", className)} role="toolbar" aria-label={label}>
      {children}
    </div>
  );
}

export function ToolbarGroup({ title, children, className }: { title: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("rd-toolbar-group", className)} role="group" aria-label={typeof title === "string" ? title : undefined}>
      <span className="rd-toolbar-group-title">{title}</span>
      <div className="rd-toolbar-group-body">{children}</div>
    </div>
  );
}

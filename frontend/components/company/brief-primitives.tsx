/**
 * Shared primitive components used by the company research brief page
 * and the extracted feature section components.
 */

import { Component, type ReactNode } from "react";
import Link from "next/link";

import { resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";
import { EvidenceMetaBlock } from "@/components/ui/evidence-meta-block";
import { Panel } from "@/components/ui/panel";
import { formatDate } from "@/lib/format";
import type { ProvenanceEntryPayload, SourceMixPayload } from "@/lib/types";
import type { SemanticTone } from "@/lib/activity-feed-tone";

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type AsyncState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
};

export type ResearchBriefCue = {
  label: string;
  asOf?: string | null;
  lastRefreshedAt?: string | null;
  lastChecked?: string | null;
  provenance?: ProvenanceEntryPayload[] | null;
  sourceMix?: SourceMixPayload | null;
  confidenceFlags?: string[] | null;
};

export type SectionLink = {
  href: string;
  label: string;
};

export type MonitorChecklistItem = {
  title: string;
  detail: string;
  tone: SemanticTone;
};

// ---------------------------------------------------------------------------
// ResearchBriefSection
// ---------------------------------------------------------------------------

export function ResearchBriefSection({
  id,
  title,
  question,
  summary,
  cues,
  links,
  expanded,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  question: string;
  summary?: string | null;
  cues: ResearchBriefCue[];
  links: SectionLink[];
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const contentId = `${id}-content`;

  return (
    <section id={id} data-brief-section className="research-brief-anchor">
      <Panel
        title={title}
        subtitle={question}
        aside={<ResearchBriefSectionControls links={links} expanded={expanded} title={title} contentId={contentId} onToggle={onToggle} />}
        variant="subtle"
        bodyId={contentId}
        bodyHidden={!expanded}
        className="research-brief-section-panel"
      >
        <div className="research-brief-section-stack">
          {summary || cues.length ? (
            <div className="research-brief-section-intro">
              {summary ? <p className="research-brief-section-summary">{summary}</p> : null}
              <ResearchBriefFreshness cues={cues} />
            </div>
          ) : null}
          <div className="research-brief-evidence-grid">{children}</div>
        </div>
      </Panel>
    </section>
  );
}

// ---------------------------------------------------------------------------
// ResearchBriefSectionControls / SectionLinks
// ---------------------------------------------------------------------------

export function ResearchBriefSectionControls({
  links,
  expanded,
  title,
  contentId,
  onToggle,
}: {
  links: SectionLink[];
  expanded: boolean;
  title: string;
  contentId: string;
  onToggle: () => void;
}) {
  return (
    <div className="research-brief-section-controls">
      <SectionLinks links={links} />
      <button
        type="button"
        className="research-brief-section-toggle"
        aria-controls={contentId}
        aria-label={`${expanded ? "Collapse" : "Expand"} ${title}`}
        data-expanded={expanded ? "true" : "false"}
        onClick={onToggle}
      >
        <span>{expanded ? "Collapse" : "Expand"}</span>
        <span className="research-brief-section-toggle-chevron" aria-hidden="true" />
      </button>
    </div>
  );
}

export function SectionLinks({ links }: { links: SectionLink[] }) {
  return (
    <div className="research-brief-section-links">
      {links.map((link) => (
        <Link key={link.href} href={link.href} className="research-brief-section-link">
          {link.label}
        </Link>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResearchBriefFreshness
// ---------------------------------------------------------------------------

export function ResearchBriefFreshness({ cues }: { cues: ResearchBriefCue[] }) {
  const visibleCues = cues.filter(
    (cue) => cue.asOf || cue.lastRefreshedAt || cue.lastChecked || cue.provenance?.length || cue.sourceMix || cue.confidenceFlags?.length
  );

  if (!visibleCues.length) {
    return null;
  }

  return (
    <div className="research-brief-freshness-grid">
      {visibleCues.map((cue) => {
        const sourceSummary = formatEvidenceSourceSummary(cue.sourceMix, cue.provenance);
        const fallbackLabel = formatEvidenceFallbackLabel(cue.provenance, cue.sourceMix);
        const confidenceFlags = (cue.confidenceFlags ?? []).slice(0, 2);

        return (
          <div key={cue.label} className="research-brief-freshness-card">
            <div className="research-brief-freshness-head">
              <div className="research-brief-freshness-title">{cue.label}</div>
              {confidenceFlags.length ? <div className="research-brief-freshness-flags">Flags: {confidenceFlags.map(humanizeToken).join(", ")}</div> : null}
            </div>
            <EvidenceMetaBlock
              items={[
                { label: "Source", value: sourceSummary, emphasized: true },
                { label: "As of", value: cue.asOf ? formatDate(cue.asOf) : "Pending" },
                { label: "Freshness", value: formatBriefEvidenceFreshness(cue.lastRefreshedAt, cue.lastChecked) },
                { label: "Fallback label", value: fallbackLabel },
              ]}
            />
            {cue.provenance?.length ? (
              <div className="research-brief-freshness-note">
                {cue.provenance.length.toLocaleString()} registry source{cue.provenance.length === 1 ? "" : "s"} backing this section.
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EvidenceCard
// ---------------------------------------------------------------------------

export function EvidenceCard({
  title,
  copy,
  className,
  children,
}: {
  title: string;
  copy: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={`research-brief-evidence-card${className ? ` ${className}` : ""}`}>
      <div className="research-brief-evidence-head">
        <h3 className="research-brief-evidence-title">{title}</h3>
        <p className="research-brief-evidence-copy">{copy}</p>
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResearchBriefStateBlock
// ---------------------------------------------------------------------------

export function ResearchBriefStateBlock({
  kind,
  kicker,
  title,
  message,
  minHeight = 220,
}: {
  kind: "loading" | "empty" | "error";
  kicker: string;
  title: string;
  message: string;
  minHeight?: number;
}) {
  return (
    <div className={`research-brief-state research-brief-state-${kind}${minHeight <= 180 ? " is-compact" : ""}`}>
      <div className="grid-empty-kicker">{kicker}</div>
      <div className="grid-empty-title">{title}</div>
      <div className="grid-empty-copy">{message}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PanelErrorBoundary
// ---------------------------------------------------------------------------

type PanelErrorBoundaryState = { hasError: boolean; errorMessage: string | null };

export class PanelErrorBoundary extends Component<
  { kicker: string; title: string; children: ReactNode },
  PanelErrorBoundaryState
> {
  constructor(props: { kicker: string; title: string; children: ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMessage: null };
  }

  static getDerivedStateFromError(error: unknown): PanelErrorBoundaryState {
    const message =
      error instanceof Error ? error.message : "An unexpected error occurred in this panel.";
    return { hasError: true, errorMessage: message };
  }

  override render() {
    if (this.state.hasError) {
      return (
        <ResearchBriefStateBlock
          kind="error"
          kicker={this.props.kicker}
          title={this.props.title}
          message={this.state.errorMessage ?? "This panel encountered an unexpected error and could not render."}
        />
      );
    }

    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// AlertOrEntryCard
// ---------------------------------------------------------------------------

export function AlertOrEntryCard({
  href,
  tone,
  topLeft,
  topRight,
  title,
  detail,
}: {
  href: string | null;
  tone: SemanticTone;
  topLeft: ReactNode;
  topRight: string;
  title: string;
  detail: string;
}) {
  const cardClassName = `filing-link-card company-pulse-card tone-${tone}`;
  const content = (
    <>
      <div className="company-pulse-card-top">
        <div className="company-pulse-card-pills">{topLeft}</div>
        <div className="text-muted">{topRight}</div>
      </div>
      <div className="company-pulse-card-title">{title}</div>
      <div className="company-pulse-card-detail">{detail}</div>
    </>
  );

  if (href) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className={`${cardClassName} research-brief-linked-card`}
      >
        {content}
      </a>
    );
  }

  return (
    <div className={`${cardClassName} research-brief-linked-card`}>
      {content}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

export function formatBriefEvidenceFreshness(lastRefreshedAt: string | null | undefined, lastChecked: string | null | undefined): string {
  if (lastRefreshedAt) {
    return `Refreshed ${formatDate(lastRefreshedAt)}`;
  }
  if (lastChecked) {
    return `Checked ${formatDate(lastChecked)}`;
  }
  return "Pending";
}

function formatSourceMixLabel(sourceMix: SourceMixPayload | null | undefined, provenance: ProvenanceEntryPayload[] | null | undefined): string | null {
  const fallbackLabels = resolveCommercialFallbackLabels(provenance, sourceMix);

  if (sourceMix?.official_only) {
    return "Official/public only";
  }

  if (fallbackLabels.length) {
    return "Official + labeled fallback";
  }

  if (provenance?.length) {
    return "Cached source mix";
  }

  return null;
}

export function formatEvidenceSourceSummary(sourceMix: SourceMixPayload | null | undefined, provenance: ProvenanceEntryPayload[] | null | undefined): string {
  return formatSourceMixLabel(sourceMix, provenance) ?? "Pending";
}

export function formatEvidenceFallbackLabel(
  provenance: ProvenanceEntryPayload[] | null | undefined,
  sourceMix: SourceMixPayload | null | undefined,
): string {
  const fallbackLabels = resolveCommercialFallbackLabels(provenance, sourceMix);

  if (fallbackLabels.length) {
    return fallbackLabels.join(", ");
  }

  if (sourceMix?.official_only || provenance?.length) {
    return "Official only";
  }

  return "Pending";
}

function humanizeToken(value: string): string {
  return value.replaceAll("_", " ");
}

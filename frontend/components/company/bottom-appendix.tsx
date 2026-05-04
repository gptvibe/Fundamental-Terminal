"use client";

import { useMemo, useState, type ReactNode } from "react";

import { Panel } from "@/components/ui/panel";

export type BottomAppendixSection = {
  id: string;
  title: string;
  content: ReactNode;
  defaultOpen?: boolean;
  hidden?: boolean;
};

type BottomAppendixProps = {
  id: string;
  title: string;
  subtitle: string;
  toggleLabel?: string;
  defaultExpanded?: boolean;
  unmountWhenCollapsed?: boolean;
  className?: string;
  sections: BottomAppendixSection[];
};

export function BottomAppendix({
  id,
  title,
  subtitle,
  toggleLabel,
  defaultExpanded = false,
  unmountWhenCollapsed = false,
  className = "research-brief-section",
  sections,
}: BottomAppendixProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const visibleSections = useMemo(() => sections.filter((section) => !section.hidden), [sections]);
  const shouldRenderSections = expanded || !unmountWhenCollapsed;

  return (
    <section id={id} className={className} aria-labelledby={`${id}-toggle`}>
      <button
        id={`${id}-toggle`}
        type="button"
        className="research-brief-section-toggle"
        onClick={() => setExpanded((current) => !current)}
        aria-controls={`${id}-panel`}
      >
        <span className="research-brief-section-toggle-label">{toggleLabel ?? title}</span>
        <span className="research-brief-section-toggle-caret" aria-hidden="true">
          {expanded ? "▲" : "▼"}
        </span>
      </button>

      {shouldRenderSections ? (
        <div id={`${id}-panel`} hidden={!expanded}>
          <Panel title={title} subtitle={subtitle} variant="subtle">
            <div className="company-overview-data-quality-stack">
              {visibleSections.length ? (
                visibleSections.map((section) => (
                  <details key={section.id} className="subtle-details" open={section.defaultOpen}>
                    <summary>{section.title}</summary>
                    <div className="subtle-details-body company-overview-data-quality-body">{section.content}</div>
                  </details>
                ))
              ) : (
                <div className="text-muted">No appendix details are available for this page yet.</div>
              )}
            </div>
          </Panel>
        </div>
      ) : null}
    </section>
  );
}

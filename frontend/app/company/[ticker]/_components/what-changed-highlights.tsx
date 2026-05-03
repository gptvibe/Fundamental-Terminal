import { ResearchBriefStateBlock } from "@/components/company/brief-primitives";
import { formatDate } from "@/lib/format";

import type { WhatChangedHighlightItem } from "../_lib/what-changed-summary";

function toneForSeverity(severity: WhatChangedHighlightItem["severity"]): "red" | "gold" | "cyan" {
  if (severity === "high") {
    return "red";
  }
  if (severity === "medium") {
    return "gold";
  }
  return "cyan";
}

export function WhatChangedHighlights({ items, loading }: { items: WhatChangedHighlightItem[]; loading: boolean }) {
  if (!items.length) {
    return loading ? (
      <ResearchBriefStateBlock
        kind="loading"
        kicker="What changed"
        title="Ranking newest changes"
        message="Checking filings, event feed, model outputs, and ownership/governance summaries for dated change signals."
        minHeight={180}
      />
    ) : (
      <ResearchBriefStateBlock
        kind="empty"
        kicker="What changed"
        title="No ranked changes available"
        message="No recent filing/event, financial, model, or ownership/governance changes are cached yet for this company."
        minHeight={180}
      />
    );
  }

  return (
    <div className="what-changed-highlight-list" aria-label="Ranked what changed highlights">
      {items.map((item) => {
        const tone = toneForSeverity(item.severity);

        return (
          <article key={item.id} className={`what-changed-highlight-item tone-${tone}`}>
            <div className="what-changed-highlight-topline">
              <h4 className="what-changed-highlight-title">{item.title}</h4>
              <span className={`pill tone-${tone}`}>{item.severity}</span>
            </div>
            <p className="what-changed-highlight-detail">{item.detail}</p>
            <div className="what-changed-highlight-meta">Date: {formatDate(item.occurredAt)} · Source: {item.sourceLabel}</div>
            <div className="what-changed-highlight-meta">Provenance: {item.provenance}</div>
          </article>
        );
      })}
    </div>
  );
}

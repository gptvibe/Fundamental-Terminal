import type { ReactNode } from "react";

import { clsx } from "clsx";

export interface EvidenceMetaItem {
  label: string;
  value: ReactNode;
  emphasized?: boolean;
}

export function EvidenceMetaBlock({
  items,
  className,
}: {
  items: EvidenceMetaItem[];
  className?: string;
}) {
  return (
    <dl className={clsx("evidence-meta-block", className)}>
      {items.map((item) => (
        <div key={item.label} className={clsx("evidence-meta-item", item.emphasized && "is-emphasized")}>
          <dt className="evidence-meta-label">{item.label}</dt>
          <dd className="evidence-meta-value">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
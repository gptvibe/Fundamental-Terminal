"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export type MetricFreshnessState = "fresh" | "stale" | "unknown";

export interface MetricConfidenceMetadata {
  freshness?: MetricFreshnessState | null;
  source?: string | null;
  formulaVersion?: string | null;
  missingInputsCount?: number | null;
  missingInputs?: string[] | null;
  proxyUsed?: boolean | null;
  fallbackUsed?: boolean | null;
  qualityFlags?: string[] | null;
  lastRefreshedAt?: string | null;
  stalenessReason?: string | null;
}

interface MetricConfidenceBadgeProps {
  metadata: MetricConfidenceMetadata;
  className?: string;
  ariaLabel?: string;
}

export function MetricConfidenceBadge({
  metadata,
  className,
  ariaLabel = "Metric confidence details",
}: MetricConfidenceBadgeProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const chipCount = useMemo(() => countVisibleChips(metadata), [metadata]);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open]);

  if (chipCount === 0) {
    return null;
  }

  const freshness = normalizeFreshness(metadata.freshness);
  const source = normalizeText(metadata.source);
  const formulaVersion = normalizeText(metadata.formulaVersion);
  const missingInputsCount = normalizeMissingCount(metadata.missingInputsCount, metadata.missingInputs);
  const proxyUsed = Boolean(metadata.proxyUsed);
  const fallbackUsed = Boolean(metadata.fallbackUsed);
  const qualityFlags = (metadata.qualityFlags ?? []).filter((flag) => Boolean(normalizeText(flag)));

  return (
    <div ref={rootRef} className={`metric-confidence-badge-container ${className ?? ""}`.trim()}>
      <button
        type="button"
        className={`metric-confidence-trigger ${open ? "is-open" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((current) => !current)}
      >
        {freshness !== "unknown" ? (
          <span className={`metric-confidence-chip tone-${freshness === "fresh" ? "green" : "gold"}`}>{freshness}</span>
        ) : null}
        {source ? <span className="metric-confidence-chip">src {source}</span> : null}
        {formulaVersion ? <span className="metric-confidence-chip">formula {formulaVersion}</span> : null}
        {missingInputsCount > 0 ? <span className="metric-confidence-chip tone-gold">missing {missingInputsCount}</span> : null}
        {proxyUsed ? <span className="metric-confidence-chip tone-gold">proxy</span> : null}
        {fallbackUsed ? <span className="metric-confidence-chip tone-red">fallback</span> : null}
      </button>

      <div
        role="dialog"
        aria-label={ariaLabel}
        className={`metric-confidence-popover ${open ? "is-open" : ""}`}
      >
        <div className="metric-confidence-popover-row">
          <span className="metric-confidence-popover-label">Freshness</span>
          <span className="metric-confidence-popover-value">{freshness}</span>
        </div>
        <div className="metric-confidence-popover-row">
          <span className="metric-confidence-popover-label">Source</span>
          <span className="metric-confidence-popover-value">{source ?? "unknown"}</span>
        </div>
        <div className="metric-confidence-popover-row">
          <span className="metric-confidence-popover-label">Formula version</span>
          <span className="metric-confidence-popover-value">{formulaVersion ?? "unknown"}</span>
        </div>
        <div className="metric-confidence-popover-row">
          <span className="metric-confidence-popover-label">Missing inputs</span>
          <span className="metric-confidence-popover-value">{missingInputsCount}</span>
        </div>
        <div className="metric-confidence-popover-row">
          <span className="metric-confidence-popover-label">Proxy used</span>
          <span className="metric-confidence-popover-value">{proxyUsed ? "yes" : "no"}</span>
        </div>
        <div className="metric-confidence-popover-row">
          <span className="metric-confidence-popover-label">Fallback used</span>
          <span className="metric-confidence-popover-value">{fallbackUsed ? "yes" : "no"}</span>
        </div>
        {metadata.lastRefreshedAt ? (
          <div className="metric-confidence-popover-row">
            <span className="metric-confidence-popover-label">Last refreshed</span>
            <span className="metric-confidence-popover-value">{metadata.lastRefreshedAt}</span>
          </div>
        ) : null}
        {metadata.stalenessReason ? (
          <div className="metric-confidence-popover-row">
            <span className="metric-confidence-popover-label">Staleness reason</span>
            <span className="metric-confidence-popover-value">{metadata.stalenessReason}</span>
          </div>
        ) : null}
        {qualityFlags.length ? (
          <div className="metric-confidence-popover-row">
            <span className="metric-confidence-popover-label">Quality flags</span>
            <span className="metric-confidence-popover-value">{qualityFlags.join(", ")}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function countVisibleChips(metadata: MetricConfidenceMetadata): number {
  let count = 0;

  const freshness = normalizeFreshness(metadata.freshness);
  if (freshness !== "unknown") {
    count += 1;
  }
  if (normalizeText(metadata.source)) {
    count += 1;
  }
  if (normalizeText(metadata.formulaVersion)) {
    count += 1;
  }
  if (normalizeMissingCount(metadata.missingInputsCount, metadata.missingInputs) > 0) {
    count += 1;
  }
  if (metadata.proxyUsed) {
    count += 1;
  }
  if (metadata.fallbackUsed) {
    count += 1;
  }

  return count;
}

function normalizeFreshness(value: MetricFreshnessState | null | undefined): MetricFreshnessState {
  if (value === "fresh" || value === "stale") {
    return value;
  }
  return "unknown";
}

function normalizeText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  return trimmed;
}

function normalizeMissingCount(explicitCount: number | null | undefined, explicitInputs: string[] | null | undefined): number {
  if (typeof explicitCount === "number" && Number.isFinite(explicitCount) && explicitCount > 0) {
    return Math.max(0, Math.floor(explicitCount));
  }

  if (Array.isArray(explicitInputs)) {
    return explicitInputs.filter((item) => Boolean(normalizeText(item))).length;
  }

  return 0;
}

"use client";

import type { ReactNode } from "react";
import { clsx } from "clsx";

export interface Change {
  id: string;
  title: string;
  description: ReactNode;
  severity?: "critical" | "high" | "medium" | "low";
  timestamp?: string;
  actionUrl?: string;
  actionLabel?: string;
}

export interface ImportantChangesPanelProps {
  changes: Change[];
  title?: string;
  subtitle?: string;
  emptyDescription?: string;
  emptyActionLabel?: string;
  loading?: boolean;
  className?: string;
  onActionClick?: (change: Change) => void;
  onEmptyActionClick?: () => void;
}

export function ImportantChangesPanel({
  changes,
  title = "Important changes",
  subtitle,
  emptyDescription = "No high-signal filing or activity changes are available in the cached brief yet.",
  emptyActionLabel,
  loading = false,
  className,
  onActionClick,
  onEmptyActionClick,
}: ImportantChangesPanelProps) {
  if (loading) {
    return (
      <div
        className={clsx("important-changes-panel", "panel-loading", className)}
        role="status"
        aria-label="Loading changes"
      >
        <h3 className="panel-title">{title}</h3>
        <div className="loading-skeleton">
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line" style={{ width: "70%" }} />
        </div>
      </div>
    );
  }

  if (changes.length === 0) {
    return (
      <div className={clsx("important-changes-panel", "panel-empty", className)}>
        <h3 className="panel-title">{title}</h3>
        <p className="panel-empty-message">{emptyDescription}</p>
        {emptyActionLabel && onEmptyActionClick ? (
          <button type="button" className="change-action-button" onClick={onEmptyActionClick}>
            {emptyActionLabel} →
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className={clsx("important-changes-panel", className)}>
      <div className="panel-header">
        <h3 className="panel-title">{title}</h3>
        {subtitle && <p className="panel-subtitle">{subtitle}</p>}
      </div>

      <div className="changes-list">
        {changes.map((change) => (
          <article
            key={change.id}
            className={clsx(
              "change-item",
              change.severity && `severity-${change.severity}`
            )}
          >
            <div className="change-header">
              {change.severity && (
                <span
                  className="severity-indicator"
                  aria-label={`Severity: ${change.severity}`}
                  title={`Severity: ${change.severity}`}
                >
                  {getSeverityIcon(change.severity)}
                </span>
              )}
              <h4 className="change-title">{change.title}</h4>
              {change.severity && (
                <span className={clsx("severity-label", getSeverityToneClass(change.severity))}>
                  {change.severity}
                </span>
              )}
              {change.timestamp && (
                <time className="change-timestamp" dateTime={change.timestamp}>
                  {formatRelativeTime(change.timestamp)}
                </time>
              )}
            </div>

            <div className="change-description">{change.description}</div>

            {(change.actionUrl || change.actionLabel) && (
              <div className="change-action">
                <button
                  className="change-action-button"
                  onClick={() => {
                    if (onActionClick) {
                      onActionClick(change);
                      return;
                    }
                    if (change.actionUrl) {
                      window.location.href = change.actionUrl;
                    }
                  }}
                  aria-label={change.actionLabel || "View details"}
                >
                  {change.actionLabel || "View details"} →
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

function getSeverityIcon(severity: string): ReactNode {
  const icons: Record<string, string> = {
    critical: "🔴",
    high: "🟠",
    medium: "🟡",
    low: "🔵",
  };
  return icons[severity] || "•";
}

function getSeverityToneClass(severity: string): string {
  if (severity === "critical" || severity === "high") {
    return "tone-red";
  }
  if (severity === "medium") {
    return "tone-gold";
  }
  return "tone-cyan";
}

function formatRelativeTime(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;

  return date.toLocaleDateString();
}

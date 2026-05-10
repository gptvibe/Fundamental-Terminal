"use client";

import { type ReactNode } from "react";
import { clsx } from "clsx";

export interface LoadingStateProps {
  title?: string;
  subtitle?: string;
  details?: string[];
  type?: "loading" | "refreshing" | "queued" | "cached" | "missing";
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function LoadingStateIndicator({
  title = "Loading data",
  subtitle,
  details,
  type = "loading",
  action,
  className,
}: LoadingStateProps) {
  const stateConfig = {
    loading: {
      icon: "⟳",
      tone: "neutral",
      animated: true,
    },
    refreshing: {
      icon: "↻",
      tone: "info",
      animated: true,
    },
    queued: {
      icon: "⌛",
      tone: "warning",
      animated: false,
    },
    cached: {
      icon: "✓",
      tone: "success",
      animated: false,
    },
    missing: {
      icon: "⊘",
      tone: "warning",
      animated: false,
    },
  };

  const config = stateConfig[type];

  return (
    <div
      className={clsx(
        "loading-state-indicator",
        `loading-state-${type}`,
        `loading-state-tone-${config.tone}`,
        config.animated && "loading-state-animated",
        className
      )}
      role="status"
      aria-live="polite"
      aria-label={`${type}: ${title}`}
    >
      <div className="loading-state-icon">{config.icon}</div>
      <div className="loading-state-content">
        <h3 className="loading-state-title">{title}</h3>
        {subtitle && <p className="loading-state-subtitle">{subtitle}</p>}
        {details && details.length > 0 && (
          <ul className="loading-state-details">
            {details.map((detail, i) => (
              <li key={i} className="loading-state-detail">
                {detail}
              </li>
            ))}
          </ul>
        )}
      </div>
      {action && (
        <button
          className="loading-state-action"
          onClick={action.onClick}
          aria-label={`${action.label}: ${title}`}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: string;
  actions?: Array<{
    label: string;
    href?: string;
    onClick?: () => void;
    variant?: "primary" | "secondary";
  }>;
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon = "○",
  actions,
  className,
}: EmptyStateProps) {
  return (
    <div className={clsx("empty-state", className)} role="status" aria-live="polite">
      <div className="empty-state-icon">{icon}</div>
      <h3 className="empty-state-title">{title}</h3>
      {description && <p className="empty-state-description">{description}</p>}
      {actions && actions.length > 0 && (
        <div className="empty-state-actions">
          {actions.map((action, i) => (
            <button
              key={i}
              className={clsx("empty-state-action", `empty-state-action-${action.variant ?? "primary"}`)}
              onClick={() => {
                action.onClick?.();
                if (action.href) {
                  window.location.href = action.href;
                }
              }}
              aria-label={action.label}
            >
              {action.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export interface DataLoadingWrapperProps {
  loading?: boolean;
  error?: string | null;
  isEmpty?: boolean;
  children?: ReactNode;
  onRetry?: () => void;
  loadingTitle?: string;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function DataLoadingWrapper({
  loading,
  error,
  isEmpty,
  children,
  onRetry,
  loadingTitle = "Loading data",
  emptyTitle = "No data available",
  emptyDescription = "This data will appear once it's available.",
}: DataLoadingWrapperProps) {
  if (error) {
    return (
      <EmptyState
        title="Error loading data"
        description={error}
        icon="⚠"
        actions={
          onRetry
            ? [
                {
                  label: "Retry",
                  onClick: onRetry,
                  variant: "primary",
                },
              ]
            : undefined
        }
      />
    );
  }

  if (loading && !children) {
    return <LoadingStateIndicator title={loadingTitle} type="loading" />;
  }

  if (isEmpty && !children) {
    return (
      <EmptyState
        title={emptyTitle}
        description={emptyDescription}
        icon="○"
      />
    );
  }

  return <>{children}</>;
}

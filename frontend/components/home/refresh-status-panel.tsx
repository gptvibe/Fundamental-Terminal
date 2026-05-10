"use client";

import { useEffect, useMemo, useState } from "react";

import { Panel } from "@/components/ui/panel";
import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import { useJobStream } from "@/hooks/use-job-stream";
import { ACTIVE_JOB_EVENT, clearStoredActiveJob, readStoredActiveJob, type StoredActiveJob } from "@/lib/active-job";
import { formatRelativeMoment } from "@/lib/format";
import { titleCase } from "@/lib/format";
import type { ConsoleEntry, WatchlistSummaryItemPayload } from "@/lib/types";

type HomeChangeTone = "attention-high" | "attention-medium" | "live" | "success" | "error";

interface HomeChangeItem {
  id: string;
  ticker: string | null;
  name: string | null;
  label: string;
  title: string;
  detail: string;
  date: string | null;
  tone: HomeChangeTone;
}

function toneFromConsoleEntry(entry: ConsoleEntry): HomeChangeTone {
  if (entry.level === "error") return "error";
  if (entry.level === "success" || entry.status === "completed") return "success";
  return "live";
}

function getChangeToneClass(tone: HomeChangeTone): string {
  return `is-${tone}`;
}

function toTimestamp(value: string | null | undefined): number {
  if (!value) return 0;
  const ts = Date.parse(value);
  return Number.isNaN(ts) ? 0 : ts;
}

function buildRecentChangeFeed(summaryItems: WatchlistSummaryItemPayload[], consoleEntries: ConsoleEntry[]): HomeChangeItem[] {
  const watchlistChanges = summaryItems.flatMap((item) => {
    const changes: HomeChangeItem[] = [];

    if (item.latest_alert) {
      changes.push({
        id: `${item.ticker}-alert-${item.latest_alert.id}`,
        ticker: item.ticker,
        name: item.name,
        label: `${item.latest_alert.level.toUpperCase()} alert`,
        title: item.latest_alert.title,
        detail: [
          item.latest_alert.source,
          item.alert_summary.total ? `${item.alert_summary.total} active alerts` : null,
        ]
          .filter(Boolean)
          .join(" · "),
        date: item.latest_alert.date ?? item.last_checked,
        tone: item.latest_alert.level === "high" ? "attention-high" : "attention-medium",
      });
    }

    if (item.latest_activity) {
      changes.push({
        id: `${item.ticker}-activity-${item.latest_activity.id}`,
        ticker: item.ticker,
        name: item.name,
        label: item.latest_activity.badge || titleCase(item.latest_activity.type),
        title: item.latest_activity.title,
        detail: [item.sector, titleCase(item.latest_activity.type)].filter(Boolean).join(" · ") || "Watchlist activity",
        date: item.latest_activity.date ?? item.last_checked,
        tone: "live",
      });
    }

    return changes;
  });

  const streamChanges = consoleEntries.map((entry) => ({
    id: `console-${entry.id}`,
    ticker: entry.ticker?.trim().toUpperCase() || null,
    name: null,
    label: entry.level === "error" ? "Pipeline issue" : entry.status === "completed" ? "Refresh complete" : titleCase(entry.stage),
    title: entry.message,
    detail:
      [
        entry.ticker?.trim().toUpperCase() || null,
        entry.kind ? titleCase(entry.kind) : null,
        entry.trace_id ? `#${entry.trace_id.slice(0, 8)}` : null,
      ]
        .filter(Boolean)
        .join(" · ") || "Background refresh",
    date: entry.timestamp,
    tone: toneFromConsoleEntry(entry),
  }));

  return [...watchlistChanges, ...streamChanges]
    .sort((left, right) => toTimestamp(right.date) - toTimestamp(left.date))
    .slice(0, 8);
}

function getLiveFeedLabel(
  connectionState: "idle" | "connecting" | "open" | "closed" | "error",
  recentJob: StoredActiveJob | null
): string {
  if (!recentJob) return "Watching for updates";

  switch (connectionState) {
    case "open":
      return `${recentJob.ticker} live`;
    case "connecting":
      return `${recentJob.ticker} connecting`;
    case "error":
      return `${recentJob.ticker} reconnecting`;
    case "closed":
      return `${recentJob.ticker} paused`;
    default:
      return `${recentJob.ticker} queued`;
  }
}

interface RefreshStatusPanelProps {
  watchlistTickers: string[];
  summaryItems: WatchlistSummaryItemPayload[];
  summaryLoading: boolean;
  summaryError: string | null;
}

export function RefreshStatusPanel({ watchlistTickers, summaryItems, summaryLoading, summaryError }: RefreshStatusPanelProps) {
  const [recentJob, setRecentJob] = useState<StoredActiveJob | null>(null);
  const goToTicker = useGoToTicker();

  useEffect(() => {
    setRecentJob(readStoredActiveJob());

    function syncRecentJob() {
      setRecentJob(readStoredActiveJob());
    }

    window.addEventListener(ACTIVE_JOB_EVENT, syncRecentJob as EventListener);
    return () => window.removeEventListener(ACTIVE_JOB_EVENT, syncRecentJob as EventListener);
  }, []);

  const { consoleEntries, connectionState } = useJobStream(recentJob?.jobId ?? null);

  // Auto-clear a failed job with no output
  useEffect(() => {
    if (!recentJob || connectionState !== "error" || consoleEntries.length) {
      return;
    }
    clearStoredActiveJob(recentJob.jobId);
    setRecentJob(null);
  }, [connectionState, consoleEntries.length, recentJob]);

  const recentChanges = useMemo(() => buildRecentChangeFeed(summaryItems, consoleEntries), [summaryItems, consoleEntries]);
  const liveFeedLabel = useMemo(() => getLiveFeedLabel(connectionState, recentJob), [connectionState, recentJob]);

  return (
    <Panel
      title="Recent Changes"
      subtitle={
        watchlistTickers.length
          ? "Latest watchlist alerts, filing activity, and background refresh events in one feed."
          : "Background refreshes stay visible here. Add watchlist names to layer in persisted alerts and activity."
      }
      className="home-terminal-panel home-terminal-panel-wide"
      variant="subtle"
      aside={<span className="pill">{liveFeedLabel}</span>}
    >
      {summaryError ? <div className="text-muted">{summaryError}</div> : null}
      {summaryLoading && watchlistTickers.length ? <div className="text-muted">Loading watchlist changes...</div> : null}
      {recentChanges.length ? (
        <div className="home-change-list">
          {recentChanges.map((change) => (
            <div key={change.id} className="home-change-item">
              <div className="home-change-copy">
                <div className="home-change-kicker-row">
                  <span className={`home-change-badge ${getChangeToneClass(change.tone)}`}>{change.label}</span>
                  {change.ticker ? (
                    <span className="home-change-company">
                      {change.ticker}
                      {change.name ? ` · ${change.name}` : ""}
                    </span>
                  ) : null}
                </div>
                {change.ticker ? (
                  <button
                    type="button"
                    className="home-inline-link home-change-link"
                    onClick={() =>
                      goToTicker(change.ticker ?? "", "company", {
                        ticker: change.ticker ?? "",
                        name: change.name,
                      })
                    }
                  >
                    {change.title}
                  </button>
                ) : (
                  <div className="home-change-title">{change.title}</div>
                )}
                <div className="home-change-detail">{change.detail}</div>
              </div>
              <div className="home-change-time">{formatRelativeMoment(change.date)}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="home-utility-empty">No recent changes yet. Launch a company or run a refresh to start building the feed.</div>
      )}
    </Panel>
  );
}

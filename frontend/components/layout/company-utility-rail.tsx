"use client";

import type { ReactNode } from "react";
import Link from "next/link";

import { CompanyDevicePanel } from "@/components/personal/company-device-panel";
import { StatusConsole } from "@/components/console/status-console";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import type { ConsoleEntry, RefreshState } from "@/lib/types";

type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";

interface CompanyUtilityRailProps {
  ticker: string;
  companyName?: string | null;
  sector?: string | null;
  refreshState: RefreshState | null;
  refreshing: boolean;
  onRefresh: () => void | Promise<void>;
  actionTitle?: string;
  actionSubtitle?: string;
  primaryActionLabel: string;
  primaryActionDescription?: string;
  secondaryActionHref?: string;
  secondaryActionLabel?: string;
  secondaryActionDescription?: string;
  statusLines?: string[];
  consoleEntries: ConsoleEntry[];
  connectionState: ConnectionState;
  actionTone?: "green" | "gold";
  children?: ReactNode;
}

export function CompanyUtilityRail({
  ticker,
  companyName,
  sector,
  refreshState,
  refreshing,
  onRefresh,
  actionTitle = "Quick Actions",
  actionSubtitle = "Choose what to do next for this company.",
  primaryActionLabel,
  primaryActionDescription,
  secondaryActionHref,
  secondaryActionLabel,
  secondaryActionDescription,
  statusLines = [],
  consoleEntries,
  connectionState,
  actionTone = "green",
  children
}: CompanyUtilityRailProps) {
  const effectiveState =
    refreshState ?? {
      triggered: false,
      reason: "none" as const,
      ticker,
      job_id: null
    };
  const actionStyle =
    actionTone === "gold"
      ? { borderColor: "rgba(255,215,0,0.35)", color: "#FFD700" }
      : { borderColor: "rgba(0,255,65,0.35)", color: "#00FF41" };
  const refreshInProgress =
    refreshing ||
    (Boolean(effectiveState.triggered && effectiveState.job_id) && connectionState !== "idle" && connectionState !== "error");

  // Find the latest console entry message if refreshing
  let dynamicStatusMsg: string | null = null;
  if (refreshInProgress && consoleEntries.length > 0) {
    // Show the last non-empty message
    const lastMsg = [...consoleEntries].reverse().find(e => e.message && e.status === "running");
    if (lastMsg) {
      dynamicStatusMsg = lastMsg.message;
    }
  }

  const refreshButtonLabel = refreshing
    ? "Starting refresh..."
    : refreshInProgress
      ? dynamicStatusMsg || "Refresh in progress"
      : primaryActionLabel;

  return (
    <div className="company-utility-stack">
      <Panel title={actionTitle} subtitle={actionSubtitle}>
        <div className="utility-action-list">
          <div className="utility-action-item">
              <button
                onClick={() => void onRefresh()}
                className="ticker-button utility-action-button"
                style={actionStyle}
                disabled={refreshInProgress}
                aria-disabled={refreshInProgress}
              >
                {refreshInProgress && (
                  <span className="spinner" style={{ marginRight: 8, verticalAlign: "middle" }}>
                    <svg width="18" height="18" viewBox="0 0 50 50">
                      <circle cx="25" cy="25" r="20" fill="none" stroke="#00FF41" strokeWidth="5" strokeDasharray="31.4 31.4" strokeLinecap="round">
                        <animateTransform attributeName="transform" type="rotate" from="0 25 25" to="360 25 25" dur="1s" repeatCount="indefinite" />
                      </circle>
                    </svg>
                  </span>
                )}
                {refreshButtonLabel}
              </button>
            {primaryActionDescription ? <div className="utility-action-description">{primaryActionDescription}</div> : null}
          </div>
          {secondaryActionHref && secondaryActionLabel ? (
            <div className="utility-action-item">
              <Link href={secondaryActionHref} className="ticker-button utility-action-button" style={{ display: "block" }}>
                {secondaryActionLabel}
              </Link>
              {secondaryActionDescription ? <div className="utility-action-description">{secondaryActionDescription}</div> : null}
            </div>
          ) : null}
        </div>
      </Panel>

      <Panel title="Saved On This Device" subtitle="Keep your own watchlist and private notes without creating an account.">
        <CompanyDevicePanel ticker={ticker} companyName={companyName} sector={sector} />
      </Panel>

      {children}

      <Panel title="Data Status" subtitle="See what is available and whether this workspace is up to date.">
        <div style={{ display: "grid", gap: 12 }}>
          <StatusPill state={effectiveState} />
          {statusLines.map((line) => (
            <div key={line} className="sparkline-note">
              {line}
            </div>
          ))}
        </div>
      </Panel>

      <Panel title="Live Updates" subtitle="Follow progress while company data refreshes in the background.">
        <StatusConsole entries={consoleEntries} connectionState={connectionState} />
      </Panel>
    </div>
  );
}

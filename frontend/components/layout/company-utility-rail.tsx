"use client";

import type { ReactNode } from "react";
import Link from "next/link";

import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { CompanyDevicePanel } from "@/components/personal/company-device-panel";
import { StatusConsole } from "@/components/console/status-console";
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
  presentation?: "default" | "brief";
  children?: ReactNode;
}

export function CompanyUtilityRail({
  ticker,
  companyName,
  sector,
  refreshState,
  refreshing,
  onRefresh,
  actionTitle,
  actionSubtitle,
  primaryActionLabel,
  primaryActionDescription,
  secondaryActionHref,
  secondaryActionLabel,
  secondaryActionDescription,
  statusLines,
  consoleEntries,
  connectionState,
  presentation = "default",
  children,
}: CompanyUtilityRailProps) {
  const effectiveState =
    refreshState ?? {
      triggered: false,
      reason: "none" as const,
      ticker,
      job_id: null,
    };
  const refreshInProgress =
    refreshing ||
    (Boolean(effectiveState.triggered && effectiveState.job_id) &&
      connectionState !== "idle" &&
      connectionState !== "error");
  const effectiveStatusLines = [...buildRefreshStatusLines(effectiveState, refreshInProgress), ...(statusLines ?? [])];
  const secondaryPanels = presentation === "brief"
    ? (
        <>
          {children}
          <CompanyDevicePanel ticker={ticker} companyName={companyName} sector={sector} />
        </>
      )
    : (
        <>
          <CompanyDevicePanel ticker={ticker} companyName={companyName} sector={sector} />
          {children}
        </>
      );

  return (
    <div className={`company-utility-stack${presentation === "brief" ? " company-utility-stack-brief" : ""}`}>
      <Panel
        title={actionTitle ?? (presentation === "brief" ? "Brief actions" : "Actions")}
        subtitle={actionSubtitle}
        variant="subtle"
      >
        <div className="utility-action-bar">
          <div className="utility-action-item">
            <StatusPill state={effectiveState} />
            <button
              onClick={() => void onRefresh()}
              disabled={refreshInProgress}
              className="ticker-button utility-action-button utility-action-button-primary"
            >
              {refreshInProgress ? (
                <span className="utility-action-spinner" aria-hidden="true" />
              ) : null}
              {refreshInProgress ? "Refreshing…" : primaryActionLabel}
            </button>
            {primaryActionDescription ? (
              <span className="utility-action-description">{primaryActionDescription}</span>
            ) : null}
          </div>
          {secondaryActionHref ? (
            <div className="utility-action-item">
              <Link
                href={secondaryActionHref}
                className="ticker-button utility-action-button utility-action-button-secondary utility-action-link-button"
              >
                {secondaryActionLabel ?? "Navigate"}
              </Link>
              {secondaryActionDescription ? (
                <span className="utility-action-description">{secondaryActionDescription}</span>
              ) : null}
            </div>
          ) : null}
        </div>

        {presentation === "brief" && effectiveStatusLines.length ? (
          <div className="utility-status-quiet" aria-label="Brief data status">
            {effectiveStatusLines.map((line, index) => (
              <div key={index} className="utility-status-quiet-line">{line}</div>
            ))}
          </div>
        ) : null}
      </Panel>

      {presentation !== "brief" && effectiveStatusLines.length ? (
        <Panel title="Data status" variant="subtle">
          <div className="utility-status-stack">
            {effectiveStatusLines.map((line, index) => (
              <div key={index} className="utility-status-line">{line}</div>
            ))}
          </div>
        </Panel>
      ) : null}

      {secondaryPanels}

      {presentation !== "brief" ? (
        <Panel title="Console" variant="subtle">
          <StatusConsole entries={consoleEntries} connectionState={connectionState} />
        </Panel>
      ) : null}
    </div>
  );
}

function buildRefreshStatusLines(refreshState: RefreshState, refreshInProgress: boolean): string[] {
  const lines = [
    `Refresh status: ${describeRefreshStatus(refreshState, refreshInProgress)}`,
    refreshState.job_id ? `Background job: ${refreshState.job_id}` : null,
  ];

  return lines.filter((line): line is string => Boolean(line));
}

function describeRefreshStatus(refreshState: RefreshState, refreshInProgress: boolean): string {
  if (refreshInProgress || refreshState.job_id) {
    return "running in the background";
  }

  switch (refreshState.reason) {
    case "fresh":
      return "cache is up to date";
    case "stale":
      return "cached data is stale";
    case "missing":
      return "first snapshot is still warming";
    case "manual":
      return "manual refresh requested";
    case "none":
      return "background-first";
    default:
      return refreshState.reason;
  }
}

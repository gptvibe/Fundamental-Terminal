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
  children?: ReactNode;
}

export function CompanyUtilityRail({
  ticker,
  companyName,
  sector,
  refreshState,
  refreshing,
  onRefresh,
  primaryActionLabel,
  primaryActionDescription,
  secondaryActionHref,
  secondaryActionLabel,
  secondaryActionDescription,
  statusLines,
  consoleEntries,
  connectionState,
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

  return (
    <div className="company-utility-stack">
      <Panel title="Actions" variant="subtle">
        <div className="utility-action-bar">
          <div className="utility-action-item">
            <StatusPill state={effectiveState} />
            <button
              onClick={() => void onRefresh()}
              disabled={refreshInProgress}
              className="ticker-button utility-action-button"
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
                className="ticker-button utility-action-button utility-action-link-button"
              >
                {secondaryActionLabel ?? "Navigate"}
              </Link>
              {secondaryActionDescription ? (
                <span className="utility-action-description">{secondaryActionDescription}</span>
              ) : null}
            </div>
          ) : null}
        </div>
      </Panel>

      {statusLines?.length ? (
        <Panel title="Data Status" variant="subtle">
          <div className="utility-status-stack">
            {statusLines.map((line, index) => (
              <div key={index} className="utility-status-line">{line}</div>
            ))}
          </div>
        </Panel>
      ) : null}

      <CompanyDevicePanel ticker={ticker} companyName={companyName} sector={sector} />

      {children}

      <Panel title="Console" variant="subtle">
        <StatusConsole entries={consoleEntries} connectionState={connectionState} />
      </Panel>
    </div>
  );
}

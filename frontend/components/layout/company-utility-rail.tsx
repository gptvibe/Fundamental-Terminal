"use client";

import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";

import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { CompanyDevicePanel } from "@/components/personal/company-device-panel";
import { StatusConsole } from "@/components/console/status-console";
import { useLocalCompareSet } from "@/hooks/use-local-compare-set";
import { MAX_COMPARE_TICKERS } from "@/lib/local-compare-set";
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
  const [compareDrawerOpen, setCompareDrawerOpen] = useState(false);
  const [compareInput, setCompareInput] = useState("");
  const {
    compareCompanies,
    compareTickers,
    compareHref,
    hasTicker,
    addCompanies,
    toggleCompany,
    removeCompany,
    clearCompareSet,
    syncMetadata,
  } = useLocalCompareSet();
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
  const currentTickerSaved = hasTicker(ticker);
  const compareCount = compareCompanies.length;

  useEffect(() => {
    syncMetadata({ ticker, name: companyName ?? null, sector: sector ?? null });
  }, [ticker, companyName, sector, syncMetadata]);

  useEffect(() => {
    if (!compareDrawerOpen) {
      return undefined;
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setCompareDrawerOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [compareDrawerOpen]);

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
    <>
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

            <div className="utility-action-item">
              <button
                type="button"
                onClick={() => setCompareDrawerOpen(true)}
                className="ticker-button utility-action-button utility-action-button-secondary"
              >
                Compare
              </button>
              <span className="utility-action-description">
                Build a local compare set for up to {MAX_COMPARE_TICKERS} tickers. Currently saved: {compareCount}.
              </span>
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

      {compareDrawerOpen ? (
        <>
          <button
            type="button"
            className="utility-compare-overlay"
            aria-label="Close compare drawer"
            onClick={() => setCompareDrawerOpen(false)}
          />
          <aside className="utility-compare-drawer" role="dialog" aria-modal="true" aria-label="Compare companies">
            <div className="utility-compare-shell">
              <div className="utility-compare-header">
                <div>
                  <div className="utility-compare-title">Compare Workspace</div>
                  <p className="utility-compare-copy">
                    Save up to {MAX_COMPARE_TICKERS} tickers locally, then open a single compare page for statements,
                    derived metrics, and valuation outputs.
                  </p>
                </div>
                <button
                  type="button"
                  className="ticker-button utility-action-button utility-action-button-secondary utility-compare-close"
                  onClick={() => setCompareDrawerOpen(false)}
                >
                  Close
                </button>
              </div>

              <div className="utility-compare-actions">
                <div className="utility-action-item">
                  <button
                    type="button"
                    onClick={() => toggleCompany({ ticker, name: companyName ?? null, sector: sector ?? null })}
                    className="ticker-button utility-action-button utility-action-button-secondary"
                  >
                    {currentTickerSaved ? `Remove ${ticker}` : `Add ${ticker}`}
                  </button>
                  <span className="utility-action-description">
                    {currentTickerSaved
                      ? "The current company is already in the compare set."
                      : "Add the current company without typing the ticker manually."}
                  </span>
                </div>

                <form
                  className="utility-compare-input-row"
                  onSubmit={(event) => handleCompareSubmit(event, compareInput, addCompanies, setCompareInput)}
                >
                  <label className="utility-action-label" htmlFor="utility-compare-input">
                    Add tickers
                  </label>
                  <input
                    id="utility-compare-input"
                    className="utility-compare-input"
                    value={compareInput}
                    onChange={(event) => setCompareInput(event.target.value.toUpperCase())}
                    placeholder="MSFT, NVDA, AMZN"
                    autoComplete="off"
                    spellCheck={false}
                  />
                  <button type="submit" className="ticker-button utility-action-button utility-action-button-primary">
                    Add To Compare
                  </button>
                </form>
              </div>

              {compareCompanies.length ? (
                <div className="utility-compare-chip-grid" aria-label="Saved compare companies">
                  {compareCompanies.map((company) => (
                    <span key={company.ticker} className="utility-compare-chip">
                      <span className="utility-compare-chip-text">
                        <strong>{company.ticker}</strong>
                        {company.name ? <span className="utility-compare-chip-name">{company.name}</span> : null}
                      </span>
                      <button
                        type="button"
                        className="utility-compare-chip-remove"
                        aria-label={`Remove ${company.ticker} from compare set`}
                        onClick={() => removeCompany(company.ticker)}
                      >
                        x
                      </button>
                    </span>
                  ))}
                </div>
              ) : (
                <p className="utility-compare-note">No compare tickers saved yet. Add the current company or paste a few symbols.</p>
              )}

              <div className="utility-compare-footer">
                <div className="utility-compare-footer-actions">
                  <button
                    type="button"
                    className="ticker-button utility-action-button utility-action-button-secondary"
                    onClick={() => clearCompareSet()}
                    disabled={!compareCompanies.length}
                  >
                    Clear Set
                  </button>
                  {compareTickers.length ? (
                    <Link
                      href={compareHref}
                      className="ticker-button utility-action-button utility-action-button-primary utility-action-link-button"
                      onClick={() => setCompareDrawerOpen(false)}
                    >
                      Open Compare Page
                    </Link>
                  ) : (
                    <button
                      type="button"
                      className="ticker-button utility-action-button utility-action-button-primary"
                      disabled
                    >
                      Open Compare Page
                    </button>
                  )}
                </div>
                <p className="utility-compare-note">
                  The compare set lives in local browser storage. Newest additions keep the list capped at {MAX_COMPARE_TICKERS}.
                </p>
              </div>
            </div>
          </aside>
        </>
      ) : null}
    </>
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

function handleCompareSubmit(
  event: FormEvent<HTMLFormElement>,
  compareInput: string,
  addCompanies: (snapshots: Array<{ ticker: string }>) => unknown,
  setCompareInput: (value: string) => void
): void {
  event.preventDefault();
  const tickers = parseCompareInput(compareInput);
  if (!tickers.length) {
    return;
  }
  addCompanies(tickers.map((ticker) => ({ ticker })));
  setCompareInput("");
}

function parseCompareInput(value: string): string[] {
  return [...new Set(value.split(/[\s,]+/).map((ticker) => ticker.trim().toUpperCase()).filter(Boolean))];
}

"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";

import { Panel } from "@/components/ui/panel";
import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { formatRelativeMoment } from "@/lib/format";
import type { WatchlistSummaryItemPayload } from "@/lib/types";

interface WatchlistSummaryProps {
  summaryLoading: boolean;
  summaryError: string | null;
  summaryItems: WatchlistSummaryItemPayload[];
}

export function WatchlistSummary({ summaryLoading, summaryError, summaryItems }: WatchlistSummaryProps) {
  const router = useRouter();
  const goToTicker = useGoToTicker();
  const { savedCompanies, watchlistCount, noteCount, savedCompanyCount } = useLocalUserData();

  const savedFocus = useMemo(() => savedCompanies.slice(0, 4), [savedCompanies]);

  return (
    <Panel
      title="Saved & Watchlist"
      subtitle="Browser-local saved names and thesis notes kept within reach of search."
      className="home-terminal-panel"
      variant="subtle"
      aside={
        <button type="button" className="ticker-button home-toolbar-link" onClick={() => router.push("/watchlist")}>
          Open Watchlist
        </button>
      }
    >
      <div className="home-saved-summary-grid">
        <div className="home-saved-summary-card">
          <span className="home-saved-summary-label">Saved names</span>
          <span className="home-saved-summary-value">{savedCompanyCount}</span>
          <span className="home-saved-summary-detail">Local watchlist entries or notes.</span>
        </div>
        <div className="home-saved-summary-card">
          <span className="home-saved-summary-label">Watchlist</span>
          <span className="home-saved-summary-value">{watchlistCount}</span>
          <span className="home-saved-summary-detail">Tracked names ready for refresh and triage.</span>
        </div>
        <div className="home-saved-summary-card">
          <span className="home-saved-summary-label">Notes</span>
          <span className="home-saved-summary-value">{noteCount}</span>
          <span className="home-saved-summary-detail">Local research notes attached to a ticker.</span>
        </div>
      </div>

      {summaryError ? <div className="text-muted">{summaryError}</div> : null}
      {summaryLoading && summaryItems.length === 0 ? <div className="text-muted">Loading watchlist data...</div> : null}

      {savedFocus.length ? (
        <div className="home-utility-list">
          {savedFocus.map((company) => (
            <div key={company.ticker} className="home-utility-item">
              <div className="home-company-line">
                <button
                  type="button"
                  className="home-inline-link home-company-button"
                  onClick={() =>
                    goToTicker(company.ticker, "company", {
                      ticker: company.ticker,
                      name: company.name,
                      sector: company.sector,
                    })
                  }
                >
                  <span className="home-company-ticker">{company.ticker}</span>
                  <span className="home-company-name">{company.name ?? "Saved company"}</span>
                </button>
                <span className="home-utility-time">{formatRelativeMoment(company.activityAt)}</span>
              </div>
              <div className="home-utility-meta">
                {company.sector ? <span className="pill">{company.sector}</span> : null}
                {company.isInWatchlist ? <span className="pill">Watchlist</span> : null}
                {company.hasNote ? <span className="pill">Note</span> : null}
              </div>
              <div className="home-utility-note">
                {company.note ?? "No local note yet. Save a note from the company workspace to keep the thesis visible here."}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="home-utility-empty">Save a company or add a local note from any workspace to keep it pinned here.</div>
      )}
    </Panel>
  );
}

"use client";

import { useRouter } from "next/navigation";

import { useLocalUserData } from "@/hooks/use-local-user-data";

export function HomeWatchlistSnapshot() {
  const router = useRouter();
  const { watchlistCount, noteCount, savedCompanyCount } = useLocalUserData();

  return (
    <div className="watchlist-snapshot-card">
      <div className="grid-empty-kicker">Watchlist workspace</div>
      <div className="grid-empty-title">Track multiple companies in one place</div>
      <div className="grid-empty-copy">
        Open your local watchlist workspace to triage alerts, review latest activity, and jump directly into each company workspace.
      </div>

      <div className="saved-companies-summary">
        <span className="pill">{watchlistCount} watchlist</span>
        <span className="pill">{noteCount} notes</span>
        <span className="pill">{savedCompanyCount} saved total</span>
      </div>

      <button type="button" className="ticker-button" onClick={() => router.push("/watchlist")}>
        Open Watchlist Workspace
      </button>
    </div>
  );
}

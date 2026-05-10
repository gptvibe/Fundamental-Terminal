"use client";

import { useEffect, useMemo, useState } from "react";

import { HomeSearch } from "@/components/home/home-search";
import { MarketContextRail } from "@/components/home/market-context-rail";
import { RecentCompanies } from "@/components/home/recent-companies";
import { RefreshStatusPanel } from "@/components/home/refresh-status-panel";
import { SourceStatusCard } from "@/components/home/source-status-card";
import { WatchlistSummary } from "@/components/home/watchlist-summary";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import { getWatchlistSummary } from "@/lib/api";
import type { WatchlistSummaryItemPayload } from "@/lib/types";

const MAX_WATCHLIST_SUMMARY_TICKERS = 8;

export default function HomePage() {
  const { watchlist } = useLocalUserData();

  const watchlistTickers = useMemo(
    () => watchlist.map((item) => item.ticker.trim().toUpperCase()).filter(Boolean).slice(0, MAX_WATCHLIST_SUMMARY_TICKERS),
    [watchlist]
  );

  const [watchlistSummary, setWatchlistSummary] = useState<WatchlistSummaryItemPayload[]>([]);
  const [watchlistSummaryLoading, setWatchlistSummaryLoading] = useState(false);
  const [watchlistSummaryError, setWatchlistSummaryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadWatchlistSummary() {
      if (!watchlistTickers.length) {
        setWatchlistSummary([]);
        setWatchlistSummaryError(null);
        setWatchlistSummaryLoading(false);
        return;
      }

      try {
        setWatchlistSummaryLoading(true);
        setWatchlistSummaryError(null);
        const response = await getWatchlistSummary(watchlistTickers);
        if (cancelled) return;
        setWatchlistSummary(response.companies);
      } catch (err) {
        if (cancelled) return;
        setWatchlistSummary([]);
        setWatchlistSummaryError(err instanceof Error ? err.message : "Unable to load watchlist summary");
      } finally {
        if (!cancelled) setWatchlistSummaryLoading(false);
      }
    }

    void loadWatchlistSummary();
    return () => {
      cancelled = true;
    };
  }, [watchlistTickers]);

  return (
    <div className="home-shell home-shell-terminal">
      <h1 className="sr-only">Fundamental Terminal Home</h1>

      <section className="home-launchpad">
        <HomeSearch railContent={<><MarketContextRail /><SourceStatusCard /></>} />
      </section>

      <div className="home-terminal-grid">
        <RecentCompanies />
        <WatchlistSummary
          summaryLoading={watchlistSummaryLoading}
          summaryError={watchlistSummaryError}
          summaryItems={watchlistSummary}
        />
        <RefreshStatusPanel
          watchlistTickers={watchlistTickers}
          summaryItems={watchlistSummary}
          summaryLoading={watchlistSummaryLoading}
          summaryError={watchlistSummaryError}
        />
      </div>
    </div>
  );
}

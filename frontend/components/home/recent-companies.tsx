"use client";

import { useEffect, useMemo, useState } from "react";

import { Panel } from "@/components/ui/panel";
import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import { formatDate, formatRelativeMoment } from "@/lib/format";
import { readRecentCompanies, subscribeRecentCompanies, type RecentCompany } from "@/lib/recent-companies";

export function RecentCompanies() {
  const [recentLaunches, setRecentLaunches] = useState<RecentCompany[]>([]);
  const goToTicker = useGoToTicker();

  useEffect(() => {
    setRecentLaunches(readRecentCompanies());
    const unsubscribe = subscribeRecentCompanies(() => {
      setRecentLaunches(readRecentCompanies());
    });
    return unsubscribe;
  }, []);

  const recentCompanies = useMemo(() => recentLaunches.slice(0, 4), [recentLaunches]);

  return (
    <Panel
      title="Recent Companies"
      subtitle="Names opened most recently across company workspaces."
      className="home-terminal-panel"
      variant="subtle"
    >
      {recentCompanies.length ? (
        <div className="home-utility-list">
          {recentCompanies.map((company) => (
            <div key={company.ticker} className="home-utility-item">
              <div className="home-company-line">
                <button
                  type="button"
                  className="home-inline-link home-company-button"
                  onClick={() => goToTicker(company.ticker, "company", company)}
                >
                  <span className="home-company-ticker">{company.ticker}</span>
                  <span className="home-company-name">{company.name ?? "Open company workspace"}</span>
                </button>
                <span className="home-utility-time">{formatRelativeMoment(company.openedAt)}</span>
              </div>
              <div className="home-utility-meta">
                {company.sector ? <span className="pill">{company.sector}</span> : null}
                <span className="pill">Opened {formatDate(company.openedAt)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="home-utility-empty">Recent launches will appear here after you open a company workspace.</div>
      )}
    </Panel>
  );
}

"use client";

import { useMemo } from "react";

import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import { readRecentCompanies } from "@/lib/recent-companies";
import { formatDate } from "@/lib/format";
import "./recent-companies.css";

export function RecentCompanies() {
  const goToTicker = useGoToTicker();

  const recentCompanies = useMemo(() => {
    return readRecentCompanies();
  }, []); // Read from localStorage on mount

  if (!recentCompanies.length) {
    return (
      <section className="home-recent-companies">
        <h2 className="home-recent-companies-title">Recent Companies</h2>
        <div className="home-recent-companies-empty">
          <p>No recent companies yet. Start exploring to see them here.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-recent-companies">
      <h2 className="home-recent-companies-title">Recent Companies</h2>
      <div className="home-recent-companies-grid">
        {recentCompanies.map((company) => (
          <button
            key={company.ticker}
            onClick={() =>
              goToTicker(company.ticker, "company", {
                ticker: company.ticker,
                name: company.name,
                sector: company.sector,
              })
            }
            className="home-recent-company-card"
            type="button"
          >
            <div className="home-recent-company-ticker">
              {company.ticker}
            </div>
            {company.name && (
              <div className="home-recent-company-name">
                {company.name}
              </div>
            )}
            {company.sector && (
              <div className="home-recent-company-sector">
                {company.sector}
              </div>
            )}
            {company.openedAt && (
              <div className="home-recent-company-date">
                {formatDate(company.openedAt)}
              </div>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

"use client";

import { useEffect, useState } from "react";

import { getGlobalMarketContext } from "@/lib/api";
import { formatPercent } from "@/lib/format";
import type { CompanyMarketContextResponse } from "@/lib/types";
import "./market-context-rail.css";

export function MarketContextRail() {
  const [context, setContext] = useState<CompanyMarketContextResponse | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadContext() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getGlobalMarketContext();
        if (cancelled) return;
        setContext(data);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load market context");
        setContext(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadContext();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <section className="home-market-context-rail">
        <h3 className="home-market-context-title">Market Context</h3>
        <div className="home-market-context-error">
          <p>Unable to load market context</p>
        </div>
      </section>
    );
  }

  if (isLoading || !context) {
    return (
      <section className="home-market-context-rail">
        <h3 className="home-market-context-title">Market Context</h3>
        <div className="home-market-context-loading">
          <p>Loading…</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-market-context-rail">
      <h3 className="home-market-context-title">Market Context</h3>

      <div className="home-market-context-metrics">
        {context.slope_2s10s && context.slope_2s10s.value !== null && (
          <div className="home-market-context-metric">
            <span className="home-market-context-metric-label">
              2s/10s Slope
            </span>
            <span className="home-market-context-metric-value">
              {formatPercent(context.slope_2s10s.value / 100)}
            </span>
          </div>
        )}

        {context.slope_3m10y && context.slope_3m10y.value !== null && (
          <div className="home-market-context-metric">
            <span className="home-market-context-metric-label">
              3m/10y Slope
            </span>
            <span className="home-market-context-metric-value">
              {formatPercent(context.slope_3m10y.value / 100)}
            </span>
          </div>
        )}

        {context.fred_series && context.fred_series.length > 0 && (
          <div className="home-market-context-metric">
            <span className="home-market-context-metric-label">
              Fed Rate
            </span>
            <span className="home-market-context-metric-value">
              {context.fred_series[0]?.value?.toFixed(2)}%
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

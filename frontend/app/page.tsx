"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { StatusConsole } from "@/components/console/status-console";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useJobStream } from "@/hooks/use-job-stream";
import { searchCompanies } from "@/lib/api";
import { MODEL_GUIDE, TRENDING_TICKERS } from "@/lib/constants";
import type { CompanyPayload, CompanySearchResponse, RefreshState } from "@/lib/types";

interface ActiveSearchJob {
  id: string;
  ticker: string;
}

const HOW_IT_WORKS_STEPS = [
  {
    title: "Enter a ticker",
    copy: "Type a stock ticker and open the company workspace or the valuation models page."
  },
  {
    title: "We fetch the source data",
    copy: "The app checks company filings and other saved market data, then refreshes anything missing or out of date."
  },
  {
    title: "The calculations run automatically",
    copy: "Financial data is processed in the background and the available models are calculated for that ticker."
  },
  {
    title: "Charts and tables fill in",
    copy: "Once the refresh finishes, the financial views and model visuals update on their own."
  }
];

const WHERE_TO_LOOK = [
  {
    title: "Company Workspace",
    accentClass: "neon-green",
    copy: "Use this page for statements, historical financial data, and company-level views."
  },
  {
    title: "Valuation Models",
    accentClass: "neon-gold",
    copy: "Use this page for DCF, DuPont, Piotroski, Altman Z, ratios, and the model charts."
  },
  {
    title: "Live Updates",
    accentClass: "neon-cyan",
    copy: "Use this panel whenever a new ticker needs time to fetch data and finish the calculations."
  }
];

export default function HomePage() {
  const router = useRouter();
  const [query, setQuery] = useState("AAPL");
  const [data, setData] = useState<CompanySearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<ActiveSearchJob | null>(null);
  const [lastSettledJobId, setLastSettledJobId] = useState<string | null>(null);
  const normalizedQuery = query.trim().toUpperCase();
  const { consoleEntries, connectionState, lastEvent } = useJobStream(activeJob?.id);
  const bestMatch = getBestMatch(data?.results ?? [], normalizedQuery);
  const refreshLabel = getRefreshLabel(data?.refresh, loading);

  const goToTicker = useCallback(
    (ticker: string, destination: "company" | "models" = "company") => {
      const normalizedTicker = ticker.trim().toUpperCase();
      if (!normalizedTicker) {
        return;
      }

      const suffix = destination === "models" ? "/models" : "";
      router.push(`/company/${encodeURIComponent(normalizedTicker)}${suffix}`);
    },
    [router]
  );

  const loadSearch = useCallback(
    async (ticker: string, options?: { preserveActiveJob?: boolean }) => {
      const normalizedTicker = ticker.trim().toUpperCase();
      if (!normalizedTicker) {
        setData(null);
        setError(null);
        setLoading(false);
        setActiveJob(null);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        const response = await searchCompanies(normalizedTicker);
        setData(response);
        if (response.refresh.job_id) {
          setActiveJob({ id: response.refresh.job_id, ticker: normalizedTicker });
        } else if (!options?.preserveActiveJob) {
          setActiveJob(null);
        }
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      await loadSearch(normalizedQuery);
    }, 250);

    return () => window.clearTimeout(timer);
  }, [loadSearch, normalizedQuery]);

  useEffect(() => {
    if (activeJob && activeJob.ticker !== normalizedQuery) {
      setActiveJob(null);
    }
  }, [activeJob, normalizedQuery]);

  useEffect(() => {
    if (!activeJob || !lastEvent) {
      return;
    }

    const terminal = lastEvent.status === "completed" || lastEvent.status === "failed";
    if (!terminal || lastSettledJobId === activeJob.id || activeJob.ticker !== normalizedQuery) {
      return;
    }

    setLastSettledJobId(activeJob.id);
    void loadSearch(activeJob.ticker, { preserveActiveJob: true });
  }, [activeJob, lastEvent, lastSettledJobId, loadSearch, normalizedQuery]);

  return (
    <div className="home-shell">
      <Panel
        title="Start Here"
        subtitle="Type a ticker. We pull SEC filings and saved market data, refresh anything stale, then fill in the charts and model pages. This can take a little while."
        className="home-hero"
      >
        <div className="home-hero-grid">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              goToTicker(normalizedQuery);
            }}
            className="home-search-form"
          >
            <label className="home-search-label">
              <span className="home-search-kicker">Enter Ticker</span>
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value.toUpperCase())}
                placeholder="Type any ticker..."
                className="home-search-input"
              />
            </label>

            <div className="home-hero-note">
              You only need the ticker. If the data is missing or old, the platform refreshes it automatically and updates the pages when ready.
            </div>

            {error ? (
              <div className="pill" style={{ borderColor: "rgba(255, 77, 109, 0.35)", color: "var(--danger)" }}>
                {error}
              </div>
            ) : null}

            <div className="home-search-actions">
              <button type="submit" className="ticker-button home-action-primary">
                Open Company Workspace
              </button>
              <button type="button" className="ticker-button home-action-secondary" onClick={() => goToTicker(normalizedQuery, "models")}>
                Open Valuation Models
              </button>
            </div>
          </form>

          <div className="home-hero-side">
            {data ? <StatusPill state={data.refresh} /> : <span className="pill">Ready for a ticker</span>}

            <div className="metric-grid">
              <div className="metric-card">
                <div className="metric-label">Ticker</div>
                <div className="metric-value neon-cyan">{normalizedQuery || "-"}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Match</div>
                <div className="metric-value neon-green">{bestMatch?.ticker ?? (loading ? "Checking" : "Pending")}</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Models</div>
                <div className="metric-value neon-gold">{MODEL_GUIDE.length}</div>
              </div>
            </div>

            <div className="home-hero-note">
              {bestMatch
                ? `${bestMatch.name}${bestMatch.sector ? ` - ${bestMatch.sector}` : ""}`
                : loading
                  ? "Checking the ticker and whether a refresh is needed."
                  : "New tickers can take a bit longer while filings, price history, and model results are prepared."}
            </div>

            <div className="pill">{refreshLabel}</div>
          </div>
        </div>
      </Panel>

      <div className="home-main-column">
        <Panel title="What Happens Next" subtitle="The app handles the data fetch and model runs in the background">
          <div className="workflow-grid">
            {HOW_IT_WORKS_STEPS.map((step, index) => (
              <div key={step.title} className="workflow-card">
                <div className="grid-empty-kicker">Step {index + 1}</div>
                <div className="grid-empty-title">{step.title}</div>
                <div className="grid-empty-copy">{step.copy}</div>
              </div>
            ))}
          </div>

          <div className="sparkline-note">
            New tickers and stale data can take a little longer because SEC data, saved market data, and model calculations run before the charts update.
          </div>
        </Panel>

        <Panel title="Available Models" subtitle="Open Valuation Models to see these sections. You do not need to know the formulas.">
          <div className="model-guide-grid">
            {MODEL_GUIDE.map((model) => (
              <div key={model.key} className="model-guide-card">
                <div className="grid-empty-kicker">{model.label}</div>
                <div className="grid-empty-copy">Open Valuation Models and check {model.locationSummary}.</div>
              </div>
            ))}
          </div>

          <div className="sparkline-note">Every model section fills in automatically after the ticker finishes refreshing.</div>
        </Panel>
      </div>

      <div className="home-rail">
        <Panel title="Live Updates" subtitle="Watch SEC fetches and background calculations when a ticker needs fresh data">
          <StatusConsole entries={consoleEntries} connectionState={connectionState} />
        </Panel>

        <Panel title="Trending" subtitle="Popular starting points">
          <div className="home-trending-list">
            {TRENDING_TICKERS.map((item, index) => (
              <button
                key={item.ticker}
                className="ticker-button home-trending-item"
                onClick={() => goToTicker(item.ticker)}
                style={{ borderColor: index % 3 === 0 ? "rgba(0,255,65,0.22)" : index % 3 === 1 ? "rgba(255,215,0,0.22)" : "rgba(0,229,255,0.22)" }}
              >
                <div className="home-trending-copy">
                  <div className="home-trending-symbol">{item.ticker}</div>
                  <div className="text-muted home-trending-name">{item.name}</div>
                </div>
                <div className="home-trending-open">Open</div>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Where To Look" subtitle="Use these pages once the ticker is loaded">
          <div className="home-notes-stack">
            {WHERE_TO_LOOK.map((note) => (
              <div key={note.title} className="pill">
                <span className={note.accentClass}>{note.title}</span> {note.copy}
              </div>
            ))}
            <div className="sparkline-note">If a page is still filling in, keep this dashboard open and watch Live Updates until the refresh finishes.</div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function getBestMatch(results: CompanyPayload[], ticker: string): CompanyPayload | null {
  return results.find((result) => result.ticker.toUpperCase() === ticker) ?? results[0] ?? null;
}

function getRefreshLabel(refresh: RefreshState | null | undefined, loading: boolean): string {
  if (!refresh) {
    return loading ? "Checking ticker..." : "Ready to load data.";
  }

  switch (refresh.reason) {
    case "missing":
      return "Fetching source data for a new ticker.";
    case "stale":
      return "Refreshing older data before the pages update.";
    case "manual":
      return "A background refresh is already running.";
    case "fresh":
      return "Saved data is ready to use.";
    default:
      return refresh.triggered ? "Background refresh in progress." : "Open a page to start exploring.";
  }
}

"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { getSourceRegistry } from "@/lib/api";
import { formatDurationFromSeconds, formatRelativeMoment } from "@/lib/format";
import type { SourceRegistryResponse } from "@/lib/types";

const MACRO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

interface DataHealthCard {
  label: string;
  value: string;
  detail: string;
}

function buildDataHealthSnapshot(sourceRegistry: SourceRegistryResponse | null): {
  cards: DataHealthCard[];
  recentErrors: SourceRegistryResponse["health"]["sources_with_recent_errors"];
} {
  if (!sourceRegistry) {
    return {
      cards: [
        { label: "Companies cached", value: "—", detail: "Loading cache footprint" },
        { label: "Average age", value: "—", detail: "Loading cache freshness" },
        { label: "Recent source errors", value: "—", detail: "Loading source-monitoring state" },
      ],
      recentErrors: [],
    };
  }

  const recentErrors = sourceRegistry.health.sources_with_recent_errors;
  return {
    cards: [
      {
        label: "Companies cached",
        value: new Intl.NumberFormat("en-US").format(sourceRegistry.health.total_companies_cached),
        detail: "Names with cached financial coverage available for workspaces.",
      },
      {
        label: "Average age",
        value: formatDurationFromSeconds(sourceRegistry.health.average_data_age_seconds),
        detail: "Mean age of cached company financial refresh timestamps.",
      },
      {
        label: "Recent source errors",
        value: String(recentErrors.length),
        detail: `Rolling ${sourceRegistry.health.recent_error_window_hours}h error window.`,
      },
    ],
    recentErrors,
  };
}

export function SourceStatusCard() {
  const router = useRouter();
  const [sourceRegistry, setSourceRegistry] = useState<SourceRegistryResponse | null>(null);
  const [sourceRegistryError, setSourceRegistryError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const result = await getSourceRegistry();
        if (cancelled) return;
        setSourceRegistry(result);
        setSourceRegistryError(null);
      } catch (err) {
        if (cancelled) return;
        setSourceRegistryError(err instanceof Error ? err.message : "Unable to load data health");
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible") void load();
    }

    function onWindowFocus() {
      void load();
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, MACRO_REFRESH_INTERVAL_MS);

    window.addEventListener("focus", onWindowFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    void load();

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onWindowFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const demoFixtureActive = useMemo(
    () => Boolean(sourceRegistry?.sources?.some((source) => source.source_id === "ft_demo_fixture_pack")),
    [sourceRegistry]
  );

  const dataHealthSnapshot = useMemo(() => buildDataHealthSnapshot(sourceRegistry), [sourceRegistry]);

  return (
    <>
      {demoFixtureActive ? (
        <div className="research-brief-fallback-notice" role="status" aria-live="polite">
          Demo mode active: this workspace is running deterministic fixture payloads (not live source data).
        </div>
      ) : null}

      <div className="home-data-health">
        <div className="home-data-health-head">
          <div>
            <span className="home-section-kicker">Cache coverage</span>
            <div className="home-data-health-title">Data Health</div>
          </div>
          <button type="button" className="ticker-button home-toolbar-link" onClick={() => router.push("/data-sources")}>
            Open Data Sources
          </button>
        </div>
        <div className="home-data-health-copy">
          Official/public sources drive fundamentals, labeled fallbacks stay constrained, and this summary shows how fresh the cached
          company base looks right now.
        </div>
        {sourceRegistryError ? <div className="text-muted">{sourceRegistryError}</div> : null}
        <div className="home-data-health-grid">
          {dataHealthSnapshot.cards.map((card) => (
            <div key={card.label} className="home-data-health-card">
              <div className="home-data-health-label">{card.label}</div>
              <div className="home-data-health-value">{card.value}</div>
              <div className="home-data-health-detail">{card.detail}</div>
            </div>
          ))}
        </div>
        <div className="home-data-health-errors">
          <div className="home-data-health-errors-title">Sources with recent errors</div>
          {dataHealthSnapshot.recentErrors.length ? (
            <div className="home-data-health-error-list">
              {dataHealthSnapshot.recentErrors.map((error) => (
                <div key={error.source_id} className="home-data-health-error-item">
                  <div className="home-data-health-error-name">{error.display_label}</div>
                  <div className="home-data-health-error-detail">
                    {error.failure_count} failures across {error.affected_company_count} companies ·{" "}
                    {formatRelativeMoment(error.last_error_at)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="home-data-health-empty">No recent source errors in the current monitoring window.</div>
          )}
        </div>
      </div>
    </>
  );
}

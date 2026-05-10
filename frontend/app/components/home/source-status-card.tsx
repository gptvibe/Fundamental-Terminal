"use client";

import { useEffect, useState } from "react";

import { getSourceRegistry } from "@/lib/api";
import type { SourceRegistryResponse } from "@/lib/types";
import "./source-status-card.css";

export function SourceStatusCard() {
  const [registry, setRegistry] = useState<SourceRegistryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadRegistry() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getSourceRegistry();
        if (cancelled) return;
        setRegistry(data);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load source status");
        setRegistry(null);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void loadRegistry();
    return () => {
      cancelled = true;
    };
  }, []);

  // Check if we're in demo/fixture mode
  const isDemoMode = registry?.strict_official_mode === false;

  if (error) {
    return (
      <section className="home-source-status-card">
        <div className="home-source-status-content">
          <p className="home-source-status-error">Unable to load source status</p>
        </div>
      </section>
    );
  }

  if (isLoading || !registry) {
    return (
      <section className="home-source-status-card">
        <div className="home-source-status-content">
          <p className="home-source-status-loading">Loading…</p>
        </div>
      </section>
    );
  }

  return (
    <section className="home-source-status-card">
      {isDemoMode && (
        <div className="home-source-status-banner home-source-status-demo">
          <span className="home-source-status-badge">DEMO</span>
          <span className="home-source-status-message">
            Using demonstration data
          </span>
        </div>
      )}

      <div className="home-source-status-content">
        {registry.health && (
          <div className="home-source-status-health">
            <h4 className="home-source-status-health-title">Data Health</h4>
            <div className="home-source-status-health-stats">
              {registry.sources !== undefined && (
                <div className="home-source-status-health-stat">
                  <span className="home-source-status-health-label">
                    Total Sources
                  </span>
                  <span className="home-source-status-health-value">
                    {registry.sources.length}
                  </span>
                </div>
              )}

              {registry.health.sources_with_recent_errors && (
                <div className="home-source-status-health-stat">
                  <span className="home-source-status-health-label">
                    Errors
                  </span>
                  <span className="home-source-status-health-value">
                    {registry.health.sources_with_recent_errors.length}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {registry.generated_at && (
          <div className="home-source-status-updated">
            <span className="home-source-status-updated-label">
              Generated
            </span>
            <span className="home-source-status-updated-value">
              {new Date(registry.generated_at).toLocaleString()}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

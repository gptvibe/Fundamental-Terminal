"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  isPerformanceAuditEnabled,
  type PerformanceAuditRequestRecord,
} from "@/lib/performance-audit";

type CacheDiagnosticsPanelProps = {
  ticker: string;
  maxRows?: number;
};

type DiagnosticRow = {
  key: string;
  startedAt: string;
  path: string;
  cacheKey: string | null;
  cacheDisposition: string;
  responseSource: string;
  cachePolicy: string;
  backgroundRevalidate: string;
  payloadSize: string;
  statusCode: string;
};

export function CacheDiagnosticsPanel({ ticker, maxRows = 12 }: CacheDiagnosticsPanelProps) {
  const enabled = isPerformanceAuditEnabled();
  const [rows, setRows] = useState<DiagnosticRow[]>([]);
  const previousSignatureRef = useRef<string>("");

  const tickerPathToken = useMemo(() => {
    const normalizedTicker = encodeURIComponent(ticker.trim().toUpperCase());
    return `/companies/${normalizedTicker}`;
  }, [ticker]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") {
      return;
    }

    const readRows = () => {
      const snapshot = window.__FT_PERFORMANCE_AUDIT__?.snapshot();
      if (!snapshot) {
        setRows([]);
        return;
      }

      const nextRows = snapshot.requests
        .filter((record) => matchesCompanyTicker(record, tickerPathToken))
        .slice(-maxRows)
        .reverse()
        .map((record) => toRow(record));

      const nextSignature = `${nextRows.length}:${nextRows[0]?.key ?? "none"}`;
      if (nextSignature !== previousSignatureRef.current && nextRows.length > 0) {
        previousSignatureRef.current = nextSignature;
        if (process.env.NODE_ENV !== "production") {
          console.table(nextRows);
        }
      }

      setRows(nextRows);
    };

    readRows();
    const intervalId = window.setInterval(readRows, 1250);
    window.addEventListener("storage", readRows);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("storage", readRows);
    };
  }, [enabled, maxRows, tickerPathToken]);

  if (!enabled) {
    return null;
  }

  return (
    <details className="cache-diagnostics-panel" open={false}>
      <summary>
        Cache diagnostics
        <span className="cache-diagnostics-panel-summary-meta">{rows.length ? `${rows.length} recent events` : "No events yet"}</span>
      </summary>
      {rows.length ? (
        <div className="cache-diagnostics-table-scroll" role="region" aria-label="Recent cache diagnostics events">
          <table className="cache-diagnostics-table">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Route</th>
                <th scope="col">Source</th>
                <th scope="col">Disposition</th>
                <th scope="col">Policy</th>
                <th scope="col">Revalidate</th>
                <th scope="col">Payload</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key}>
                  <td>{row.startedAt}</td>
                  <td title={row.cacheKey ?? row.path}>{row.path}</td>
                  <td>{row.responseSource}</td>
                  <td>{row.cacheDisposition}</td>
                  <td>{row.cachePolicy}</td>
                  <td>{row.backgroundRevalidate}</td>
                  <td>{row.payloadSize}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="cache-diagnostics-empty">Run a few tab navigations to populate cache diagnostics.</p>
      )}
    </details>
  );
}

function matchesCompanyTicker(record: PerformanceAuditRequestRecord, tickerPathToken: string): boolean {
  if (record.path.startsWith(tickerPathToken)) {
    return true;
  }

  if (record.cacheKey && record.cacheKey.startsWith(tickerPathToken)) {
    return true;
  }

  return false;
}

function toRow(record: PerformanceAuditRequestRecord): DiagnosticRow {
  return {
    key: record.id,
    startedAt: formatStartedAt(record.startedAt),
    path: trimPath(record.path),
    cacheKey: record.cacheKey,
    cacheDisposition: record.cacheDisposition,
    responseSource: record.responseSource ?? (record.networkRequest ? "network" : "unknown"),
    cachePolicy: formatCachePolicy(record.cachePolicyTtlMs, record.cachePolicyStaleMs),
    backgroundRevalidate: record.backgroundRevalidate ? "yes" : "no",
    payloadSize: formatBytes(record.payloadBytes ?? record.responseBytes),
    statusCode: record.statusCode == null ? "-" : String(record.statusCode),
  };
}

function formatStartedAt(value: string): string {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }

  return new Date(parsed).toLocaleTimeString();
}

function trimPath(path: string): string {
  if (path.length <= 56) {
    return path;
  }

  return `${path.slice(0, 53)}...`;
}

function formatCachePolicy(ttlMs: number | null, staleMs: number | null): string {
  if (ttlMs == null && staleMs == null) {
    return "-";
  }

  return `ttl ${formatDuration(ttlMs)} / stale ${formatDuration(staleMs)}`;
}

function formatDuration(value: number | null): string {
  if (value == null || value <= 0) {
    return "-";
  }

  if (value % 1000 === 0) {
    return `${Math.round(value / 1000)}s`;
  }

  return `${value}ms`;
}

function formatBytes(value: number | null): string {
  if (value == null || !Number.isFinite(value) || value < 0) {
    return "-";
  }

  if (value < 1024) {
    return `${Math.round(value)} B`;
  }

  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }

  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

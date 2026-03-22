"use client";

import { formatDate, formatPercent } from "@/lib/format";
import type { CompanyMarketContextResponse, MarketCurvePointPayload } from "@/lib/types";

interface MarketContextPanelProps {
  context: CompanyMarketContextResponse | null;
}

const CURVE_ORDER = ["rrp", "1m", "2m", "3m", "4m", "6m", "1y", "3y", "5y", "7y", "10y", "20y", "30y"];

export function MarketContextPanel({ context }: MarketContextPanelProps) {
  if (!context) {
    return <div className="text-muted">Market context is loading...</div>;
  }

  const curvePoints = [...context.curve_points]
    .filter((point) => point.tenor !== "2y")
    .sort((left, right) => tenorRank(left.tenor) - tenorRank(right.tenor));
  const fredEnabled = isFredEnabled(context);

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <span className="pill">Status: {normalizeStatus(context.status)}</span>
        <span className="pill">Treasury: {curvePoints.length ? "Loaded" : "Missing"}</span>
        <span className="pill">FRED: {fredEnabled ? "Configured" : "Not configured"}</span>
        <span className="pill">Fetched: {formatDate(context.fetched_at)}</span>
      </div>

      <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
        <MetricCard label="2s10s" value={formatPercent(context.slope_2s10s.value)} detail={buildSlopeDetail(context.slope_2s10s.short_tenor, context.slope_2s10s.observation_date)} />
        <MetricCard label="3m10y" value={formatPercent(context.slope_3m10y.value)} detail={buildSlopeDetail(context.slope_3m10y.short_tenor, context.slope_3m10y.observation_date)} />
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600, color: "var(--text)" }}>Current Treasury Curve</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
          {curvePoints.map((point) => (
            <div key={point.tenor} className="metric-card" style={{ minHeight: 68 }}>
              <div className="metric-label">{formatTenor(point.tenor)}</div>
              <div className="metric-value">{formatPercent(point.rate)}</div>
              <div className="text-muted" style={{ fontSize: 12 }}>{point.observation_date}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600, color: "var(--text)" }}>Curated FRED Series</div>
        <div style={{ display: "grid", gap: 8 }}>
          {context.fred_series.length ? (
            context.fred_series.map((series) => (
              <div key={series.series_id} className="filing-link-card" style={{ display: "grid", gap: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <strong>{series.label}</strong>
                  <span className="pill">{normalizeStatus(series.state)}</span>
                </div>
                <div className="text-muted">
                  {formatSeriesValue(series.value, series.units)}
                  {series.observation_date ? ` | ${series.observation_date}` : ""}
                </div>
              </div>
            ))
          ) : (
            <div className="text-muted">Supplemental macro indicators are unavailable in the current snapshot.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      <div className="text-muted" style={{ fontSize: 12 }}>{detail}</div>
    </div>
  );
}

function tenorRank(tenor: string): number {
  const index = CURVE_ORDER.indexOf(tenor.toLowerCase());
  return index === -1 ? CURVE_ORDER.length : index;
}

function formatTenor(tenor: string): string {
  return tenor.toLowerCase() === "rrp" ? "RRP" : tenor.toUpperCase();
}

function formatSeriesValue(value: number | null, units: string): string {
  if (value === null) {
    return "Unavailable";
  }
  if (units === "percent") {
    return formatPercent(value);
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 }).format(value);
}

function buildSlopeDetail(shortTenor: string, observationDate: string | null): string {
  const shortLabel = shortTenor.toUpperCase();
  if (!observationDate) {
    return `${shortLabel} vs 10Y unavailable`;
  }
  return `${shortLabel} vs 10Y | ${observationDate}`;
}

function normalizeStatus(status: string): string {
  if (status === "ok") {
    return "OK";
  }
  if (status === "partial") {
    return "Partial";
  }
  if (status === "insufficient_data") {
    return "Insufficient data";
  }
  if (status === "missing_api_key") {
    return "Missing API key";
  }
  return status;
}

function isFredEnabled(context: CompanyMarketContextResponse): boolean {
  const fred = context.provenance.fred;
  if (!fred || typeof fred !== "object") {
    return false;
  }
  const enabled = (fred as Record<string, unknown>).enabled;
  return enabled === true;
}

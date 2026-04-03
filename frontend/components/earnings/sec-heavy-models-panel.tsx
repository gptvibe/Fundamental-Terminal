"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { MetricLabel } from "@/components/ui/metric-label";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatPercent } from "@/lib/format";
import type { EarningsModelPointPayload } from "@/lib/types";
import { PanelEmptyState } from "@/components/company/panel-empty-state";

const SEGMENT_COLORS = ["var(--positive)", "var(--accent)", "var(--warning)", "var(--negative)", "#a78bfa", "var(--positive)", "var(--accent)"];

type SecModelPoint = {
  key: string;
  label: string;
  qualityScore: number;
  epsDelta: number;
  epsDeltaPercent: number | null;
  coverageRatio: number | null;
  fallbackRatio: number | null;
  stalePeriodWarning: boolean;
};

type SegmentContributionRow = {
  segmentId: string;
  segmentName: string;
  shortName: string;
  revenue: number;
  share: number;
  shareDelta: number;
  revenueDelta: number | null;
  color: string;
};

export function SecHeavyModelsPanel({
  modelPoints,
  loading,
}: {
  modelPoints: EarningsModelPointPayload[];
  loading: boolean;
}) {
  const secModelPoints = useMemo(() => buildSecModelPointsFromWorkspace(modelPoints), [modelPoints]);
  const secModelWindow = useMemo(() => secModelPoints.slice(-8), [secModelPoints]);
  const latestSecModelPoint = secModelPoints.at(-1) ?? null;
  const segmentContributionRows = useMemo(() => buildSegmentContributionRowsFromWorkspace(modelPoints), [modelPoints]);

  if (loading) {
    return <div className="text-muted">Loading SEC-heavy model visuals...</div>;
  }

  if (!secModelPoints.length) {
    return <PanelEmptyState message="SEC-heavy models need at least two filing statements with revenue, cash-flow, and EPS fields." />;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">Latest quality score {latestSecModelPoint ? `${latestSecModelPoint.qualityScore.toFixed(1)}/100` : "\u2014"}</span>
        <span className="pill">Latest EPS drift {latestSecModelPoint ? formatEpsDelta(latestSecModelPoint.epsDelta) : "\u2014"}</span>
        <span className="pill">Coverage ratio {latestSecModelPoint?.coverageRatio != null ? formatPercent(latestSecModelPoint.coverageRatio) : "\u2014"}</span>
        <span className="pill">Fallback ratio {latestSecModelPoint?.fallbackRatio != null ? formatPercent(latestSecModelPoint.fallbackRatio) : "\u2014"}</span>
        <span className="pill">Stale warning {latestSecModelPoint?.stalePeriodWarning ? "Yes" : "No"}</span>
        <span className="pill">Segment rows {segmentContributionRows.length.toLocaleString()}</span>
        <span className="pill">Source: SEC financial statements</span>
      </div>

      <div className="metric-card" style={{ display: "grid", gap: 8 }}>
        <div className="metric-label">
          <MetricLabel label="How To Read This (Plain English)" />
        </div>
        <div className="text-muted" style={{ fontSize: 14 }}>
          Earnings quality score: higher means free cash flow conversion is stronger and accrual noise is lower versus reported earnings.
        </div>
        <div className="text-muted" style={{ fontSize: 14 }}>
          EPS drift: bars above zero mean EPS improved versus the prior reported period; below zero means EPS weakened.
        </div>
        <div className="text-muted" style={{ fontSize: 14 }}>
          Segment contribution delta: positive bars mean that segment gained share of total revenue versus the prior comparable filing.
        </div>
      </div>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        <div className="metric-card" style={{ display: "grid", gap: 10 }}>
          <div className="metric-label">
            <MetricLabel label="Earnings Quality Score Trend" />
          </div>
          <div className="text-muted" style={{ fontSize: 13 }}>Blend of FCF margin, cash conversion, and accrual discipline.</div>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <LineChart data={secModelWindow} margin={{ top: 8, right: 14, left: 2, bottom: 6 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(11)} domain={[0, 100]} width={40} />
                <Tooltip
                  {...RECHARTS_TOOLTIP_PROPS}
                  formatter={(value, _name, item) => {
                    if (String(item?.dataKey) === "qualityScore") {
                      return [`${Number(value).toFixed(1)}/100`, "Quality score"];
                    }
                    return [String(value), "Value"];
                  }}
                />
                <ReferenceLine y={50} stroke="var(--panel-border)" strokeDasharray="4 4" />
                <Line dataKey="qualityScore" stroke="var(--positive)" strokeWidth={2.6} dot={{ r: 3 }} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="metric-card" style={{ display: "grid", gap: 10 }}>
          <div className="metric-label">
            <MetricLabel label="EPS Drift (Period-over-Period)" />
          </div>
          <div className="text-muted" style={{ fontSize: 13 }}>Shows whether diluted EPS is accelerating or decelerating each period.</div>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer>
              <BarChart data={secModelWindow} margin={{ top: 8, right: 14, left: 2, bottom: 6 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(11)} />
                <YAxis
                  stroke={CHART_AXIS_COLOR}
                  tick={chartTick(11)}
                  width={48}
                  tickFormatter={(value) => formatEps(Number(value))}
                />
                <Tooltip
                  {...RECHARTS_TOOLTIP_PROPS}
                  formatter={(value, name, props) => {
                    if (String(name) === "epsDelta") {
                      const payload = props?.payload as SecModelPoint | undefined;
                      const driftText = formatEpsDelta(Number(value));
                      const pctText = payload?.epsDeltaPercent == null ? "\u2014" : formatPercent(payload.epsDeltaPercent);
                      return [`${driftText} (${pctText})`, "EPS drift"];
                    }
                    return [String(value), "Value"];
                  }}
                />
                <ReferenceLine y={0} stroke="var(--panel-border)" />
                <Bar dataKey="epsDelta" radius={[8, 8, 0, 0]} isAnimationActive={false}>
                  {secModelWindow.map((entry) => (
                    <Cell key={entry.key} fill={entry.epsDelta >= 0 ? "var(--accent)" : "var(--negative)"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="metric-card" style={{ display: "grid", gap: 10 }}>
        <div className="metric-label">
          <MetricLabel label="Segment Contribution Delta" />
        </div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          Share-of-revenue change by segment versus previous statement with segment disclosures.
        </div>
        {segmentContributionRows.length ? (
          <>
            <div style={{ width: "100%", height: 320 }}>
              <ResponsiveContainer>
                <BarChart data={segmentContributionRows} layout="vertical" margin={{ top: 8, right: 20, left: 24, bottom: 4 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} horizontal={false} />
                  <XAxis
                    type="number"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick(11)}
                    tickFormatter={(value) => formatPercent(Number(value))}
                    width={52}
                  />
                  <YAxis
                    type="category"
                    dataKey="shortName"
                    stroke={CHART_AXIS_COLOR}
                    tick={chartTick(11)}
                    width={120}
                  />
                  <Tooltip
                    {...RECHARTS_TOOLTIP_PROPS}
                    formatter={(value, _name, props) => {
                      const payload = props?.payload as SegmentContributionRow | undefined;
                      if (!payload) {
                        return [String(value), "Share delta"];
                      }
                      return [
                        `${formatPercent(Number(value))} (${formatCompactNumber(payload.revenue)} latest)`,
                        `${payload.segmentName}`
                      ];
                    }}
                  />
                  <ReferenceLine x={0} stroke="var(--panel-border)" />
                  <Bar dataKey="shareDelta" radius={[0, 8, 8, 0]} isAnimationActive={false}>
                    {segmentContributionRows.map((row) => (
                      <Cell key={row.segmentId} fill={row.shareDelta >= 0 ? row.color : "var(--negative)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table className="company-data-table" style={{ minWidth: 620 }}>
                <thead>
                  <tr>
                    <th align="left">Segment</th>
                    <th align="right">Latest Revenue</th>
                    <th align="right">Share of Revenue</th>
                    <th align="right">Share Delta</th>
                    <th align="right">Revenue Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {segmentContributionRows.map((row) => (
                    <tr key={row.segmentId}>
                      <td>{row.segmentName}</td>
                      <td style={{ textAlign: "right" }}>{formatCompactNumber(row.revenue)}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.share)}</td>
                      <td style={{ textAlign: "right", color: row.shareDelta >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedPercent(row.shareDelta)}
                      </td>
                      <td style={{ textAlign: "right", color: row.revenueDelta != null && row.revenueDelta >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedCompactNumber(row.revenueDelta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <PanelEmptyState message="No segment history delta available yet. The model appears once at least two filings include segment revenue breakdowns." />
        )}
      </div>
    </div>
  );
}

function buildSecModelPointsFromWorkspace(modelPoints: EarningsModelPointPayload[]): SecModelPoint[] {
  return [...modelPoints]
    .sort((left, right) => (left.period_end || "").localeCompare(right.period_end || ""))
    .map((point, index, rows) => {
      const previous = index > 0 ? rows[index - 1] : null;
      const epsDeltaPercent = safeRatio(point.eps_drift, previous?.eps_drift ?? null);
      return {
        key: `${point.filing_type}:${point.period_end}`,
        label: new Date(point.period_end).toLocaleDateString("en-US", { month: "short", year: "2-digit" }),
        qualityScore: point.quality_score ?? 0,
        epsDelta: point.eps_drift ?? 0,
        epsDeltaPercent,
        coverageRatio: point.release_statement_coverage_ratio,
        fallbackRatio: point.fallback_ratio,
        stalePeriodWarning: point.stale_period_warning,
      };
    });
}

function buildSegmentContributionRowsFromWorkspace(modelPoints: EarningsModelPointPayload[]): SegmentContributionRow[] {
  const latest = [...modelPoints].sort((left, right) => (right.period_end || "").localeCompare(left.period_end || ""))[0];
  if (!latest) {
    return [];
  }

  const segmentDeltas = latest.explainability.segment_deltas;
  if (!Array.isArray(segmentDeltas) || !segmentDeltas.length) {
    return [];
  }

  return segmentDeltas
    .filter((row): row is Record<string, unknown> => typeof row === "object" && row !== null)
    .map((row, index) => {
      const segmentName = String(row.segment_name ?? row.segment_id ?? "Unknown");
      const share = typeof row.current_share === "number" ? row.current_share : 0;
      const previousShare = typeof row.previous_share === "number" ? row.previous_share : 0;
      const shareDelta = typeof row.delta === "number" ? row.delta : share - previousShare;
      return {
        segmentId: String(row.segment_id ?? segmentName),
        segmentName,
        shortName: shortenLabel(segmentName, 18),
        revenue: 0,
        share,
        shareDelta,
        revenueDelta: null,
        color: SEGMENT_COLORS[index % SEGMENT_COLORS.length],
      };
    })
    .sort((left, right) => Math.abs(right.shareDelta) - Math.abs(left.shareDelta));
}

function safeRatio(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

function shortenLabel(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}...`;
}

function formatEps(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatEpsDelta(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  const formatted = formatEps(Math.abs(value));
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

function formatSignedPercent(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  const formatted = formatPercent(Math.abs(value));
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

function formatSignedCompactNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  const formatted = formatCompactNumber(Math.abs(value));
  return value > 0 ? `+${formatted}` : value < 0 ? `-${formatted}` : formatted;
}

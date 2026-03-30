"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SnapshotSurfaceStatus } from "@/components/company/snapshot-surface-status";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useJobStream } from "@/hooks/use-job-stream";
import { getCompanyCapitalStructure, invalidateApiReadCacheForTicker } from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartLegendStyle, chartTick } from "@/lib/chart-theme";
import { difference, formatSignedCompactDelta, formatSignedPointDelta } from "@/lib/financial-chart-state";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import { dedupeSnapshotSurfaceWarnings, resolveSnapshotSurfaceMode, type SnapshotSurfaceCapabilities, type SnapshotSurfaceWarning } from "@/lib/snapshot-surface";
import type {
  CapitalStructureBucketPayload,
  CapitalStructureSectionMetaPayload,
  CapitalStructureSnapshotPayload,
  CompanyCapitalStructureResponse,
  FinancialPayload,
} from "@/lib/types";

const REFRESH_POLL_INTERVAL_MS = 3000;
const CAPABILITIES: SnapshotSurfaceCapabilities = {
  supports_selected_period: true,
  supports_compare_mode: true,
  supports_trend_mode: true,
};

interface CapitalStructureIntelligencePanelProps {
  ticker: string;
  reloadKey?: string | null;
  maxPeriods?: number;
  initialPayload?: CompanyCapitalStructureResponse | null;
  selectedFinancial?: Pick<FinancialPayload, "period_end" | "filing_type"> | null;
  comparisonFinancial?: Pick<FinancialPayload, "period_end" | "filing_type"> | null;
}

export function CapitalStructureIntelligencePanel({
  ticker,
  reloadKey,
  maxPeriods = 6,
  initialPayload = null,
  selectedFinancial = null,
  comparisonFinancial = null,
}: CapitalStructureIntelligencePanelProps) {
  const [payload, setPayload] = useState<CompanyCapitalStructureResponse | null>(initialPayload);
  const [loading, setLoading] = useState(initialPayload === null);
  const [error, setError] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(initialPayload?.refresh.job_id ?? null);
  const { lastEvent } = useJobStream(activeJobId);

  const loadCapitalStructure = useCallback(
    async (showLoading: boolean) => {
      try {
        if (showLoading) {
          setLoading(true);
        }
        setError(null);
        const next = await getCompanyCapitalStructure(ticker, { maxPeriods });
        setPayload(next);
        setActiveJobId(next.refresh.job_id);
      } catch (nextError) {
        setError(nextError instanceof Error ? nextError.message : "Unable to load capital structure intelligence");
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [maxPeriods, ticker]
  );

  useEffect(() => {
    if (!initialPayload) {
      return;
    }

    setPayload(initialPayload);
    setLoading(false);
    setError(null);
    setActiveJobId(initialPayload.refresh.job_id);
  }, [initialPayload]);

  useEffect(() => {
    void loadCapitalStructure(initialPayload === null);
  }, [initialPayload, loadCapitalStructure, reloadKey]);

  useEffect(() => {
    if (!activeJobId || !lastEvent) {
      return;
    }
    if (lastEvent.status !== "completed" && lastEvent.status !== "failed") {
      return;
    }
    invalidateApiReadCacheForTicker(ticker);
    void loadCapitalStructure(false);
  }, [activeJobId, lastEvent, loadCapitalStructure, ticker]);

  useEffect(() => {
    if (!activeJobId) {
      return;
    }
    if (lastEvent?.status === "completed" || lastEvent?.status === "failed") {
      return;
    }
    const timerId = window.setInterval(() => {
      void loadCapitalStructure(false);
    }, REFRESH_POLL_INTERVAL_MS);
    return () => window.clearInterval(timerId);
  }, [activeJobId, lastEvent?.status, loadCapitalStructure]);

  const latest = payload?.latest ?? null;
  const history = useMemo(() => payload?.history ?? [], [payload]);
  const snapshotHistory = useMemo(() => buildSnapshotHistory(latest, history), [history, latest]);
  const focusSnapshot = useMemo(
    () => findMatchingSnapshot(snapshotHistory, selectedFinancial) ?? latest,
    [latest, selectedFinancial, snapshotHistory]
  );
  const comparisonSnapshot = useMemo(
    () => findMatchingSnapshot(snapshotHistory, comparisonFinancial),
    [comparisonFinancial, snapshotHistory]
  );
  const trendRows = useMemo(() => snapshotHistory.slice(0, 5), [snapshotHistory]);
  const warnings = buildWarnings(snapshotHistory, comparisonFinancial, comparisonSnapshot);
  const mode = resolveSnapshotSurfaceMode({
    comparisonAvailable: comparisonSnapshot !== null,
    trendAvailable: snapshotHistory.length > 1,
    capabilities: CAPABILITIES,
  });
  const trendChartData = useMemo(
    () => [...snapshotHistory].reverse().map((snapshot) => ({
      period: formatSnapshotLabel(snapshot),
      totalDebt: snapshot.summary.total_debt,
      nextTwelveMonths: snapshot.summary.debt_due_next_twelve_months,
      grossPayout: snapshot.summary.gross_shareholder_payout,
      netDilution: snapshot.summary.net_dilution_ratio,
    })),
    [snapshotHistory]
  );

  if (loading) {
    return <div className="text-muted">Loading capital structure intelligence...</div>;
  }
  if (error) {
    return <div className="text-muted">{error}</div>;
  }
  if (!payload || !latest) {
    return <PanelEmptyState message="No persisted capital structure intelligence is available yet. Queue a refresh to compute SEC-derived debt, payout, and dilution views." />;
  }

  const activeSnapshot = focusSnapshot ?? latest;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <SnapshotSurfaceStatus capabilities={CAPABILITIES} mode={mode} warnings={warnings} />

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">Period {formatDate(activeSnapshot.period_end)}</span>
        {selectedFinancial ? <span className="pill tone-cyan">Focus {formatSnapshotLabel(activeSnapshot)}</span> : null}
        {comparisonSnapshot ? <span className="pill tone-gold">Compare {formatSnapshotLabel(comparisonSnapshot)}</span> : null}
        <span className="pill">Debt {formatCompactNumber(activeSnapshot.summary.total_debt)}</span>
        <span className="pill">12m maturities {formatCompactNumber(activeSnapshot.summary.debt_due_next_twelve_months)}</span>
        <span className="pill">Gross payout {formatCompactNumber(activeSnapshot.summary.gross_shareholder_payout)}</span>
        <span className="pill">Net dilution {formatPercent(activeSnapshot.summary.net_dilution_ratio)}</span>
        {activeSnapshot.confidence_score != null ? <span className="pill">Confidence {formatPercent(activeSnapshot.confidence_score)}</span> : null}
        {activeJobId ? <span className="pill">refreshing</span> : null}
      </div>

      {comparisonSnapshot ? (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <span className="pill tone-gold">Debt Δ {formatSignedCompactDelta(difference(activeSnapshot.summary.total_debt, comparisonSnapshot.summary.total_debt))}</span>
          <span className="pill tone-gold">12m maturities Δ {formatSignedCompactDelta(difference(activeSnapshot.summary.debt_due_next_twelve_months, comparisonSnapshot.summary.debt_due_next_twelve_months))}</span>
          <span className="pill tone-gold">Gross payout Δ {formatSignedCompactDelta(difference(activeSnapshot.summary.gross_shareholder_payout, comparisonSnapshot.summary.gross_shareholder_payout))}</span>
          <span className="pill tone-gold">Net dilution Δ {formatSignedPointDelta(toPercentPointDelta(activeSnapshot.summary.net_dilution_ratio, comparisonSnapshot.summary.net_dilution_ratio))}</span>
        </div>
      ) : null}

      {trendChartData.length > 1 ? (
        <div className="metric-card" style={{ display: "grid", gap: 10 }}>
          <div className="metric-label">Funding, Maturities, and Payout Trend</div>
          <div className="text-muted" style={{ fontSize: 13 }}>
            Compare total debt, next-twelve-month maturities, gross payout load, and net dilution across the visible filing history.
          </div>
          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <ComposedChart data={trendChartData} margin={{ top: 8, right: 12, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                <YAxis yAxisId="amount" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
                <YAxis yAxisId="ratio" orientation="right" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} />
                <Tooltip
                  {...RECHARTS_TOOLTIP_PROPS}
                  labelFormatter={(value) => String(value)}
                  formatter={(value: number, name: string) => {
                    if (name === "Net Dilution") {
                      return formatPercent(value);
                    }
                    return formatCompactNumber(value);
                  }}
                />
                <Legend wrapperStyle={chartLegendStyle()} />
                <Bar yAxisId="amount" dataKey="totalDebt" name="Total Debt" fill="var(--chart-series-1)" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="amount" dataKey="nextTwelveMonths" name="12m Maturities" fill="var(--chart-series-2)" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="amount" dataKey="grossPayout" name="Gross Payout" fill="var(--chart-series-3)" radius={[4, 4, 0, 0]} />
                <Line yAxisId="ratio" type="monotone" dataKey="netDilution" name="Net Dilution" stroke="var(--chart-series-5)" strokeWidth={2.2} dot={false} isAnimationActive={false} />
                <ReferenceLine x={formatSnapshotLabel(activeSnapshot)} yAxisId="amount" stroke="var(--accent)" strokeDasharray="4 4" />
                {comparisonSnapshot ? <ReferenceLine x={formatSnapshotLabel(comparisonSnapshot)} yAxisId="amount" stroke="var(--warning)" strokeDasharray="4 4" /> : null}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}

      <SourceFreshnessSummary
        provenance={payload.provenance}
        asOf={payload.as_of}
        lastRefreshedAt={payload.last_refreshed_at}
        sourceMix={payload.source_mix}
        confidenceFlags={payload.confidence_flags}
      />

      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <MetricCard label="Interest Burden" value={formatPercent(activeSnapshot.interest_burden.interest_to_average_debt)} hint="Interest expense as a share of average debt" />
        <MetricCard label="Interest Coverage" value={formatMultiple(activeSnapshot.interest_burden.interest_coverage_proxy)} hint="Operating income divided by interest expense" />
        <MetricCard label="Dividends" value={formatCompactNumber(activeSnapshot.capital_returns.dividends)} hint="Cash dividends reported in the filing period" />
        <MetricCard label="Repurchases" value={formatCompactNumber(activeSnapshot.capital_returns.share_repurchases)} hint="Cash spent on share repurchases" />
        <MetricCard label="SBC" value={formatCompactNumber(activeSnapshot.capital_returns.stock_based_compensation)} hint="Stock-based compensation expense" />
        <MetricCard label="Net Share Change" value={formatCompactNumber(activeSnapshot.net_dilution_bridge.net_share_change)} hint="Ending shares minus opening shares" />
      </div>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        <BucketTable
          title="Debt Maturity Ladder"
          subtitle="Latest contractual debt maturities from SEC-reported principal schedules"
          buckets={activeSnapshot.debt_maturity_ladder.buckets}
          meta={activeSnapshot.debt_maturity_ladder.meta}
          emptyMessage="No contractual debt maturity schedule was extracted for this filing."
        />
        <BucketTable
          title="Lease Obligations"
          subtitle="Latest operating lease cash obligations from SEC lease footnotes"
          buckets={activeSnapshot.lease_obligations.buckets}
          meta={activeSnapshot.lease_obligations.meta}
          emptyMessage="No lease payment schedule was extracted for this filing."
        />
      </div>

      <div className="metric-card" style={{ display: "grid", gap: 10 }}>
        <div className="metric-label">Debt Rollforward & Net Dilution Bridge</div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          Debt issuance and repayment are paired with the latest share issuance / repurchase bridge so we can separate funding, payouts, and dilution effects.
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <MetricCard label="Debt Issued" value={formatCompactNumber(activeSnapshot.debt_rollforward.debt_issued)} />
          <MetricCard label="Debt Repaid" value={formatCompactNumber(activeSnapshot.debt_rollforward.debt_repaid)} />
          <MetricCard label="Net Debt Change" value={formatCompactNumber(activeSnapshot.debt_rollforward.net_debt_change)} />
          <MetricCard label="Shares Issued" value={formatCompactNumber(activeSnapshot.net_dilution_bridge.shares_issued ?? activeSnapshot.net_dilution_bridge.shares_issued_proxy)} />
          <MetricCard label="Shares Repurchased" value={formatCompactNumber(activeSnapshot.net_dilution_bridge.shares_repurchased)} />
          <MetricCard label="Ending Shares" value={formatCompactNumber(activeSnapshot.net_dilution_bridge.ending_shares)} />
        </div>
        <SectionMeta meta={activeSnapshot.debt_rollforward.meta} />
        <SectionMeta meta={activeSnapshot.net_dilution_bridge.meta} />
      </div>

      <div className="metric-card" style={{ display: "grid", gap: 10 }}>
        <div className="metric-label">Interest, Payout, and Dilution Trend</div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          Recent filing history for interest burden, payout mix, SBC offset, and share-count change.
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 820 }}>
            <thead>
              <tr className="text-muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.08 }}>
                <th align="left" style={{ padding: "8px 10px" }}>Period</th>
                <th align="right" style={{ padding: "8px 10px" }}>Interest / Avg Debt</th>
                <th align="right" style={{ padding: "8px 10px" }}>Coverage</th>
                <th align="right" style={{ padding: "8px 10px" }}>Dividends</th>
                <th align="right" style={{ padding: "8px 10px" }}>Repurchases</th>
                <th align="right" style={{ padding: "8px 10px" }}>SBC</th>
                <th align="right" style={{ padding: "8px 10px" }}>Net Share Change</th>
              </tr>
            </thead>
            <tbody>
              {trendRows.map((row) => (
                <tr
                  key={`${row.filing_type}:${row.period_end}`}
                  style={resolveTrendRowStyle(row, activeSnapshot, comparisonSnapshot)}
                >
                  <td style={{ padding: "10px 10px" }}>{formatDate(row.period_end)}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatPercent(row.interest_burden.interest_to_average_debt)}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatMultiple(row.interest_burden.interest_coverage_proxy)}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatCompactNumber(row.capital_returns.dividends)}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatCompactNumber(row.capital_returns.share_repurchases)}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatCompactNumber(row.capital_returns.stock_based_compensation)}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatCompactNumber(row.net_dilution_bridge.net_share_change)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function BucketTable({
  title,
  subtitle,
  buckets,
  meta,
  emptyMessage,
}: {
  title: string;
  subtitle: string;
  buckets: CapitalStructureBucketPayload[];
  meta: CapitalStructureSectionMetaPayload;
  emptyMessage: string;
}) {
  return (
    <div className="metric-card" style={{ display: "grid", gap: 10 }}>
      <div className="metric-label">{title}</div>
      <div className="text-muted" style={{ fontSize: 13 }}>{subtitle}</div>
      {buckets.length ? (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr className="text-muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.08 }}>
                <th align="left" style={{ padding: "8px 10px" }}>Bucket</th>
                <th align="right" style={{ padding: "8px 10px" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {buckets.map((bucket) => (
                <tr key={bucket.bucket_key}>
                  <td style={{ padding: "10px 10px" }}>{bucket.label}</td>
                  <td style={{ padding: "10px 10px", textAlign: "right" }}>{formatCompactNumber(bucket.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <PanelEmptyState message={emptyMessage} />
      )}
      <SectionMeta meta={meta} />
    </div>
  );
}

function SectionMeta({ meta }: { meta: CapitalStructureSectionMetaPayload }) {
  const details = [
    meta.as_of ? `As of ${formatDate(meta.as_of)}` : null,
    meta.last_refreshed_at ? `Refreshed ${formatDate(meta.last_refreshed_at)}` : null,
    meta.confidence_score != null ? `Confidence ${formatPercent(meta.confidence_score)}` : null,
    meta.confidence_flags.length ? meta.confidence_flags.join(", ") : null,
  ].filter(Boolean);

  if (!details.length) {
    return null;
  }

  return (
    <div className="text-muted" style={{ fontSize: 12 }}>
      {details.join(" | ")}
    </div>
  );
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="metric-card" style={{ display: "grid", gap: 6 }}>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint ? <div className="text-muted" style={{ fontSize: 12 }}>{hint}</div> : null}
    </div>
  );
}

function formatMultiple(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "?";
  }
  return `${value.toFixed(1)}x`;
}

function findMatchingSnapshot(
  history: CapitalStructureSnapshotPayload[],
  statement: Pick<FinancialPayload, "period_end" | "filing_type"> | null
): CapitalStructureSnapshotPayload | null {
  if (!statement) {
    return null;
  }
  return history.find((item) => item.period_end === statement.period_end && item.filing_type === statement.filing_type) ?? null;
}

function formatSnapshotLabel(snapshot: CapitalStructureSnapshotPayload): string {
  return `${snapshot.filing_type} ${formatDate(snapshot.period_end)}`;
}

function buildSnapshotHistory(
  latest: CapitalStructureSnapshotPayload | null,
  history: CapitalStructureSnapshotPayload[]
): CapitalStructureSnapshotPayload[] {
  const ordered = [...history].sort((left, right) => Date.parse(right.period_end) - Date.parse(left.period_end));
  if (latest) {
    ordered.unshift(latest);
  }

  const seen = new Set<string>();
  return ordered.filter((snapshot) => {
    const key = `${snapshot.period_end}|${snapshot.filing_type}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function buildWarnings(
  snapshotHistory: CapitalStructureSnapshotPayload[],
  requestedComparison: Pick<FinancialPayload, "period_end" | "filing_type"> | null,
  comparisonSnapshot: CapitalStructureSnapshotPayload | null
): SnapshotSurfaceWarning[] {
  const warnings: SnapshotSurfaceWarning[] = [];
  if (requestedComparison && !comparisonSnapshot) {
    warnings.push({
      code: "capital_structure_comparison_missing",
      label: "Comparison snapshot unavailable",
      detail: "The selected comparison period does not have a persisted capital-structure snapshot in the current history window.",
      tone: "warning",
    });
  }
  if (snapshotHistory.length < 2) {
    warnings.push({
      code: "capital_structure_history_sparse",
      label: "Sparse capital-structure history",
      detail: "Only one persisted capital-structure snapshot is visible, so trend mode falls back to the selected period view.",
      tone: "info",
    });
  }
  return dedupeSnapshotSurfaceWarnings(warnings);
}

function resolveTrendRowStyle(
  row: CapitalStructureSnapshotPayload,
  activeSnapshot: CapitalStructureSnapshotPayload,
  comparisonSnapshot: CapitalStructureSnapshotPayload | null
): CSSProperties | undefined {
  if (row.period_end === activeSnapshot.period_end && row.filing_type === activeSnapshot.filing_type) {
    return {
      background: "color-mix(in srgb, var(--accent) 8%, transparent)",
      boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--accent) 22%, transparent)",
    };
  }
  if (comparisonSnapshot && row.period_end === comparisonSnapshot.period_end && row.filing_type === comparisonSnapshot.filing_type) {
    return {
      background: "color-mix(in srgb, var(--warning) 8%, transparent)",
      boxShadow: "inset 0 0 0 1px color-mix(in srgb, var(--warning) 22%, transparent)",
    };
  }
  return undefined;
}

function toPercentPointDelta(current: number | null | undefined, previous: number | null | undefined): number | null {
  const delta = difference(current, previous);
  return delta == null ? null : delta * 100;
}

"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { useJobStream } from "@/hooks/use-job-stream";
import { getCompanyCapitalStructure, invalidateApiReadCacheForTicker } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CapitalStructureBucketPayload,
  CapitalStructureSectionMetaPayload,
  CapitalStructureSnapshotPayload,
  CompanyCapitalStructureResponse,
} from "@/lib/types";

const REFRESH_POLL_INTERVAL_MS = 3000;

interface CapitalStructureIntelligencePanelProps {
  ticker: string;
  reloadKey?: string | null;
  maxPeriods?: number;
  initialPayload?: CompanyCapitalStructureResponse | null;
}

export function CapitalStructureIntelligencePanel({
  ticker,
  reloadKey,
  maxPeriods = 6,
  initialPayload = null,
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
  const history = payload?.history;
  const trendRows = useMemo(() => (history ? history.slice(0, 5) : []), [history]);

  if (loading) {
    return <div className="text-muted">Loading capital structure intelligence...</div>;
  }
  if (error) {
    return <div className="text-muted">{error}</div>;
  }
  if (!payload || !latest) {
    return <PanelEmptyState message="No persisted capital structure intelligence is available yet. Queue a refresh to compute SEC-derived debt, payout, and dilution views." />;
  }

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">Latest period {formatDate(latest.period_end)}</span>
        <span className="pill">Debt {formatCompactNumber(latest.summary.total_debt)}</span>
        <span className="pill">12m maturities {formatCompactNumber(latest.summary.debt_due_next_twelve_months)}</span>
        <span className="pill">Gross payout {formatCompactNumber(latest.summary.gross_shareholder_payout)}</span>
        <span className="pill">Net dilution {formatPercent(latest.summary.net_dilution_ratio)}</span>
        {latest.confidence_score != null ? <span className="pill">Confidence {formatPercent(latest.confidence_score)}</span> : null}
        {activeJobId ? <span className="pill">refreshing</span> : null}
      </div>

      <SourceFreshnessSummary
        provenance={payload.provenance}
        asOf={payload.as_of}
        lastRefreshedAt={payload.last_refreshed_at}
        sourceMix={payload.source_mix}
        confidenceFlags={payload.confidence_flags}
      />

      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <MetricCard label="Interest Burden" value={formatPercent(latest.interest_burden.interest_to_average_debt)} hint="Interest expense as a share of average debt" />
        <MetricCard label="Interest Coverage" value={formatMultiple(latest.interest_burden.interest_coverage_proxy)} hint="Operating income divided by interest expense" />
        <MetricCard label="Dividends" value={formatCompactNumber(latest.capital_returns.dividends)} hint="Cash dividends reported in the filing period" />
        <MetricCard label="Repurchases" value={formatCompactNumber(latest.capital_returns.share_repurchases)} hint="Cash spent on share repurchases" />
        <MetricCard label="SBC" value={formatCompactNumber(latest.capital_returns.stock_based_compensation)} hint="Stock-based compensation expense" />
        <MetricCard label="Net Share Change" value={formatCompactNumber(latest.net_dilution_bridge.net_share_change)} hint="Ending shares minus opening shares" />
      </div>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))" }}>
        <BucketTable
          title="Debt Maturity Ladder"
          subtitle="Latest contractual debt maturities from SEC-reported principal schedules"
          buckets={latest.debt_maturity_ladder.buckets}
          meta={latest.debt_maturity_ladder.meta}
          emptyMessage="No contractual debt maturity schedule was extracted for this filing."
        />
        <BucketTable
          title="Lease Obligations"
          subtitle="Latest operating lease cash obligations from SEC lease footnotes"
          buckets={latest.lease_obligations.buckets}
          meta={latest.lease_obligations.meta}
          emptyMessage="No lease payment schedule was extracted for this filing."
        />
      </div>

      <div className="metric-card" style={{ display: "grid", gap: 10 }}>
        <div className="metric-label">Debt Rollforward & Net Dilution Bridge</div>
        <div className="text-muted" style={{ fontSize: 13 }}>
          Debt issuance and repayment are paired with the latest share issuance / repurchase bridge so we can separate funding, payouts, and dilution effects.
        </div>
        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <MetricCard label="Debt Issued" value={formatCompactNumber(latest.debt_rollforward.debt_issued)} />
          <MetricCard label="Debt Repaid" value={formatCompactNumber(latest.debt_rollforward.debt_repaid)} />
          <MetricCard label="Net Debt Change" value={formatCompactNumber(latest.debt_rollforward.net_debt_change)} />
          <MetricCard label="Shares Issued" value={formatCompactNumber(latest.net_dilution_bridge.shares_issued ?? latest.net_dilution_bridge.shares_issued_proxy)} />
          <MetricCard label="Shares Repurchased" value={formatCompactNumber(latest.net_dilution_bridge.shares_repurchased)} />
          <MetricCard label="Ending Shares" value={formatCompactNumber(latest.net_dilution_bridge.ending_shares)} />
        </div>
        <SectionMeta meta={latest.debt_rollforward.meta} />
        <SectionMeta meta={latest.net_dilution_bridge.meta} />
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
                <tr key={`${row.filing_type}:${row.period_end}`}>
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

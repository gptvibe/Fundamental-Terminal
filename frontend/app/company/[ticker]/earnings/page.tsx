"use client";

import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { EarningsTrendChart, type EarningsTrendDatum } from "@/components/charts/earnings-trend-chart";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { Panel } from "@/components/ui/panel";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyEarningsWorkspace } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { CompanyEarningsWorkspaceResponse, EarningsAlertPayload, EarningsReleasePayload, FinancialPayload } from "@/lib/types";

const EARNINGS_POLL_INTERVAL_MS = 3000;

const DeferredSecHeavyModelsPanel = dynamic(
  () => import("@/components/earnings/sec-heavy-models-panel").then((module) => module.SecHeavyModelsPanel),
  { ssr: false, loading: () => <div className="text-muted">Loading SEC-heavy model visuals...</div> }
);

export default function CompanyEarningsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials = [],
    loading: workspaceLoading,
    error: workspaceError,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker);
  const [workspaceData, setWorkspaceData] = useState<CompanyEarningsWorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedReleaseKey, setSelectedReleaseKey] = useState<string | null>(null);
  const [showMetadataRows, setShowMetadataRows] = useState(false);

  const loadEarningsData = useCallback(
    async ({ background = false }: { background?: boolean } = {}) => {
      if (!background) {
        setLoading(true);
      }
      setLoadError(null);

      const result = await Promise.allSettled([getCompanyEarningsWorkspace(ticker)]);

      const errors: string[] = [];

      if (result[0].status === "fulfilled") {
        setWorkspaceData(result[0].value);
        if (result[0].value.error) {
          errors.push(result[0].value.error);
        }
      } else {
        errors.push(asErrorMessage(result[0].reason, "Unable to load earnings workspace"));
      }

      setLoadError(errors.length ? errors.join(" · ") : null);

      if (!background) {
        setLoading(false);
      }
    },
    [ticker]
  );

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        await loadEarningsData();
      } catch (error) {
        if (!cancelled) {
          setLoadError(asErrorMessage(error, "Unable to load earnings data"));
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [loadEarningsData, reloadKey]);

  const releases = useMemo(() => workspaceData?.earnings_releases ?? [], [workspaceData?.earnings_releases]);
  const sortedReleases = useMemo(
    () => [...releases].sort((left, right) => getReleaseSortKey(right).localeCompare(getReleaseSortKey(left))),
    [releases]
  );
  const usefulReleases = useMemo(() => sortedReleases.filter(hasReleaseSignal), [sortedReleases]);
  const displayReleases = useMemo(() => (showMetadataRows ? sortedReleases : usefulReleases), [showMetadataRows, sortedReleases, usefulReleases]);
  const selectedRelease = useMemo(
    () => displayReleases.find((release) => getReleaseKey(release) === selectedReleaseKey) ?? displayReleases[0] ?? null,
    [displayReleases, selectedReleaseKey]
  );
  const effectiveRefreshState = workspaceData?.refresh ?? refreshState;
  const pageCompany = company ?? workspaceData?.company ?? null;
  const summary = workspaceData?.summary;
  const trackedJobId = effectiveRefreshState?.job_id;
  const fallbackTrendPoints = useMemo(() => buildFallbackTrendPoints(financials), [financials]);
  const latestModelPoint = useMemo(
    () => [...(workspaceData?.model_points ?? [])].sort((left, right) => (right.period_end || "").localeCompare(left.period_end || ""))[0] ?? null,
    [workspaceData?.model_points]
  );
  const alerts = workspaceData?.alerts ?? [];
  const peerContext = workspaceData?.peer_context ?? null;
  const backtests = workspaceData?.backtests ?? null;

  useEffect(() => {
    if (!trackedJobId) {
      return;
    }

    let cancelled = false;
    let intervalId: number | null = null;

    const pollEarnings = async () => {
      try {
        const response = await getCompanyEarningsWorkspace(ticker);

        if (cancelled) {
          return;
        }

        setWorkspaceData(response);
        setLoadError(response.error || null);

        const refreshComplete = !response.refresh.job_id;
        if (refreshComplete && intervalId !== null) {
          window.clearInterval(intervalId);
          intervalId = null;
        }
      } catch (error) {
        if (!cancelled) {
          setLoadError(asErrorMessage(error, "Unable to refresh earnings data"));
        }
      }
    };

    void pollEarnings();
    intervalId = window.setInterval(() => {
      void pollEarnings();
    }, EARNINGS_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
    };
  }, [ticker, trackedJobId]);

  useEffect(() => {
    if (!displayReleases.length) {
      setSelectedReleaseKey(null);
      return;
    }

    const firstReleaseKey = getReleaseKey(displayReleases[0]);
    if (!selectedReleaseKey || !displayReleases.some((release) => getReleaseKey(release) === selectedReleaseKey)) {
      setSelectedReleaseKey(firstReleaseKey);
    }
  }, [displayReleases, selectedReleaseKey]);

  const latestRelease = sortedReleases[0] ?? null;
  const latestPeriodLabel = latestRelease?.reported_period_label ?? formatDate(summary?.latest_reported_period_end ?? latestRelease?.reported_period_end);
  const latestFilingValue = summary?.latest_filing_date
    ? formatDate(summary.latest_filing_date)
    : latestRelease?.filing_date
      ? formatDate(latestRelease.filing_date)
      : "Pending";
  const parsedReleases = summary?.parsed_releases ?? sortedReleases.filter((release) => release.parse_state === "parsed").length;
  const releasesWithGuidance = summary?.releases_with_guidance ?? sortedReleases.filter(hasGuidance).length;
  const releasesWithCapitalReturn = sortedReleases.filter(hasCapitalReturn).length;
  const releasesWithTrendMetrics = sortedReleases.filter((release) => release.revenue != null || release.diluted_eps != null).length;
  const totalReleases = summary?.total_releases ?? sortedReleases.length;
  const metadataOnlyForTrend = Math.max(0, totalReleases - releasesWithTrendMetrics);
  const useFallbackTrend = releasesWithTrendMetrics === 0 && fallbackTrendPoints.length > 0;
  const chartSourceLabel = useFallbackTrend ? "Financial statements (10-Q/10-K)" : "Earnings releases (8-K Item 2.02)";
  const lastCheckedValue = pageCompany?.earnings_last_checked ?? pageCompany?.last_checked ?? null;
  const combinedError = [workspaceError, loadError].filter(Boolean).join(" · ") || null;

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={pageCompany?.name ?? null}
          sector={pageCompany?.sector ?? null}
          refreshState={effectiveRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh earnings releases or jump into the broader filings view for related SEC context."
          primaryActionLabel="Refresh Earnings Data"
          primaryActionDescription="Queues a company refresh so the latest 8-K earnings releases and their exhibits are reloaded."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/filings`}
          secondaryActionLabel="Open Filings"
          secondaryActionDescription="Review the SEC timeline around each release and open the underlying documents."
          statusLines={[
            `Releases tracked: ${totalReleases.toLocaleString()}`,
            `Latest period: ${latestPeriodLabel}`,
            `With guidance: ${releasesWithGuidance.toLocaleString()} · capital return: ${releasesWithCapitalReturn.toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Earnings" subtitle={pageCompany?.name ?? ticker} aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}>
        {combinedError ? (
          <div className="text-muted" style={{ marginBottom: 12 }}>
            {combinedError}
          </div>
        ) : null}

        <div className="metric-grid">
          <Metric label="Releases" value={totalReleases.toLocaleString()} />
          <Metric label="Parsed Releases" value={parsedReleases.toLocaleString()} />
          <Metric label="With Guidance" value={releasesWithGuidance.toLocaleString()} />
          <Metric label="Capital Return Signals" value={releasesWithCapitalReturn.toLocaleString()} />
          <Metric label="Latest Period" value={latestPeriodLabel} />
          <Metric label="Latest Filing" value={latestFilingValue} />
          <Metric label="Latest Revenue" value={summary?.latest_revenue != null ? formatCompactNumber(summary.latest_revenue) : formatCompactNumber(latestRelease?.revenue)} />
          <Metric label="Latest Diluted EPS" value={formatEps(summary?.latest_diluted_eps ?? latestRelease?.diluted_eps)} />
          <Metric label="Last Checked" value={lastCheckedValue ? formatDate(lastCheckedValue) : null} />
        </div>
      </Panel>

      <Panel title="Reported Revenue vs Diluted EPS" subtitle="SEC earnings releases plotted by reported period so the top-line and per-share trend stay visible at a glance">
        {!loading && !workspaceLoading && useFallbackTrend ? (
          <div className="text-muted" style={{ marginBottom: 12 }}>
            Release-level numeric metrics are currently unavailable. Showing fallback quarterly trend from cached financial statements. This means the chart is using reported quarterly results from company filings instead of earnings-release exhibits.
          </div>
        ) : null}
        {!loading && !workspaceLoading && !useFallbackTrend && totalReleases > 0 && metadataOnlyForTrend > 0 ? (
          <div className="text-muted" style={{ marginBottom: 12 }}>
            {`Only ${releasesWithTrendMetrics.toLocaleString()} of ${totalReleases.toLocaleString()} cached releases currently include reported revenue or diluted EPS. ${metadataOnlyForTrend.toLocaleString()} metadata-only releases are excluded from the chart until numeric metrics are parsed.`}
          </div>
        ) : null}
        {loading || workspaceLoading ? (
          <div className="text-muted">Loading earnings trend...</div>
        ) : releases.length || fallbackTrendPoints.length ? (
          <EarningsTrendChart earnings={sortedReleases} points={useFallbackTrend ? fallbackTrendPoints : undefined} sourceLabel={chartSourceLabel} />
        ) : (
          <PanelEmptyState message="No earnings releases have been cached yet for this company." />
        )}
      </Panel>

      <Panel
        title="SEC-Heavy Earnings Models"
        subtitle="Models built from SEC filing fundamentals first: earnings quality, EPS drift, and segment contribution delta"
      >
        <DeferredClientSection placeholder={<div className="text-muted">Loading SEC-heavy model visuals...</div>}>
          <DeferredSecHeavyModelsPanel
            loading={loading || workspaceLoading}
            modelPoints={workspaceData?.model_points ?? []}
          />
        </DeferredClientSection>
      </Panel>

      <Panel title="Peer-Relative Context" subtitle="Percentile view of quality and EPS drift versus sector and peer group">
        {peerContext ? (
          <div className="metric-grid">
            <Metric label="Peer basis" value={peerContext.peer_group_basis.replace("_", " ")} />
            <Metric label="Peer group size" value={peerContext.peer_group_size.toLocaleString()} />
            <Metric label="Quality percentile" value={peerContext.quality_percentile != null ? formatPercent(peerContext.quality_percentile) : "\u2014"} />
            <Metric label="EPS drift percentile" value={peerContext.eps_drift_percentile != null ? formatPercent(peerContext.eps_drift_percentile) : "\u2014"} />
            <Metric label="Sector group size" value={peerContext.sector_group_size.toLocaleString()} />
            <Metric label="Sector quality percentile" value={peerContext.sector_quality_percentile != null ? formatPercent(peerContext.sector_quality_percentile) : "\u2014"} />
            <Metric label="Sector EPS percentile" value={peerContext.sector_eps_drift_percentile != null ? formatPercent(peerContext.sector_eps_drift_percentile) : "\u2014"} />
          </div>
        ) : (
          <PanelEmptyState message="Peer-relative context is unavailable until model points are cached." />
        )}
      </Panel>

      <Panel title="Directional Backtests" subtitle="Directional consistency around earnings filing windows using cached price history only">
        {backtests ? (
          <div style={{ display: "grid", gap: 12 }}>
            <div className="metric-grid">
              <Metric label="Window" value={`${backtests.window_sessions} trading sessions`} />
              <Metric
                label="Quality consistency"
                value={backtests.quality_directional_consistency != null ? formatPercent(backtests.quality_directional_consistency) : "\u2014"}
              />
              <Metric label="Quality windows" value={`${backtests.quality_consistent_windows}/${backtests.quality_total_windows}`} />
              <Metric
                label="EPS drift consistency"
                value={backtests.eps_directional_consistency != null ? formatPercent(backtests.eps_directional_consistency) : "\u2014"}
              />
              <Metric label="EPS windows" value={`${backtests.eps_consistent_windows}/${backtests.eps_total_windows}`} />
            </div>
            <div className="text-muted" style={{ fontSize: 13 }}>
              Price reaction uses cached daily bars only: close on filing date window start versus close after the configured post-event sessions.
            </div>
          </div>
        ) : (
          <PanelEmptyState message="Backtests will appear after model points and price windows are available." />
        )}
      </Panel>

      <Panel title="Model Alerts" subtitle="Regime and threshold changes from SEC-heavy model series">
        {alerts.length ? (
          <div style={{ display: "grid", gap: 10 }}>
            {alerts.map((alert) => (
              <AlertRow key={alert.id} alert={alert} />
            ))}
          </div>
        ) : (
          <PanelEmptyState message="No quality regime shifts, EPS sign flips, or large segment-share changes were detected." />
        )}
      </Panel>

      <Panel title="Explainability" subtitle="Exact SEC fields, periods, and fallback usage for latest model point">
        {latestModelPoint?.explainability ? (
          <div style={{ display: "grid", gap: 12 }}>
            <div className="text-muted" style={{ fontSize: 13 }}>
              Formulas: {latestModelPoint.explainability.quality_formula} | {latestModelPoint.explainability.eps_drift_formula}
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 760 }}>
                <thead>
                  <tr className="text-muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.08 }}>
                    <th align="left" style={{ padding: "8px 10px" }}>Field</th>
                    <th align="right" style={{ padding: "8px 10px" }}>Value</th>
                    <th align="left" style={{ padding: "8px 10px" }}>Period</th>
                    <th align="left" style={{ padding: "8px 10px" }}>SEC tags</th>
                  </tr>
                </thead>
                <tbody>
                  {latestModelPoint.explainability.inputs.map((input) => (
                    <tr key={`${input.field}:${input.period_end}`}>
                      <td style={{ padding: "10px" }}>{input.field.replace(/_/g, " ")}</td>
                      <td style={{ padding: "10px", textAlign: "right" }}>{formatExplainValue(input.field, input.value)}</td>
                      <td style={{ padding: "10px" }}>{formatDate(input.period_end)}</td>
                      <td style={{ padding: "10px" }}>{input.sec_tags.length ? input.sec_tags.join(", ") : "\u2014"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : (
          <PanelEmptyState message="Explainability rows appear after at least two comparable SEC periods are cached." />
        )}
      </Panel>

      <Panel title="Earnings Releases" subtitle="Review each release with guidance, capital return, highlights, exhibit links, and parse status">
        {!loading && !workspaceLoading && sortedReleases.length ? (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            <span className="pill">Signal-bearing releases {usefulReleases.length.toLocaleString()} / {sortedReleases.length.toLocaleString()}</span>
            <button
              type="button"
              className="ticker-button"
              onClick={() => setShowMetadataRows((current) => !current)}
              style={{ padding: "6px 10px", fontSize: 12 }}
            >
              {showMetadataRows ? "Hide metadata-only releases" : "Show metadata-only releases"}
            </button>
          </div>
        ) : null}
        {loading || workspaceLoading ? (
          <div className="text-muted">Loading earnings releases...</div>
        ) : displayReleases.length ? (
          <div style={{ display: "grid", gap: 16, gridTemplateColumns: "minmax(0, 1.35fr) minmax(280px, 0.85fr)" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720 }}>
                <thead>
                  <tr className="text-muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.08 }}>
                    <th align="left" style={{ padding: "10px 12px" }}>Filed</th>
                    <th align="left" style={{ padding: "10px 12px" }}>Period</th>
                    <th align="right" style={{ padding: "10px 12px" }}>Revenue</th>
                    <th align="right" style={{ padding: "10px 12px" }}>EPS</th>
                    <th align="left" style={{ padding: "10px 12px" }}>Guidance</th>
                    <th align="left" style={{ padding: "10px 12px" }}>Capital Return</th>
                    <th align="left" style={{ padding: "10px 12px" }}>Parse</th>
                  </tr>
                </thead>
                <tbody>
                  {displayReleases.map((release) => {
                    const releaseKey = getReleaseKey(release);
                    const isSelected = releaseKey === selectedReleaseKey;
                    return (
                      <tr
                        key={releaseKey}
                        onClick={() => setSelectedReleaseKey(releaseKey)}
                        onKeyDown={(event) => handleRowKeyDown(event, releaseKey, setSelectedReleaseKey)}
                        tabIndex={0}
                        style={{
                          cursor: "pointer",
                          background: isSelected ? "rgba(0, 255, 65, 0.08)" : "transparent",
                          outline: isSelected ? "1px solid rgba(0, 255, 65, 0.28)" : "1px solid transparent"
                        }}
                      >
                        <td style={{ padding: "12px 12px", verticalAlign: "top" }}>{formatDate(release.filing_date)}</td>
                        <td style={{ padding: "12px 12px", verticalAlign: "top" }}>{displayPeriod(release)}</td>
                        <td style={{ padding: "12px 12px", verticalAlign: "top", textAlign: "right" }}>{formatCompactNumber(release.revenue)}</td>
                        <td style={{ padding: "12px 12px", verticalAlign: "top", textAlign: "right" }}>{formatEps(release.diluted_eps)}</td>
                        <td style={{ padding: "12px 12px", verticalAlign: "top" }}>{formatGuidanceSnippet(release)}</td>
                        <td style={{ padding: "12px 12px", verticalAlign: "top" }}>{formatCapitalReturnSnippet(release)}</td>
                        <td style={{ padding: "12px 12px", verticalAlign: "top" }}>{release.parse_state.replace(/_/g, " ")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="filing-link-card" style={{ display: "grid", gap: 14 }}>
              {selectedRelease ? (
                <>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "flex-start" }}>
                    <div style={{ display: "grid", gap: 6 }}>
                      <div style={{ fontSize: 18, fontWeight: 700, color: "var(--text)" }}>{displayReleaseTitle(selectedRelease)}</div>
                      <div className="text-muted" style={{ fontSize: 13 }}>{describeRelease(selectedRelease)}</div>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <span className="pill">{selectedRelease.form}</span>
                      <span className="pill">{selectedRelease.parse_state.replace(/_/g, " ")}</span>
                    </div>
                  </div>

                  <div style={{ display: "grid", gap: 8 }}>
                    <DetailRow label="Filing date" value={formatDate(selectedRelease.filing_date)} />
                    <DetailRow label="Reported period" value={selectedRelease.reported_period_label ?? formatDate(selectedRelease.reported_period_end)} />
                    <DetailRow label="Revenue" value={formatCompactNumber(selectedRelease.revenue)} />
                    <DetailRow label="Operating income" value={formatCompactNumber(selectedRelease.operating_income)} />
                    <DetailRow label="Net income" value={formatCompactNumber(selectedRelease.net_income)} />
                    <DetailRow label="Diluted EPS" value={formatEps(selectedRelease.diluted_eps)} />
                    <DetailRow
                      label="Guidance"
                      value={formatGuidanceDetail(selectedRelease)}
                    />
                    <DetailRow
                      label="Capital return"
                      value={formatCapitalReturnDetail(selectedRelease)}
                    />
                  </div>

                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <a href={selectedRelease.source_url} target="_blank" rel="noreferrer" className="ticker-button" style={{ display: "inline-flex" }}>
                      Open SEC Filing
                    </a>
                    {selectedRelease.exhibit_document ? <span className="pill">Exhibit {selectedRelease.exhibit_type ?? selectedRelease.exhibit_document}</span> : null}
                    {selectedRelease.primary_document ? <span className="pill">{selectedRelease.primary_document}</span> : null}
                  </div>

                  <div style={{ display: "grid", gap: 8 }}>
                    <div className="text-muted" style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.08 }}>Highlights</div>
                    {selectedRelease.highlights.length ? (
                      <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 8 }}>
                        {selectedRelease.highlights.map((highlight) => (
                          <li key={highlight} style={{ color: "var(--text)" }}>{highlight}</li>
                        ))}
                      </ul>
                    ) : (
                      <div className="sparkline-note">No highlight bullets were extracted for this release.</div>
                    )}
                  </div>
                </>
              ) : (
                <PanelEmptyState message="Select a release to inspect its guidance, capital return, and exhibit details." />
              )}
            </div>
          </div>
        ) : (
          <PanelEmptyState message="No earnings releases with metrics, guidance, or capital-return signals are available yet. Enable metadata-only rows to inspect all cached filings." />
        )}
      </Panel>
    </CompanyWorkspaceShell>
  );
}

function Metric({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value ?? "?"}</div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
      <span className="text-muted" style={{ fontSize: 13 }}>{label}</span>
      <span style={{ color: "var(--text)", fontSize: 13, textAlign: "right" }}>{value}</span>
    </div>
  );
}

function AlertRow({ alert }: { alert: EarningsAlertPayload }) {
  const color = alert.level === "high" ? "#FF9E9E" : alert.level === "medium" ? "#FFD98D" : "#B7FFD5";
  return (
    <div className="metric-card" style={{ borderColor: color, display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
        <div className="metric-label">{alert.title}</div>
        <span className="pill" style={{ borderColor: color }}>{alert.level}</span>
      </div>
      <div style={{ color: "var(--text)", fontSize: 14 }}>{alert.detail}</div>
      <div className="text-muted" style={{ fontSize: 12 }}>{formatDate(alert.period_end)}</div>
    </div>
  );
}

function formatExplainValue(field: string, value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "\u2014";
  }
  if (field === "eps") {
    return formatEps(value);
  }
  return formatCompactNumber(value);
}

function displayPeriod(release: EarningsReleasePayload): string {
  return release.reported_period_label ?? formatDate(release.reported_period_end ?? release.report_date ?? release.filing_date);
}

function displayReleaseTitle(release: EarningsReleasePayload): string {
  return release.reported_period_label ? `${release.reported_period_label} earnings release` : `${displayPeriod(release)} earnings release`;
}

function describeRelease(release: EarningsReleasePayload): string {
  if (release.highlights.length) {
    return release.highlights[0] ?? "";
  }

  if (release.parse_state === "parsed") {
    return release.exhibit_type
      ? `Parsed from SEC Exhibit ${release.exhibit_type}.`
      : "Parsed from the primary SEC filing document.";
  }

  return "Metadata only capture; open the SEC filing to inspect the full release narrative.";
}

function formatGuidanceSnippet(release: EarningsReleasePayload): string {
  const revenue = formatRange(release.revenue_guidance_low, release.revenue_guidance_high, "revenue");
  const eps = formatRange(release.eps_guidance_low, release.eps_guidance_high, "eps");
  if (revenue === "—" && eps === "—") {
    return "—";
  }
  return [revenue !== "—" ? `Rev ${revenue}` : null, eps !== "—" ? `EPS ${eps}` : null].filter(Boolean).join(" · ");
}

function formatCapitalReturnSnippet(release: EarningsReleasePayload): string {
  const parts = [
    release.share_repurchase_amount != null ? `Buyback ${formatCompactNumber(release.share_repurchase_amount)}` : null,
    release.dividend_per_share != null ? `Dividend ${formatEps(release.dividend_per_share)}` : null
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

function formatGuidanceDetail(release: EarningsReleasePayload): string {
  const revenue = formatRange(release.revenue_guidance_low, release.revenue_guidance_high, "revenue");
  const eps = formatRange(release.eps_guidance_low, release.eps_guidance_high, "eps");
  return revenue === "—" && eps === "—" ? "No guidance disclosed" : [revenue !== "—" ? `Revenue ${revenue}` : null, eps !== "—" ? `EPS ${eps}` : null].filter(Boolean).join(" · ");
}

function formatCapitalReturnDetail(release: EarningsReleasePayload): string {
  const parts = [
    release.share_repurchase_amount != null ? `Buyback authorization ${formatCompactNumber(release.share_repurchase_amount)}` : null,
    release.dividend_per_share != null ? `Dividend per share ${formatEps(release.dividend_per_share)}` : null
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "No capital return disclosed";
}

function formatRange(low: number | null, high: number | null, kind: "revenue" | "eps"): string {
  if (low == null && high == null) {
    return "—";
  }

  if (kind === "revenue") {
    if (low != null && high != null) {
      return `${formatCompactNumber(low)}-${formatCompactNumber(high)}`;
    }
    return formatCompactNumber(low ?? high);
  }

  if (low != null && high != null) {
    return `${formatEps(low)}-${formatEps(high)}`;
  }
  return formatEps(low ?? high);
}

function formatEps(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

function hasGuidance(release: EarningsReleasePayload): boolean {
  return [release.revenue_guidance_low, release.revenue_guidance_high, release.eps_guidance_low, release.eps_guidance_high].some((value) => value != null);
}

function hasCapitalReturn(release: EarningsReleasePayload): boolean {
  return release.share_repurchase_amount != null || release.dividend_per_share != null;
}

function hasReleaseSignal(release: EarningsReleasePayload): boolean {
  return (
    release.revenue != null ||
    release.diluted_eps != null ||
    release.operating_income != null ||
    release.net_income != null ||
    hasGuidance(release) ||
    hasCapitalReturn(release)
  );
}

function getReleaseKey(release: EarningsReleasePayload): string {
  return (
    release.accession_number ??
    `${release.filing_date ?? release.report_date ?? release.reported_period_end ?? release.form}-${release.primary_document ?? release.exhibit_document ?? release.source_url}`
  );
}

function handleRowKeyDown(
  event: KeyboardEvent<HTMLTableRowElement>,
  releaseKey: string,
  setSelectedReleaseKey: (value: string) => void
) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    setSelectedReleaseKey(releaseKey);
  }
}

function getReleaseSortKey(release: EarningsReleasePayload): string {
  return release.reported_period_end ?? release.filing_date ?? release.report_date ?? release.accession_number ?? "";
}

function asErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function buildFallbackTrendPoints(financials: FinancialPayload[]): EarningsTrendDatum[] {
  const quarterlyStatements = financials.filter(
    (statement) => ["10-Q", "6-K"].includes(statement.filing_type) && (statement.revenue != null || statement.eps != null)
  );
  const annualStatements = financials.filter(
    (statement) => ["10-K", "20-F", "40-F"].includes(statement.filing_type) && (statement.revenue != null || statement.eps != null)
  );
  const sourceStatements = quarterlyStatements.length ? quarterlyStatements : annualStatements;
  const seenPeriods = new Set<string>();

  return [...sourceStatements]
    .sort((left, right) => (left.period_end || "").localeCompare(right.period_end || ""))
    .filter((statement) => {
      const key = `${statement.filing_type}:${statement.period_end}`;
      if (seenPeriods.has(key)) {
        return false;
      }
      seenPeriods.add(key);
      return true;
    })
    .map((statement) => ({
      label: formatDate(statement.period_end),
      filingDate: statement.last_updated,
      reportedPeriodEnd: statement.period_end,
      revenue: statement.revenue,
      dilutedEps: statement.eps,
      parseState: "financials_fallback"
    }));
}


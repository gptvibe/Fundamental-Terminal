"use client";

import { useCallback, useEffect, useMemo, useState, type KeyboardEvent } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { BottomAppendix } from "@/components/company/bottom-appendix";
import { EarningsTrendChart, type EarningsTrendDatum } from "@/components/charts/earnings-trend-chart";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { CompanyMetricGrid, CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { DataQualityDiagnostics } from "@/components/ui/data-quality-diagnostics";
import { MetricLabel } from "@/components/ui/metric-label";
import { Panel } from "@/components/ui/panel";
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
  const strictOfficialMode = Boolean(pageCompany?.strict_official_mode);

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
      <CompanyResearchHeader
        ticker={ticker}
        title="Earnings"
        companyName={pageCompany?.name ?? ticker}
        sector={pageCompany?.sector}
        description={
          strictOfficialMode
            ? "Release-level earnings analysis stays SEC-first, while price-window backtests remain disabled in strict official mode."
            : "Release-level earnings analysis stays SEC-first, serving cached 8-K Item 2.02 data immediately and polling in the background when refresh jobs are active."
        }
        freshness={{
          cacheState: pageCompany?.cache_state ?? null,
          refreshState: effectiveRefreshState,
          loading: loading || workspaceLoading,
          hasData: Boolean(pageCompany || summary || sortedReleases.length || (workspaceData?.model_points ?? []).length),
          lastChecked: lastCheckedValue,
          errors: [combinedError],
          detailLines: [
            `Releases tracked: ${totalReleases.toLocaleString()}`,
            `Latest period: ${latestPeriodLabel}`,
            `With guidance: ${releasesWithGuidance.toLocaleString()} · capital return: ${releasesWithCapitalReturn.toLocaleString()}`,
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={(loading || workspaceLoading) && !pageCompany && !summary && !sortedReleases.length}
        summariesLoading={(loading || workspaceLoading) && !pageCompany && !summary && !sortedReleases.length}
        facts={[
          { label: "Releases", value: totalReleases.toLocaleString() },
          { label: "Parsed Releases", value: parsedReleases.toLocaleString() },
          { label: "Latest Period", value: latestPeriodLabel },
          { label: "Last Checked", value: lastCheckedValue ? formatDate(lastCheckedValue) : null }
        ]}
        ribbonItems={[
          { label: "Release Source", value: "SEC 8-K Item 2.02", tone: "green" },
          { label: "Fallback Trend", value: chartSourceLabel, tone: useFallbackTrend ? "gold" : "cyan" },
          { label: "Latest Filing", value: latestFilingValue, tone: "cyan" },
          { label: "Refresh", value: trackedJobId ? "Polling cached workspace" : "Background-first", tone: trackedJobId ? "cyan" : "green" }
        ]}
        summaries={[
          { label: "With Guidance", value: releasesWithGuidance.toLocaleString(), accent: "gold" },
          { label: "Capital Return", value: releasesWithCapitalReturn.toLocaleString(), accent: "green" },
          { label: "Latest Revenue", value: summary?.latest_revenue != null ? formatCompactNumber(summary.latest_revenue) : formatCompactNumber(latestRelease?.revenue), accent: "cyan" },
          { label: "Latest Diluted EPS", value: formatEps(summary?.latest_diluted_eps ?? latestRelease?.diluted_eps), accent: "gold" }
        ]}
      >
        {strictOfficialMode ? (
          <div className="text-muted" style={{ marginBottom: 12 }}>
            Strict official mode keeps SEC release analysis available, but disables price-window backtests because no official end-of-day equity price feed is configured.
          </div>
        ) : null}
        {combinedError ? (
          <div className="text-muted" style={{ marginBottom: 12 }}>
            {combinedError}
          </div>
        ) : null}
      </CompanyResearchHeader>

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
          <CompanyMetricGrid
            items={[
              { label: "Peer basis", value: peerContext.peer_group_basis.replace("_", " ") },
              { label: "Peer group size", value: peerContext.peer_group_size.toLocaleString() },
              { label: "Quality percentile", value: peerContext.quality_percentile != null ? formatPercent(peerContext.quality_percentile) : "\u2014" },
              { label: "EPS drift percentile", value: peerContext.eps_drift_percentile != null ? formatPercent(peerContext.eps_drift_percentile) : "\u2014" },
              { label: "Sector group size", value: peerContext.sector_group_size.toLocaleString() },
              { label: "Sector quality percentile", value: peerContext.sector_quality_percentile != null ? formatPercent(peerContext.sector_quality_percentile) : "\u2014" },
              { label: "Sector EPS percentile", value: peerContext.sector_eps_drift_percentile != null ? formatPercent(peerContext.sector_eps_drift_percentile) : "\u2014" }
            ]}
          />
        ) : (
          <PanelEmptyState message="Peer-relative context is unavailable until model points are cached." />
        )}
      </Panel>

      <Panel title="Directional Backtests" subtitle={strictOfficialMode ? "Disabled in strict mode because price windows require a non-official equity feed" : "Directional consistency around earnings filing windows using cached price history only"}>
        {strictOfficialMode ? (
          <PanelEmptyState message="Directional backtests are unavailable in strict official mode because post-filing price windows depend on commercial equity price data." />
        ) : backtests ? (
          <div className="workspace-card-stack">
            <CompanyMetricGrid
              items={[
                { label: "Window", value: `${backtests.window_sessions} trading sessions` },
                { label: "Quality consistency", value: backtests.quality_directional_consistency != null ? formatPercent(backtests.quality_directional_consistency) : "\u2014" },
                { label: "Quality windows", value: `${backtests.quality_consistent_windows}/${backtests.quality_total_windows}` },
                { label: "EPS drift consistency", value: backtests.eps_directional_consistency != null ? formatPercent(backtests.eps_directional_consistency) : "\u2014" },
                { label: "EPS windows", value: `${backtests.eps_consistent_windows}/${backtests.eps_total_windows}` }
              ]}
            />
            <div className="text-muted workspace-card-copy">
              Price reaction uses cached daily bars only: close on filing date window start versus close after the configured post-event sessions.
            </div>
          </div>
        ) : (
          <PanelEmptyState message="Backtests will appear after model points and price windows are available." />
        )}
      </Panel>

      <Panel title="Model Alerts" subtitle="Regime and threshold changes from SEC-heavy model series">
        {alerts.length ? (
          <div className="workspace-alert-list">
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
          <div className="workspace-card-stack">
            <div className="text-muted workspace-card-copy">
              Formulas: {latestModelPoint.explainability.quality_formula} | {latestModelPoint.explainability.eps_drift_formula}
            </div>
            <div className="company-data-table-shell">
              <table className="company-data-table company-data-table-wide">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th className="is-numeric">Value</th>
                    <th>Period</th>
                    <th className="is-wrap">SEC tags</th>
                  </tr>
                </thead>
                <tbody>
                  {latestModelPoint.explainability.inputs.map((input) => (
                    <tr key={`${input.field}:${input.period_end}`}>
                      <td>{input.field.replace(/_/g, " ")}</td>
                      <td className="is-numeric">{formatExplainValue(input.field, input.value)}</td>
                      <td>{formatDate(input.period_end)}</td>
                      <td className="is-wrap">{input.sec_tags.length ? input.sec_tags.join(", ") : "\u2014"}</td>
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
          <div className="workspace-filter-row workspace-filter-row-spaced">
            <span className="pill">Signal-bearing releases {usefulReleases.length.toLocaleString()} / {sortedReleases.length.toLocaleString()}</span>
            <button
              type="button"
              className="ticker-button workspace-inline-action"
              onClick={() => setShowMetadataRows((current) => !current)}
            >
              {showMetadataRows ? "Hide metadata-only releases" : "Show metadata-only releases"}
            </button>
          </div>
        ) : null}
        {loading || workspaceLoading ? (
          <div className="text-muted">Loading earnings releases...</div>
        ) : displayReleases.length ? (
          <div className="workspace-release-grid">
            <div className="company-data-table-shell">
              <table className="company-data-table company-data-table-wide">
                <thead>
                  <tr>
                    <th>Filed</th>
                    <th>Period</th>
                    <th className="is-numeric">Revenue</th>
                    <th className="is-numeric">EPS</th>
                    <th className="is-wrap">Guidance</th>
                    <th className="is-wrap">Capital Return</th>
                    <th>Parse</th>
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
                        className={`is-interactive${isSelected ? " is-selected" : ""}`}
                      >
                        <td>{formatDate(release.filing_date)}</td>
                        <td>{displayPeriod(release)}</td>
                        <td className="is-numeric">{formatCompactNumber(release.revenue)}</td>
                        <td className="is-numeric">{formatEps(release.diluted_eps)}</td>
                        <td className="is-wrap">{formatGuidanceSnippet(release)}</td>
                        <td className="is-wrap">{formatCapitalReturnSnippet(release)}</td>
                        <td>{release.parse_state.replace(/_/g, " ")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="filing-link-card workspace-card-stack workspace-release-detail">
              {selectedRelease ? (
                <>
                  <div className="workspace-card-row is-start">
                    <div className="workspace-card-stack workspace-card-stack-tight">
                      <div className="workspace-detail-title">{displayReleaseTitle(selectedRelease)}</div>
                      <div className="text-muted workspace-card-copy">{describeRelease(selectedRelease)}</div>
                    </div>
                    <div className="workspace-pill-row">
                      <span className="pill">{selectedRelease.form}</span>
                      <span className="pill">{selectedRelease.parse_state.replace(/_/g, " ")}</span>
                    </div>
                  </div>

                  <div className="workspace-card-stack workspace-card-stack-tight">
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

                  <div className="workspace-pill-row">
                    <a href={selectedRelease.source_url} target="_blank" rel="noreferrer" className="ticker-button workspace-inline-action is-inline-link">
                      Open SEC Filing
                    </a>
                    {selectedRelease.exhibit_document ? <span className="pill">Exhibit {selectedRelease.exhibit_type ?? selectedRelease.exhibit_document}</span> : null}
                    {selectedRelease.primary_document ? <span className="pill">{selectedRelease.primary_document}</span> : null}
                  </div>

                  <div className="workspace-card-stack workspace-card-stack-tight">
                    <div className="text-muted workspace-eyebrow">Highlights</div>
                    {selectedRelease.highlights.length ? (
                      <ul className="workspace-highlight-list">
                        {selectedRelease.highlights.map((highlight) => (
                          <li key={highlight}>{highlight}</li>
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

      <BottomAppendix
        id="earnings-appendix"
        title="Earnings appendix"
        subtitle="Secondary diagnostics, refresh state, and release-source detail live here to keep the core earnings read front-loaded."
        toggleLabel="Earnings appendix"
        sections={[
          {
            id: "source-details",
            title: "Source details",
            content: (
              <div className="workspace-card-stack">
                <div className="text-muted workspace-card-copy">
                  Primary source: SEC 8-K Item 2.02 earnings releases and linked exhibits.
                </div>
                <div className="workspace-card-copy text-muted">
                  Releases tracked: {totalReleases.toLocaleString()} · Parsed: {parsedReleases.toLocaleString()} · Metadata-only: {Math.max(0, totalReleases - parsedReleases).toLocaleString()}
                </div>
              </div>
            ),
          },
          {
            id: "refresh-state",
            title: "Refresh state",
            content: (
              <div className="workspace-pill-row">
                <span className="pill">{trackedJobId ? "Refresh queued" : "No active refresh"}</span>
                <span className="pill">Latest filing {latestFilingValue}</span>
                <span className="pill">Last checked {lastCheckedValue ? formatDate(lastCheckedValue) : "Pending"}</span>
              </div>
            ),
          },
          {
            id: "methodology",
            title: "Methodology",
            content: (
              <div className="text-muted workspace-card-copy">
                Trend charts prioritize parsed release metrics. If releases are metadata-only, the view falls back to cached statement trends while preserving period labeling.
              </div>
            ),
          },
          {
            id: "diagnostics",
            title: "Diagnostics",
            content: <DataQualityDiagnostics diagnostics={workspaceData?.diagnostics} />,
          },
          {
            id: "partial-errors",
            title: "Partial errors",
            content: combinedError ? <div className="text-muted">{combinedError}</div> : <div className="text-muted">No partial errors are currently active.</div>,
          },
          {
            id: "raw-evidence",
            title: "Raw evidence/provenance",
            content: sortedReleases.length ? (
              <div className="workspace-card-stack">
                {sortedReleases.slice(0, 8).map((release) => (
                  <a
                    key={getReleaseKey(release)}
                    href={release.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="filing-link-card workspace-card-link"
                  >
                    <div className="workspace-card-row">
                      <div className="workspace-pill-row">
                        <span className="pill">{release.form}</span>
                        <span className="pill">{release.parse_state.replace(/_/g, " ")}</span>
                      </div>
                      <div className="text-muted">{formatDate(release.filing_date ?? release.report_date)}</div>
                    </div>
                    <div className="workspace-card-title">{displayReleaseTitle(release)}</div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-muted">No release evidence is available yet.</div>
            ),
          },
        ]}
      />
    </CompanyWorkspaceShell>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="company-detail-row">
      <span className="company-detail-label">{label}</span>
      <span className="company-detail-value">{value}</span>
    </div>
  );
}

function AlertRow({ alert }: { alert: EarningsAlertPayload }) {
  const toneClass = alert.level === "high" ? "is-high" : alert.level === "medium" ? "is-medium" : "is-low";
  return (
    <div className={`metric-card workspace-alert-card ${toneClass}`}>
      <div className="workspace-card-row">
        <div className="metric-label">
          <MetricLabel label={alert.title} />
        </div>
        <span className={`pill workspace-alert-pill ${toneClass}`}>{alert.level}</span>
      </div>
      <div className="workspace-note-line workspace-note-strong">{alert.detail}</div>
      <div className="text-muted workspace-card-copy-small">{formatDate(alert.period_end)}</div>
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


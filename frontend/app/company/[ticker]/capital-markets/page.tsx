"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import { DeferredClientSection } from "@/components/performance/deferred-client-section";
import { CompanyMetricGrid, CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { Panel } from "@/components/ui/panel";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyCapitalMarkets, getCompanyEquityClaimRisk } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import type { CapitalRaisePayload, CompanyCapitalRaisesResponse, CompanyEquityClaimRiskResponse, EquityClaimRiskEvidencePayload } from "@/lib/types";

const ShareDilutionTrackerChart = dynamic(
  () => import("@/components/charts/share-dilution-tracker-chart").then((m) => ({ default: m.ShareDilutionTrackerChart })),
  { ssr: false, loading: () => <div className="text-muted" style={{ minHeight: 280 }}>Loading share dilution chart...</div> }
);

export default function CompanyCapitalMarketsPage() {
  const params = useParams<{ ticker: string }>();
  const searchParams = useSearchParams();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const requestedAsOf = searchParams.get("as_of") ?? searchParams.get("asOf");
  const {
    company,
    financials,
    loading: workspaceLoading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker);
  const [riskData, setRiskData] = useState<CompanyEquityClaimRiskResponse | null>(null);
  const [riskLoading, setRiskLoading] = useState(true);
  const [riskError, setRiskError] = useState<string | null>(null);
  const [capitalMarketsData, setCapitalMarketsData] = useState<CompanyCapitalRaisesResponse | null>(null);
  const [capitalMarketsLoading, setCapitalMarketsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setRiskLoading(true);
        setRiskError(null);
        const response = await getCompanyEquityClaimRisk(ticker, { asOf: requestedAsOf });
        if (!cancelled) {
          setRiskData(response);
        }
      } catch (nextError) {
        if (!cancelled) {
          setRiskError(nextError instanceof Error ? nextError.message : "Unable to load the equity claim risk pack");
        }
      } finally {
        if (!cancelled) {
          setRiskLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, requestedAsOf, ticker]);

  useEffect(() => {
    let cancelled = false;

    async function loadCapitalMarkets() {
      try {
        setCapitalMarketsLoading(true);
        const data = await getCompanyCapitalMarkets(ticker);
        if (!cancelled) setCapitalMarketsData(data);
      } catch {
        // S-8 section degrades gracefully; no explicit error state needed.
      } finally {
        if (!cancelled) setCapitalMarketsLoading(false);
      }
    }

    void loadCapitalMarkets();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  const equityPlanFilings = (capitalMarketsData?.filings ?? []).filter(
    (f) => f.form === "S-8" || f.form === "S-8/A"
  );

  const summary = riskData?.summary ?? null;
  const shareCountBridge = riskData?.share_count_bridge ?? null;
  const shelfRegistration = riskData?.shelf_registration ?? null;
  const atmDependency = riskData?.atm_and_financing_dependency ?? null;
  const hybridSecurities = riskData?.warrants_and_convertibles ?? null;
  const sbcAndDilution = riskData?.sbc_and_dilution ?? null;
  const debtMaturityWall = riskData?.debt_maturity_wall ?? null;
  const covenantSignals = riskData?.covenant_risk_signals ?? null;
  const reportingControls = riskData?.reporting_and_controls ?? null;
  const provenance = riskData?.provenance ?? [];
  const confidenceFlags = riskData?.confidence_flags ?? [];
  const diagnostics = riskData?.diagnostics ?? null;
  const latestFinancial = financials[0] ?? null;
  const effectiveRefreshState = riskData?.refresh ?? refreshState;
  const financingEvidence = useMemo(
    () => [...(shelfRegistration?.evidence ?? []), ...(atmDependency?.evidence ?? [])],
    [atmDependency?.evidence, shelfRegistration?.evidence]
  );
  const hybridAndDebtEvidence = useMemo(
    () => [...(hybridSecurities?.evidence ?? []), ...(debtMaturityWall?.evidence ?? [])],
    [debtMaturityWall?.evidence, hybridSecurities?.evidence]
  );
  const covenantAndReportingEvidence = useMemo(
    () => [...(covenantSignals?.evidence ?? []), ...(reportingControls?.evidence ?? [])],
    [covenantSignals?.evidence, reportingControls?.evidence]
  );

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? riskData?.company?.name ?? null}
          sector={company?.sector ?? riskData?.company?.sector ?? null}
          refreshState={effectiveRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh the pack or jump back to the default brief after you have a view on dilution and financing risk."
          primaryActionLabel="Refresh Risk Pack"
          primaryActionDescription="Queues a company refresh so share-count, financing, debt wall, and reporting-control signals stay current."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/events`}
          secondaryActionLabel="Open Event Feed"
          secondaryActionDescription="Review the broader SEC event stream if the pack points to a filing that needs more context."
          statusLines={[
            `Overall risk: ${summary ? titleCase(summary.overall_risk_level) : "Pending"}`,
            `As of: ${formatDate(riskData?.as_of ?? requestedAsOf)}`,
            `Debt due in 24 months: ${formatCompactCurrency(summary?.debt_due_next_twenty_four_months)}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Equity Claim Risk Pack"
        companyName={company?.name ?? riskData?.company?.name ?? ticker}
        sector={company?.sector ?? riskData?.company?.sector ?? null}
        description="SEC-derived underwriting workspace covering dilution, shelf capacity, ATM dependence, hybrid securities, debt wall pressure, covenant language, and reporting-control risk."
        freshness={{
          cacheState: company?.cache_state ?? riskData?.company?.cache_state ?? null,
          refreshState: effectiveRefreshState,
          loading: riskLoading || workspaceLoading,
          hasData: Boolean(company || riskData?.company || summary || shareCountBridge?.evidence.length),
          lastChecked: company?.last_checked ?? riskData?.company?.last_checked ?? null,
          errors: [riskError],
          detailLines: [
            `Overall risk: ${summary ? titleCase(summary.overall_risk_level) : "Pending"}`,
            `Dilution risk: ${summary ? titleCase(summary.dilution_risk_level) : "Pending"}`,
            `Financing risk: ${summary ? titleCase(summary.financing_risk_level) : "Pending"}`,
          ],
        }}
        freshnessPlacement="subtitle"
        factsLoading={(riskLoading || workspaceLoading) && !company && !riskData?.company && !summary}
        summariesLoading={(riskLoading || workspaceLoading) && !company && !riskData?.company && !summary}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "As Of", value: riskData?.as_of ? formatDate(riskData.as_of) : requestedAsOf ? formatDate(requestedAsOf) : "Latest" },
          { label: "Overall Risk", value: summary ? titleCase(summary.overall_risk_level) : "Pending" },
          { label: "Restatement Severity", value: summary ? titleCase(summary.restatement_severity) : "Pending" },
        ]}
        ribbonItems={[
          { label: "Dilution", value: summary ? titleCase(summary.dilution_risk_level) : "Pending", tone: toneForRiskLevel(summary?.dilution_risk_level) },
          { label: "Financing", value: summary ? titleCase(summary.financing_risk_level) : "Pending", tone: toneForRiskLevel(summary?.financing_risk_level) },
          { label: "Reporting", value: summary ? titleCase(summary.reporting_risk_level) : "Pending", tone: toneForRiskLevel(summary?.reporting_risk_level) },
          { label: "Sources", value: riskData?.source_mix?.official_only ? "Official + derived only" : "Derived + SEC source mix", tone: riskData?.source_mix?.official_only ? "green" : "gold" },
        ]}
        summaries={[
          { label: "Net Dilution", value: formatPercent(summary?.net_dilution_ratio), accent: toneForRiskLevel(summary?.dilution_risk_level) },
          { label: "Shelf Remaining", value: formatCompactCurrency(summary?.shelf_capacity_remaining), accent: "gold" },
          { label: "Debt Due 24M", value: formatCompactCurrency(summary?.debt_due_next_twenty_four_months), accent: toneForRiskLevel(summary?.financing_risk_level) },
          { label: "Internal Control Flags", value: summary ? String(summary.internal_control_flag_count) : "0", accent: toneForRiskLevel(summary?.reporting_risk_level) },
        ]}
      />

      <Panel title="Investor summary" subtitle="Compact underwriting conclusion built from the full SEC-derived pack.">
        {riskError ? (
          <div className="text-muted">{riskError}</div>
        ) : riskLoading && !summary ? (
          <div className="text-muted">Loading the equity claim risk summary...</div>
        ) : summary ? (
          <div className="workspace-card-stack">
            <div className="workspace-card-row">
              <div className="workspace-pill-row">
                <span className={`pill tone-${toneForRiskLevel(summary.overall_risk_level)}`}>Overall {titleCase(summary.overall_risk_level)}</span>
                <span className={`pill tone-${toneForRiskLevel(summary.dilution_risk_level)}`}>Dilution {titleCase(summary.dilution_risk_level)}</span>
                <span className={`pill tone-${toneForRiskLevel(summary.financing_risk_level)}`}>Financing {titleCase(summary.financing_risk_level)}</span>
                <span className={`pill tone-${toneForRiskLevel(summary.reporting_risk_level)}`}>Reporting {titleCase(summary.reporting_risk_level)}</span>
                {requestedAsOf ? <span className="pill">Requested as of {formatDate(requestedAsOf)}</span> : null}
              </div>
              <div className="text-muted">Latest period {formatDate(summary.latest_period_end)}</div>
            </div>
            <div className="workspace-card-title">{summary.headline || "The pack will summarize dilution and financing risk once cached inputs are available."}</div>
            <div className="text-muted workspace-card-copy">
              Net dilution {formatPercent(summary.net_dilution_ratio)} · SBC / revenue {formatPercent(summary.sbc_to_revenue)} · Shelf remaining {formatCompactCurrency(summary.shelf_capacity_remaining)} · Debt due in 24 months {formatCompactCurrency(summary.debt_due_next_twenty_four_months)} · Restatement severity {titleCase(summary.restatement_severity)}
            </div>
            {summary.key_points.length ? (
              <div className="workspace-card-stack">
                {summary.key_points.map((point) => (
                  <div key={point} className="text-muted workspace-card-copy">
                    {point}
                  </div>
                ))}
              </div>
            ) : null}
            <div className="workspace-card-row">
              <Link href={`/company/${encodeURIComponent(ticker)}`} className="workspace-card-link">
                Return to the default brief
              </Link>
              <Link href={`/company/${encodeURIComponent(ticker)}/events`} className="workspace-card-link">
                Review the event feed
              </Link>
            </div>
          </div>
        ) : (
          <div className="text-muted">No risk summary is available yet for this company.</div>
        )}
      </Panel>

      <DeferredClientSection placeholder={<div className="text-muted" style={{ minHeight: 260 }}>Loading share-count bridge...</div>}>
        <Panel title="Share-count bridge" subtitle="Opening shares, issuance, repurchases, and dilution direction anchored to persisted SEC filing history.">
        {riskError ? (
          <div className="text-muted">Unable to load the share-count bridge while the pack is unavailable.</div>
        ) : riskLoading && !shareCountBridge ? (
          <div className="text-muted">Loading the latest share-count bridge...</div>
        ) : shareCountBridge ? (
          <div className="workspace-card-stack">
            <CompanyMetricGrid
              items={[
                { label: "Opening Shares", value: formatCompactNumber(shareCountBridge.bridge.opening_shares) },
                { label: "Shares Issued", value: formatCompactNumber(shareCountBridge.bridge.shares_issued ?? shareCountBridge.bridge.shares_issued_proxy) },
                { label: "Shares Repurchased", value: formatCompactNumber(shareCountBridge.bridge.shares_repurchased) },
                { label: "Ending Shares", value: formatCompactNumber(shareCountBridge.bridge.ending_shares) },
                { label: "Net Share Change", value: formatCompactNumber(shareCountBridge.bridge.net_share_change) },
                { label: "Net Dilution", value: formatPercent(shareCountBridge.bridge.net_dilution_ratio) },
                { label: "WA Diluted Shares", value: formatCompactNumber(shareCountBridge.bridge.weighted_average_diluted_shares) },
                { label: "Bridge Period", value: formatDate(shareCountBridge.latest_period_end) },
              ]}
            />
            {financials.length ? (
              <div>
                <ShareDilutionTrackerChart financials={financials} />
              </div>
            ) : null}
            <RiskEvidenceList
              evidence={shareCountBridge.evidence}
              emptyMessage="No direct share-count bridge evidence is cached yet."
            />
          </div>
        ) : (
          <div className="text-muted">No share-count bridge is available yet.</div>
        )}
      </Panel>
      </DeferredClientSection>

      <DeferredClientSection placeholder={<div className="text-muted" style={{ minHeight: 260 }}>Loading financing capacity data...</div>}>
        <Panel title="Financing capacity and dependency" subtitle="Shelf remaining, ATM activity, negative free cash flow pressure, and near-term financing need.">
        {riskError ? (
          <div className="text-muted">Unable to load financing-capacity data while the pack is unavailable.</div>
        ) : riskLoading && !shelfRegistration && !atmDependency ? (
          <div className="text-muted">Loading financing capacity and dependency signals...</div>
        ) : shelfRegistration || atmDependency ? (
          <div className="workspace-card-stack">
            <CompanyMetricGrid
              items={[
                { label: "Shelf Status", value: shelfRegistration ? titleCase(shelfRegistration.status) : "Pending" },
                { label: "Latest Shelf", value: shelfRegistration?.latest_shelf_form ? `${shelfRegistration.latest_shelf_form} · ${formatDate(shelfRegistration.latest_shelf_filing_date)}` : "None" },
                { label: "Gross Capacity", value: formatCompactCurrency(shelfRegistration?.gross_capacity) },
                { label: "Utilized Capacity", value: formatCompactCurrency(shelfRegistration?.utilized_capacity) },
                { label: "Remaining Capacity", value: formatCompactCurrency(shelfRegistration?.remaining_capacity) },
                { label: "ATM Detected", value: atmDependency?.atm_detected ? "Yes" : "No" },
                { label: "ATM Filings", value: atmDependency ? String(atmDependency.recent_atm_filing_count) : "0" },
                { label: "Financing Dependency", value: atmDependency ? titleCase(atmDependency.financing_dependency_level) : "Pending" },
                { label: "Negative FCF", value: atmDependency?.negative_free_cash_flow ? "Yes" : "No" },
                { label: "Cash Runway", value: formatRunway(atmDependency?.cash_runway_years) },
                { label: "Debt Due 12M", value: formatCompactCurrency(atmDependency?.debt_due_next_twelve_months) },
                { label: "Latest ATM Filing", value: formatDate(atmDependency?.latest_atm_filing_date) },
              ]}
            />
            <RiskEvidenceList evidence={financingEvidence} emptyMessage="No direct financing-capacity evidence is cached yet." />
          </div>
        ) : (
          <div className="text-muted">No financing-capacity signals are available yet.</div>
        )}
      </Panel>
      </DeferredClientSection>

      <DeferredClientSection placeholder={<div className="text-muted" style={{ minHeight: 200 }}>Loading equity plan data...</div>}>
        <Panel title="Equity plan registrations (S-8)" subtitle="Employee equity plan registrations filed on Form S-8, showing plan names, registered shares, and parse confidence.">
        {capitalMarketsLoading && equityPlanFilings.length === 0 ? (
          <div className="text-muted">Loading equity plan registration filings...</div>
        ) : equityPlanFilings.length > 0 ? (
          <div className="workspace-card-stack">
            <CompanyMetricGrid
              items={[
                { label: "S-8 Filings", value: String(equityPlanFilings.length) },
                {
                  label: "Total Registered Shares",
                  value: formatCompactNumber(
                    equityPlanFilings.reduce((sum, f) => sum + (f.registered_shares ?? 0), 0) || null
                  ),
                },
                { label: "Latest S-8", value: formatDate(equityPlanFilings[0]?.filing_date) },
              ]}
            />
            <div className="workspace-card-stack">
              {equityPlanFilings.map((filing) => (
                <EquityPlanFilingCard key={filing.accession_number ?? `${filing.form}-${filing.filing_date}`} filing={filing} />
              ))}
            </div>
          </div>
        ) : (
          <div className="text-muted">No S-8 equity plan registrations are cached for this company yet.</div>
        )}
      </Panel>
      </DeferredClientSection>

      <DeferredClientSection placeholder={<div className="text-muted" style={{ minHeight: 260 }}>Loading hybrid securities data...</div>}>
        <Panel title="Hybrid securities and debt maturity wall" subtitle="Warrants, convertibles, and the amount of debt that needs attention in the next two years.">
        {riskError ? (
          <div className="text-muted">Unable to load hybrid-security or debt-wall signals while the pack is unavailable.</div>
        ) : riskLoading && !hybridSecurities && !debtMaturityWall ? (
          <div className="text-muted">Loading hybrid-security and debt-wall signals...</div>
        ) : hybridSecurities || debtMaturityWall ? (
          <div className="workspace-card-stack">
            <CompanyMetricGrid
              items={[
                { label: "Warrant Filings", value: hybridSecurities ? String(hybridSecurities.warrant_filing_count) : "0" },
                { label: "Convertible Filings", value: hybridSecurities ? String(hybridSecurities.convertible_filing_count) : "0" },
                { label: "Latest Hybrid Filing", value: formatDate(hybridSecurities?.latest_security_filing_date) },
                { label: "Total Debt", value: formatCompactCurrency(debtMaturityWall?.total_debt) },
                { label: "Debt Due 12M", value: formatCompactCurrency(debtMaturityWall?.debt_due_next_twelve_months) },
                { label: "Debt Due Year 2", value: formatCompactCurrency(debtMaturityWall?.debt_due_year_two) },
                { label: "Debt Due 24M", value: formatCompactCurrency(debtMaturityWall?.debt_due_next_twenty_four_months) },
                { label: "Debt Due / Total Debt", value: formatPercent(debtMaturityWall?.debt_due_next_twenty_four_months_ratio) },
                { label: "Interest Coverage Proxy", value: formatCoverage(debtMaturityWall?.interest_coverage_proxy) },
                { label: "Latest Debt Change", value: formatCompactNumber(latestFinancial?.debt_changes) },
              ]}
            />
            <RiskEvidenceList evidence={hybridAndDebtEvidence} emptyMessage="No hybrid-security or debt-wall evidence is cached yet." />
          </div>
        ) : (
          <div className="text-muted">No hybrid-security or debt-wall signals are available yet.</div>
        )}
      </Panel>
      </DeferredClientSection>

      <DeferredClientSection placeholder={<div className="text-muted" style={{ minHeight: 260 }}>Loading covenant signals...</div>}>
        <Panel title="Covenant, restatement, and control signals" subtitle="Keyword-backed covenant stress cues plus restatement severity and internal-control flags where identifiable.">
        {riskError ? (
          <div className="text-muted">Unable to load covenant or reporting-control signals while the pack is unavailable.</div>
        ) : riskLoading && !covenantSignals && !reportingControls ? (
          <div className="text-muted">Loading covenant and reporting-control signals...</div>
        ) : covenantSignals || reportingControls ? (
          <div className="workspace-card-stack">
            <CompanyMetricGrid
              items={[
                { label: "Covenant Signal Level", value: covenantSignals ? titleCase(covenantSignals.level) : "Pending" },
                { label: "Covenant Matches", value: covenantSignals ? String(covenantSignals.match_count) : "0" },
                { label: "Matched Terms", value: covenantSignals?.matched_terms.length ? covenantSignals.matched_terms.join(", ") : "None" },
                { label: "Restatement Count", value: reportingControls ? String(reportingControls.restatement_count) : "0" },
                { label: "Restatement Severity", value: reportingControls ? titleCase(reportingControls.restatement_severity) : "Pending" },
                { label: "High-Impact Restatements", value: reportingControls ? String(reportingControls.high_impact_restatements) : "0" },
                { label: "Latest Restatement", value: formatDate(reportingControls?.latest_restatement_date) },
                { label: "Internal Control Flags", value: reportingControls ? String(reportingControls.internal_control_flag_count) : "0" },
                { label: "Control Terms", value: reportingControls?.internal_control_terms.length ? reportingControls.internal_control_terms.join(", ") : "None" },
              ]}
            />
            <RiskEvidenceList evidence={covenantAndReportingEvidence} emptyMessage="No covenant or reporting-control evidence is cached yet." />
          </div>
        ) : (
          <div className="text-muted">No covenant or reporting-control signals are available yet.</div>
        )}
      </Panel>
      </DeferredClientSection>

      <DeferredClientSection placeholder={<div className="text-muted" style={{ minHeight: 200 }}>Loading provenance data...</div>}>
        <Panel title="Provenance and diagnostics" subtitle="Source mix, refresh state, and any missing inputs that can weaken the underwriting read.">
        {riskError ? (
          <div className="text-muted">The pack failed before provenance and diagnostic details could be displayed.</div>
        ) : riskLoading && !riskData ? (
          <div className="text-muted">Loading provenance and diagnostic details...</div>
        ) : riskData ? (
          <div className="workspace-card-stack">
            <div className="workspace-card-row">
              <div className="workspace-pill-row">
                <span className={`pill tone-${riskData.source_mix.official_only ? "green" : "gold"}`}>
                  {riskData.source_mix.official_only ? "Official / derived only" : "SEC + derived source mix"}
                </span>
                {riskData.refresh.job_id ? <span className="pill">Refresh queued</span> : null}
                {riskData.as_of ? <span className="pill">As of {formatDate(riskData.as_of)}</span> : null}
              </div>
              <div className="text-muted">Last refreshed {formatDateTime(riskData.last_refreshed_at)}</div>
            </div>

            {confidenceFlags.length ? (
              <div className="workspace-card-copy text-muted">Confidence flags: {confidenceFlags.join(", ")}</div>
            ) : null}

            {diagnostics?.missing_field_flags.length ? (
              <div className="workspace-card-copy text-muted">Missing inputs: {diagnostics.missing_field_flags.join(", ")}</div>
            ) : null}

            {provenance.length ? (
              <div className="workspace-card-stack">
                {provenance.map((entry) => (
                  <a
                    key={`${entry.source_id}-${entry.role}`}
                    href={entry.url}
                    target="_blank"
                    rel="noreferrer"
                    className="filing-link-card workspace-card-link"
                  >
                    <div className="workspace-card-row">
                      <div className="workspace-pill-row">
                        <span className="pill">{entry.display_label}</span>
                        <span className="pill">{titleCase(entry.role)}</span>
                      </div>
                      <div className="text-muted">{entry.as_of ? formatDate(entry.as_of) : "As of pending"}</div>
                    </div>
                    <div className="workspace-card-title">{entry.disclosure_note}</div>
                    <div className="text-muted workspace-card-copy">
                      Source ID: {entry.source_id} · Tier: {titleCase(entry.source_tier.replace(/_/g, " "))}
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-muted">No provenance records are available yet.</div>
            )}
          </div>
        ) : (
          <div className="text-muted">No provenance or diagnostic detail is available yet.</div>
        )}
      </Panel>
      </DeferredClientSection>
    </CompanyWorkspaceShell>
  );
}

function RiskEvidenceList({
  evidence,
  emptyMessage,
}: {
  evidence: EquityClaimRiskEvidencePayload[];
  emptyMessage: string;
}) {
  if (!evidence.length) {
    return <div className="text-muted">{emptyMessage}</div>;
  }

  return (
    <div className="workspace-card-stack">
      {evidence.map((item) => {
        const key = item.accession_number ?? `${item.category}-${item.title}-${item.filing_date ?? "pending"}`;

        if (item.source_url) {
          return (
            <a
              key={key}
              href={item.source_url}
              target="_blank"
              rel="noreferrer"
              className="filing-link-card workspace-card-link"
              title={`${item.title} evidence`}
            >
              <EvidenceCardBody item={item} />
            </a>
          );
        }

        return (
          <div key={key} className="filing-link-card">
            <EvidenceCardBody item={item} />
          </div>
        );
      })}
    </div>
  );
}

function EvidenceCardBody({ item }: { item: EquityClaimRiskEvidencePayload }) {
  return (
    <>
      <div className="workspace-card-row">
        <div className="workspace-pill-row">
          <span className="pill">{titleCase(item.category.replace(/_/g, " "))}</span>
          {item.form ? <span className="pill">{item.form}</span> : null}
          <span className="pill">{item.source_id}</span>
        </div>
        <div className="text-muted">{formatDate(item.filing_date)}</div>
      </div>
      <div className="workspace-card-title">{item.title}</div>
      <div className="text-muted workspace-card-copy">{item.detail}</div>
      {item.accession_number ? <div className="text-muted workspace-card-copy">{item.accession_number}</div> : null}
    </>
  );
}

function EquityPlanFilingCard({ filing }: { filing: CapitalRaisePayload }) {
  const confidence = filing.shares_parse_confidence;
  const confidenceTone = confidence === "high" ? "green" : confidence === "medium" ? "gold" : "red";

  const content = (
    <>
      <div className="workspace-card-row">
        <div className="workspace-pill-row">
          <span className="pill">{filing.form}</span>
          {filing.plan_name ? <span className="pill">{filing.plan_name}</span> : null}
          {confidence ? (
            <span className={`pill tone-${confidenceTone}`}>{confidence} confidence</span>
          ) : null}
        </div>
        <div className="text-muted">{formatDate(filing.filing_date)}</div>
      </div>
      <div className="workspace-card-title">{filing.summary}</div>
      <div className="text-muted workspace-card-copy">
        {filing.registered_shares != null
          ? `Registered shares: ${formatCompactNumber(filing.registered_shares)}`
          : "Registered shares: not parsed"}
        {filing.accession_number ? ` · ${filing.accession_number}` : ""}
      </div>
    </>
  );

  return filing.source_url ? (
    <a href={filing.source_url} target="_blank" rel="noreferrer" className="filing-link-card workspace-card-link">
      {content}
    </a>
  ) : (
    <div className="filing-link-card">{content}</div>
  );
}

function toneForRiskLevel(level: "low" | "medium" | "high" | undefined): "green" | "gold" | "red" | "cyan" {
  switch (level) {
    case "high":
      return "red";
    case "medium":
      return "gold";
    case "low":
      return "green";
    default:
      return "cyan";
  }
}

function formatCompactCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  return `$${formatCompactNumber(value)}`;
}

function formatRunway(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  return `${value.toFixed(1)} years`;
}

function formatCoverage(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }

  return `${value.toFixed(2)}x`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(date);
}
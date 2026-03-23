"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { InstitutionalOwnershipTrendChart } from "@/components/charts/institutional-ownership-trend-chart";
import { SmartMoneyFlowChart } from "@/components/charts/smart-money-flow-chart";
import { NewVsExitedPositions } from "@/components/institutional/new-vs-exited-positions";
import { ConvictionHeatmap } from "@/components/institutional/conviction-heatmap";
import { SmartMoneySummary } from "@/components/institutional/smart-money-summary";
import { TopHolderTrend } from "@/components/institutional/top-holder-trend";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { HedgeFundActivityTable } from "@/components/tables/hedge-fund-activity-table";
import { Panel } from "@/components/ui/panel";
import { PlainEnglishScorecard } from "@/components/ui/plain-english-scorecard";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyInstitutionalHoldings, getCompanyInstitutionalHoldingsSummary } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { buildSmartMoneySummary } from "@/lib/smart-money";
import type { CompanyInstitutionalHoldingsResponse, CompanyInstitutionalHoldingsSummaryResponse } from "@/lib/types";

const OWNERSHIP_POLL_INTERVAL_MS = 3000;

export default function CompanyOwnershipPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    financials,
    institutionalData,
    institutionalHoldings: workspaceInstitutionalHoldings,
    institutionalError,
    loading,
    refreshing,
    refreshState,
    activeJobId,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker, { includeInstitutional: true });
  const [liveInstitutionalData, setLiveInstitutionalData] = useState<CompanyInstitutionalHoldingsResponse | null>(null);
  const [summaryData, setSummaryData] = useState<CompanyInstitutionalHoldingsSummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const institutionalHoldings = liveInstitutionalData?.institutional_holdings ?? workspaceInstitutionalHoldings;
  const ownershipRefreshState = liveInstitutionalData?.refresh ?? summaryData?.refresh ?? refreshState;
  const latestReportingDate = useMemo(
    () =>
      institutionalHoldings.reduce<string | null>(
        (latest, row) => (!latest || row.reporting_date > latest ? row.reporting_date : latest),
        null
      ),
    [institutionalHoldings]
  );
  const summary = summaryData?.summary ?? null;
  const smartMoney = useMemo(() => buildSmartMoneySummary(institutionalHoldings), [institutionalHoldings]);
  const investorScorecard = useMemo(
    () =>
      buildOwnershipScorecard({
        totalRows: summary?.total_rows ?? institutionalHoldings.length,
        uniqueManagers: summary?.unique_managers ?? 0,
        amendedRows: summary?.amended_rows ?? 0,
        latestQuarter: summary?.latest_reporting_date ?? latestReportingDate,
        smartMoney
      }),
    [institutionalHoldings.length, latestReportingDate, smartMoney, summary?.amended_rows, summary?.latest_reporting_date, summary?.total_rows, summary?.unique_managers]
  );

  useEffect(() => {
    if (!institutionalData) {
      return;
    }

    setLiveInstitutionalData(institutionalData);
  }, [institutionalData]);

  useEffect(() => {
    let cancelled = false;

    async function loadSummary() {
      try {
        setSummaryError(null);
        const response = await getCompanyInstitutionalHoldingsSummary(ticker);
        if (!cancelled) {
          setSummaryData(response);
        }
      } catch (error) {
        if (!cancelled) {
          setSummaryError(error instanceof Error ? error.message : "Unable to load institutional summary");
          setSummaryData(null);
        }
      }
    }

    void loadSummary();
    return () => {
      cancelled = true;
    };
  }, [ticker, reloadKey]);

  useEffect(() => {
    const trackedJobId = activeJobId ?? ownershipRefreshState?.job_id;
    if (!trackedJobId) {
      return;
    }

    let cancelled = false;
    let intervalId: number | null = null;

    const pollOwnership = async () => {
      try {
        const [holdingsResponse, summaryResponse] = await Promise.all([
          getCompanyInstitutionalHoldings(ticker),
          getCompanyInstitutionalHoldingsSummary(ticker)
        ]);

        if (cancelled) {
          return;
        }

        setLiveInstitutionalData(holdingsResponse);
        setSummaryData(summaryResponse);
        setSummaryError(null);

        const hasHoldings = holdingsResponse.institutional_holdings.length > 0;
        const refreshComplete = !holdingsResponse.refresh.job_id && !summaryResponse.refresh.job_id;
        if ((hasHoldings || refreshComplete) && intervalId !== null) {
          window.clearInterval(intervalId);
          intervalId = null;
        }
      } catch (error) {
        if (!cancelled) {
          setSummaryError(error instanceof Error ? error.message : "Unable to refresh institutional summary");
        }
      }
    };

    void pollOwnership();
    intervalId = window.setInterval(() => {
      void pollOwnership();
    }, OWNERSHIP_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
    };
  }, [activeJobId, ownershipRefreshState?.job_id, ticker]);

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? null}
          sector={company?.sector ?? null}
          refreshState={ownershipRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh(true)}
          actionTitle="Next Steps"
          actionSubtitle="Refresh the latest ownership data or jump into valuation models."
          primaryActionLabel="Refresh Ownership Data"
          primaryActionDescription="Updates institutional holdings, filing history, and ownership summaries in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="View DCF, health score, scenario analysis, and model outputs."
          statusLines={[
            `Tracked holdings available: ${(summary?.total_rows ?? institutionalHoldings.length).toLocaleString()}`,
            `Latest filing quarter: ${summary?.latest_reporting_date ? formatDate(summary.latest_reporting_date) : latestReportingDate ? formatDate(latestReportingDate) : "Pending"}`,
            `Unique managers: ${(summary?.unique_managers ?? 0).toLocaleString()} · Amended filings: ${(summary?.amended_rows ?? 0).toLocaleString()}`,
            `Financial periods available: ${financials.length.toLocaleString()}`
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <Panel title="Ownership" subtitle={company?.name ?? ticker} aside={ownershipRefreshState ? <StatusPill state={ownershipRefreshState} /> : undefined}>
        <div className="metric-grid">
          <Metric label="Ticker" value={ticker} />
          <Metric label="Tracked Holdings" value={(summary?.total_rows ?? institutionalHoldings.length).toLocaleString()} />
          <Metric label="Unique Managers" value={(summary?.unique_managers ?? 0).toLocaleString()} />
          <Metric label="Amended Filings" value={(summary?.amended_rows ?? 0).toLocaleString()} />
          <Metric label="Latest Quarter" value={summary?.latest_reporting_date ? formatDate(summary.latest_reporting_date) : latestReportingDate ? formatDate(latestReportingDate) : "Pending"} />
          <Metric label="Last Checked" value={company?.last_checked ? formatDate(company.last_checked) : null} />
        </div>
        {summaryError ? <div className="text-muted">{summaryError}</div> : null}
        {!loading && !summaryError && institutionalHoldings.length === 0 ? (
          <div className="text-muted" style={{ marginTop: 12 }}>
            No institutional holdings are cached yet for this ticker. Trigger a refresh to pull the latest 13F coverage.
          </div>
        ) : null}
      </Panel>

      <Panel title="Plain-English Scorecard" subtitle="Simple read on whether institutional holders are adding, trimming, or staying mixed">
        <PlainEnglishScorecard
          title="Ownership Dashboard Scorecard"
          label={investorScorecard.label}
          tone={investorScorecard.tone}
          summary={investorScorecard.summary}
          explanation={investorScorecard.explanation}
          chips={investorScorecard.chips}
        />
      </Panel>

      <Panel title="Smart Money Summary" subtitle="Quarter-over-quarter view of institutional positioning from 13F filings">
        <SmartMoneySummary
          holdings={institutionalHoldings}
          loading={loading && institutionalData === null}
          error={institutionalError}
          refresh={ownershipRefreshState}
        />
      </Panel>

      <Panel title="Institutional Ownership Trend" subtitle="Quarterly tracked shares, top 10 funds combined, and tracked ownership percentage">
        <InstitutionalOwnershipTrendChart holdings={institutionalHoldings} financials={financials} />
      </Panel>

      <Panel title="Top Holder Trend" subtitle="Latest top tracked funds and how their reported share counts moved across quarters">
        <TopHolderTrend holdings={institutionalHoldings} />
      </Panel>

      <Panel title="New vs Exited Positions" subtitle="How the latest quarter compares with the prior quarter across tracked 13F funds">
        <NewVsExitedPositions holdings={institutionalHoldings} />
      </Panel>

      <Panel title="Conviction Heatmap" subtitle="Latest tracked funds ranked by position weight and quarter-over-quarter position change">
        <ConvictionHeatmap holdings={institutionalHoldings} />
      </Panel>

      <Panel title="Smart Money Flow" subtitle="Quarterly buying, selling, and net institutional flow from 13F filings">
        <SmartMoneyFlowChart holdings={institutionalHoldings} loading={loading && institutionalData === null} error={institutionalError} refresh={ownershipRefreshState} />
      </Panel>

      <Panel title="Hedge Fund Activity" subtitle="Sortable holdings table with share changes, portfolio weights, and quarter labels">
        <HedgeFundActivityTable ticker={ticker} holdings={institutionalHoldings} loading={loading && institutionalData === null} error={institutionalError} refresh={ownershipRefreshState} />
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

function buildOwnershipScorecard({
  totalRows,
  uniqueManagers,
  amendedRows,
  latestQuarter,
  smartMoney
}: {
  totalRows: number;
  uniqueManagers: number;
  amendedRows: number;
  latestQuarter: string | null;
  smartMoney: ReturnType<typeof buildSmartMoneySummary>;
}) {
  if (!smartMoney) {
    return {
      label: "Coverage pending",
      tone: "low" as const,
      summary: "There is not enough quarter-over-quarter 13F data here to form a clean institutional signal yet.",
      explanation: "As more reporting periods are cached, this page will become better at showing whether funds are building or trimming positions.",
      chips: [`${totalRows.toLocaleString()} tracked rows`, `${uniqueManagers.toLocaleString()} managers`]
    };
  }

  if (smartMoney.sentiment === "bullish") {
    return {
      label: "Accumulation signal",
      tone: "bullish" as const,
      summary: "Institutional holders are leaning toward adding exposure.",
      explanation: "More funds are increasing positions than cutting them, and the net dollar flow is positive. That usually means professional investors are getting more comfortable owning the stock.",
      chips: [
        `${smartMoney.fund_increasing} funds adding`,
        `${smartMoney.fund_decreasing} trimming`,
        `${amendedRows.toLocaleString()} amended filings`,
        latestQuarter ? `latest quarter ${formatDate(latestQuarter)}` : "latest quarter pending"
      ]
    };
  }

  if (smartMoney.sentiment === "bearish") {
    return {
      label: "Distribution signal",
      tone: "bearish" as const,
      summary: "Institutional holders are leaning toward trimming exposure.",
      explanation: "More funds are reducing positions than adding, and the net dollar flow is negative. That can signal weaker conviction or risk reduction by professional investors.",
      chips: [
        `${smartMoney.fund_increasing} funds adding`,
        `${smartMoney.fund_decreasing} trimming`,
        `${uniqueManagers.toLocaleString()} managers`,
        latestQuarter ? `latest quarter ${formatDate(latestQuarter)}` : "latest quarter pending"
      ]
    };
  }

  return {
    label: "Mixed positioning",
    tone: "neutral" as const,
    summary: "Institutional ownership looks active, but not clearly one-sided.",
    explanation: "Funds are trading the name, but the available 13F changes do not point to a strong accumulation or distribution trend right now.",
    chips: [
      `${smartMoney.fund_increasing} funds adding`,
      `${smartMoney.fund_decreasing} trimming`,
      `${totalRows.toLocaleString()} tracked rows`,
      latestQuarter ? `latest quarter ${formatDate(latestQuarter)}` : "latest quarter pending"
    ]
  };
}

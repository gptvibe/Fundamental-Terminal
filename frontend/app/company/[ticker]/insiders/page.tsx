"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { InsiderActivityTrendChart } from "@/components/charts/insider-activity-trend-chart";
import { InsiderRoleActivityChart } from "@/components/charts/insider-role-activity-chart";
import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { InsiderActivitySummary } from "@/components/insiders/insider-activity-summary";
import { InsiderSignalBreakdown } from "@/components/insiders/insider-signal-breakdown";
import { Form144FilingsTable } from "@/components/tables/form144-filings-table";
import { InsiderTransactionsTable } from "@/components/tables/insider-transactions-table";
import { Panel } from "@/components/ui/panel";
import { PlainEnglishScorecard } from "@/components/ui/plain-english-scorecard";
import { StatusPill } from "@/components/ui/status-pill";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { getCompanyForm144Filings } from "@/lib/api";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { CompanyForm144Response, InsiderActivitySummaryPayload } from "@/lib/types";

export default function CompanyInsidersPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    company,
    insiderData,
    insiderTrades,
    insiderError,
    loading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker, { includeInsiders: true });

  const [form144Data, setForm144Data] = useState<CompanyForm144Response | null>(null);
  const [form144Loading, setForm144Loading] = useState(true);
  const [form144Error, setForm144Error] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setForm144Loading(true);
    setForm144Error(null);
    getCompanyForm144Filings(ticker)
      .then((result) => { if (!cancelled) { setForm144Data(result); } })
      .catch((err: unknown) => { if (!cancelled) { setForm144Error(err instanceof Error ? err.message : "Unable to load Form 144 filings"); } })
      .finally(() => { if (!cancelled) setForm144Loading(false); });
    return () => { cancelled = true; };
  }, [ticker, reloadKey]);
  const latestTradeDate = useMemo(
    () => insiderTrades.reduce<string | null>((latest, row) => (!row.date || (latest && row.date <= latest) ? latest : row.date), null),
    [insiderTrades]
  );
  const investorScorecard = useMemo(
    () => buildInsiderScorecard(insiderData?.summary ?? null, insiderTrades.length, latestTradeDate),
    [insiderData?.summary, insiderTrades.length, latestTradeDate]
  );
  const insiderSummaryMetrics = insiderData?.summary?.metrics ?? null;
  const form144Count = form144Data?.filings.length ?? 0;
  const latestForm144Date = form144Data?.filings[0]?.filing_date ?? form144Data?.filings[0]?.planned_sale_date ?? null;
  const effectiveRefreshState = form144Data?.refresh ?? insiderData?.refresh ?? refreshState;

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? null}
          sector={company?.sector ?? null}
          refreshState={effectiveRefreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle="Refresh the latest insider activity or jump into valuation models."
          primaryActionLabel="Refresh Insider Data"
          primaryActionDescription="Updates Form 4 filings, insider activity, and transaction summaries in the background."
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/models`}
          secondaryActionLabel="Open Valuation Models"
          secondaryActionDescription="View DCF, health score, scenario analysis, and model outputs."
          statusLines={[
            `Insider trades available: ${insiderTrades.length.toLocaleString()}`,
            `Latest filing date: ${latestTradeDate ? formatDate(latestTradeDate) : "Pending"}`,
            "Open-market activity only; updates appear here automatically in the background."
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Insiders"
        companyName={company?.name ?? ticker}
        sector={company?.sector ?? null}
        cacheState={company?.cache_state ?? null}
        description="SEC-first insider workspace with open-market Form 4 activity and Form 144 planned sales kept current through background refreshes."
        aside={effectiveRefreshState ? <StatusPill state={effectiveRefreshState} /> : undefined}
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Cached Trades", value: insiderTrades.length.toLocaleString() },
          { label: "Latest Filing", value: latestTradeDate ? formatDate(latestTradeDate) : "Pending" },
          { label: "Form 144 Filings", value: form144Count.toLocaleString() },
        ]}
        ribbonItems={[
          { label: "Insiders", value: company?.last_checked_insiders ? formatDate(company.last_checked_insiders) : company?.last_checked ? formatDate(company.last_checked) : "Pending", tone: "green" },
          { label: "Form 144", value: latestForm144Date ? formatDate(latestForm144Date) : "Pending", tone: "gold" },
          { label: "Sources", value: "SEC Form 4 + Form 144 filings", tone: "cyan" },
          { label: "Refresh", value: effectiveRefreshState?.job_id ? "Queued" : "Background-first", tone: effectiveRefreshState?.job_id ? "cyan" : "green" },
        ]}
        summaries={[
          { label: "Buys", value: formatCompactNumber(insiderSummaryMetrics?.total_buy_value), accent: "green" },
          { label: "Sells", value: formatCompactNumber(insiderSummaryMetrics?.total_sell_value), accent: "red" },
          { label: "Net Value", value: formatCompactNumber(insiderSummaryMetrics?.net_value), accent: "cyan" },
          { label: "Planned Sales", value: form144Count.toLocaleString(), accent: "gold" },
        ]}
      />

      <Panel title="Plain-English Scorecard" subtitle="Simple read on whether insiders are buying, selling, or sending a mixed signal">
        <PlainEnglishScorecard
          title="Insider Activity Scorecard"
          label={investorScorecard.label}
          tone={investorScorecard.tone}
          summary={investorScorecard.summary}
          explanation={investorScorecard.explanation}
          chips={investorScorecard.chips}
        />
      </Panel>

      <Panel title="Insider Activity (Last 12 Months)" subtitle="Summary of Form 4 open-market buying and selling signals">
        <InsiderActivitySummary summary={insiderData?.summary ?? null} loading={loading && insiderData === null} error={insiderError} refresh={insiderData?.refresh ?? null} />
      </Panel>

      <Panel title="Insider Activity Trend" subtitle="Monthly insider buys, sells, and net activity from Form 4 filings">
        <InsiderActivityTrendChart trades={insiderTrades} />
      </Panel>

      <Panel title="Signal Quality" subtitle="Separate higher-signal open-market trades from plan-driven or administrative Form 4 entries">
        <InsiderSignalBreakdown trades={insiderTrades} />
      </Panel>

      <Panel title="Role Activity" subtitle="Open-market buy, sell, and net value split by insider role">
        <InsiderRoleActivityChart trades={insiderTrades} />
      </Panel>

      <Panel title="Insider Transactions" subtitle="Sortable Form 4 activity with buy, sell, and 10b5-1 details">
        <InsiderTransactionsTable ticker={ticker} trades={insiderTrades} loading={loading && insiderData === null} error={insiderError} refresh={insiderData?.refresh ?? null} />
      </Panel>

      <Panel title="Form 144 Planned Sales" subtitle="Planned insider dispositions of restricted or control securities filed before sale">
        <Form144FilingsTable ticker={ticker} filings={form144Data?.filings ?? []} loading={form144Loading && form144Data === null} error={form144Error} refresh={form144Data?.refresh ?? null} />
      </Panel>
    </CompanyWorkspaceShell>
  );
}

function buildInsiderScorecard(summary: InsiderActivitySummaryPayload | null, tradeCount: number, latestTradeDate: string | null) {
  if (!summary) {
    return {
      label: "Coverage pending",
      tone: "low" as const,
      summary: "There is not enough recent open-market Form 4 data here to form a clean insider signal yet.",
      explanation: "This page ignores grants and other lower-signal transactions, so it can stay empty until meaningful insider trades are cached.",
      chips: [`${tradeCount.toLocaleString()} cached trades`, latestTradeDate ? `latest filing ${formatDate(latestTradeDate)}` : "latest filing pending"]
    };
  }

  if (summary.sentiment === "bullish") {
    return {
      label: "Net insider buying",
      tone: "bullish" as const,
      summary: "Insiders are buying more than they are selling in the open market.",
      explanation: "That can be a constructive signal because executives and directors are putting personal capital to work rather than just receiving compensation stock.",
      chips: [
        `${summary.metrics.unique_insiders_buying} buyers`,
        `${summary.metrics.unique_insiders_selling} sellers`,
        `${tradeCount.toLocaleString()} cached trades`,
        latestTradeDate ? `latest filing ${formatDate(latestTradeDate)}` : "latest filing pending"
      ]
    };
  }

  if (summary.sentiment === "bearish") {
    return {
      label: "Net insider selling",
      tone: "bearish" as const,
      summary: "Insiders are selling more than they are buying in the open market.",
      explanation: "Selling is not always a red flag, but broad or repeated insider selling can mean management sees less near-term upside or is reducing risk.",
      chips: [
        `${summary.metrics.unique_insiders_buying} buyers`,
        `${summary.metrics.unique_insiders_selling} sellers`,
        `${tradeCount.toLocaleString()} cached trades`,
        latestTradeDate ? `latest filing ${formatDate(latestTradeDate)}` : "latest filing pending"
      ]
    };
  }

  return {
    label: "Mixed insider signal",
    tone: "neutral" as const,
    summary: "Insider trading activity is present, but it does not point clearly in one direction.",
    explanation: "There may be both buyers and sellers, or the dollar amounts are close enough that the signal should be treated as inconclusive rather than bullish or bearish.",
    chips: [
      `${summary.metrics.unique_insiders_buying} buyers`,
      `${summary.metrics.unique_insiders_selling} sellers`,
      `${tradeCount.toLocaleString()} cached trades`,
      latestTradeDate ? `latest filing ${formatDate(latestTradeDate)}` : "latest filing pending"
    ]
  };
}

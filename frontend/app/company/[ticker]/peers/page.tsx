"use client";

import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

import { CompanyResearchHeader } from "@/components/layout/company-research-header";
import { CompanyUtilityRail } from "@/components/layout/company-utility-rail";
import { CompanyWorkspaceShell } from "@/components/layout/company-workspace-shell";
import { CommercialFallbackNotice } from "@/components/ui/commercial-fallback-notice";
import { useCompanyWorkspace } from "@/hooks/use-company-workspace";
import { formatDate } from "@/lib/format";

const PeerComparisonDashboard = dynamic(
  () => import("@/components/peers/peer-comparison-dashboard").then((module) => module.PeerComparisonDashboard),
  { ssr: false, loading: () => <div className="text-muted">Loading peer comparison...</div> }
);

export default function CompanyPeersPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = decodeURIComponent(params.ticker).toUpperCase();
  const {
    data,
    company,
    financials,
    loading,
    refreshing,
    refreshState,
    consoleEntries,
    connectionState,
    queueRefresh,
    reloadKey
  } = useCompanyWorkspace(ticker);
  const strictOfficialMode = Boolean(company?.strict_official_mode);

  return (
    <CompanyWorkspaceShell
      rail={
        <CompanyUtilityRail
          ticker={ticker}
          companyName={company?.name ?? null}
          sector={company?.sector ?? null}
          refreshState={refreshState}
          refreshing={refreshing}
          onRefresh={() => queueRefresh()}
          actionTitle="Next Steps"
          actionSubtitle={
            strictOfficialMode
              ? "Refresh this company for official-source filings and SEC SIC classification updates."
              : "Refresh this company, then compare valuation and quality against close peers."
          }
          primaryActionLabel="Refresh Peer Data"
          primaryActionDescription={
            strictOfficialMode
              ? "Updates cached filings and official company classification metadata used by peer selection."
              : "Updates cached filings, prices, and model metrics used by peer comparison panels."
          }
          secondaryActionHref={`/company/${encodeURIComponent(ticker)}/financials`}
          secondaryActionLabel="Open Financials"
          secondaryActionDescription="Review statement context behind peer valuation, margin, and quality differences."
          statusLines={[
            `Financial statements available: ${financials.length.toLocaleString()}`,
            `Selection model: focus company plus up to 4 peers`,
            company?.last_checked ? `Last checked: ${formatDate(company.last_checked)}` : "Last checked: pending"
          ]}
          consoleEntries={consoleEntries}
          connectionState={connectionState}
        />
      }
      mainClassName="company-page-grid"
    >
      <CompanyResearchHeader
        ticker={ticker}
        title="Peers"
        companyName={company?.name ?? ticker}
        sector={company?.sector}
        description={
          strictOfficialMode
            ? "Peer matching stays official-only in strict mode, using SEC SIC classification while price-dependent comparison charts remain disabled."
            : "Compare valuation, quality, and growth against a cached peer set without blocking the page on live vendor fetches."
        }
        freshness={{
          cacheState: company?.cache_state ?? null,
          refreshState,
          loading,
          hasData: Boolean(company || financials.length),
          lastChecked: company?.last_checked ?? null,
          detailLines: [
            `Financial statements available: ${financials.length.toLocaleString()}`,
            "Selection model: focus company plus up to 4 peers",
            company?.last_checked ? `Last checked: ${formatDate(company.last_checked)}` : "Last checked: pending",
          ],
        }}
        freshnessPlacement="subtitle"
        facts={[
          { label: "Ticker", value: ticker },
          { label: "Sector", value: company?.sector ?? null },
          { label: "Peer Limit", value: "4 selected peers" },
          { label: "Last Checked", value: company?.last_checked ? formatDate(company.last_checked) : loading ? "Loading..." : null }
        ]}
        ribbonItems={[
          { label: "Financial Inputs", value: "SEC EDGAR/XBRL", tone: "green" },
          { label: "Market Profile", value: strictOfficialMode ? "SEC SIC mapping" : "Yahoo Finance", tone: strictOfficialMode ? "green" : "cyan" },
          { label: "Selection Model", value: "Focus company + cached peers", tone: "gold" },
          { label: "Refresh", value: refreshState?.job_id ? "Queued" : "Background-first", tone: refreshState?.job_id ? "cyan" : "green" }
        ]}
        summaries={[
          { label: "Statements", value: financials.length.toLocaleString(), accent: "cyan" },
          { label: "Peer Limit", value: "4 names", accent: "gold" },
          { label: "Source Policy", value: "Official/public only", accent: "green" },
          { label: "Last Checked", value: company?.last_checked ? formatDate(company.last_checked) : "Pending", accent: "cyan" }
        ]}
      >
        {!strictOfficialMode ? (
          <CommercialFallbackNotice
            provenance={data?.provenance}
            sourceMix={data?.source_mix}
            subject="Market profile and peer-comparison price inputs on this surface"
          />
        ) : null}
        {strictOfficialMode ? (
          <div className="text-muted" style={{ marginBottom: 12 }}>
            Strict official mode disables peer valuation charts because no official end-of-day equity price source is enabled. Classification still uses SEC SIC mappings.
          </div>
        ) : null}
      </CompanyResearchHeader>

      <PeerComparisonDashboard ticker={ticker} reloadKey={reloadKey} />
    </CompanyWorkspaceShell>
  );
}
/**
 * Investment Memo builder.
 *
 * Accepts pre-loaded, cached research-brief data and returns a sober
 * Markdown string suitable for offline reading or archival.  No live
 * network calls are made here.
 */

import { buildPlainTextTable } from "@/lib/export";
import { formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyActivityOverviewResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyCapitalMarketsSummaryResponse,
  CompanyCapitalStructureResponse,
  CompanyChangesSinceLastFilingResponse,
  CompanyEarningsSummaryResponse,
  CompanyGovernanceSummaryResponse,
  CompanyModelsResponse,
  CompanyPeersResponse,
  FilingTimelineItemPayload,
  FinancialPayload,
  ProvenanceEntryPayload,
  SourceMixPayload,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// Public input shape
// ---------------------------------------------------------------------------

export interface InvestmentMemoInput {
  ticker: string;
  exportedAt: string;

  // Company identity
  company: {
    ticker?: string | null;
    name?: string | null;
    cik?: string | null;
    sector?: string | null;
    market_sector?: string | null;
    market_industry?: string | null;
    last_checked?: string | null;
    cache_state?: string | null;
  } | null;

  // Freshness / provenance
  asOf: string | null;
  lastRefreshedAt: string | null;
  provenance: ProvenanceEntryPayload[] | null | undefined;
  sourceMix: SourceMixPayload | null | undefined;
  filingTimeline: FilingTimelineItemPayload[];

  // Financial data
  latestFinancial: FinancialPayload | null;
  annualStatementsCount: number;
  topSegment: FinancialPayload["segment_breakdown"][number] | null;

  // Pre-built narratives (already computed by the page layer)
  snapshotNarrative: string;
  whatChangedNarrative: string;
  businessQualityNarrative: string;
  capitalRiskNarrative: string;
  valuationNarrative: string;
  monitorNarrative: string;

  // Pre-built structured rows
  capitalSignalRows: Array<{ signal: string; currentRead: string; latestEvidence: string }>;
  monitorChecklist: Array<{ title: string; detail: string }>;

  // Section data
  changes: CompanyChangesSinceLastFilingResponse | null;
  earningsSummary: CompanyEarningsSummaryResponse | null;
  activityOverview: CompanyActivityOverviewResponse | null;
  capitalStructure: CompanyCapitalStructureResponse | null;
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse | null;
  governanceSummary: CompanyGovernanceSummaryResponse | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse | null;
  models: CompanyModelsResponse | null;
  peers: CompanyPeersResponse | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function section(title: string, body: string): string {
  return `## ${title}\n\n${body.trim()}`;
}

function compactCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  return `$${value.toFixed(2)}`;
}

function fmtOrDash(value: number | null | undefined, formatter: (v: number) => string): string {
  return value == null || Number.isNaN(value) ? "—" : formatter(value);
}

function pct(v: number | null | undefined): string {
  return fmtOrDash(v, (n) => formatPercent(n));
}

function safeDiv(a: number | null | undefined, b: number | null | undefined): number | null {
  if (a == null || b == null || b === 0) return null;
  return a / b;
}

// ---------------------------------------------------------------------------
// Section builders
// ---------------------------------------------------------------------------

function buildIdentitySection(input: InvestmentMemoInput): string {
  const { company, ticker } = input;
  const lines: string[] = [];

  lines.push(`| Field | Value |`);
  lines.push(`|---|---|`);
  lines.push(`| Ticker | ${ticker} |`);
  if (company?.name) lines.push(`| Name | ${company.name} |`);
  if (company?.cik) lines.push(`| CIK | ${company.cik} |`);

  const sector = company?.sector ?? company?.market_sector;
  if (sector) lines.push(`| Sector | ${sector} |`);
  if (company?.market_industry) lines.push(`| Industry | ${company.market_industry} |`);
  if (company?.last_checked) lines.push(`| Last checked | ${formatDate(company.last_checked)} |`);
  if (company?.cache_state) lines.push(`| Cache state | ${company.cache_state} |`);
  if (input.annualStatementsCount) {
    lines.push(`| Annual filings cached | ${input.annualStatementsCount.toLocaleString()} |`);
  }

  return section("Company Identity", lines.join("\n"));
}

function buildFreshnessSection(input: InvestmentMemoInput): string {
  const lines: string[] = [];

  if (input.asOf) lines.push(`**Data as of:** ${formatDate(input.asOf)}`);
  if (input.lastRefreshedAt) lines.push(`**Last refreshed:** ${formatDate(input.lastRefreshedAt)}`);

  const sm = input.sourceMix;
  if (sm) {
    const officialLabel = sm.official_only ? "official-source-only mode" : "mixed-source mode";
    lines.push(`**Source mode:** ${officialLabel}`);
    if (sm.primary_source_ids.length) {
      lines.push(`**Primary sources:** ${sm.primary_source_ids.join(", ")}`);
    }
    if (sm.fallback_source_ids.length) {
      lines.push(`**Fallback sources:** ${sm.fallback_source_ids.join(", ")}`);
    }
  }

  if (input.filingTimeline.length) {
    lines.push("");
    lines.push("**Filing timeline (most recent first):**");
    lines.push("");
    lines.push("| Form | Date | Description |");
    lines.push("|---|---|---|");
    for (const item of input.filingTimeline.slice(0, 8)) {
      const desc = item.description ?? "";
      lines.push(`| ${item.form} | ${formatDate(item.date)} | ${desc} |`);
    }
  }

  return section("Source & Freshness State", lines.join("\n"));
}

function buildBusinessSummarySection(input: InvestmentMemoInput): string {
  const { latestFinancial, topSegment, snapshotNarrative } = input;
  const lines: string[] = [snapshotNarrative, ""];

  if (latestFinancial) {
    const margin = safeDiv(latestFinancial.operating_income, latestFinancial.revenue);
    const fcfMargin = safeDiv(latestFinancial.free_cash_flow, latestFinancial.revenue);

    lines.push("**Key financials (latest cached period):**");
    lines.push("");
    lines.push("| Metric | Value |");
    lines.push("|---|---|");
    lines.push(`| Revenue | ${compactCurrency(latestFinancial.revenue)} |`);
    lines.push(`| Gross profit | ${compactCurrency(latestFinancial.gross_profit)} |`);
    lines.push(`| Operating income | ${compactCurrency(latestFinancial.operating_income)} |`);
    lines.push(`| Operating margin | ${pct(margin)} |`);
    lines.push(`| Net income | ${compactCurrency(latestFinancial.net_income)} |`);
    lines.push(`| Free cash flow | ${compactCurrency(latestFinancial.free_cash_flow)} |`);
    lines.push(`| FCF margin | ${pct(fcfMargin)} |`);
    lines.push(`| Filing type | ${latestFinancial.filing_type} |`);
    lines.push(`| Period end | ${formatDate(latestFinancial.period_end)} |`);

    if (topSegment) {
      lines.push("");
      const shareLabel =
        topSegment.share_of_revenue != null
          ? ` (${pct(topSegment.share_of_revenue)} of revenue)`
          : "";
      lines.push(`**Top segment:** ${topSegment.segment_name}${shareLabel}`);
    }
  }

  return section("Business Summary", lines.join("\n"));
}

function buildWhatChangedSection(input: InvestmentMemoInput): string {
  const { whatChangedNarrative, changes, earningsSummary, activityOverview } = input;
  const lines: string[] = [whatChangedNarrative, ""];

  if (changes?.summary) {
    const s = changes.summary;
    lines.push("**Changes summary:**");
    lines.push(`- High-signal changes: ${s.high_signal_change_count.toLocaleString()}`);
    lines.push(`- Total metric deltas: ${s.metric_delta_count.toLocaleString()}`);
    lines.push(`- Comment letters: ${s.comment_letter_count.toLocaleString()}`);
  }

  if (earningsSummary?.summary) {
    const s = earningsSummary.summary;
    lines.push("");
    lines.push("**Earnings capture:**");
    if (s.latest_revenue != null) lines.push(`- Latest revenue: ${compactCurrency(s.latest_revenue)}`);
    if (s.latest_diluted_eps != null) lines.push(`- Latest diluted EPS: ${s.latest_diluted_eps.toFixed(2)}`);
  }

  if (activityOverview?.summary) {
    const s = activityOverview.summary;
    lines.push("");
    lines.push(
      `**Activity feed:** ${s.total.toLocaleString()} alert${s.total === 1 ? "" : "s"} — ` +
        `${s.high.toLocaleString()} high / ${s.medium.toLocaleString()} medium / ${s.low.toLocaleString()} low`
    );
  }

  if (activityOverview?.alerts?.length) {
    lines.push("");
    lines.push("**Top alerts:**");
    for (const alert of activityOverview.alerts.slice(0, 5)) {
      const date = alert.date ? ` (${formatDate(alert.date)})` : "";
      lines.push(`- ${alert.title}${date}`);
    }
  }

  return section("What Changed", lines.join("\n"));
}

function buildBusinessQualitySection(input: InvestmentMemoInput): string {
  const { businessQualityNarrative, latestFinancial } = input;
  const lines: string[] = [businessQualityNarrative, ""];

  if (latestFinancial) {
    const debtToAssets = safeDiv(latestFinancial.total_liabilities, latestFinancial.total_assets);
    const currentRatio = safeDiv(latestFinancial.current_assets, latestFinancial.current_liabilities);

    lines.push("**Balance sheet snapshot:**");
    lines.push("");
    lines.push("| Metric | Value |");
    lines.push("|---|---|");
    lines.push(`| Total assets | ${compactCurrency(latestFinancial.total_assets)} |`);
    lines.push(`| Total liabilities | ${compactCurrency(latestFinancial.total_liabilities)} |`);
    lines.push(`| Stockholders equity | ${compactCurrency(latestFinancial.stockholders_equity)} |`);
    lines.push(`| Cash & equivalents | ${compactCurrency(latestFinancial.cash_and_cash_equivalents)} |`);
    lines.push(`| Long-term debt | ${compactCurrency(latestFinancial.long_term_debt)} |`);
    lines.push(`| Debt to assets | ${pct(debtToAssets)} |`);
    lines.push(`| Current ratio | ${fmtOrDash(currentRatio, (v) => v.toFixed(2))} |`);
    lines.push(`| Operating cash flow | ${compactCurrency(latestFinancial.operating_cash_flow)} |`);
    lines.push(`| Capex | ${compactCurrency(latestFinancial.capex)} |`);
    if (latestFinancial.stock_based_compensation != null) {
      lines.push(`| Stock-based compensation | ${compactCurrency(latestFinancial.stock_based_compensation)} |`);
    }
  }

  return section("Business Quality", lines.join("\n"));
}

function buildCapitalRiskSection(input: InvestmentMemoInput): string {
  const { capitalRiskNarrative, capitalSignalRows, capitalStructure } = input;
  const lines: string[] = [capitalRiskNarrative, ""];

  if (capitalSignalRows.length) {
    lines.push("**Capital & governance signals:**");
    lines.push("");
    const tableText = buildPlainTextTable(
      ["Signal", "Current read", "Latest evidence"],
      capitalSignalRows.map((r) => [r.signal, r.currentRead, r.latestEvidence])
    );
    lines.push("```");
    lines.push(tableText);
    lines.push("```");
  }

  const latest = capitalStructure?.latest;
  if (latest?.summary) {
    const s = latest.summary;
    lines.push("");
    lines.push("**Capital structure (latest):**");
    lines.push("");
    lines.push("| Item | Value |");
    lines.push("|---|---|");
    if (s.total_debt != null) lines.push(`| Total debt | ${compactCurrency(s.total_debt)} |`);

    if (s.net_dilution_ratio != null) lines.push(`| Net dilution ratio | ${pct(s.net_dilution_ratio)} |`);
    if (s.debt_due_next_twelve_months != null) {
      lines.push(`| Debt due next 12 months | ${compactCurrency(s.debt_due_next_twelve_months)} |`);
    }
  }

  return section("Capital, Risk, Dilution & Governance", lines.join("\n"));
}

function buildValuationSection(input: InvestmentMemoInput): string {
  const { valuationNarrative, models, peers } = input;
  const lines: string[] = [valuationNarrative, ""];

  if (models?.models.length) {
    const dcf = models.models.find((m) => m.model_name === "dcf");
    const residual = models.models.find((m) => m.model_name === "residual_income");
    const dcfFairValue =
      dcf?.result &&
      typeof dcf.result === "object" &&
      "fair_value_per_share" in dcf.result &&
      typeof (dcf.result as Record<string, unknown>).fair_value_per_share === "number"
        ? ((dcf.result as Record<string, unknown>).fair_value_per_share as number)
        : null;
    const residualValue =
      residual?.result &&
      typeof residual.result === "object" &&
      "intrinsic_value" in residual.result &&
      typeof (residual.result as Record<string, unknown>).intrinsic_value === "object"
        ? (() => {
            const iv = (residual.result as Record<string, unknown>).intrinsic_value as Record<string, unknown>;
            return typeof iv.intrinsic_value_per_share === "number" ? iv.intrinsic_value_per_share : null;
          })()
        : null;

    lines.push("**Cached model anchors:**");
    lines.push("");
    lines.push("| Model | Fair value / share |");
    lines.push("|---|---|");
    if (dcfFairValue != null) lines.push(`| DCF | ${compactCurrency(dcfFairValue)} |`);
    if (residualValue != null) lines.push(`| Residual income | ${compactCurrency(residualValue)} |`);
    if (dcfFairValue == null && residualValue == null) {
      lines.push("| — | No cached model outputs available |");
    }
  }

  if (peers?.peers?.length) {
    const focusPeer = peers.peers.find((p) => p.is_focus);
    const otherPeers = peers.peers.filter((p) => !p.is_focus);

    lines.push("");
    lines.push("**Peer snapshot:**");
    lines.push("");
    lines.push("| Ticker | Name | P/E | EV/EBIT | Price | Focus |");
    lines.push("|---|---|---|---|---|---|");

    const allPeers = focusPeer ? [focusPeer, ...otherPeers] : otherPeers;
    for (const peer of allPeers.slice(0, 10)) {
      const pe = peer.pe != null ? peer.pe.toFixed(1) : "—";
      const evEbit = peer.ev_to_ebit != null ? peer.ev_to_ebit.toFixed(1) : "—";
      const price = peer.latest_price != null ? compactCurrency(peer.latest_price) : "—";
      const focus = peer.is_focus ? "✓" : "";
      lines.push(`| ${peer.ticker} | ${peer.name ?? "—"} | ${pe} | ${evEbit} | ${price} | ${focus} |`);
    }
  }

  return section("Peer & Valuation Summary", lines.join("\n"));
}

function buildMonitorSection(input: InvestmentMemoInput): string {
  const { monitorNarrative, monitorChecklist } = input;
  const lines: string[] = [monitorNarrative, ""];

  if (monitorChecklist.length) {
    lines.push("**Monitor checklist:**");
    lines.push("");
    for (const item of monitorChecklist) {
      lines.push(`- **${item.title}:** ${item.detail}`);
    }
  }

  return section("Monitor Checklist", lines.join("\n"));
}

function buildProvenanceSection(input: InvestmentMemoInput): string {
  const lines: string[] = [];

  if (input.provenance?.length) {
    lines.push("**Data sources:**");
    lines.push("");
    lines.push("| Source | Tier | Role | As of | Disclosure |");
    lines.push("|---|---|---|---|---|");
    for (const entry of input.provenance) {
      const asOf = entry.as_of ? formatDate(entry.as_of) : "—";
      lines.push(
        `| [${entry.display_label}](${entry.url}) | ${entry.source_tier} | ${entry.role} | ${asOf} | ${entry.disclosure_note} |`
      );
    }
  }

  if (input.filingTimeline.length) {
    lines.push("");
    lines.push("**Filing provenance (cached timeline):**");
    lines.push("");
    for (const item of input.filingTimeline.slice(0, 12)) {
      const acc = item.accession ? ` · ${item.accession}` : "";
      lines.push(`- ${item.form} · ${formatDate(item.date)}${acc}`);
    }
  }

  if (!lines.length) {
    lines.push("_No provenance data is available in the cached workspace._");
  }

  return section("Source Links & Provenance", lines.join("\n"));
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export function buildInvestmentMemo(input: InvestmentMemoInput): string {
  const { ticker, company, exportedAt } = input;
  const displayName = company?.name ?? ticker;

  const header = [
    `# Investment Memo: ${displayName}`,
    "",
    `> **Ticker:** ${ticker}  `,
    `> **Generated:** ${formatDate(exportedAt)} · ${exportedAt}  `,
    `> **Source:** Fundamental Terminal — cached data only; no live SEC fetches were made during export.`,
    "",
    "---",
    "",
  ].join("\n");

  const sections = [
    buildIdentitySection(input),
    buildFreshnessSection(input),
    buildBusinessSummarySection(input),
    buildWhatChangedSection(input),
    buildBusinessQualitySection(input),
    buildCapitalRiskSection(input),
    buildValuationSection(input),
    buildMonitorSection(input),
    buildProvenanceSection(input),
  ];

  const footer = [
    "",
    "---",
    "",
    `_Memo generated from cached workspace data at ${exportedAt}. All data is sourced from persisted snapshots — refer to the Source & Freshness section for data-as-of dates and provenance disclosures._`,
  ].join("\n");

  return header + sections.join("\n\n") + footer;
}

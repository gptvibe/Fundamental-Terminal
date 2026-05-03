import { resolveCommercialFallbackLabels } from "@/components/ui/commercial-fallback-notice";
import { toneForEntryCard } from "@/lib/activity-feed-tone";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
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
  ConsoleEntry,
  EquityClaimRiskSummaryPayload,
  FinancialPayload,
  FilingTimelineItemPayload,
  ProvenanceEntryPayload,
  RefreshState,
  ResearchBriefBuildState,
  ResearchBriefSectionStatusPayload,
  ResearchBriefSummaryCardPayload,
  SourceMixPayload,
} from "@/lib/types";
import type { SemanticTone } from "@/lib/activity-feed-tone";
import type { AsyncState, MonitorChecklistItem } from "@/components/company/brief-primitives";

import type { BriefCompany, ResearchBriefAsyncState, ResearchBriefDataState } from "./research-brief-types";
import { BRIEF_SECTION_IDS } from "./research-brief-types";

// ---------------------------------------------------------------------------
// Math helpers
// ---------------------------------------------------------------------------

export function safeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

export function safeDivide(numerator: number | null | undefined, denominator: number | null | undefined): number | null {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }
  return numerator / denominator;
}

export function growthRate(current: number | null | undefined, previous: number | null | undefined): number | null {
  if (current == null || previous == null || previous === 0) {
    return null;
  }
  return (current - previous) / Math.abs(previous);
}

export function median(values: Array<number | null | undefined>): number | null {
  const numericValues = values
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value))
    .sort((left, right) => left - right);
  if (!numericValues.length) {
    return null;
  }
  const middle = Math.floor(numericValues.length / 2);
  if (numericValues.length % 2 === 0) {
    return (numericValues[middle - 1] + numericValues[middle]) / 2;
  }
  return numericValues[middle];
}

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

export function formatCompactCurrency(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `$${formatCompactNumber(value)}`;
}

export function formatMultiple(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)}x`;
}

export function formatFeedEntryType(type: string): string {
  if (type === "form144") {
    return "planned-sale";
  }
  return type;
}

export function formatResearchBriefBuildState(state: ResearchBriefBuildState): string {
  if (state === "ready") {
    return "Ready";
  }
  if (state === "partial") {
    return "Partial";
  }
  return "Building";
}

// ---------------------------------------------------------------------------
// Domain helpers
// ---------------------------------------------------------------------------

export function isForeignIssuerAnnualForm(filingType: string | null | undefined): boolean {
  return filingType === "20-F" || filingType === "40-F";
}

export function toneForRiskLevel(level: "none" | "low" | "medium" | "high"): SemanticTone {
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

export function extractTopSegment(latestFinancial: FinancialPayload | null): FinancialPayload["segment_breakdown"][number] | null {
  if (!latestFinancial?.segment_breakdown.length) {
    return null;
  }
  return (
    [...latestFinancial.segment_breakdown].sort((left, right) => {
      const leftValue = left.share_of_revenue ?? left.revenue ?? Number.NEGATIVE_INFINITY;
      const rightValue = right.share_of_revenue ?? right.revenue ?? Number.NEGATIVE_INFINITY;
      return rightValue - leftValue;
    })[0] ?? null
  );
}

export function extractModelNumber(models: CompanyModelsResponse["models"], modelName: string, path: string[]): number | null {
  const model = models.find((entry) => entry.model_name === modelName);
  if (!model) {
    return null;
  }
  let current: unknown = model.result;
  for (const key of path) {
    current = asRecord(current)[key];
  }
  return safeNumber(current);
}

// ---------------------------------------------------------------------------
// Narrative builders
// ---------------------------------------------------------------------------

export function buildSnapshotNarrative({
  company,
  latestFinancial,
  topSegment,
  alertCount,
  buildState,
  filingTimeline,
  sourceMix,
  provenance,
  loading,
}: {
  company: BriefCompany | null;
  latestFinancial: FinancialPayload | null;
  topSegment: FinancialPayload["segment_breakdown"][number] | null;
  alertCount: number;
  buildState: ResearchBriefBuildState;
  filingTimeline: FilingTimelineItemPayload[];
  sourceMix: SourceMixPayload | null | undefined;
  provenance: ProvenanceEntryPayload[] | null | undefined;
  loading: boolean;
}): string {
  if (!latestFinancial) {
    if (company && filingTimeline.length) {
      const latestFiling = filingTimeline[0];
      return `${company.name ?? company.ticker ?? "This company"} is in ${buildState === "building" ? "cold-start bootstrap" : "partial brief"} mode. The latest visible SEC filing is ${latestFiling.form} dated ${formatDate(latestFiling.date)} and the rest of the specialist sections will fill in as cached datasets finish warming.`;
    }
    return loading
      ? "The brief is loading the latest persisted filing, segment mix, and price context before the deeper sections render."
      : "The default brief is waiting for persisted financials and segment disclosures before it can frame the company at a glance.";
  }

  const fallbackLabels = resolveCommercialFallbackLabels(provenance, sourceMix);
  const topSegmentSummary =
    topSegment && topSegment.share_of_revenue != null
      ? `${topSegment.segment_name} contributes ${formatPercent(topSegment.share_of_revenue)} of reported revenue`
      : topSegment?.segment_name
        ? `${topSegment.segment_name} is the most visible reported segment`
        : "segment concentration is still limited in the cached disclosures";
  const fallbackSummary = fallbackLabels.length
    ? `Price context is coming through a labeled ${fallbackLabels.join(", ")} fallback while fundamentals remain official-source-first.`
    : "Both the operating history and its freshness cues remain anchored in the persisted SEC-first workspace.";

  return `${company?.name ?? company?.ticker ?? "This company"} last reported ${formatCompactCurrency(latestFinancial.revenue)} of revenue and ${formatCompactCurrency(latestFinancial.free_cash_flow)} of free cash flow; ${topSegmentSummary}; ${alertCount.toLocaleString()} current alert${alertCount === 1 ? " is" : "s are"} already on the monitor. ${fallbackSummary}`;
}

export function buildWhatChangedNarrative({
  changes,
  earningsSummary,
  activityOverview,
  loading,
}: {
  changes: CompanyChangesSinceLastFilingResponse | null;
  earningsSummary: CompanyEarningsSummaryResponse | null;
  activityOverview: CompanyActivityOverviewResponse | null;
  loading: boolean;
}): string {
  if (!changes && !earningsSummary && !activityOverview) {
    return loading
      ? "The brief is comparing the latest filing, earnings summary, and activity feed before it answers what changed."
      : "This section will summarize filing deltas, earnings capture, and dated SEC activity once the persisted change surfaces are available.";
  }

  const metricDeltas = changes?.summary.metric_delta_count ?? 0;
  const highSignalChanges = changes?.summary.high_signal_change_count ?? 0;
  const commentLetters = changes?.summary.comment_letter_count ?? 0;
  const latestRevenue = earningsSummary?.summary.latest_revenue;
  const latestEps = earningsSummary?.summary.latest_diluted_eps;
  const highAlerts = activityOverview?.summary.high ?? 0;

  return `The latest comparable filing surfaced ${highSignalChanges.toLocaleString()} curated high-signal change${highSignalChanges === 1 ? "" : "s"} and ${commentLetters.toLocaleString()} comment-letter update${commentLetters === 1 ? "" : "s"}; the full comparison still retains ${metricDeltas.toLocaleString()} raw metric delta${metricDeltas === 1 ? "" : "s"}; the latest earnings capture reads ${formatCompactCurrency(latestRevenue)} of revenue and ${latestEps != null ? latestEps.toFixed(2) : "—"} diluted EPS; the activity feed is currently carrying ${highAlerts.toLocaleString()} high-priority alert${highAlerts === 1 ? "" : "s"}.`;
}

export function buildBusinessQualityNarrative({
  latestFinancial,
  previousAnnual,
  loading,
}: {
  latestFinancial: FinancialPayload | null;
  previousAnnual: FinancialPayload | null;
  loading: boolean;
}): string {
  if (!latestFinancial) {
    return loading
      ? "The brief is loading the latest quality metrics before it judges whether the business is strengthening or deteriorating."
      : "This section will evaluate margins, cash generation, and balance-sheet quality once persisted annual statement history is available.";
  }

  const revenueGrowth = growthRate(latestFinancial.revenue, previousAnnual?.revenue ?? null);
  const operatingMargin = safeDivide(latestFinancial.operating_income, latestFinancial.revenue);
  const fcfMargin = safeDivide(latestFinancial.free_cash_flow, latestFinancial.revenue);
  const debtToAssets = safeDivide(latestFinancial.total_liabilities, latestFinancial.total_assets);

  return `Revenue is ${revenueGrowth != null ? `${revenueGrowth >= 0 ? "up" : "down"} ${formatPercent(Math.abs(revenueGrowth))} year over year` : "not yet comparable year over year"}, operating margin sits at ${formatPercent(operatingMargin)}, free-cash-flow margin at ${formatPercent(fcfMargin)}, and debt-to-assets at ${formatPercent(debtToAssets)}. The goal here is to decide whether improvement is real, fragile, or mostly accounting noise.`;
}

export function buildCapitalRiskNarrative({
  capitalStructure,
  capitalMarketsSummary,
  governanceSummary,
  ownershipSummary,
  equityClaimRiskSummary,
  isForeignIssuerLike,
  loading,
}: {
  capitalStructure: CompanyCapitalStructureResponse | null;
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse | null;
  governanceSummary: CompanyGovernanceSummaryResponse | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse | null;
  equityClaimRiskSummary: EquityClaimRiskSummaryPayload | null;
  isForeignIssuerLike: boolean;
  loading: boolean;
}): string {
  const latest = capitalStructure?.latest ?? null;

  if (!latest && !capitalMarketsSummary && !governanceSummary && !ownershipSummary) {
    return loading
      ? "The brief is loading persisted debt, governance, and ownership signals before it judges whether the equity claim is protected."
      : "This section will summarize debt burden, dilution risk, governance coverage, and ownership pressure once the persisted control signals are available.";
  }

  const debtDue = latest?.summary.debt_due_next_twelve_months;
  const netDilution = latest?.summary.net_dilution_ratio;
  const proxyCount = governanceSummary?.summary.total_filings ?? 0;
  const stakeChangeCount = ownershipSummary?.summary.total_filings ?? 0;
  const registrationFilings = capitalMarketsSummary?.summary.registration_filings ?? 0;
  const governanceRead =
    isForeignIssuerLike && proxyCount === 0
      ? "governance coverage is limited because many 20-F and 40-F issuers do not file U.S. proxy materials"
      : `governance coverage spans ${proxyCount.toLocaleString()} proxy filing${proxyCount === 1 ? "" : "s"}`;

  if (equityClaimRiskSummary) {
    return `${equityClaimRiskSummary.headline} Net dilution currently reads ${formatPercent(equityClaimRiskSummary.net_dilution_ratio)}, remaining shelf capacity is ${formatCompactCurrency(equityClaimRiskSummary.shelf_capacity_remaining)}, debt due inside 24 months is ${formatCompactCurrency(equityClaimRiskSummary.debt_due_next_twenty_four_months)}, and internal-control flags total ${equityClaimRiskSummary.internal_control_flag_count.toLocaleString()}. ${governanceRead}, stake-change monitoring covers ${stakeChangeCount.toLocaleString()} major-holder filing${stakeChangeCount === 1 ? "" : "s"}, and registration activity counts ${registrationFilings.toLocaleString()} financing filing${registrationFilings === 1 ? "" : "s"}.`;
  }

  return `Near-term debt due is ${formatCompactCurrency(debtDue)}, net dilution is ${formatPercent(netDilution)}, ${governanceRead}, stake-change monitoring covers ${stakeChangeCount.toLocaleString()} major-holder filing${stakeChangeCount === 1 ? "" : "s"}, and registration activity counts ${registrationFilings.toLocaleString()} financing filing${registrationFilings === 1 ? "" : "s"} so the brief can answer whether capital allocation is supportive or leaking value.`;
}

export function buildValuationNarrative({
  models,
  peers,
  priceHistory,
  loading,
}: {
  models: CompanyModelsResponse["models"];
  peers: CompanyPeersResponse["peers"];
  priceHistory: { date: string; close: number | null }[];
  loading: boolean;
}): string {
  if (!models.length && !peers.length) {
    return loading
      ? "The brief is loading cached models and the persisted peer universe before it answers the valuation question."
      : "This section will compare cached model ranges with peer multiples once the valuation workspace has persisted outputs for the company.";
  }

  const latestPrice = priceHistory.at(-1)?.close ?? peers.find((peer) => peer.is_focus)?.latest_price ?? null;
  const dcfFairValue = extractModelNumber(models, "dcf", ["fair_value_per_share"]);
  const residualValue = extractModelNumber(models, "residual_income", ["intrinsic_value", "intrinsic_value_per_share"]);
  const anchors = [dcfFairValue, residualValue].filter((value): value is number => value != null);
  const midpoint = anchors.length ? anchors.reduce((sum, value) => sum + value, 0) / anchors.length : null;
  const gap = midpoint != null && latestPrice != null && latestPrice > 0 ? (midpoint - latestPrice) / latestPrice : null;
  const focusPeer = peers.find((peer) => peer.is_focus) ?? null;
  const otherPeers = peers.filter((peer) => !peer.is_focus);
  const peerMedianPe = median(otherPeers.map((peer) => peer.pe));

  if (gap != null && focusPeer?.pe != null && peerMedianPe != null) {
    const direction = gap >= 0 ? "above" : "below";
    return `Cached model anchors put intrinsic value about ${formatPercent(Math.abs(gap))} ${direction} the latest price, while ${focusPeer.ticker} trades at ${formatMultiple(focusPeer.pe)} earnings versus a ${formatMultiple(peerMedianPe)} peer median. The brief's job here is to tell you whether underwriting still points to upside before you open the full model workbench.`;
  }

  if (midpoint != null && latestPrice != null) {
    return `The current valuation read is anchored on a cached midpoint of ${formatCompactCurrency(midpoint)} per share versus a latest price of ${formatCompactCurrency(latestPrice)}. Peer metrics are available below to pressure-test whether the market is already paying up for that quality.`;
  }

  return `Cached valuation outputs are partially available, so the brief uses the peer snapshot below to frame relative valuation while the fuller model range continues to warm.`;
}

export function buildMonitorNarrative({
  activityOverview,
  refreshState,
  company,
  loading,
}: {
  activityOverview: CompanyActivityOverviewResponse | null;
  refreshState: RefreshState | null;
  company: BriefCompany | null;
  loading: boolean;
}): string {
  if (!activityOverview) {
    return loading
      ? "The brief is loading alerts, dated activity, and freshness cues before it closes with the monitor view."
      : "This section will tell you what to re-check next once the cached monitoring feed has alerts and dated SEC activity for the company.";
  }

  const latestEntry = activityOverview.entries[0] ?? null;
  const refreshSummary = refreshState?.job_id ? "A refresh is already queued in the background." : "No refresh job is queued right now.";
  const latestEntrySummary = latestEntry ? `The newest dated activity is ${latestEntry.title} on ${formatDate(latestEntry.date)}.` : "No dated SEC activity is cached yet.";

  return `${activityOverview.summary.total.toLocaleString()} alert${activityOverview.summary.total === 1 ? " is" : "s are"} currently on the monitor for ${company?.ticker ?? "this company"}. ${latestEntrySummary} ${refreshSummary}`;
}

// ---------------------------------------------------------------------------
// Capital signal row and monitor checklist builders
// ---------------------------------------------------------------------------

export function buildCapitalSignalRows({
  capitalMarketsSummary,
  governanceSummary,
  ownershipSummary,
  equityClaimRiskSummary,
  isForeignIssuerLike,
}: {
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse["summary"] | null;
  governanceSummary: CompanyGovernanceSummaryResponse["summary"] | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse["summary"] | null;
  equityClaimRiskSummary: EquityClaimRiskSummaryPayload | null;
  isForeignIssuerLike: boolean;
}): Array<{ signal: string; currentRead: string; latestEvidence: string }> {
  const rows: Array<{ signal: string; currentRead: string; latestEvidence: string }> = [];

  if (capitalMarketsSummary) {
    rows.push({
      signal: "Capital markets",
      currentRead: `${capitalMarketsSummary.total_filings.toLocaleString()} filings · largest offering ${formatCompactCurrency(capitalMarketsSummary.max_offering_amount)}`,
      latestEvidence: capitalMarketsSummary.latest_filing_date ? formatDate(capitalMarketsSummary.latest_filing_date) : "Pending",
    });
  }

  if (governanceSummary) {
    rows.push({
      signal: "Governance",
      currentRead:
        isForeignIssuerLike && governanceSummary.total_filings === 0
          ? "U.S. proxy materials may be unavailable for many 20-F and 40-F issuers"
          : `${governanceSummary.total_filings.toLocaleString()} proxy filings · ${governanceSummary.filings_with_vote_items.toLocaleString()} with vote items`,
      latestEvidence:
        isForeignIssuerLike && governanceSummary.total_filings === 0
          ? "Limited by filing regime"
          : governanceSummary.latest_meeting_date
            ? formatDate(governanceSummary.latest_meeting_date)
            : "Pending",
    });
  }

  if (ownershipSummary) {
    rows.push({
      signal: "Stake changes",
      currentRead: `${ownershipSummary.total_filings.toLocaleString()} filings · ${ownershipSummary.ownership_increase_events.toLocaleString()} up / ${ownershipSummary.ownership_decrease_events.toLocaleString()} down`,
      latestEvidence: ownershipSummary.latest_event_date ? formatDate(ownershipSummary.latest_event_date) : "Pending",
    });
  }

  if (equityClaimRiskSummary) {
    rows.push({
      signal: "Equity claim",
      currentRead: `${titleCase(equityClaimRiskSummary.overall_risk_level)} risk · net dilution ${formatPercent(equityClaimRiskSummary.net_dilution_ratio)}`,
      latestEvidence: equityClaimRiskSummary.latest_period_end ? formatDate(equityClaimRiskSummary.latest_period_end) : "Pending",
    });
  }

  return rows;
}

export function buildMonitorChecklist({
  refreshState,
  activityOverview,
  company,
  ownershipSummary,
  capitalMarketsSummary,
}: {
  refreshState: RefreshState | null;
  activityOverview: CompanyActivityOverviewResponse | null;
  company: BriefCompany | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse["summary"] | null;
  capitalMarketsSummary: CompanyCapitalMarketsSummaryResponse["summary"] | null;
}): MonitorChecklistItem[] {
  const items: MonitorChecklistItem[] = [];

  items.push({
    title: "Refresh status",
    detail: refreshState?.job_id
      ? `Refresh job ${refreshState.job_id} is running in the background.`
      : company?.last_checked
        ? `No refresh queued. Last full company check ran on ${formatDate(company.last_checked)}.`
        : "No refresh queued yet.",
    tone: refreshState?.job_id || company?.last_checked ? "cyan" : "gold",
  });

  if (activityOverview) {
    items.push({
      title: "Alert count",
      detail: `${activityOverview.summary.high.toLocaleString()} high, ${activityOverview.summary.medium.toLocaleString()} medium, and ${activityOverview.summary.low.toLocaleString()} low alert${activityOverview.summary.total === 1 ? " is" : "s are"} currently active.`,
      tone:
        activityOverview.summary.high > 0
          ? "red"
          : activityOverview.summary.medium > 0
            ? "gold"
            : activityOverview.summary.low > 0
              ? "green"
              : "cyan",
    });

    if (activityOverview.entries[0]) {
      items.push({
        title: "Latest activity",
        detail: `${activityOverview.entries[0].title} on ${formatDate(activityOverview.entries[0].date)} should be the first thing to revisit if the thesis changes.`,
        tone: toneForEntryCard(activityOverview.entries[0]),
      });
    }
  }

  if (ownershipSummary) {
    items.push({
      title: "Ownership watch",
      detail: ownershipSummary.latest_event_date
        ? `${ownershipSummary.total_filings.toLocaleString()} major-holder filing${ownershipSummary.total_filings === 1 ? "" : "s"} are cached through ${formatDate(ownershipSummary.latest_event_date)}.`
        : "Major-holder change monitoring is enabled, but the latest dated filing is still pending.",
      tone: ownershipSummary.ownership_decrease_events > 0 ? "gold" : "cyan",
    });
  }

  if (capitalMarketsSummary) {
    items.push({
      title: "Financing watch",
      detail: capitalMarketsSummary.latest_filing_date
        ? `${capitalMarketsSummary.registration_filings.toLocaleString()} registration filing${capitalMarketsSummary.registration_filings === 1 ? "" : "s"} are cached through ${formatDate(capitalMarketsSummary.latest_filing_date)}.`
        : "No recent financing filing date is cached yet.",
      tone: capitalMarketsSummary.registration_filings > 0 ? "gold" : "cyan",
    });
  }

  return items.slice(0, 4);
}

// ---------------------------------------------------------------------------
// State transformation utilities
// ---------------------------------------------------------------------------

export function resolveAsyncState<T>(
  previous: AsyncState<T>,
  result: PromiseSettledResult<T>,
  fallback: string
): AsyncState<T> {
  if (result.status === "fulfilled") {
    return {
      data: result.value,
      error: null,
      loading: false,
    };
  }

  return {
    data: previous.data,
    error: result.reason instanceof Error ? result.reason.message : fallback,
    loading: false,
  };
}

export function mapBriefResponseToAsyncState(brief: import("@/lib/types").CompanyResearchBriefResponse): ResearchBriefDataState {
  const whatChangedAvailable = isBriefSectionAvailable(brief, "what_changed") || brief.build_state === "ready";
  const capitalRiskAvailable = isBriefSectionAvailable(brief, "capital_and_risk") || brief.build_state === "ready";
  const valuationAvailable = isBriefSectionAvailable(brief, "valuation") || brief.build_state === "ready";

  return {
    brief,
    error: null,
    loading: false,
    buildState: brief.build_state,
    buildStatus: brief.build_status,
    availableSections: [...brief.available_sections],
    sectionStatuses: [...brief.section_statuses],
    filingTimeline: [...brief.filing_timeline],
    summaryCards: [...brief.stale_summary_cards],
    activityOverview: resolveBriefSectionData(whatChangedAvailable, brief.what_changed.activity_overview),
    changes: resolveBriefSectionData(whatChangedAvailable, brief.what_changed.changes),
    earningsSummary: resolveBriefSectionData(whatChangedAvailable, brief.what_changed.earnings_summary),
    capitalStructure: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.capital_structure),
    capitalMarketsSummary: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.capital_markets_summary),
    governanceSummary: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.governance_summary),
    ownershipSummary: resolveBriefSectionData(capitalRiskAvailable, brief.capital_and_risk.ownership_summary),
    models: resolveBriefSectionData(valuationAvailable, brief.valuation.models),
    peers: resolveBriefSectionData(valuationAvailable, brief.valuation.peers),
  };
}

export function resolveBriefSectionData<T>(available: boolean, data: T): AsyncState<T> {
  return {
    data: available ? data : null,
    error: null,
    loading: !available,
  };
}

export function isBriefSectionAvailable(brief: import("@/lib/types").CompanyResearchBriefResponse, sectionId: string): boolean {
  return brief.available_sections.includes(sectionId);
}

export function advanceResearchBriefDataState(
  current: ResearchBriefDataState,
  sectionId: string,
  updates: Partial<ResearchBriefAsyncState>
): ResearchBriefDataState {
  const availableSections = current.availableSections.includes(sectionId)
    ? current.availableSections
    : [...current.availableSections, sectionId];

  return {
    ...current,
    ...updates,
    loading: false,
    buildState: current.buildState === "building" ? "partial" : current.buildState,
    buildStatus: buildStatusForAvailableSections(availableSections),
    availableSections,
    sectionStatuses: updateResearchBriefSectionStatuses(current.sectionStatuses, availableSections),
  };
}

export function updateResearchBriefSectionStatuses(
  currentStatuses: ResearchBriefSectionStatusPayload[],
  availableSections: string[]
): ResearchBriefSectionStatusPayload[] {
  const byId = new Map(currentStatuses.map((item) => [item.id, item]));
  const available = new Set(availableSections);
  let partialAssigned = false;

  return ["snapshot", "what_changed", "business_quality", "capital_and_risk", "valuation"].map((sectionId) => {
    const existing = byId.get(sectionId);
    let state: ResearchBriefBuildState = "building";
    let detail = existing?.detail ?? "Warming up.";

    if (available.has(sectionId)) {
      state = "ready";
      detail = "Available now.";
    } else if (!partialAssigned && available.size > 0) {
      state = "partial";
      detail = "Queued next.";
      partialAssigned = true;
    }

    return {
      id: sectionId,
      title: existing?.title ?? titleCase(sectionId.replaceAll("_", " ")),
      state,
      available: available.has(sectionId),
      detail,
    };
  });
}

export function buildStatusForAvailableSections(availableSections: string[]): string {
  if (availableSections.includes("valuation")) {
    return "Most specialist sections are visible while the cached brief catches up.";
  }
  if (availableSections.includes("capital_and_risk")) {
    return "Capital and risk signals are live. Valuation is loading next.";
  }
  if (availableSections.includes("what_changed")) {
    return "Change summaries are live. Capital and risk is loading next.";
  }
  return "Showing the bootstrap snapshot while the rest of the brief hydrates.";
}

export function mergeBusinessQualitySectionStatus(
  sectionStatuses: ResearchBriefSectionStatusPayload[],
  { loading, hasFinancials }: { loading: boolean; hasFinancials: boolean }
): ResearchBriefSectionStatusPayload[] {
  const nextStatuses = [...sectionStatuses];
  const sectionId = "business_quality";
  const index = nextStatuses.findIndex((item) => item.id === sectionId);

  const nextStatus: ResearchBriefSectionStatusPayload = {
    id: sectionId,
    title: nextStatuses[index]?.title ?? "Business Quality",
    state: hasFinancials ? "ready" : loading ? "partial" : nextStatuses[index]?.state ?? "building",
    available: hasFinancials || nextStatuses[index]?.available || false,
    detail: hasFinancials
      ? "Available now."
      : loading
        ? "Loading company financial history."
        : nextStatuses[index]?.detail ?? "Warming up.",
  };

  if (index >= 0) {
    nextStatuses[index] = nextStatus;
    return nextStatuses;
  }

  nextStatuses.push(nextStatus);
  return nextStatuses;
}

export function findBriefSummaryCardValue(cards: ResearchBriefSummaryCardPayload[], title: string): string | null {
  return cards.find((card) => card.title === title)?.value ?? null;
}

export function buildInitialCompanyLoadMessage(
  initialCompanyLoad: boolean,
  activeRefreshEntry: ConsoleEntry | null,
  buildState: ResearchBriefBuildState,
  buildStatus: string | null,
): string | null {
  if (!initialCompanyLoad) {
    return buildState !== "ready" ? buildStatus : null;
  }

  if (activeRefreshEntry?.status === "queued") {
    const jobsAhead = activeRefreshEntry.jobs_ahead;
    if (typeof jobsAhead === "number") {
      if (jobsAhead <= 0) {
        return "No cached company snapshot exists yet. Your first overview is next in the refresh queue.";
      }
      const plural = jobsAhead === 1 ? "" : "es";
      return `No cached company snapshot exists yet. Queued behind ${jobsAhead.toLocaleString()} other refresh${plural} before the first overview starts.`;
    }
    return "No cached company snapshot exists yet. The first overview is queued and will start shortly.";
  }

  if (activeRefreshEntry?.status === "running") {
    return "No cached company snapshot exists yet. Building the first overview now.";
  }

  return "No cached company snapshot exists yet. Fetching the first overview now.";
}

export function buildRefreshQueueDetailLine(activeRefreshEntry: ConsoleEntry | null): string | null {
  if (activeRefreshEntry?.status === "queued") {
    const jobsAhead = activeRefreshEntry.jobs_ahead;
    if (typeof jobsAhead === "number") {
      if (jobsAhead <= 0) {
        return "Refresh queue: next in line for the worker.";
      }
      const plural = jobsAhead === 1 ? "" : "es";
      return `Refresh queue: ${jobsAhead.toLocaleString()} refresh${plural} ahead before this company snapshot starts.`;
    }
    return "Refresh queue: waiting for the worker to claim this company refresh.";
  }

  if (activeRefreshEntry?.status === "running") {
    return "Refresh queue: worker claimed this company and the first snapshot is building now.";
  }

  return null;
}

export function createDefaultResearchBriefSectionState(): Record<string, boolean> {
  return Object.fromEntries(BRIEF_SECTION_IDS.map((sectionId) => [sectionId, true]));
}

export function mergeResearchBriefSectionState(
  defaultState: Record<string, boolean>,
  parsedState: unknown,
  sectionIds: string[]
): Record<string, boolean> {
  if (!parsedState || typeof parsedState !== "object") {
    return defaultState;
  }

  const nextState = { ...defaultState };

  for (const sectionId of sectionIds) {
    const value = (parsedState as Record<string, unknown>)[sectionId];
    if (typeof value === "boolean") {
      nextState[sectionId] = value;
    }
  }

  return nextState;
}

export function persistResearchBriefSectionState(
  storageKey: string,
  expandedSections: Record<string, boolean>,
  sectionIds: string[]
): boolean {
  try {
    const defaultState = Object.fromEntries(sectionIds.map((id) => [id, true]));
    const normalizedState = mergeResearchBriefSectionState(defaultState, expandedSections, sectionIds);
    window.localStorage.setItem(storageKey, JSON.stringify(normalizedState));
    return true;
  } catch {
    return false;
  }
}

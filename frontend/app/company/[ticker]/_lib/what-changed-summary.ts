import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  CompanyActivityOverviewResponse,
  CompanyBeneficialOwnershipSummaryResponse,
  CompanyChangesSinceLastFilingResponse,
  CompanyEarningsSummaryResponse,
  CompanyGovernanceSummaryResponse,
  CompanyModelsResponse,
  FilingComparisonMetricDeltaPayload,
  ModelPayload,
  ProvenanceEntryPayload,
} from "@/lib/types";

export type WhatChangedSeverity = "high" | "medium" | "low";

export type WhatChangedHighlightItem = {
  id: string;
  title: string;
  detail: string;
  occurredAt: string | null;
  severity: WhatChangedSeverity;
  sourceLabel: string;
  provenance: string;
};

type BuildWhatChangedHighlightsInput = {
  changes: CompanyChangesSinceLastFilingResponse | null;
  earningsSummary: CompanyEarningsSummaryResponse | null;
  activityOverview: CompanyActivityOverviewResponse | null;
  models: CompanyModelsResponse | null;
  ownershipSummary: CompanyBeneficialOwnershipSummaryResponse | null;
  governanceSummary: CompanyGovernanceSummaryResponse | null;
  limit?: number;
};

const DEFAULT_LIMIT = 4;

const SEVERITY_RANK: Record<WhatChangedSeverity, number> = {
  high: 3,
  medium: 2,
  low: 1,
};

const FINANCIAL_METRIC_MATCHERS = [
  /revenue/i,
  /margin/i,
  /free cash flow/i,
  /operating cash flow/i,
  /debt/i,
  /liabilit/i,
];

export function buildWhatChangedHighlights({
  changes,
  earningsSummary,
  activityOverview,
  models,
  ownershipSummary,
  governanceSummary,
  limit = DEFAULT_LIMIT,
}: BuildWhatChangedHighlightsInput): WhatChangedHighlightItem[] {
  const latestHighlight = buildLatestFilingOrEventHighlight(changes, activityOverview);
  const financialHighlight = buildFinancialMovementHighlight(changes, earningsSummary);
  const modelHighlight = buildModelMovementHighlight(models);
  const ownershipHighlight = buildOwnershipHighlight(ownershipSummary);
  const governanceHighlight = buildGovernanceHighlight(governanceSummary);
  const alertHighlight = buildAlertPressureHighlight(activityOverview);

  const controlSignalHighlight = pickBestControlSignal([ownershipHighlight, governanceHighlight]) ?? alertHighlight;

  const candidates = [latestHighlight, financialHighlight, modelHighlight, controlSignalHighlight].filter(
    (item): item is WhatChangedHighlightItem => item != null
  );

  return candidates
    .sort((left, right) => {
      const timeDelta = asTimestamp(right.occurredAt) - asTimestamp(left.occurredAt);
      if (timeDelta !== 0) {
        return timeDelta;
      }
      const severityDelta = SEVERITY_RANK[right.severity] - SEVERITY_RANK[left.severity];
      if (severityDelta !== 0) {
        return severityDelta;
      }
      return left.id.localeCompare(right.id);
    })
    .slice(0, limit);
}

function pickBestControlSignal(
  candidates: Array<WhatChangedHighlightItem | null>
): WhatChangedHighlightItem | null {
  const available = candidates.filter((item): item is WhatChangedHighlightItem => item != null);
  if (!available.length) {
    return null;
  }

  return (
    [...available].sort((left, right) => {
      const timeDelta = asTimestamp(right.occurredAt) - asTimestamp(left.occurredAt);
      if (timeDelta !== 0) {
        return timeDelta;
      }
      const severityDelta = SEVERITY_RANK[right.severity] - SEVERITY_RANK[left.severity];
      if (severityDelta !== 0) {
        return severityDelta;
      }
      return left.id.localeCompare(right.id);
    })[0] ?? null
  );
}

function buildLatestFilingOrEventHighlight(
  changes: CompanyChangesSinceLastFilingResponse | null,
  activityOverview: CompanyActivityOverviewResponse | null,
): WhatChangedHighlightItem | null {
  const filingDate =
    changes?.current_filing?.filing_acceptance_at ??
    changes?.current_filing?.fetch_timestamp ??
    changes?.summary.current_period_end ??
    null;
  const latestEntry = activityOverview?.entries[0] ?? null;
  const entryDate = latestEntry?.date ?? null;

  const chooseEntry = asTimestamp(entryDate) > asTimestamp(filingDate);

  if (chooseEntry && latestEntry) {
    return {
      id: "latest-event",
      title: "Latest filing/event",
      detail: latestEntry.title,
      occurredAt: latestEntry.date,
      severity: inferActivitySeverity(activityOverview),
      sourceLabel: resolvePrimarySourceLabel(activityOverview?.provenance),
      provenance: summarizeProvenance(activityOverview?.provenance),
    };
  }

  if (!changes?.current_filing) {
    return null;
  }

  const filing = changes.current_filing;
  const highSignalCount = changes.summary.high_signal_change_count;

  return {
    id: "latest-filing",
    title: "Latest filing/event",
    detail: `${filing.filing_type} covering ${formatDate(filing.period_end)} with ${highSignalCount.toLocaleString()} high-signal change${highSignalCount === 1 ? "" : "s"}.`,
    occurredAt: filingDate,
    severity: highSignalCount > 0 ? "high" : "medium",
    sourceLabel: resolvePrimarySourceLabel(changes.provenance),
    provenance: summarizeProvenance(changes.provenance),
  };
}

function buildFinancialMovementHighlight(
  changes: CompanyChangesSinceLastFilingResponse | null,
  earningsSummary: CompanyEarningsSummaryResponse | null,
): WhatChangedHighlightItem | null {
  const candidate = pickLargestFinancialMetricDelta(changes?.metric_deltas ?? []);
  if (candidate) {
    const absRelativeChange = Math.abs(candidate.relative_change ?? 0);

    return {
      id: `financial-${candidate.metric_key}`,
      title: "Financial movement",
      detail: formatMetricDeltaDetail(candidate),
      occurredAt: changes?.summary.current_period_end ?? null,
      severity: absRelativeChange >= 0.25 ? "high" : absRelativeChange >= 0.1 ? "medium" : "low",
      sourceLabel: resolvePrimarySourceLabel(changes?.provenance),
      provenance: summarizeProvenance(changes?.provenance),
    };
  }

  if (!earningsSummary?.summary.latest_reported_period_end) {
    return null;
  }

  return {
    id: "financial-earnings-latest",
    title: "Financial movement",
    detail: `Latest earnings report shows revenue ${formatUsd(earningsSummary.summary.latest_revenue)} and diluted EPS ${formatCompactNumber(earningsSummary.summary.latest_diluted_eps)}.`,
    occurredAt: earningsSummary.summary.latest_reported_period_end,
    severity: "low",
    sourceLabel: "Earnings summary",
    provenance: "Earnings release extracts",
  };
}

function buildModelMovementHighlight(models: CompanyModelsResponse | null): WhatChangedHighlightItem | null {
  const model = models?.models.find((entry) => entry.model_name === "dcf") ?? models?.models[0] ?? null;
  if (!model) {
    return null;
  }

  const latestValue = extractModelAnchor(model);
  const previousValue = findPreviousModelAnchor(models?.models ?? [], model);

  if (latestValue == null) {
    return null;
  }

  if (previousValue != null && previousValue !== 0) {
    const changeRatio = (latestValue - previousValue) / Math.abs(previousValue);
    const severity = Math.abs(changeRatio) >= 0.15 ? "high" : Math.abs(changeRatio) >= 0.05 ? "medium" : "low";

    return {
      id: `model-${model.model_name}`,
      title: "Valuation/model movement",
      detail: `${model.model_name.toUpperCase()} anchor moved ${formatPercent(changeRatio)} to ${formatUsd(latestValue)}.`,
      occurredAt: model.created_at,
      severity,
      sourceLabel: resolvePrimarySourceLabel(models?.provenance),
      provenance: summarizeProvenance(models?.provenance),
    };
  }

  return {
    id: `model-${model.model_name}`,
    title: "Valuation/model movement",
    detail: `Latest ${model.model_name.toUpperCase()} anchor is ${formatUsd(latestValue)} (no prior cached anchor to compute a delta).`,
    occurredAt: model.created_at,
    severity: "low",
    sourceLabel: resolvePrimarySourceLabel(models?.provenance),
    provenance: summarizeProvenance(models?.provenance),
  };
}

function buildOwnershipHighlight(ownershipSummary: CompanyBeneficialOwnershipSummaryResponse | null): WhatChangedHighlightItem | null {
  const summary = ownershipSummary?.summary;
  if (!summary?.latest_event_date) {
    return null;
  }

  const decreases = summary.ownership_decrease_events;
  const increases = summary.ownership_increase_events;
  const severity = decreases > increases && decreases >= 3 ? "high" : decreases > increases ? "medium" : "low";

  return {
    id: "ownership-signal",
    title: "Ownership signal",
    detail: `${summary.total_filings.toLocaleString()} major-holder filings: ${increases.toLocaleString()} increase vs ${decreases.toLocaleString()} decrease events.`,
    occurredAt: summary.latest_event_date,
    severity,
    sourceLabel: "Beneficial ownership summary",
    provenance: "SEC Schedule 13D/13G filings",
  };
}

function buildGovernanceHighlight(governanceSummary: CompanyGovernanceSummaryResponse | null): WhatChangedHighlightItem | null {
  const summary = governanceSummary?.summary;
  if (!summary) {
    return null;
  }

  const hasDatedEvidence = Boolean(summary.latest_meeting_date);
  if (!hasDatedEvidence && summary.total_filings === 0) {
    return null;
  }

  return {
    id: "governance-signal",
    title: "Governance signal",
    detail: `${summary.total_filings.toLocaleString()} proxy filings with up to ${summary.max_vote_item_count.toLocaleString()} vote items in a meeting packet.`,
    occurredAt: summary.latest_meeting_date,
    severity: summary.max_vote_item_count >= 8 ? "medium" : "low",
    sourceLabel: "Governance summary",
    provenance: "SEC DEF 14A / DEFA14A filings",
  };
}

function buildAlertPressureHighlight(activityOverview: CompanyActivityOverviewResponse | null): WhatChangedHighlightItem | null {
  const summary = activityOverview?.summary;
  if (!summary || summary.total === 0) {
    return null;
  }

  const latestHigh = activityOverview?.alerts.find((alert) => alert.level === "high") ?? null;

  return {
    id: "activity-alert-pressure",
    title: "Alert pressure",
    detail: `${summary.high.toLocaleString()} high, ${summary.medium.toLocaleString()} medium, and ${summary.low.toLocaleString()} low alerts are active.`,
    occurredAt: latestHigh?.date ?? activityOverview?.alerts[0]?.date ?? null,
    severity: summary.high > 0 ? "high" : summary.medium > 0 ? "medium" : "low",
    sourceLabel: resolvePrimarySourceLabel(activityOverview?.provenance),
    provenance: summarizeProvenance(activityOverview?.provenance),
  };
}

function pickLargestFinancialMetricDelta(metricDeltas: FilingComparisonMetricDeltaPayload[]): FilingComparisonMetricDeltaPayload | null {
  const filtered = metricDeltas.filter((delta) => {
    if (delta.relative_change == null) {
      return false;
    }

    const candidateText = `${delta.metric_key} ${delta.label}`;
    return FINANCIAL_METRIC_MATCHERS.some((matcher) => matcher.test(candidateText));
  });

  if (!filtered.length) {
    return null;
  }

  return filtered.sort((left, right) => Math.abs(right.relative_change ?? 0) - Math.abs(left.relative_change ?? 0))[0] ?? null;
}

function formatMetricDeltaDetail(metric: FilingComparisonMetricDeltaPayload): string {
  const direction = metric.relative_change != null && metric.relative_change >= 0 ? "up" : "down";
  const relative = metric.relative_change != null ? formatPercent(Math.abs(metric.relative_change)) : "—";
  const current = formatMetricValue(metric.current_value, metric.unit);
  const previous = formatMetricValue(metric.previous_value, metric.unit);

  return `${metric.label} is ${direction} ${relative} (${previous} -> ${current}).`;
}

function formatMetricValue(value: number | null, unit: FilingComparisonMetricDeltaPayload["unit"]): string {
  if (value == null) {
    return "—";
  }

  if (unit === "usd" || unit === "usd_per_share") {
    return formatUsd(value);
  }

  if (unit === "ratio") {
    return formatPercent(value);
  }

  return formatCompactNumber(value);
}

function formatUsd(value: number | null): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `$${formatCompactNumber(value)}`;
}

function asTimestamp(value: string | null | undefined): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function inferActivitySeverity(activityOverview: CompanyActivityOverviewResponse | null): WhatChangedSeverity {
  const summary = activityOverview?.summary;
  if (!summary) {
    return "low";
  }

  if (summary.high > 0) {
    return "high";
  }
  if (summary.medium > 0) {
    return "medium";
  }
  return "low";
}

function resolvePrimarySourceLabel(provenance: ProvenanceEntryPayload[] | null | undefined): string {
  if (!provenance?.length) {
    return "Cached dataset";
  }
  const primary = provenance.find((entry) => entry.role === "primary");
  return (primary ?? provenance[0]).display_label;
}

function summarizeProvenance(provenance: ProvenanceEntryPayload[] | null | undefined): string {
  if (!provenance?.length) {
    return "Provenance unavailable";
  }

  const labels = provenance.map((entry) => entry.display_label);
  const preview = labels.slice(0, 2).join(" + ");
  const remainder = labels.length > 2 ? ` (+${(labels.length - 2).toLocaleString()} more)` : "";
  return `${preview}${remainder}`;
}

function extractModelAnchor(model: ModelPayload): number | null {
  if (model.model_name === "dcf") {
    return asNumber(model.result.fair_value_per_share);
  }

  if (model.model_name === "residual_income") {
    const intrinsic = asRecord(model.result.intrinsic_value);
    return asNumber(intrinsic.intrinsic_value_per_share);
  }

  return asNumber(model.result.fair_value_per_share) ?? asNumber(model.result.intrinsic_value_per_share);
}

function findPreviousModelAnchor(models: ModelPayload[], currentModel: ModelPayload): number | null {
  const sameModelSeries = models
    .filter((entry) => entry.model_name === currentModel.model_name && entry.created_at !== currentModel.created_at)
    .sort((left, right) => asTimestamp(right.created_at) - asTimestamp(left.created_at));

  for (const entry of sameModelSeries) {
    const value = extractModelAnchor(entry);
    if (value != null) {
      return value;
    }
  }

  return null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

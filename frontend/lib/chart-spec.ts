import type {
  CompanyChartsAssumptionsCardPayload,
  CompanyChartsCardPayload,
  CompanyChartsCardsPayload,
  CompanyChartsComparisonCardPayload,
  CompanyChartsDashboardResponse,
  CompanyChartsOutlookSpecPayload,
  CompanyChartsProjectionStudioPayload,
  CompanyChartsSpecPayload,
  CompanyChartsStudioSpecPayload,
} from "@/lib/types";

export const COMPANY_CHART_SPEC_SCHEMA_VERSION = "company_chart_spec_v1";

const OUTLOOK_PRIMARY_CARD_ORDER = ["revenue", "revenue_growth", "profit_metric", "cash_flow_metric", "eps"] as const;
const OUTLOOK_SECONDARY_CARD_ORDER = ["revenue_outlook_bridge", "margin_path", "fcf_outlook"] as const;
const OUTLOOK_COMPARISON_CARD_ORDER = ["growth_summary"] as const;
const OUTLOOK_DETAIL_CARD_ORDER = ["forecast_assumptions", "forecast_calculations"] as const;
const PROJECTION_STUDIO_SUMMARY = "Inspection of projected values, sensitivities, waterfall bridges, and traceable formulas.";
const EMPTY_EVENT_OVERLAY = {
  title: "Event overlays",
  available_event_types: [],
  default_enabled_event_types: [],
  events: [],
  sparse_data_note: null,
} as const;
const EMPTY_QUARTER_CHANGE = {
  title: "What changed since last quarter?",
  latest_period_label: null,
  prior_period_label: null,
  summary: null,
  items: [],
  empty_state: "Not enough period history for a change summary yet.",
} as const;

type OrderedMetricCardKey = (typeof OUTLOOK_PRIMARY_CARD_ORDER)[number] | (typeof OUTLOOK_SECONDARY_CARD_ORDER)[number];
type OrderedComparisonCardKey = (typeof OUTLOOK_COMPARISON_CARD_ORDER)[number];
type OrderedDetailCardKey = (typeof OUTLOOK_DETAIL_CARD_ORDER)[number];

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isCompanyChartsSpecPayload(value: unknown): value is CompanyChartsSpecPayload {
  if (!isObjectRecord(value)) {
    return false;
  }

  return (
    typeof value.schema_version === "string" &&
    typeof value.payload_version === "string" &&
    Array.isArray(value.available_modes) &&
    typeof value.default_mode === "string" &&
    isObjectRecord(value.outlook)
  );
}

export function buildCompanyChartsSpecFromPayload(payload: CompanyChartsDashboardResponse): CompanyChartsSpecPayload {
  if (isCompanyChartsSpecPayload(payload.chart_spec)) {
    return payload.chart_spec;
  }

  return {
    schema_version: COMPANY_CHART_SPEC_SCHEMA_VERSION,
    payload_version: payload.payload_version,
    company: payload.company,
    build_state: payload.build_state,
    build_status: payload.build_status,
    refresh: payload.refresh,
    diagnostics: payload.diagnostics,
    provenance: payload.provenance,
    as_of: payload.as_of,
    last_refreshed_at: payload.last_refreshed_at,
    source_mix: payload.source_mix,
    confidence_flags: payload.confidence_flags,
    available_modes: payload.projection_studio ? ["outlook", "studio"] : ["outlook"],
    default_mode: "outlook",
    outlook: {
      title: payload.title,
      summary: payload.summary,
      legend: payload.legend,
      cards: payload.cards,
      primary_card_order: presentCardOrder(payload.cards, OUTLOOK_PRIMARY_CARD_ORDER),
      secondary_card_order: presentCardOrder(payload.cards, OUTLOOK_SECONDARY_CARD_ORDER),
      comparison_card_order: presentCardOrder(payload.cards, OUTLOOK_COMPARISON_CARD_ORDER),
      detail_card_order: presentCardOrder(payload.cards, OUTLOOK_DETAIL_CARD_ORDER),
      methodology: payload.forecast_methodology,
      forecast_diagnostics: payload.forecast_diagnostics ?? {
        score_key: "forecast_stability",
        score_name: "Forecast Stability",
        heuristic: true,
        final_score: null,
        summary: null,
        history_depth_years: 0,
        thin_history: false,
        growth_volatility: null,
        growth_volatility_band: null,
        missing_data_penalty: 0,
        quality_score: null,
        missing_inputs: [],
        sample_size: 0,
        scenario_dispersion: null,
        sector_template: null,
        guidance_usage: null,
        historical_backtest_error_band: null,
        backtest_weighted_error: null,
        backtest_horizon_errors: {},
        backtest_metric_weights: {},
        backtest_metric_errors: {},
        backtest_metric_horizon_errors: {},
        backtest_metric_sample_sizes: {},
        components: [],
      },
      event_overlay: payload.event_overlay ?? EMPTY_EVENT_OVERLAY,
      quarter_change: payload.quarter_change ?? EMPTY_QUARTER_CHANGE,
    },
    studio: payload.projection_studio
      ? {
          title: "Projection Studio",
          summary: PROJECTION_STUDIO_SUMMARY,
          projection_studio: payload.projection_studio,
          what_if: payload.what_if,
        }
      : null,
  };
}

export function serializeCompanyChartsSpec(spec: CompanyChartsSpecPayload): string {
  return JSON.stringify(spec);
}

export function deserializeCompanyChartsSpec(input: string | CompanyChartsSpecPayload | null | undefined): CompanyChartsSpecPayload | null {
  if (!input) {
    return null;
  }

  if (typeof input === "string") {
    try {
      const parsed = JSON.parse(input) as unknown;
      return isCompanyChartsSpecPayload(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }

  return isCompanyChartsSpecPayload(input) ? input : null;
}

export function getCompanyChartsOutlookSpec(payload: CompanyChartsDashboardResponse): CompanyChartsOutlookSpecPayload {
  return buildCompanyChartsSpecFromPayload(payload).outlook;
}

export function getCompanyChartsStudioSpec(payload: CompanyChartsDashboardResponse): CompanyChartsStudioSpecPayload | null {
  return buildCompanyChartsSpecFromPayload(payload).studio;
}

export function getOrderedOutlookMetricCards(spec: CompanyChartsOutlookSpecPayload, lane: "primary" | "secondary"): CompanyChartsCardPayload[] {
  const order = lane === "primary" ? spec.primary_card_order : spec.secondary_card_order;
  return order
    .map((key) => getMetricCard(spec.cards, key as OrderedMetricCardKey))
    .filter((card): card is CompanyChartsCardPayload => card !== null);
}

export function getOrderedOutlookComparisonCards(spec: CompanyChartsOutlookSpecPayload): CompanyChartsComparisonCardPayload[] {
  return spec.comparison_card_order
    .map((key) => getComparisonCard(spec.cards, key as OrderedComparisonCardKey))
    .filter((card): card is CompanyChartsComparisonCardPayload => card !== null);
}

export function getOrderedOutlookDetailCards(spec: CompanyChartsOutlookSpecPayload): CompanyChartsAssumptionsCardPayload[] {
  return spec.detail_card_order
    .map((key) => getDetailCard(spec.cards, key as OrderedDetailCardKey))
    .filter((card): card is CompanyChartsAssumptionsCardPayload => card !== null);
}

function presentCardOrder<T extends keyof CompanyChartsCardsPayload>(cards: CompanyChartsCardsPayload, order: readonly T[]): T[] {
  return order.filter((key) => cards[key] != null);
}

function getMetricCard(cards: CompanyChartsCardsPayload, key: OrderedMetricCardKey): CompanyChartsCardPayload | null {
  const card = cards[key];
  return card ?? null;
}

function getComparisonCard(cards: CompanyChartsCardsPayload, key: OrderedComparisonCardKey): CompanyChartsComparisonCardPayload | null {
  const card = cards[key];
  return card ?? null;
}

function getDetailCard(cards: CompanyChartsCardsPayload, key: OrderedDetailCardKey): CompanyChartsAssumptionsCardPayload | null {
  const card = cards[key];
  return card ?? null;
}

export function getStudioProjectionPayload(payload: CompanyChartsDashboardResponse): CompanyChartsProjectionStudioPayload | null {
  return getCompanyChartsStudioSpec(payload)?.projection_studio ?? payload.projection_studio;
}

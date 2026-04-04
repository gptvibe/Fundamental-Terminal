import type { CompanyPayload, ModelEvaluationResponse } from "@/lib/types";

export function supportsOilWorkspace(status: string | null | undefined): boolean {
  return status === "supported" || status === "partial";
}

export function companySupportsOilWorkspace(company: CompanyPayload | null | undefined): boolean {
  return supportsOilWorkspace(company?.oil_support_status);
}

export function describeOilSupportReason(reason: string): string {
  switch (reason) {
    case "non_energy_classification":
      return "The issuer is not currently classified as an energy or oil-exposed company.";
    case "oilfield_services_not_supported_v1":
      return "v1 does not model oilfield-services economics yet.";
    case "midstream_not_supported_v1":
      return "v1 does not model midstream or pipeline oil economics yet.";
    case "refining_margin_exposure_partial_v1":
      return "Refiner economics are only partially supported because v1 is built around producer-style realized-versus-benchmark dynamics.";
    case "oil_taxonomy_unresolved_v1":
      return "The issuer's oil exposure could not be resolved from the current classification signals.";
    case "integrated_oil_supported_v1":
      return "Integrated upstream producer economics are supported in v1.";
    case "upstream_oil_supported_v1":
      return "Upstream producer economics are supported in v1.";
    default:
      return reason.includes(":") ? reason.replace(":", ": ") : humanizeFlag(reason);
  }
}

export function describeOilOverlayAvailability(reasons: string[]): string {
  if (reasons.includes("non_energy_classification")) {
    return "the issuer is not currently classified as an energy or oil-exposed company.";
  }
  if (reasons.includes("oilfield_services_not_supported_v1")) {
    return "v1 does not model oilfield-services economics yet.";
  }
  if (reasons.includes("midstream_not_supported_v1")) {
    return "v1 does not model midstream or pipeline oil economics yet.";
  }
  if (reasons.includes("oil_taxonomy_unresolved_v1")) {
    return "the issuer's oil exposure could not be resolved from the current classification signals.";
  }
  return "this issuer is not currently supported by the oil scenario overlay.";
}

export function resolveOilOverlayEvaluationSummary(
  ticker: string,
  oilOverlayEvaluation: ModelEvaluationResponse | null,
): {
  sampleCount: number | null;
  maeLift: number | null;
  improvementRate: number | null;
  asOf: string | null;
  description: string;
} | null {
  const run = oilOverlayEvaluation?.run;
  if (!run) {
    return null;
  }
  const summary = asRecord(run.summary);
  const artifacts = asRecord(run.artifacts);
  const comparison = asRecord(summary.comparison ?? artifacts.comparison);
  const companySummaries = asRecord(artifacts.company_summaries);
  const companySummary = asRecord(companySummaries[ticker]);

  const sampleCount = asNumber(companySummary.sample_count ?? comparison.sample_count);
  const maeLift = asNumber(companySummary.mean_absolute_error_lift ?? comparison.mean_absolute_error_lift);
  const improvementRate = asNumber(companySummary.improvement_rate ?? comparison.improvement_rate);
  const asOf = asString(companySummary.latest_as_of ?? summary.latest_as_of ?? run.completed_at)?.slice(0, 10) ?? null;
  const description = companySummary.ticker
    ? `${ticker} point-in-time comparison of the base model versus base-plus-oil-overlay.`
    : "Latest point-in-time comparison across supported oil names in the historical overlay harness.";

  return { sampleCount, maeLift, improvementRate, asOf, description };
}

function humanizeFlag(value: string): string {
  return value.replaceAll("_", " ");
}

function asRecord(value: unknown): Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length ? value : null;
}
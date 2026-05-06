import type {
  CompanyChartsDashboardResponse,
  CompanyChartsForecastAccuracyResponse,
  CompanyChartsScenarioCloneRequest,
  CompanyChartsScenarioDetailPayload,
  CompanyChartsScenarioListResponse,
  CompanyChartsShareSnapshotPayload,
  CompanyChartsShareSnapshotRecordPayload,
  CompanyChartsScenarioUpsertRequest,
  CompanyChartsWhatIfRequest,
  ModelEvaluationResponse,
  CompanyModelsResponse,
} from "@/lib/types";
import { appendAsOf, buildProjectionStudioViewerHeader, fetchAndParse, fetchJson } from "./client";

export function getCompanyCharts(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChartsDashboardResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts${suffix}`, { signal: options?.signal });
}

export function getCompanyChartsForecastAccuracy(
  ticker: string,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChartsForecastAccuracyResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/forecast-accuracy${suffix}`, { signal: options?.signal });
}

export function getCompanyChartsWhatIf(
  ticker: string,
  body: CompanyChartsWhatIfRequest,
  options?: { asOf?: string | null; signal?: AbortSignal }
): Promise<CompanyChartsDashboardResponse> {
  const params = new URLSearchParams();
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/what-if${suffix}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export function createCompanyChartsShareSnapshot(
  ticker: string,
  body: CompanyChartsShareSnapshotPayload,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsShareSnapshotRecordPayload> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/share-snapshots`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export function getCompanyChartsShareSnapshot(
  ticker: string,
  snapshotId: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsShareSnapshotRecordPayload> {
  return fetchAndParse(`/companies/${encodeURIComponent(ticker)}/charts/share-snapshots/${encodeURIComponent(snapshotId)}`, {
    cache: "no-store",
    signal: options?.signal,
  });
}

export function listCompanyChartsScenarios(
  ticker: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsScenarioListResponse> {
  return fetchAndParse(`/companies/${encodeURIComponent(ticker)}/charts/scenarios`, {
    headers: buildProjectionStudioViewerHeader(),
    cache: "no-store",
    signal: options?.signal,
  });
}

export function getCompanyChartsScenario(
  ticker: string,
  scenarioId: string,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsScenarioDetailPayload> {
  return fetchAndParse(`/companies/${encodeURIComponent(ticker)}/charts/scenarios/${encodeURIComponent(scenarioId)}`, {
    headers: buildProjectionStudioViewerHeader(),
    cache: "no-store",
    signal: options?.signal,
  });
}

export function createCompanyChartsScenario(
  ticker: string,
  body: CompanyChartsScenarioUpsertRequest,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsScenarioDetailPayload> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/scenarios`, {
    method: "POST",
    headers: {
      ...buildProjectionStudioViewerHeader(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export function updateCompanyChartsScenario(
  ticker: string,
  scenarioId: string,
  body: CompanyChartsScenarioUpsertRequest,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsScenarioDetailPayload> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/scenarios/${encodeURIComponent(scenarioId)}`, {
    method: "POST",
    headers: {
      ...buildProjectionStudioViewerHeader(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export function cloneCompanyChartsScenario(
  ticker: string,
  scenarioId: string,
  body: CompanyChartsScenarioCloneRequest,
  options?: { signal?: AbortSignal }
): Promise<CompanyChartsScenarioDetailPayload> {
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/charts/scenarios/${encodeURIComponent(scenarioId)}/clone`, {
    method: "POST",
    headers: {
      ...buildProjectionStudioViewerHeader(),
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
    signal: options?.signal,
  });
}

export function getCompanyModels(
  ticker: string,
  modelNames?: string[],
  options?: { dupontMode?: "auto" | "annual" | "ttm"; asOf?: string | null; expandInputPeriods?: boolean; signal?: AbortSignal }
): Promise<CompanyModelsResponse> {
  const params = new URLSearchParams();
  if (modelNames?.length) {
    params.set("model", modelNames.join(","));
  }
  if (options?.expandInputPeriods) {
    params.set("expand", "input_periods");
  }
  if (options?.dupontMode) {
    params.set("dupont_mode", options.dupontMode);
  }
  appendAsOf(params, options?.asOf);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/companies/${encodeURIComponent(ticker)}/models${suffix}`, { signal: options?.signal });
}

export function getLatestModelEvaluation(
  suiteKey?: string | null,
  options?: { signal?: AbortSignal }
): Promise<ModelEvaluationResponse> {
  const params = new URLSearchParams();
  if (suiteKey) {
    params.set("suite_key", suiteKey);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/model-evaluations/latest${suffix}`, { signal: options?.signal });
}

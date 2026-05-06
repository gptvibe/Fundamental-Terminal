import type {
  CacheMetricsResponse,
  SourceRegistryResponse,
} from "@/lib/types";
import { fetchJson } from "./client";

export function getSourceRegistry(): Promise<SourceRegistryResponse> {
  return fetchJson("/source-registry");
}

export function getCacheMetrics(): Promise<CacheMetricsResponse> {
  return fetchJson("/internal/cache-metrics");
}

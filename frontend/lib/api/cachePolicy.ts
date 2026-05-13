import type { ReadCachePolicy } from "./types";

export const DEFAULT_READ_POLICY: ReadCachePolicy = {
  ttlMs: 45_000,
  staleMs: 180_000,
};

export const STABLE_SEC_POLICY: ReadCachePolicy = {
  // SEC filings and historical statements change infrequently once published.
  // A longer fresh window avoids unnecessary tab-to-tab refetches for stable pages.
  ttlMs: 600_000,
  staleMs: 3_600_000,
};

export const READ_POLICY_BY_PATH: Array<{ pattern: RegExp; policy: ReadCachePolicy }> = [
  { pattern: /^\/companies\/search\?/, policy: { ttlMs: 20_000, staleMs: 90_000 } },
  { pattern: /^\/screener\/filters(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/companies\/[^/]+\/financials(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/overview(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/workspace-bootstrap(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/segment-history(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/capital-structure(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/charts(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/brief(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/filing-risk-signals(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/earnings\/summary(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
  { pattern: /^\/companies\/[^/]+\/models(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/oil-scenario(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/oil-scenario-overlay(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/model-evaluations\/latest(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 240_000 } },
  { pattern: /^\/companies\/[^/]+\/peers(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/governance(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/ownership(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/institutional-holdings(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/beneficial-ownership(?:\?|$)/, policy: STABLE_SEC_POLICY },
  { pattern: /^\/companies\/[^/]+\/sector-context(?:\?|$)/, policy: { ttlMs: 45_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/metrics(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/metrics-timeseries(?:\?|$)/, policy: { ttlMs: 60_000, staleMs: 180_000 } },
  { pattern: /^\/companies\/[^/]+\/market-context(?:\?|$)/, policy: { ttlMs: 20_000, staleMs: 90_000 } },
  { pattern: /^\/market-context(?:\?|$)/, policy: { ttlMs: 20_000, staleMs: 90_000 } },
  { pattern: /^\/jobs\/[^/]+(?:\/status|\/progress|\/events)?(?:\?|$)/, policy: { ttlMs: 5_000, staleMs: 20_000 } },
  { pattern: /^\/source-registry(?:\?|$)/, policy: { ttlMs: 300_000, staleMs: 900_000 } },
  { pattern: /^\/watchlist\/summary(?:\?|$)/, policy: { ttlMs: 30_000, staleMs: 120_000 } },
];

export function resolveReadPolicy(path: string): ReadCachePolicy {
  return READ_POLICY_BY_PATH.find((entry) => entry.pattern.test(path))?.policy ?? DEFAULT_READ_POLICY;
}

export function isReadRequest(init?: RequestInit): boolean {
  return !init?.method || init.method.toUpperCase() === "GET";
}

export function shouldBypassReadCache(path: string): boolean {
  if (/^\/companies\/compare(?:\?|$)/.test(path)) {
    return true;
  }

  if (path.includes("/refresh")) {
    return true;
  }

  const queryIndex = path.indexOf("?");
  if (queryIndex < 0) {
    return false;
  }

  const params = new URLSearchParams(path.slice(queryIndex + 1));
  if (/^\/companies\/[^/]+\/workspace-bootstrap(?:\?|$)/.test(path) && params.get("include_overview_brief") === "true") {
    return true;
  }

  return params.get("refresh") === "true";
}

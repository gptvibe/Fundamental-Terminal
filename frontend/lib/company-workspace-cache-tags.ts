export const COMPANY_WORKSPACE_CACHE_TAG_PREFIX = "company-workspace";

export function normalizeCompanyWorkspaceCacheTicker(ticker: string): string {
  return ticker.trim().toUpperCase();
}

export function buildCompanyWorkspaceCacheTags(ticker: string): string[] {
  const normalizedTicker = normalizeCompanyWorkspaceCacheTicker(ticker);
  const baseTag = `${COMPANY_WORKSPACE_CACHE_TAG_PREFIX}:${normalizedTicker}`;

  return [baseTag, `${baseTag}:latest`];
}

export function buildCompanyFinancialsCacheTags(ticker: string): string[] {
  const normalizedTicker = normalizeCompanyWorkspaceCacheTicker(ticker);
  const baseTag = `${COMPANY_WORKSPACE_CACHE_TAG_PREFIX}:${normalizedTicker}`;

  return [...buildCompanyWorkspaceCacheTags(normalizedTicker), `${baseTag}:financials`];
}
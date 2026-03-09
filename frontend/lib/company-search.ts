import type { CompanyPayload } from "@/lib/types";

export function normalizeSearchText(value: string): string {
  return value.replace(/\$/g, "").trimStart();
}

export function findExactSearchMatch(results: CompanyPayload[], query: string): CompanyPayload | null {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return null;
  }

  return results.find((result) => result.ticker.toLowerCase() === normalizedQuery || result.name.toLowerCase() === normalizedQuery) ?? null;
}

export function buildSuggestionMeta(result: CompanyPayload): string {
  const metadata = [result.sector, result.market_industry ?? result.market_sector].filter(Boolean);
  return metadata.length ? metadata.join(" · ") : "Company workspace";
}

export function getPreferredSuggestion(results: CompanyPayload[], query: string, activeIndex: number): CompanyPayload | null {
  return results[activeIndex] ?? findExactSearchMatch(results, query) ?? results[0] ?? null;
}

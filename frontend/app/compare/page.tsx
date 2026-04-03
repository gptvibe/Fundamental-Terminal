import { ComparePageClient } from "@/components/compare/compare-page-client";

interface ComparePageProps {
  searchParams?: { tickers?: string | string[] | undefined };
}

export default function ComparePage({ searchParams }: ComparePageProps) {
  const rawTickers = searchParams?.tickers;
  const tickers = parseTickers(Array.isArray(rawTickers) ? rawTickers.join(",") : rawTickers ?? null);
  return <ComparePageClient tickers={tickers} />;
}

function parseTickers(value: string | null): string[] {
  if (!value) {
    return [];
  }

  return [...new Set(value.split(",").map((ticker) => ticker.trim().toUpperCase()).filter(Boolean))].slice(0, 5);
}
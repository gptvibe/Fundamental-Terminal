"use client";

import { ReactNode, useCallback, useMemo, useRef, useState } from "react";

import { searchCompanies } from "@/lib/api";
import type { CompanyPayload } from "@/lib/types";
import { useGoToTicker } from "@/hooks/use-go-to-ticker";
import "./home-search.css";

const SEARCH_DEBOUNCE_MS = 275;
const MIN_QUERY_LENGTH = 2;
const SEARCH_CACHE_MAX = 50;

interface SearchCacheEntry {
  query: string;
  results: CompanyPayload[];
  timestamp: number;
}

export function HomeSearch({ railContent }: { railContent: ReactNode }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CompanyPayload[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const searchCache = useRef<SearchCacheEntry[]>([]);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const goToTicker = useGoToTicker();

  // Check search cache
  const getCachedResults = useCallback((q: string) => {
    const normalizedQ = q.trim().toUpperCase();
    return searchCache.current.find(
      (entry) => entry.query === normalizedQ
    )?.results;
  }, []);

  // Execute search
  const performSearch = useCallback(
    async (q: string) => {
      const normalizedQ = q.trim().toUpperCase();

      if (normalizedQ.length < MIN_QUERY_LENGTH) {
        setResults([]);
        setShowResults(false);
        return;
      }

      // Check cache first
      const cached = getCachedResults(normalizedQ);
      if (cached) {
        setResults(cached);
        setShowResults(true);
        return;
      }

      try {
        setIsLoading(true);
        const response = await searchCompanies(normalizedQ, {
          refresh: false,
        });

        // Store in cache
        if (searchCache.current.length >= SEARCH_CACHE_MAX) {
          searchCache.current.shift();
        }
        searchCache.current.push({
          query: normalizedQ,
          results: response.results,
          timestamp: Date.now(),
        });

        setResults(response.results);
        setShowResults(true);
      } catch (err) {
        setResults([]);
        setShowResults(false);
      } finally {
        setIsLoading(false);
      }
    },
    [getCachedResults]
  );

  // Debounced search handler
  const handleQueryChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newQuery = e.target.value;
      setQuery(newQuery);

      if (debounceTimer.current) {
        clearTimeout(debounceTimer.current);
      }

      if (!newQuery.trim()) {
        setResults([]);
        setShowResults(false);
        return;
      }

      debounceTimer.current = setTimeout(() => {
        void performSearch(newQuery);
      }, SEARCH_DEBOUNCE_MS);
    },
    [performSearch]
  );

  const handleResultClick = useCallback(
    (ticker: string) => {
      goToTicker(ticker, "company");
      setQuery("");
      setResults([]);
      setShowResults(false);
    },
    [goToTicker]
  );

  return (
    <div className="home-search-container">
      <div className="home-search-column">
        <div className="home-search-box">
          <input
            type="text"
            placeholder="Search companies by name or ticker…"
            value={query}
            onChange={handleQueryChange}
            onFocus={() => results.length > 0 && setShowResults(true)}
            onBlur={() => setTimeout(() => setShowResults(false), 150)}
            className="home-search-input"
            aria-label="Company search"
          />
          {isLoading && (
            <div className="home-search-spinner" aria-hidden="true" />
          )}
        </div>

        {showResults && results.length > 0 && (
          <div className="home-search-dropdown">
            {results.map((result) => (
              <button
                key={result.ticker}
                onClick={() => handleResultClick(result.ticker)}
                className="home-search-result-item"
                type="button"
              >
                <div className="home-search-result-header">
                  <span className="home-search-result-ticker">
                    {result.ticker}
                  </span>
                  <span className="home-search-result-name">
                    {result.name}
                  </span>
                </div>
                {result.sector && (
                  <div className="home-search-result-sector">
                    {result.sector}
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="home-search-rail">{railContent}</div>
    </div>
  );
}

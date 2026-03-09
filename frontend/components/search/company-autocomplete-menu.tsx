"use client";

import type { CompanyPayload } from "@/lib/types";
import { buildSuggestionMeta } from "@/lib/company-search";

interface CompanyAutocompleteMenuProps {
  id: string;
  results: CompanyPayload[];
  loading: boolean;
  activeIndex: number;
  onHover: (index: number) => void;
  onSelect: (result: CompanyPayload) => void;
  emptyMessage?: string;
}

export function CompanyAutocompleteMenu({ id, results, loading, activeIndex, onHover, onSelect, emptyMessage = "No exact match yet. Press Enter to try it as a ticker." }: CompanyAutocompleteMenuProps) {
  return (
    <div className="app-topbar-autocomplete" id={id} role="listbox" aria-label="Company suggestions">
      {loading ? (
        <div className="app-topbar-autocomplete-state">Searching companies...</div>
      ) : results.length ? (
        results.map((result, index) => (
          <button
            key={result.ticker}
            type="button"
            role="option"
            aria-selected={index === activeIndex}
            className={`app-topbar-autocomplete-option${index === activeIndex ? " is-active" : ""}`}
            onMouseEnter={() => onHover(index)}
            onMouseDown={(event) => {
              event.preventDefault();
              onSelect(result);
            }}
          >
            <span className="app-topbar-autocomplete-copy">
              <span className="app-topbar-autocomplete-name">{result.name}</span>
              <span className="app-topbar-autocomplete-meta">{buildSuggestionMeta(result)}</span>
            </span>
            <span className="app-topbar-autocomplete-ticker">${result.ticker}</span>
          </button>
        ))
      ) : (
        <div className="app-topbar-autocomplete-state">{emptyMessage}</div>
      )}
    </div>
  );
}

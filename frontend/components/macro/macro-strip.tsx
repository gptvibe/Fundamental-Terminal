"use client";

import { formatDate, formatPercent } from "@/lib/format";
import type { CompanyMarketContextResponse, MacroSeriesItemPayload } from "@/lib/types";

interface MacroStripProps {
  context: CompanyMarketContextResponse | null;
  /** Max number of indicator pills to show. Defaults to 4. */
  maxItems?: number;
}

/**
 * Compact horizontal strip showing key macro indicators for a company.
 * Prefers company-relevant series (relevant_series) if available,
 * otherwise falls back to the top items from rates_credit and inflation_labor.
 */
export function MacroStrip({ context, maxItems = 4 }: MacroStripProps) {
  if (!context) {
    return null;
  }

  const items = selectItems(context, maxItems);
  if (!items.length) {
    return null;
  }

  return (
    <div className="macro-strip" aria-label="Macro indicators">
      <span className="macro-strip-label">Macro</span>
      <div className="macro-strip-items">
        {items.map((item) => (
          <MacroStripPill key={item.series_id} item={item} />
        ))}
      </div>
      {context.sector_exposure?.length ? (
        <div className="macro-strip-exposure">
          {context.sector_exposure.slice(0, 3).map((tag) => (
            <span key={tag} className="macro-strip-tag">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function MacroStripPill({ item }: { item: MacroSeriesItemPayload }) {
  const hasChange = item.change_percent != null;
  const isUp = hasChange && (item.change_percent as number) >= 0;
  const changeClass = hasChange ? (isUp ? "macro-pill-change positive" : "macro-pill-change negative") : "";

  return (
    <div className="macro-strip-pill" title={`${item.label} — ${item.source_name}`}>
      <span className="macro-pill-label">{item.label}</span>
      <span className="macro-pill-value">{formatMacroValue(item)}</span>
      {hasChange ? (
        <span className={changeClass}>
          {isUp ? "▲" : "▼"} {Math.abs((item.change_percent as number) * 100).toFixed(2)}%
        </span>
      ) : null}
      {item.observation_date ? (
        <span className="macro-pill-date">{formatDate(item.observation_date)}</span>
      ) : null}
    </div>
  );
}

function selectItems(context: CompanyMarketContextResponse, maxItems: number): MacroSeriesItemPayload[] {
  const relevant = context.relevant_series ?? [];
  const relevantIndicators = context.relevant_indicators ?? [];
  const allItems = [
    ...relevantIndicators,
    ...(context.rates_credit ?? []),
    ...(context.inflation_labor ?? []),
    ...(context.growth_activity ?? []),
    ...(context.cyclical_demand ?? []),
    ...(context.cyclical_costs ?? []),
  ].filter((item) => item.value != null && item.status !== "unavailable");

  if (relevant.length) {
    const prioritized = allItems.filter((item) => relevant.includes(item.series_id));
    if (prioritized.length >= maxItems) {
      return prioritized.slice(0, maxItems);
    }
    // Top up with remaining items
    const remaining = allItems.filter((item) => !relevant.includes(item.series_id));
    return [...prioritized, ...remaining].slice(0, maxItems);
  }

  // No relevance mapping — show top items from rates_credit then inflation_labor
  return allItems.slice(0, maxItems);
}

function formatMacroValue(item: MacroSeriesItemPayload): string {
  if (item.value == null) {
    return "—";
  }
  if (item.units === "percent") {
    return formatPercent(item.value);
  }
  if (item.units === "thousands") {
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(item.value * 1000);
  }
  if (item.units === "billions_usd") {
    return `$${item.value.toFixed(1)}B`;
  }
  if (item.units === "millions_usd") {
    return item.value >= 1000 ? `$${(item.value / 1000).toFixed(2)}B` : `$${item.value.toFixed(0)}M`;
  }
  return String(item.value);
}

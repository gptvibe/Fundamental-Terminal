"use client";

import { useEffect, useMemo, useState } from "react";

import { getGlobalMarketContext } from "@/lib/api";
import { formatDate, formatPercent } from "@/lib/format";
import type { CompanyMarketContextResponse, MarketFredSeriesPayload } from "@/lib/types";

const MACRO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

interface MacroCard {
  label: string;
  value: string;
  detail: string;
}

function findFredSeries(context: CompanyMarketContextResponse, seriesId: string): MarketFredSeriesPayload | null {
  return context.fred_series.find((item) => item.series_id === seriesId) ?? null;
}

function describeSlope(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "Awaiting update";
  }
  if (value < 0) return "Inverted";
  if (value < 0.005) return "Flat";
  return "Positive";
}

function buildMacroSnapshot(context: CompanyMarketContextResponse | null): { title: string; copy: string; cards: MacroCard[] } {
  if (!context) {
    return {
      title: "Loading macro backdrop",
      copy: "Treasury, credit, and labor context are loading in the background.",
      cards: [
        { label: "10Y Treasury", value: "—", detail: "Treasury curve" },
        { label: "2s10s", value: "—", detail: "Curve slope" },
        { label: "BAA spread", value: "—", detail: "Credit spread" },
        { label: "Unemployment", value: "—", detail: "Labor" },
      ],
    };
  }

  const tenYearPoint = context.curve_points.find((point) => point.tenor === "10y") ?? null;
  const creditSpread = findFredSeries(context, "BAA10Y");
  const unemployment = findFredSeries(context, "UNRATE");
  const slope2s10s = context.slope_2s10s.value;
  const slope3m10y = context.slope_3m10y.value;

  let title = "Macro backdrop is steady";
  let copy = "Keep rates, labor, and credit in view while the company search stays primary.";

  if ((slope3m10y ?? 0) < 0 || (slope2s10s ?? 0) < 0) {
    title = "Curve still looks restrictive";
    copy =
      "The front end remains tighter than the long end, so financing sensitivity should stay in frame while you screen companies.";
  } else if ((creditSpread?.value ?? 0) > 0.03) {
    title = "Credit stress is elevated";
    copy = "Wider BAA spreads raise the bar for balance-sheet quality and refinancing resilience.";
  } else if ((unemployment?.value ?? 0) > 0.045) {
    title = "Labor is softening";
    copy = "A softer labor print can matter more than headline index strength when you build a fresh company brief.";
  }

  return {
    title,
    copy,
    cards: [
      {
        label: "10Y Treasury",
        value: formatPercent(tenYearPoint?.rate ?? null),
        detail: tenYearPoint?.observation_date ? formatDate(tenYearPoint.observation_date) : "Treasury curve",
      },
      {
        label: "2s10s",
        value: formatPercent(slope2s10s),
        detail: describeSlope(slope2s10s),
      },
      {
        label: "BAA spread",
        value: formatPercent(creditSpread?.value ?? null),
        detail: creditSpread?.observation_date ? formatDate(creditSpread.observation_date) : "Credit spread",
      },
      {
        label: "Unemployment",
        value: formatPercent(unemployment?.value ?? null),
        detail: unemployment?.observation_date ? formatDate(unemployment.observation_date) : "Labor backdrop",
      },
    ],
  };
}

export function MarketContextRail() {
  const [macroContext, setMacroContext] = useState<CompanyMarketContextResponse | null>(null);
  const [macroError, setMacroError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const result = await getGlobalMarketContext();
        if (cancelled) return;
        setMacroContext(result);
        setMacroError(null);
      } catch (err) {
        if (cancelled) return;
        setMacroError(err instanceof Error ? err.message : "Unable to load macro snapshot");
      }
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible") void load();
    }

    function onWindowFocus() {
      void load();
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, MACRO_REFRESH_INTERVAL_MS);

    window.addEventListener("focus", onWindowFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);
    void load();

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onWindowFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const macroSnapshot = useMemo(() => buildMacroSnapshot(macroContext), [macroContext]);

  return (
    <div className="home-macro-compact">
      <div className="home-macro-compact-head">
        <div>
          <span className="home-section-kicker">Macro backdrop</span>
          <div className="home-macro-compact-title">{macroSnapshot.title}</div>
        </div>
        <span className="pill">{macroError ? "Issue" : macroContext ? "Live" : "Loading"}</span>
      </div>
      <div className="home-macro-compact-copy">{macroError ?? macroSnapshot.copy}</div>
      <div className="home-macro-compact-grid">
        {macroSnapshot.cards.map((card) => (
          <div key={card.label} className="home-macro-compact-card">
            <div className="home-macro-compact-label">{card.label}</div>
            <div className="home-macro-compact-value">{card.value}</div>
            <div className="home-macro-compact-detail">{card.detail}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

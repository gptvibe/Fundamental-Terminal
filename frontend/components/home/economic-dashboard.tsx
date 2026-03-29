"use client";

import { useState } from "react";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { CompanyMarketContextResponse, MacroSeriesItemPayload, MarketFredSeriesPayload } from "@/lib/types";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";

interface EconomicDashboardProps {
  context: CompanyMarketContextResponse | null;
}

const CURVE_ORDER = ["rrp", "1m", "2m", "3m", "4m", "6m", "1y", "2y", "3y", "5y", "7y", "10y", "20y", "30y"];
const CURVE_DISPLAY_ORDER = ["rrp", "1m", "2m", "3m", "4m", "6m", "1y", "3y", "5y", "7y", "10y", "20y", "30y"];

export function EconomicDashboard({ context }: EconomicDashboardProps) {
  const [showAllFactors, setShowAllFactors] = useState(true);

  if (!context) {
    return <div className="text-muted">Economic dashboard is loading...</div>;
  }

  const curveData = [...context.curve_points]
    .filter((point) => CURVE_DISPLAY_ORDER.includes(point.tenor))
    .sort((left, right) => tenorRank(left.tenor) - tenorRank(right.tenor))
    .map((point) => ({
      label: formatTenor(point.tenor),
      rate: point.rate,
      observationDate: point.observation_date,
    }));

  const treasuryDate = curveData[curveData.length - 1]?.observationDate ?? null;
  const rrpPoint = findCurvePoint(context, "rrp");
  const bill3mPoint = findCurvePoint(context, "3m");
  const tenYearPoint = findCurvePoint(context, "10y");
  const longBondPoint = findCurvePoint(context, "30y");
  const tenYear = context.curve_points.find((point) => point.tenor === "10y")?.rate ?? null;
  const creditSpread = findFredSeries(context, "BAA10Y");
  const breakeven = findFredSeries(context, "T10YIE");
  const cpiHeadline = findFredSeries(context, "CPIAUCSL");
  const cpiCore = findFredSeries(context, "CPILFESL");
  const pceHeadline = findFredSeries(context, "PCEPI");
  const pceCore = findFredSeries(context, "PCEPILFE");
  const unemployment = findFredSeries(context, "UNRATE");
  const recessionSignal = findFredSeries(context, "USREC");
  const recessionActive = (recessionSignal?.value ?? 0) >= 0.5;
  const riskMood = buildRiskMood(context, recessionActive, creditSpread?.value ?? null, breakeven?.value ?? null);
  const macroTableRows = buildMacroTableRows(context, {
    rrpPoint,
    bill3mPoint,
    tenYearPoint,
    longBondPoint,
    creditSpread,
    breakeven,
    cpiHeadline,
    cpiCore,
    pceHeadline,
    pceCore,
    unemployment,
    recessionSignal,
  });
  const visibleMacroRows = showAllFactors ? macroTableRows : macroTableRows.filter((row) => row.priority === "core");
  const treasuryStats = buildTreasuryStats(context);

  const summaryCards = [
    {
      label: "10Y Treasury",
      value: formatPercent(tenYear),
      detail: treasuryDate ? `Observed ${formatDate(treasuryDate)}` : "Observation pending",
      tone: "cyan",
    },
    {
      label: "2s10s Slope",
      value: formatPercent(context.slope_2s10s.value),
      detail: slopeSummary(context.slope_2s10s.value),
      tone: slopeTone(context.slope_2s10s.value),
    },
    {
      label: "3m10y Slope",
      value: formatPercent(context.slope_3m10y.value),
      detail: slopeSummary(context.slope_3m10y.value),
      tone: slopeTone(context.slope_3m10y.value),
    },
    {
      label: "Breakeven Inflation",
      value: formatPercent(breakeven?.value ?? null),
      detail: seriesObservation(breakeven),
      tone: "gold",
    },
    {
      label: "Unemployment",
      value: formatPercent(unemployment?.value ?? null),
      detail: seriesObservation(unemployment),
      tone: "green",
    },
    {
      label: "BAA Credit Spread",
      value: formatPercent(creditSpread?.value ?? null),
      detail: seriesObservation(creditSpread),
      tone: "red",
    },
  ];

  const signalCards = [
    {
      kicker: "Regime",
      title: recessionActive ? "Recession flag active" : "Expansion regime",
      copy: recessionActive
        ? "The latest recession indicator is active, so cyclical risk should be framed defensively."
        : "The recession indicator remains off, so the dashboard is reading a non-recessionary base case.",
    },
    {
      kicker: "Curve shape",
      title: describeCurveShape(context.slope_2s10s.value, context.slope_3m10y.value),
      copy: "Use 2s10s for bank/credit conditions and 3m10y for recession-style inversion risk.",
    },
    {
      kicker: "Credit",
      title: creditSpread?.value != null ? describeCredit(creditSpread.value) : "Credit spread unavailable",
      copy: "BAA spread is a practical stress gauge for corporate financing conditions and equity risk appetite.",
    },
    {
      kicker: "Inflation",
      title: breakeven?.value != null ? describeInflation(breakeven.value) : "Inflation signal unavailable",
      copy: "10Y breakeven helps frame whether nominal yields reflect inflation pressure or real-rate tightening.",
    },
  ];

  const treasuryStatus = readTreasuryStatus(context);

  return (
    <div className="econ-dashboard">
      <SourceFreshnessSummary
        provenance={context.provenance}
        asOf={context.as_of}
        lastRefreshedAt={context.last_refreshed_at}
        sourceMix={context.source_mix}
        confidenceFlags={context.confidence_flags}
      />

      <section className="econ-hero">
        <div className="econ-hero-copy">
          <div className="grid-empty-kicker">Macro</div>
          <div className="econ-hero-title">{riskMood.title}</div>
          <div className="grid-empty-copy">{riskMood.copy}</div>
        </div>

        <div className="econ-hero-meta">
          <span className="pill">Snapshot {formatDate(context.fetched_at)}</span>
          <span className="pill">Treasury {normalizeStatus(treasuryStatus)}</span>
          <span className="pill">FRED {context.fred_series.length ? "Live" : "Unavailable"}</span>
          <span className="pill">Status {normalizeStatus(context.status)}</span>
        </div>
      </section>

      <section className="econ-summary-grid">
        {summaryCards.map((card) => (
          <article key={card.label} className={`econ-summary-card tone-${card.tone}`}>
            <div className="econ-summary-label">{card.label}</div>
            <div className="econ-summary-value">{card.value}</div>
            <div className="econ-summary-detail">{card.detail}</div>
          </article>
        ))}
      </section>

      <section className="econ-chart-grid">
        <article className="econ-chart-card econ-chart-card-wide">
          <div className="econ-chart-header">
            <div>
              <div className="grid-empty-kicker">Treasury curve</div>
              <div className="econ-chart-title">Current term structure</div>
            </div>
            <div className="text-muted">Cross-sectional yields from the latest cached Treasury snapshot.</div>
          </div>
          <div className="econ-chart-shell">
            <ResponsiveContainer>
              <LineChart data={curveData} margin={{ top: 8, right: 16, left: 2, bottom: 0 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} width={56} tickFormatter={(value: number) => formatAxisPercent(Number(value))} />
                <Tooltip
                  {...RECHARTS_TOOLTIP_PROPS}
                  formatter={(value: number) => formatPercent(value)}
                  labelFormatter={(value) => `${value} Treasury`}
                />
                <ReferenceLine y={0} stroke="rgba(148, 163, 184, 0.35)" />
                <Line type="monotone" dataKey="rate" stroke="#43c6ac" strokeWidth={3} dot={{ r: 3, strokeWidth: 0, fill: "#43c6ac" }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="econ-curve-stats-grid">
            {treasuryStats.map((item) => (
              <div key={item.label} className="econ-curve-stat-card">
                <div className="econ-curve-stat-label">{item.label}</div>
                <div className="econ-curve-stat-value">{item.value}</div>
                <div className="econ-curve-stat-detail">{item.detail}</div>
              </div>
            ))}
          </div>
        </article>

        <article className="econ-chart-card">
          <div className="econ-chart-header">
            <div className="econ-chart-heading-row">
              <div>
                <div className="grid-empty-kicker">Macro factors</div>
                <div className="econ-chart-title">Cross-market scorecard</div>
              </div>
              {macroTableRows.length > 6 ? (
                <button type="button" className="button econ-table-toggle" onClick={() => setShowAllFactors((current) => !current)}>
                  {showAllFactors ? "Show core factors" : "Show full factors"}
                </button>
              ) : null}
            </div>
            <div className="text-muted">Broader live rate, funding, labor, inflation, and credit checks in one compact view.</div>
          </div>
          {macroTableRows.length ? (
            <div className="econ-table-wrap">
              <table className="econ-data-table">
                <thead>
                  <tr>
                    <th scope="col">Group</th>
                    <th scope="col">Indicator</th>
                    <th scope="col">Latest</th>
                    <th scope="col">Signal</th>
                    <th scope="col">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleMacroRows.map((row) => (
                    <tr key={row.key}>
                      <td>
                        <span className={`econ-data-chip tone-${row.tone}`}>{row.group}</span>
                      </td>
                      <td>
                        <div className="econ-data-label">{row.label}</div>
                        <div className="econ-data-subtitle">{row.subtitle}</div>
                      </td>
                      <td className="econ-data-value">{row.value}</td>
                      <td className="econ-data-signal">{row.signal}</td>
                      <td className="econ-data-updated">{row.updated}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="econ-empty-state">Supplemental indicators are unavailable in the current snapshot.</div>
          )}
        </article>
      </section>

      <section className="econ-signal-grid">
        {signalCards.map((card) => (
          <article key={card.kicker} className="econ-signal-card">
            <div className="grid-empty-kicker">{card.kicker}</div>
            <div className="grid-empty-title">{card.title}</div>
            <div className="grid-empty-copy">{card.copy}</div>
          </article>
        ))}
      </section>

      {(context.rates_credit?.length || context.inflation_labor?.length || context.growth_activity?.length || context.cyclical_demand?.length || context.cyclical_costs?.length) ? (
        <section className="econ-macro-sections">
          <div className="econ-macro-header">
            <div className="grid-empty-kicker">Macro</div>
            <div className="econ-chart-title">At a glance</div>
          </div>
          {context.rates_credit?.length ? (
            <MacroGroupedSection title="Rates &amp; Credit" items={context.rates_credit} />
          ) : null}
          {context.inflation_labor?.length ? (
            <MacroGroupedSection title="Inflation &amp; Labor" items={context.inflation_labor} />
          ) : null}
          {context.growth_activity?.length ? (
            <MacroGroupedSection title="Growth &amp; Activity" items={context.growth_activity} />
          ) : null}
          {context.cyclical_demand?.length ? (
            <MacroGroupedSection title="Cyclical Demand" items={context.cyclical_demand} />
          ) : null}
          {context.cyclical_costs?.length ? (
            <MacroGroupedSection title="Cyclical Costs &amp; Labor" items={context.cyclical_costs} />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function MacroGroupedSection({ title, items }: { title: string; items: MacroSeriesItemPayload[] }) {
  const visibleItems = selectMacroAtAGlanceItems(title, items);

  return (
    <div className="econ-macro-section">
      <div className="econ-macro-section-title">{title}</div>
      <div className="econ-macro-items-grid">
        {visibleItems.map((item) => (
          <article key={item.series_id} className="econ-macro-item-card">
            <div className="econ-macro-item-label">{item.label}</div>
            <div className="econ-macro-item-value">
              {formatMacroValue(item)}
            </div>
            {item.change_percent != null ? (
              <div className={`econ-macro-item-change ${item.change_percent >= 0 ? "positive" : "negative"}`}>
                {item.change_percent >= 0 ? "+" : ""}
                {(item.change_percent * 100).toFixed(2)}%
              </div>
            ) : null}
            <div className="econ-macro-item-meta">
              {item.observation_date ? `${formatDate(item.observation_date)} · ` : ""}
              <a href={item.source_url} target="_blank" rel="noopener noreferrer" className="econ-macro-source-link">
                {item.source_name}
              </a>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function tenorRank(tenor: string): number {
  const index = CURVE_DISPLAY_ORDER.indexOf(tenor.toLowerCase());
  return index === -1 ? CURVE_DISPLAY_ORDER.length : index;
}

function formatTenor(tenor: string): string {
  return tenor.toLowerCase() === "rrp" ? "RRP" : tenor.toUpperCase();
}

function formatAxisPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function findCurvePoint(context: CompanyMarketContextResponse, tenor: string) {
  return context.curve_points.find((point) => point.tenor === tenor) ?? null;
}

function findFredSeries(context: CompanyMarketContextResponse, seriesId: string): MarketFredSeriesPayload | null {
  return context.fred_series.find((series) => series.series_id === seriesId) ?? null;
}

function seriesObservation(series: MarketFredSeriesPayload | null): string {
  if (!series?.observation_date) {
    return "Observation pending";
  }
  return `Observed ${formatDate(series.observation_date)}`;
}

function curveObservation(observationDate: string | null | undefined): string {
  if (!observationDate) {
    return "Observation pending";
  }
  return `Observed ${formatDate(observationDate)}`;
}

function slopeSummary(value: number | null): string {
  if (value == null) {
    return "Slope unavailable";
  }
  if (value < 0) {
    return "Inverted curve";
  }
  if (value < 0.005) {
    return "Barely positive";
  }
  return "Normally sloped";
}

function slopeTone(value: number | null): "cyan" | "gold" | "red" {
  if (value == null) {
    return "gold";
  }
  return value < 0 ? "red" : value < 0.005 ? "gold" : "cyan";
}

function buildRiskMood(
  context: CompanyMarketContextResponse,
  recessionActive: boolean,
  creditSpread: number | null,
  breakeven: number | null,
) {
  if (recessionActive) {
    return {
      title: "Macro regime is defensive with recession pressure active.",
      copy: "The dashboard is prioritizing capital preservation signals because the recession indicator is flagged and curve shape should be treated cautiously.",
    };
  }
  if ((context.slope_3m10y.value ?? 0) < 0) {
    return {
      title: "Yield-curve inversion is still a live risk signal.",
      copy: "Short rates are still pressuring the front end of the curve, so equity duration and cyclical exposure deserve tighter underwriting.",
    };
  }
  if ((creditSpread ?? 0) > 0.02 || (breakeven ?? 0) > 0.0275) {
    return {
      title: "Growth backdrop is intact, but financing conditions are not fully relaxed.",
      copy: "Credit and inflation indicators suggest the market is still paying attention to funding stress and pricing pressure, even with a positive curve slope.",
    };
  }
  return {
    title: "Macro backdrop is broadly constructive for bottom-up research.",
    copy: "The current mix of rates, labor, and inflation signals reads closer to a stable expansion regime than a stress regime.",
  };
}

function describeCurveShape(slope2s10s: number | null, slope3m10y: number | null): string {
  if ((slope3m10y ?? 0) < 0) {
    return "Front-end inversion remains the dominant caution signal";
  }
  if ((slope2s10s ?? 0) < 0) {
    return "Longer-curve inversion still pressures risk framing";
  }
  return "Curve has normalized back into positive carry territory";
}

function describeCredit(value: number): string {
  if (value >= 0.025) {
    return "Corporate credit is priced defensively";
  }
  if (value >= 0.015) {
    return "Credit markets are alert but functioning";
  }
  return "Credit spreads are relatively calm";
}

function describeInflation(value: number): string {
  if (value >= 0.03) {
    return "Inflation expectations remain elevated";
  }
  if (value >= 0.0225) {
    return "Inflation expectations are manageable";
  }
  return "Inflation expectations are relatively contained";
}

function describeCoreInflation(value: number): string {
  if (value >= 0.0325) {
    return "Underlying inflation pressure is still elevated";
  }
  if (value >= 0.025) {
    return "Core inflation is cooling, but still above target";
  }
  return "Core inflation is moving closer to target";
}

function normalizeStatus(status: string): string {
  if (status === "ok") {
    return "OK";
  }
  if (status === "partial") {
    return "Partial";
  }
  if (status === "insufficient_data") {
    return "Insufficient";
  }
  return status;
}

function readTreasuryStatus(context: CompanyMarketContextResponse): string {
  const treasury = context.provenance_details?.treasury;
  if (!treasury || typeof treasury !== "object") {
    return "unknown";
  }
  return String((treasury as Record<string, unknown>).status ?? "unknown");
}

function buildMacroTableRows(
  context: CompanyMarketContextResponse,
  inputs: {
    rrpPoint: { tenor: string; rate: number; observation_date: string } | null;
    bill3mPoint: { tenor: string; rate: number; observation_date: string } | null;
    tenYearPoint: { tenor: string; rate: number; observation_date: string } | null;
    longBondPoint: { tenor: string; rate: number; observation_date: string } | null;
    creditSpread: MarketFredSeriesPayload | null;
    breakeven: MarketFredSeriesPayload | null;
    cpiHeadline: MarketFredSeriesPayload | null;
    cpiCore: MarketFredSeriesPayload | null;
    pceHeadline: MarketFredSeriesPayload | null;
    pceCore: MarketFredSeriesPayload | null;
    unemployment: MarketFredSeriesPayload | null;
    recessionSignal: MarketFredSeriesPayload | null;
  },
) {
  const rows = [
    inputs.rrpPoint
      ? {
          key: "rrp",
          priority: "core",
          group: "Funding",
          label: "RRP award rate",
          subtitle: "Cash floor for money-market funding",
          value: formatPercent(inputs.rrpPoint.rate),
          signal: describeFundingRate(inputs.rrpPoint.rate),
          updated: curveObservation(inputs.rrpPoint.observation_date),
          tone: toneFromSignedValue(inputs.rrpPoint.rate - 0.04),
        }
      : null,
    inputs.bill3mPoint
      ? {
          key: "3m",
          priority: "core",
          group: "Rates",
          label: "3M Treasury bill",
          subtitle: "Front-end policy-sensitive rate",
          value: formatPercent(inputs.bill3mPoint.rate),
          signal: inputs.bill3mPoint.rate >= 0.045 ? "Policy remains restrictive" : "Front-end pressure is easing",
          updated: curveObservation(inputs.bill3mPoint.observation_date),
          tone: toneFromSignedValue(0.045 - inputs.bill3mPoint.rate),
        }
      : null,
    inputs.tenYearPoint
      ? {
          key: "10y",
          priority: "core",
          group: "Rates",
          label: "10Y Treasury note",
          subtitle: "Benchmark discount rate for long-duration assets",
          value: formatPercent(inputs.tenYearPoint.rate),
          signal: describeLongRate(inputs.tenYearPoint.rate),
          updated: curveObservation(inputs.tenYearPoint.observation_date),
          tone: toneFromSignedValue(0.045 - inputs.tenYearPoint.rate),
        }
      : null,
    inputs.longBondPoint
      ? {
          key: "30y",
          priority: "satellite",
          group: "Term",
          label: "30Y Treasury bond",
          subtitle: "Long-end inflation and duration premium",
          value: formatPercent(inputs.longBondPoint.rate),
          signal: inputs.longBondPoint.rate >= 0.0475 ? "Long-end premium is elevated" : "Long duration remains orderly",
          updated: curveObservation(inputs.longBondPoint.observation_date),
          tone: toneFromSignedValue(0.0475 - inputs.longBondPoint.rate),
        }
      : null,
    {
      key: "2s10s",
      priority: "core",
      group: "Curve",
      label: "2s10s slope",
      subtitle: "Banking and credit creation backdrop",
      value: formatPercent(context.slope_2s10s.value),
      signal: slopeSummary(context.slope_2s10s.value),
      updated: curveObservation(context.slope_2s10s.observation_date),
      tone: slopeTone(context.slope_2s10s.value),
    },
    {
      key: "3m10y",
      priority: "core",
      group: "Curve",
      label: "3m10y slope",
      subtitle: "Classic recession-watch spread",
      value: formatPercent(context.slope_3m10y.value),
      signal: slopeSummary(context.slope_3m10y.value),
      updated: curveObservation(context.slope_3m10y.observation_date),
      tone: slopeTone(context.slope_3m10y.value),
    },
    buildFredTableRow("breakeven", "Inflation", "10Y breakeven", "Inflation compensation embedded in Treasuries", inputs.breakeven, describeInflation, "gold", "core"),
    buildFredTableRow("cpi-headline", "Inflation", "Headline CPI (YoY)", "Consumer inflation, all items", inputs.cpiHeadline, describeInflation, "gold", "core"),
    buildFredTableRow("cpi-core", "Inflation", "Core CPI (YoY)", "Consumer inflation excluding food and energy", inputs.cpiCore, describeCoreInflation, "gold", "core"),
    buildFredTableRow("pce-headline", "Inflation", "PCE price index (YoY)", "Fed-aligned consumer inflation benchmark", inputs.pceHeadline, describeInflation, "gold", "satellite"),
    buildFredTableRow("pce-core", "Inflation", "Core PCE (YoY)", "Fed-preferred core inflation measure", inputs.pceCore, describeCoreInflation, "gold", "satellite"),
    buildFredTableRow("unemployment", "Labor", "Unemployment rate", "Slack gauge for hiring conditions", inputs.unemployment, describeLabor, "green", "core"),
    buildFredTableRow("credit", "Credit", "BAA credit spread", "Corporate funding stress premium", inputs.creditSpread, describeCredit, "red", "core"),
    buildFredTableRow("recession", "Regime", "Recession indicator", "Binary recession-state check", inputs.recessionSignal, describeRecessionSignal, (inputs.recessionSignal?.value ?? 0) >= 0.5 ? "red" : "cyan", "satellite"),
  ];

  return rows.filter(
    (
      row,
    ): row is {
      key: string;
      priority: "core" | "satellite";
      group: string;
      label: string;
      subtitle: string;
      value: string;
      signal: string;
      updated: string;
      tone: "cyan" | "gold" | "green" | "red";
    } => row !== null,
  );
}

function buildFredTableRow(
  key: string,
  group: string,
  label: string,
  subtitle: string,
  series: MarketFredSeriesPayload | null,
  describe: (value: number) => string,
  tone: "cyan" | "gold" | "green" | "red",
  priority: "core" | "satellite",
) {
  if (!series || series.value == null) {
    return null;
  }
  return {
    key,
    priority,
    group,
    label,
    subtitle,
    value: formatPercent(series.value),
    signal: describe(series.value),
    updated: seriesObservation(series),
    tone,
  };
}

function toneFromSignedValue(value: number | null): "cyan" | "gold" | "green" | "red" {
  if (value == null) {
    return "gold";
  }
  if (value < -0.0025) {
    return "red";
  }
  if (value < 0) {
    return "gold";
  }
  return "cyan";
}

function describeFundingRate(value: number): string {
  if (value >= 0.0475) {
    return "Cash remains expensive";
  }
  if (value >= 0.0425) {
    return "Funding is firm, not loose";
  }
  return "Funding floor is easing";
}

function describeLongRate(value: number): string {
  if (value >= 0.0475) {
    return "Discount rates still lean restrictive";
  }
  if (value >= 0.04) {
    return "Long-end yields are range-bound";
  }
  return "Long-end rates are supportive";
}

function describeLabor(value: number): string {
  if (value >= 0.05) {
    return "Labor slack is building";
  }
  if (value >= 0.04) {
    return "Labor market is cooling gradually";
  }
  return "Labor market remains tight";
}

function describeRecessionSignal(value: number): string {
  return value >= 0.5 ? "Recession regime flagged" : "No recession flag";
}

function buildTreasuryStats(context: CompanyMarketContextResponse): Array<{ label: string; value: string; detail: string }> {
  const avg = (tenors: string[]) => averageRates(tenors.map((tenor) => findCurvePoint(context, tenor)?.rate ?? null));

  const frontEnd = avg(["1m", "2m", "3m", "4m", "6m"]);
  const belly = avg(["1y", "2y", "3y", "5y", "7y"]);
  const longEnd = avg(["10y", "20y", "30y"]);
  const curveRange = rangeRates(context.curve_points.map((point) => point.rate));
  const rrp = findCurvePoint(context, "rrp")?.rate ?? null;
  const tenYear = findCurvePoint(context, "10y")?.rate ?? null;
  const rrpGap = rrp != null && tenYear != null ? tenYear - rrp : null;

  return [
    { label: "Front-end avg", value: formatPercent(frontEnd), detail: "1M to 6M cluster" },
    { label: "Belly avg", value: formatPercent(belly), detail: "1Y to 7Y cluster" },
    { label: "Long-end avg", value: formatPercent(longEnd), detail: "10Y to 30Y cluster" },
    { label: "Curve range", value: formatPercent(curveRange), detail: "Max minus min tenor" },
    { label: "10Y minus RRP", value: formatPercent(rrpGap), detail: "Distance from policy floor" },
  ];
}

function averageRates(values: Array<number | null>): number | null {
  const clean = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!clean.length) {
    return null;
  }
  const total = clean.reduce((sum, value) => sum + value, 0);
  return total / clean.length;
}

function rangeRates(values: Array<number | null>): number | null {
  const clean = values.filter((value): value is number => value != null && Number.isFinite(value));
  if (!clean.length) {
    return null;
  }
  return Math.max(...clean) - Math.min(...clean);
}

function formatMacroValue(item: MacroSeriesItemPayload): string {
  if (item.value == null) {
    return "—";
  }

  if (item.units === "percent") {
    return formatPercent(item.value);
  }

  if (item.units === "spread") {
    return `${item.value.toFixed(2)} pts`;
  }

  if (item.units === "billions_usd") {
    if (Math.abs(item.value) >= 1000) {
      return `$${(item.value / 1000).toFixed(2)}T`;
    }
    return `$${item.value.toFixed(1)}B`;
  }

  if (item.units === "millions_usd") {
    return item.value >= 1000 ? `$${(item.value / 1000).toFixed(2)}B` : `$${item.value.toFixed(0)}M`;
  }

  if (item.units === "thousands") {
    return `${formatCompactNumber(item.value * 1000)}`;
  }

  return formatCompactNumber(item.value);
}

function selectMacroAtAGlanceItems(title: string, items: MacroSeriesItemPayload[]): MacroSeriesItemPayload[] {
  const desiredSeriesBySection: Record<string, string[]> = {
    "Rates & Credit": ["DGS_10Y", "slope_2s10s", "BAA10Y"],
    "Inflation & Labor": ["CPIAUCSL", "PCEPILFE", "UNRATE", "CUSR0000SA0", "CUSR0000SA0L1E", "LNS14000000"],
    "Growth & Activity": ["bea_pce_total"],
    "Cyclical Demand": ["census_m3_new_orders_total", "census_m3_shipments_total", "census_retail_sales_total", "bea_gdp_manufacturing", "bea_gdp_retail_trade"],
    "Cyclical Costs & Labor": ["WPSFD4", "CIU1010000000000I", "JTS000000000000000JOL", "JTS000000000000000QUL"],
  };

  const desired = desiredSeriesBySection[title] ?? [];
  const prioritized = desired
    .map((seriesId) => items.find((item) => item.series_id === seriesId))
    .filter((item): item is MacroSeriesItemPayload => Boolean(item && item.value != null && item.status === "ok"));

  if (prioritized.length) {
    return prioritized;
  }

  return items.filter((item) => item.value != null && item.status === "ok").slice(0, 3);
}

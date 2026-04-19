"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  ChartComparePicker,
  ChartControlGroup,
  ChartSourceBadges,
  ChartStateBlock,
  exportRowsToCsv,
  type ControlOption,
  type SourceBadge,
} from "@/components/charts/chart-framework";
import { PanelEmptyState } from "@/components/company/panel-empty-state";
import { MetricLabel } from "@/components/ui/metric-label";
import { getCompanyBeneficialOwnership, getCompanyCapitalMarkets, getCompanyEarnings, getCompanyFilingEvents, getCompanyInsiderTrades, getCompanyMetricsTimeseries } from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick, chartLegendStyle } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type {
  BeneficialOwnershipFilingPayload,
  CompanyCapitalRaisesResponse,
  CompanyEarningsResponse,
  CompanyEventsResponse,
  CompanyInsiderTradesResponse,
  CompanyMetricsTimeseriesResponse,
  FinancialPayload,
  FilingEventPayload,
} from "@/lib/types";

type Cadence = "quarterly" | "annual" | "ttm";
export type ValueMode = "absolute" | "margin" | "growth" | "perShare";
export type DateRange = "3y" | "5y" | "10y" | "all";

type AnnotationKind = "earnings" | "event" | "capital" | "insider" | "ownership";

export type AnnotationRow = {
  date: string;
  kind: AnnotationKind;
  label: string;
};

export type SegmentMixRow = {
  periodEnd: string;
  periodLabel: string;
  segmentName: string;
  share: number;
};

export type FilingHeatmapRow = {
  quarter: string;
  filingCount: number;
  avgLagDays: number | null;
};

type MetricDefinition = {
  key: string;
  label: string;
  color: string;
  getAbsolute: (statement: FinancialPayload) => number | null;
};

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const QUARTERLY_FORMS = new Set(["10-Q", "6-K"]);

const METRICS: MetricDefinition[] = [
  { key: "revenue", label: "Revenue", color: "var(--accent)", getAbsolute: (s) => s.revenue },
  { key: "grossProfit", label: "Gross Profit", color: "var(--positive)", getAbsolute: (s) => s.gross_profit },
  { key: "operatingIncome", label: "Operating Income", color: "var(--warning)", getAbsolute: (s) => s.operating_income },
  { key: "netIncome", label: "Net Income", color: "var(--negative)", getAbsolute: (s) => s.net_income },
  { key: "freeCashFlow", label: "Free Cash Flow", color: "var(--positive)", getAbsolute: (s) => s.free_cash_flow },
  { key: "stockBasedComp", label: "Stock-Based Comp", color: "#A855F7", getAbsolute: (s) => s.stock_based_compensation },
  { key: "shares", label: "Shares Outstanding", color: "#64D2FF", getAbsolute: (s) => s.shares_outstanding },
];

const CADENCE_OPTIONS: ControlOption[] = [
  { key: "quarterly", label: "Quarterly" },
  { key: "annual", label: "Annual" },
  { key: "ttm", label: "TTM" },
];

const MODE_OPTIONS: ControlOption[] = [
  { key: "absolute", label: "Absolute" },
  { key: "margin", label: "Margin" },
  { key: "growth", label: "Growth" },
  { key: "perShare", label: "Per-Share" },
];

const RANGE_OPTIONS: ControlOption[] = [
  { key: "3y", label: "3Y" },
  { key: "5y", label: "5Y" },
  { key: "10y", label: "10Y" },
  { key: "all", label: "All" },
];

const ANNOTATION_COLOR: Record<AnnotationKind, string> = {
  earnings: "var(--warning)",
  event: "var(--accent)",
  capital: "var(--negative)",
  insider: "var(--positive)",
  ownership: "#A855F7",
};

interface CompanyVisualizationLabProps {
  ticker: string;
  financials: FinancialPayload[];
  reloadKey?: string | number;
}

export function CompanyVisualizationLab({ ticker, financials, reloadKey }: CompanyVisualizationLabProps) {
  const [metricsPayload, setMetricsPayload] = useState<CompanyMetricsTimeseriesResponse | null>(null);
  const [eventsPayload, setEventsPayload] = useState<CompanyEventsResponse | null>(null);
  const [earningsPayload, setEarningsPayload] = useState<CompanyEarningsResponse | null>(null);
  const [capitalPayload, setCapitalPayload] = useState<CompanyCapitalRaisesResponse | null>(null);
  const [insiderPayload, setInsiderPayload] = useState<CompanyInsiderTradesResponse | null>(null);
  const [ownershipPayload, setOwnershipPayload] = useState<BeneficialOwnershipFilingPayload[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [cadence, setCadence] = useState<Cadence>("annual");
  const [valueMode, setValueMode] = useState<ValueMode>("absolute");
  const [dateRange, setDateRange] = useState<DateRange>("5y");
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>(["revenue", "freeCashFlow"]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const [metrics, events, earnings, capital, insiders, ownership] = await Promise.all([
          getCompanyMetricsTimeseries(ticker, { cadence: "ttm", maxPoints: 40 }),
          getCompanyFilingEvents(ticker),
          getCompanyEarnings(ticker),
          getCompanyCapitalMarkets(ticker),
          getCompanyInsiderTrades(ticker),
          getCompanyBeneficialOwnership(ticker),
        ]);

        if (cancelled) {
          return;
        }

        setMetricsPayload(metrics);
        setEventsPayload(events);
        setEarningsPayload(earnings);
        setCapitalPayload(capital);
        setInsiderPayload(insiders);
        setOwnershipPayload(ownership.filings ?? []);
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load visualization overlays");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [reloadKey, ticker]);

  const cadenceRows = useMemo(() => {
    const sorted = [...financials].sort((a, b) => a.period_end.localeCompare(b.period_end));
    if (cadence === "annual") {
      return sorted.filter((row) => ANNUAL_FORMS.has(row.filing_type));
    }
    if (cadence === "quarterly") {
      return sorted.filter((row) => QUARTERLY_FORMS.has(row.filing_type));
    }
    return sorted;
  }, [cadence, financials]);

  const ttmRows = useMemo(
    () =>
      (metricsPayload?.series ?? [])
        .filter((point) => point.cadence === "ttm")
        .sort((a, b) => a.period_end.localeCompare(b.period_end)),
    [metricsPayload?.series]
  );

  useEffect(() => {
    if (!selectedMetrics.length) {
      setSelectedMetrics(["revenue"]);
    }
  }, [selectedMetrics]);

  const compareOptions = useMemo(
    () => METRICS.map((metric) => ({ key: metric.key, label: metric.label })),
    []
  );

  const chartRows = useMemo(() => {
    if (cadence === "ttm") {
      return applyDateRange(
        ttmRows.map((row) => ({
          periodEnd: row.period_end,
          periodLabel: formatDate(row.period_end),
          revenue: row.metrics.revenue_growth,
          grossProfit: row.metrics.gross_margin,
          operatingIncome: row.metrics.operating_margin,
          netIncome: row.metrics.accrual_ratio,
          freeCashFlow: row.metrics.cash_conversion,
          stockBasedComp: row.metrics.sbc_burden,
          shares: row.metrics.share_dilution,
          revenueBase: null,
          sharesOutstanding: null,
        })),
        dateRange
      );
    }

    const transformed = cadenceRows.map((row, index) => {
      const previous = cadenceRows[index - 1] ?? null;
      const revenue = row.revenue;
      const shares = row.shares_outstanding;

      return {
        periodEnd: row.period_end,
        periodLabel: formatDate(row.period_end),
        revenue: computeValueMode(row.revenue, previous?.revenue ?? null, revenue, shares, valueMode),
        grossProfit: computeValueMode(row.gross_profit, previous?.gross_profit ?? null, revenue, shares, valueMode),
        operatingIncome: computeValueMode(row.operating_income, previous?.operating_income ?? null, revenue, shares, valueMode),
        netIncome: computeValueMode(row.net_income, previous?.net_income ?? null, revenue, shares, valueMode),
        freeCashFlow: computeValueMode(row.free_cash_flow, previous?.free_cash_flow ?? null, revenue, shares, valueMode),
        stockBasedComp: computeValueMode(row.stock_based_compensation, previous?.stock_based_compensation ?? null, revenue, shares, valueMode),
        shares: computeValueMode(row.shares_outstanding, previous?.shares_outstanding ?? null, revenue, shares, valueMode),
        revenueBase: revenue,
        sharesOutstanding: shares,
      };
    });

    return applyDateRange(transformed, dateRange);
  }, [cadence, cadenceRows, dateRange, ttmRows, valueMode]);

  const annotations = useMemo(
    () =>
      applyDateRange(
        buildAnnotations({
          earnings: earningsPayload?.earnings_releases ?? [],
          events: eventsPayload?.events ?? [],
          capitalFilings: capitalPayload?.filings ?? [],
          insiderTrades: insiderPayload?.insider_trades ?? [],
          ownershipFilings: ownershipPayload,
        }),
        dateRange
      ),
    [capitalPayload?.filings, dateRange, earningsPayload?.earnings_releases, eventsPayload?.events, insiderPayload?.insider_trades, ownershipPayload]
  );

  const sourceBadges = useMemo<SourceBadge[]>(() => {
    const latest = metricsPayload?.series.at(-1) ?? null;
    const priceSource = latest?.provenance.price_source ?? "yahoo_finance";
    const statementSource = latest?.provenance.statement_source ?? "SEC EDGAR/XBRL";
    const staleness = metricsPayload?.staleness_reason ?? "fresh";
    return [
      { label: "Source", value: statementSource },
      { label: "Price", value: priceSource },
      { label: "Freshness", value: staleness },
      { label: "Provenance", value: latest?.provenance.formula_version ?? "sec_metrics_v2" },
    ];
  }, [metricsPayload?.series, metricsPayload?.staleness_reason]);

  const marginStackRows = useMemo(() => {
    const rows = cadenceRows.map((row) => ({
      periodEnd: row.period_end,
      periodLabel: formatDate(row.period_end),
      grossMargin: ratio(row.gross_profit, row.revenue),
      operatingMargin: ratio(row.operating_income, row.revenue),
      netMargin: ratio(row.net_income, row.revenue),
      fcfMargin: ratio(row.free_cash_flow, row.revenue),
    }));
    return applyDateRange(rows, dateRange);
  }, [cadenceRows, dateRange]);

  const qualityRows = useMemo(() => {
    return applyDateRange(
      (metricsPayload?.series ?? [])
        .filter((point) => point.cadence === cadence || (cadence === "annual" && point.cadence === "ttm"))
        .sort((a, b) => a.period_end.localeCompare(b.period_end))
        .map((point) => ({
          periodEnd: point.period_end,
          periodLabel: formatDate(point.period_end),
          cashConversion: point.metrics.cash_conversion,
          accrualRatio: point.metrics.accrual_ratio,
        })),
      dateRange
    );
  }, [cadence, dateRange, metricsPayload?.series]);

  const dilutionRows = useMemo(() => {
    const rows = cadenceRows.map((row, index) => {
      const previousShares = cadenceRows[index - 1]?.shares_outstanding ?? null;
      return {
        periodEnd: row.period_end,
        periodLabel: formatDate(row.period_end),
        shares: row.shares_outstanding,
        stockBasedComp: row.stock_based_compensation,
        dilution: growth(row.shares_outstanding, previousShares),
      };
    });
    return applyDateRange(rows, dateRange);
  }, [cadenceRows, dateRange]);

  const capitalAllocationRows = useMemo(() => {
    const rows = cadenceRows.map((row) => {
      const shareBuybacks = absNumber(row.share_buybacks);
      const dividends = absNumber(row.dividends);
      const fcf = absNumber(row.free_cash_flow);
      const shareholderYield = fcf && fcf !== 0 ? (shareBuybacks + dividends) / fcf : null;

      return {
        periodEnd: row.period_end,
        periodLabel: formatDate(row.period_end),
        buybacks: shareBuybacks,
        dividends,
        debtChanges: row.debt_changes,
        shareholderYield,
      };
    });
    return applyDateRange(rows, dateRange);
  }, [cadenceRows, dateRange]);

  const segmentMixRows = useMemo(() => applyDateRange(buildSegmentMixRows(cadenceRows, "business"), dateRange), [cadenceRows, dateRange]);
  const geographyMixRows = useMemo(() => applyDateRange(buildSegmentMixRows(cadenceRows, "geographic"), dateRange), [cadenceRows, dateRange]);

  const geographyConcentrationRows = useMemo(() => {
    const byPeriod = new Map<string, number>();
    for (const row of geographyMixRows) {
      byPeriod.set(row.periodEnd, (byPeriod.get(row.periodEnd) ?? 0) + row.share * row.share);
    }
    return Array.from(byPeriod.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([periodEnd, hhi]) => ({
        periodEnd,
        periodLabel: formatDate(periodEnd),
        concentration: hhi,
      }));
  }, [geographyMixRows]);

  const filingHeatmapRows = useMemo(() => {
    return buildFilingHeatmapRows(eventsPayload?.events ?? []);
  }, [eventsPayload?.events]);

  const activeMetricSeries = useMemo(
    () => selectedMetrics.map((metricKey) => METRICS.find((item) => item.key === metricKey)).filter((item): item is MetricDefinition => Boolean(item)),
    [selectedMetrics]
  );

  function toggleMetric(metricKey: string) {
    setSelectedMetrics((current) => {
      if (current.includes(metricKey)) {
        if (current.length === 1) {
          return current;
        }
        return current.filter((item) => item !== metricKey);
      }
      if (current.length >= 5) {
        return current;
      }
      return [...current, metricKey];
    });
  }

  if (loading && !metricsPayload) {
    return (
      <ChartStateBlock
        title="Visualization Lab"
        subtitle="Loading chart datasets"
        detail="Pulling cached SEC fundamentals, filing events, earnings, insider activity, and ownership markers."
      />
    );
  }

  if (error) {
    return (
      <ChartStateBlock
        title="Visualization Lab"
        subtitle="Unable to build chart overlays"
        detail={error}
      />
    );
  }

  if (!financials.length && !metricsPayload?.series.length) {
    return <PanelEmptyState message="No cached SEC financial history is available yet. Queue refresh to populate chart datasets." />;
  }

  return (
    <div className="viz-lab-shell">
      <div className="viz-lab-toolbar">
        <ChartControlGroup label="Cadence" value={cadence} options={CADENCE_OPTIONS} onChange={(value) => setCadence(value as Cadence)} />
        <ChartControlGroup label="Mode" value={valueMode} options={MODE_OPTIONS} onChange={(value) => setValueMode(value as ValueMode)} />
        <ChartControlGroup label="Date Range" value={dateRange} options={RANGE_OPTIONS} onChange={(value) => setDateRange(value as DateRange)} />
      </div>

      <ChartComparePicker
        label="Compare Metrics"
        options={compareOptions}
        selectedKeys={selectedMetrics}
        onToggle={toggleMetric}
        maxSelections={5}
      />

      <ChartSourceBadges badges={sourceBadges} />

      <section className="viz-chart-card">
        <div className="viz-chart-topline">
          <div>
            <h4 className="viz-chart-title">Performance Multi-Metric Explorer</h4>
            <p className="viz-chart-subtitle">Absolute, margin, growth, or per-share view with event annotations and compare mode.</p>
          </div>
          <button
            type="button"
            className="button tertiary"
            onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-performance-series.csv`, chartRows as Array<Record<string, string | number | null | undefined>>)}
            disabled={!chartRows.length}
          >
            Export CSV
          </button>
        </div>
        <div className="viz-chart-canvas">
          <ResponsiveContainer>
            <ComposedChart data={chartRows} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
              <YAxis
                stroke={CHART_AXIS_COLOR}
                tick={chartTick()}
                tickFormatter={(value) => formatModeValue(Number(value), valueMode)}
                width={86}
              />
              <Tooltip
                {...RECHARTS_TOOLTIP_PROPS}
                labelFormatter={(value) => formatDate(String(value))}
                formatter={(value) => {
                  const numeric = typeof value === "number" ? value : Number(value);
                  return formatModeValue(Number.isFinite(numeric) ? numeric : null, valueMode);
                }}
              />
              <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
              {activeMetricSeries.map((metric) => (
                <Line
                  key={metric.key}
                  type="monotone"
                  dataKey={metric.key}
                  name={metric.label}
                  stroke={metric.color}
                  strokeWidth={2.2}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
              {annotations.slice(-24).map((annotation) => (
                <ReferenceLine
                  key={`${annotation.kind}-${annotation.date}-${annotation.label}`}
                  x={annotation.date}
                  stroke={ANNOTATION_COLOR[annotation.kind]}
                  strokeOpacity={0.35}
                  strokeDasharray="4 4"
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="viz-annotation-row">
          {annotations.slice(-12).map((annotation) => (
            <span className="pill" key={`${annotation.kind}-${annotation.date}-${annotation.label}`}>
              <span className="viz-annotation-dot" style={{ background: ANNOTATION_COLOR[annotation.kind] }} />
              {formatDate(annotation.date)} {annotation.label}
            </span>
          ))}
        </div>
      </section>

      <section className="viz-grid-two">
        <div className="viz-chart-card">
          <div className="viz-chart-topline">
            <div>
              <h4 className="viz-chart-title">Margin Stack Over Time</h4>
              <p className="viz-chart-subtitle">Gross, operating, net, and free-cash-flow margins.</p>
            </div>
            <button
              type="button"
              className="button tertiary"
              onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-margin-stack.csv`, marginStackRows as Array<Record<string, string | number | null | undefined>>)}
              disabled={!marginStackRows.length}
            >
              Export CSV
            </button>
          </div>
          <div className="viz-chart-canvas compact">
            <ResponsiveContainer>
              <AreaChart data={marginStackRows} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} width={74} />
                <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatPercent(value)} labelFormatter={(value) => formatDate(String(value))} />
                <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                <Area type="monotone" dataKey="grossMargin" name="Gross" stroke="var(--positive)" fill="var(--positive)" stackId="1" connectNulls />
                <Area type="monotone" dataKey="operatingMargin" name="Operating" stroke="var(--accent)" fill="var(--accent)" stackId="1" connectNulls />
                <Area type="monotone" dataKey="netMargin" name="Net" stroke="var(--warning)" fill="var(--warning)" stackId="1" connectNulls />
                <Area type="monotone" dataKey="fcfMargin" name="FCF" stroke="#A855F7" fill="rgba(168,85,247,0.18)" stackId="1" connectNulls />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <ChartSourceBadges badges={[{ label: "Source", value: "SEC EDGAR financial statements" }, { label: "Freshness", value: "cache-backed" }, { label: "Provenance", value: "margin formulas" }]} />
        </div>

        <div className="viz-chart-card">
          <div className="viz-chart-topline">
            <div>
              <h4 className="viz-chart-title">Cash Conversion and Accrual Quality</h4>
              <p className="viz-chart-subtitle">Cash conversion ratio and accrual ratio from persisted derived metrics.</p>
            </div>
            <button
              type="button"
              className="button tertiary"
              onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-quality-series.csv`, qualityRows as Array<Record<string, string | number | null | undefined>>)}
              disabled={!qualityRows.length}
            >
              Export CSV
            </button>
          </div>
          <div className="viz-chart-canvas compact">
            <ResponsiveContainer>
              <ComposedChart data={qualityRows} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
                <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} width={74} />
                <Tooltip {...RECHARTS_TOOLTIP_PROPS} labelFormatter={(value) => formatDate(String(value))} formatter={(value: number) => Number(value).toFixed(2)} />
                <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                <Line type="monotone" dataKey="cashConversion" name="Cash Conversion" stroke="var(--accent)" strokeWidth={2.3} dot={false} connectNulls />
                <Bar dataKey="accrualRatio" name="Accrual Ratio" fill="var(--negative)" radius={[2, 2, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <ChartSourceBadges badges={[{ label: "Source", value: "SEC + Yahoo (price profile)" }, { label: "Freshness", value: metricsPayload?.staleness_reason ?? "fresh" }, { label: "Provenance", value: "derived metrics cache" }]} />
        </div>
      </section>

      <section className="viz-grid-two">
        <div className="viz-chart-card">
          <div className="viz-chart-topline">
            <div>
              <h4 className="viz-chart-title">Dilution and SBC Timeline</h4>
              <p className="viz-chart-subtitle">Shares outstanding, dilution rate, and stock-based compensation burden.</p>
            </div>
            <button
              type="button"
              className="button tertiary"
              onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-dilution-sbc.csv`, dilutionRows as Array<Record<string, string | number | null | undefined>>)}
              disabled={!dilutionRows.length}
            >
              Export CSV
            </button>
          </div>
          <div className="viz-chart-canvas compact">
            <ResponsiveContainer>
              <ComposedChart data={dilutionRows} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
                <YAxis yAxisId="left" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} width={76} />
                <YAxis yAxisId="right" orientation="right" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} width={68} />
                <Tooltip {...RECHARTS_TOOLTIP_PROPS} labelFormatter={(value) => formatDate(String(value))} />
                <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                <Bar yAxisId="left" dataKey="shares" name="Shares" fill="var(--accent)" radius={[2, 2, 0, 0]} />
                <Line yAxisId="left" type="monotone" dataKey="stockBasedComp" name="SBC" stroke="#A855F7" strokeWidth={2.2} dot={false} connectNulls />
                <Line yAxisId="right" type="monotone" dataKey="dilution" name="Dilution" stroke="var(--warning)" strokeWidth={2.2} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <ChartSourceBadges badges={[{ label: "Source", value: "SEC filings" }, { label: "Freshness", value: "cache-backed" }, { label: "Provenance", value: "shares + SBC fields" }]} />
        </div>

        <div className="viz-chart-card">
          <div className="viz-chart-topline">
            <div>
              <h4 className="viz-chart-title">Capital Allocation and Shareholder Yield</h4>
              <p className="viz-chart-subtitle">Buybacks, dividends, debt changes, and shareholder-yield timeline.</p>
            </div>
            <button
              type="button"
              className="button tertiary"
              onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-capital-allocation.csv`, capitalAllocationRows as Array<Record<string, string | number | null | undefined>>)}
              disabled={!capitalAllocationRows.length}
            >
              Export CSV
            </button>
          </div>
          <div className="viz-chart-canvas compact">
            <ResponsiveContainer>
              <ComposedChart data={capitalAllocationRows} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
                <YAxis yAxisId="alloc" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} width={76} />
                <YAxis yAxisId="yield" orientation="right" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} width={68} />
                <Tooltip {...RECHARTS_TOOLTIP_PROPS} labelFormatter={(value) => formatDate(String(value))} />
                <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                <Bar yAxisId="alloc" dataKey="buybacks" name="Buybacks" fill="var(--accent)" radius={[2, 2, 0, 0]} />
                <Bar yAxisId="alloc" dataKey="dividends" name="Dividends" fill="var(--positive)" radius={[2, 2, 0, 0]} />
                <Line yAxisId="alloc" type="monotone" dataKey="debtChanges" name="Debt Changes" stroke="var(--negative)" strokeWidth={2.2} dot={false} connectNulls />
                <Line yAxisId="yield" type="monotone" dataKey="shareholderYield" name="Shareholder Yield" stroke="var(--warning)" strokeWidth={2.2} dot={false} connectNulls />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <ChartSourceBadges badges={[{ label: "Source", value: "SEC filings + derived metrics" }, { label: "Freshness", value: "cache-backed" }, { label: "Provenance", value: "capital allocation formulas" }]} />
        </div>
      </section>

      <section className="viz-grid-two">
        <div className="viz-chart-card">
          <div className="viz-chart-topline">
            <div>
              <h4 className="viz-chart-title">Segment Mix Evolution</h4>
              <p className="viz-chart-subtitle">Business segment revenue share over time.</p>
            </div>
            <button
              type="button"
              className="button tertiary"
              onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-segment-mix.csv`, segmentMixRows as Array<Record<string, string | number | null | undefined>>)}
              disabled={!segmentMixRows.length}
            >
              Export CSV
            </button>
          </div>
          <SegmentStackChart rows={segmentMixRows} emptyMessage="No business segment time-series is available yet." />
          <ChartSourceBadges badges={[{ label: "Source", value: "SEC segment disclosures" }, { label: "Freshness", value: "cache-backed" }, { label: "Provenance", value: "segment revenue share" }]} />
        </div>

        <div className="viz-chart-card">
          <div className="viz-chart-topline">
            <div>
              <h4 className="viz-chart-title">Geography Concentration Evolution</h4>
              <p className="viz-chart-subtitle">Concentration index from geographic segment mix.</p>
            </div>
            <button
              type="button"
              className="button tertiary"
              onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-geography-concentration.csv`, geographyConcentrationRows as Array<Record<string, string | number | null | undefined>>)}
              disabled={!geographyConcentrationRows.length}
            >
              Export CSV
            </button>
          </div>
          <div className="viz-chart-canvas compact">
            {geographyConcentrationRows.length ? (
              <ResponsiveContainer>
                <ComposedChart data={geographyConcentrationRows} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} width={74} />
                  <Tooltip {...RECHARTS_TOOLTIP_PROPS} labelFormatter={(value) => formatDate(String(value))} formatter={(value: number) => formatPercent(value)} />
                  <Line type="monotone" dataKey="concentration" name="Concentration (HHI)" stroke="var(--negative)" strokeWidth={2.2} dot={false} connectNulls />
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <ChartStateBlock
                title="Geography Concentration"
                subtitle="No geography disclosures available"
                detail="This panel populates when SEC filings include geographic segment revenue fields."
              />
            )}
          </div>
          <ChartSourceBadges badges={[{ label: "Source", value: "SEC geographic segments" }, { label: "Freshness", value: "cache-backed" }, { label: "Provenance", value: "HHI share concentration" }]} />
        </div>
      </section>

      <section className="viz-chart-card">
        <div className="viz-chart-topline">
          <div>
            <h4 className="viz-chart-title">Filing Cadence and Filing Lag Heatmap</h4>
            <p className="viz-chart-subtitle">Quarterly filing counts and average report-to-filing lag from 8-K event data.</p>
          </div>
          <button
            type="button"
            className="button tertiary"
            onClick={() => exportRowsToCsv(`${ticker.toLowerCase()}-filing-cadence-heatmap.csv`, filingHeatmapRows as Array<Record<string, string | number | null | undefined>>)}
            disabled={!filingHeatmapRows.length}
          >
            Export CSV
          </button>
        </div>
        <FilingHeatmap rows={filingHeatmapRows} />
        <ChartSourceBadges badges={[{ label: "Source", value: "SEC filing events" }, { label: "Freshness", value: "cache-backed" }, { label: "Provenance", value: "event filing_date/report_date lag" }]} />
      </section>
    </div>
  );
}

function SegmentStackChart({ rows, emptyMessage }: { rows: SegmentMixRow[]; emptyMessage: string }) {
  const periods = Array.from(new Set(rows.map((row) => row.periodEnd))).sort((a, b) => a.localeCompare(b));
  const segmentNames = Array.from(new Set(rows.map((row) => row.segmentName))).slice(0, 6);

  const table = periods.map((period) => {
    const row: Record<string, string | number | null | undefined> = {
      periodEnd: period,
      periodLabel: formatDate(period),
    };

    for (const segmentName of segmentNames) {
      const found = rows.find((item) => item.periodEnd === period && item.segmentName === segmentName);
      row[segmentName] = found?.share ?? null;
    }
    return row;
  });

  if (!table.length || !segmentNames.length) {
    return <ChartStateBlock title="Segment Mix" subtitle="No segment history" detail={emptyMessage} />;
  }

  const palette = ["var(--accent)", "var(--positive)", "var(--warning)", "var(--negative)", "#A855F7", "#64D2FF"];

  return (
    <div className="viz-chart-canvas compact">
      <ResponsiveContainer>
        <AreaChart data={table} margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="periodEnd" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatDate(String(value))} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatPercent(Number(value))} width={74} />
          <Tooltip {...RECHARTS_TOOLTIP_PROPS} labelFormatter={(value) => formatDate(String(value))} formatter={(value: number) => formatPercent(value)} />
          <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
          {segmentNames.map((segment, index) => (
            <Area
              key={segment}
              type="monotone"
              dataKey={segment}
              name={segment}
              stackId="segment"
              stroke={palette[index % palette.length]}
              fill={withAlpha(palette[index % palette.length], 0.2)}
              connectNulls
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function FilingHeatmap({ rows }: { rows: FilingHeatmapRow[] }) {
  if (!rows.length) {
    return (
      <ChartStateBlock
        title="Filing Cadence"
        subtitle="No filing cadence data yet"
        detail="This heatmap fills once filing events with valid dates are available in cache."
      />
    );
  }

  const maxCount = Math.max(...rows.map((row) => row.filingCount), 1);

  return (
    <div className="viz-heatmap-grid">
      {rows.map((row) => {
        const intensity = row.filingCount / maxCount;
        return (
          <div
            key={row.quarter}
            className="viz-heatmap-cell"
            style={{
              background: `color-mix(in srgb, var(--accent) ${Math.round(12 + intensity * 45)}%, var(--panel))`,
              borderColor: `var(--panel-border)`,
            }}
          >
            <div className="viz-heatmap-quarter">{row.quarter}</div>
            <div className="viz-heatmap-value">{row.filingCount.toLocaleString()} filings</div>
            <div className="viz-heatmap-subvalue">Lag: {row.avgLagDays == null ? "n/a" : `${row.avgLagDays.toFixed(1)}d`}</div>
          </div>
        );
      })}
    </div>
  );
}

export function computeValueMode(
  current: number | null,
  previous: number | null,
  revenue: number | null,
  shares: number | null,
  mode: ValueMode
): number | null {
  if (mode === "absolute") {
    return current;
  }
  if (mode === "margin") {
    return ratio(current, revenue);
  }
  if (mode === "growth") {
    return growth(current, previous);
  }
  if (mode === "perShare") {
    if (current == null || shares == null || shares === 0) {
      return null;
    }
    return current / shares;
  }
  return current;
}

export function ratio(value: number | null, denom: number | null): number | null {
  if (value == null || denom == null || denom === 0) {
    return null;
  }
  return value / denom;
}

export function growth(value: number | null, previous: number | null): number | null {
  if (value == null || previous == null || previous === 0) {
    return null;
  }
  return (value - previous) / Math.abs(previous);
}

export function absNumber(value: number | null): number {
  if (value == null || Number.isNaN(value)) {
    return 0;
  }
  return Math.abs(value);
}

export function withAlpha(hexColor: string, alpha: number): string {
  const safeAlpha = Math.max(0, Math.min(1, alpha));
  if (!hexColor.startsWith("#") || (hexColor.length !== 7 && hexColor.length !== 4)) {
    return hexColor;
  }

  const expanded =
    hexColor.length === 4
      ? `#${hexColor[1]}${hexColor[1]}${hexColor[2]}${hexColor[2]}${hexColor[3]}${hexColor[3]}`
      : hexColor;
  const r = parseInt(expanded.slice(1, 3), 16);
  const g = parseInt(expanded.slice(3, 5), 16);
  const b = parseInt(expanded.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${safeAlpha})`;
}

export function formatModeValue(value: number | null, mode: ValueMode): string {
  if (value == null || Number.isNaN(value)) {
    return "?";
  }
  if (mode === "absolute") {
    return formatCompactNumber(value);
  }
  if (mode === "margin" || mode === "growth") {
    return formatPercent(value);
  }
  return value.toFixed(3);
}

export function buildAnnotations({
  earnings,
  events,
  capitalFilings,
  insiderTrades,
  ownershipFilings,
}: {
  earnings: CompanyEarningsResponse["earnings_releases"];
  events: FilingEventPayload[];
  capitalFilings: CompanyCapitalRaisesResponse["filings"];
  insiderTrades: CompanyInsiderTradesResponse["insider_trades"];
  ownershipFilings: BeneficialOwnershipFilingPayload[];
}): AnnotationRow[] {
  const rows: AnnotationRow[] = [];

  for (const release of earnings.slice(0, 48)) {
    const date = release.filing_date ?? release.report_date;
    if (!date) {
      continue;
    }
    rows.push({ date, kind: "earnings", label: "Earnings" });
  }

  for (const event of events.slice(0, 120)) {
    const date = event.filing_date ?? event.report_date;
    if (!date) {
      continue;
    }
    rows.push({ date, kind: "event", label: event.category || "8-K" });
  }

  for (const filing of capitalFilings.slice(0, 120)) {
    const date = filing.filing_date ?? filing.report_date;
    if (!date) {
      continue;
    }
    rows.push({ date, kind: "capital", label: filing.event_type ?? "Capital" });
  }

  for (const trade of insiderTrades.slice(0, 120)) {
    const date = trade.filing_date ?? trade.date;
    if (!date) {
      continue;
    }
    rows.push({ date, kind: "insider", label: trade.action || "Insider" });
  }

  for (const filing of ownershipFilings.slice(0, 120)) {
    const date = filing.filing_date ?? filing.report_date;
    if (!date) {
      continue;
    }
    rows.push({ date, kind: "ownership", label: filing.base_form });
  }

  return rows.sort((a, b) => a.date.localeCompare(b.date));
}

export function buildSegmentMixRows(financials: FinancialPayload[], kind: "business" | "geographic"): SegmentMixRow[] {
  const rows: SegmentMixRow[] = [];

  for (const statement of financials) {
    const matching = statement.segment_breakdown.filter((segment) => segment.kind === kind && (segment.revenue ?? 0) > 0);
    if (!matching.length) {
      continue;
    }
    const totalRevenue = matching.reduce((sum, segment) => sum + (segment.revenue ?? 0), 0);
    if (totalRevenue <= 0) {
      continue;
    }

    const topSegments = [...matching]
      .sort((a, b) => (b.revenue ?? 0) - (a.revenue ?? 0))
      .slice(0, 6);

    for (const segment of topSegments) {
      if (!segment.revenue) {
        continue;
      }
      rows.push({
        periodEnd: statement.period_end,
        periodLabel: formatDate(statement.period_end),
        segmentName: segment.segment_name,
        share: segment.revenue / totalRevenue,
      });
    }
  }

  return rows.sort((a, b) => a.periodEnd.localeCompare(b.periodEnd));
}

export function buildFilingHeatmapRows(events: FilingEventPayload[]): FilingHeatmapRow[] {
  const buckets = new Map<string, { count: number; lagValues: number[] }>();

  for (const event of events) {
    const filingDate = event.filing_date;
    if (!filingDate) {
      continue;
    }

    const filing = new Date(filingDate);
    if (Number.isNaN(filing.getTime())) {
      continue;
    }

    const quarter = `${filing.getUTCFullYear()}-Q${Math.floor(filing.getUTCMonth() / 3) + 1}`;
    const existing = buckets.get(quarter) ?? { count: 0, lagValues: [] };
    existing.count += 1;

    if (event.report_date) {
      const report = new Date(event.report_date);
      if (!Number.isNaN(report.getTime())) {
        const lagDays = (filing.getTime() - report.getTime()) / (1000 * 60 * 60 * 24);
        if (Number.isFinite(lagDays) && lagDays >= 0) {
          existing.lagValues.push(lagDays);
        }
      }
    }

    buckets.set(quarter, existing);
  }

  return Array.from(buckets.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([quarter, value]) => ({
      quarter,
      filingCount: value.count,
      avgLagDays: value.lagValues.length ? value.lagValues.reduce((sum, item) => sum + item, 0) / value.lagValues.length : null,
    }));
}

export function applyDateRange<T extends { periodEnd?: string; date?: string }>(rows: T[], range: DateRange): T[] {
  if (range === "all" || rows.length <= 1) {
    return rows;
  }

  const yearsBack = range === "3y" ? 3 : range === "5y" ? 5 : 10;
  const timeValues = rows
    .map((row) => Date.parse(row.periodEnd ?? row.date ?? ""))
    .filter((value) => Number.isFinite(value));

  if (!timeValues.length) {
    return rows;
  }

  const maxTime = Math.max(...timeValues);
  const cutoff = maxTime - yearsBack * 365 * 24 * 60 * 60 * 1000;

  return rows.filter((row) => {
    const raw = row.periodEnd ?? row.date;
    if (!raw) {
      return false;
    }
    const value = Date.parse(raw);
    return Number.isFinite(value) && value >= cutoff;
  });
}

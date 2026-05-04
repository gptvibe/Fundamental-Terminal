"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { Panel } from "@/components/ui/panel";
import { MetricConfidenceBadge, type MetricConfidenceMetadata } from "@/components/ui/metric-confidence-badge";
import { MetricLabel } from "@/components/ui/metric-label";
import { getCompaniesCompare } from "@/lib/api";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import { resolvePiotroskiScoreState } from "@/lib/piotroski";
import type { CompanyCompareItemPayload, CompanyCompareResponse, FinancialPayload, ModelPayload } from "@/lib/types";

const STATEMENT_ROWS = [
  { key: "revenue", label: "Revenue", metricKey: "revenue", formatter: formatStatementValue },
  { key: "operating_income", label: "Operating Income", metricKey: "operating_income", formatter: formatStatementValue },
  { key: "net_income", label: "Net Income", metricKey: "net_income", formatter: formatStatementValue },
  { key: "free_cash_flow", label: "Free Cash Flow", metricKey: "free_cash_flow", formatter: formatStatementValue },
] as const;

const DERIVED_ROWS = [
  { key: "gross_margin", label: "Gross Margin", formatter: formatPercent },
  { key: "operating_margin", label: "Operating Margin", formatter: formatPercent },
  { key: "fcf_margin", label: "FCF Margin", formatter: formatPercent },
  { key: "roic_proxy", label: "ROIC Proxy", formatter: formatPercent },
  { key: "leverage_ratio", label: "Leverage Ratio", formatter: formatRatio },
  { key: "share_dilution", label: "Share Dilution", formatter: formatPercent },
] as const;

export function ComparePageClient({ tickers }: { tickers: string[] }) {
  const [response, setResponse] = useState<CompanyCompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tickers.length) {
      setResponse(null);
      setLoading(false);
      setError(null);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    async function loadCompare() {
      try {
        setLoading(true);
        setError(null);
        const payload = await getCompaniesCompare(tickers, { signal: controller.signal });
        if (!cancelled) {
          setResponse(payload);
        }
      } catch (nextError) {
        if (!cancelled && !controller.signal.aborted) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load compare view");
          setResponse(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadCompare();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [tickers]);

  const companies = useMemo(() => response?.companies ?? [], [response]);
  const periodsByTicker = useMemo(
    () => new Map(companies.map((company) => [company.ticker, company.financials.financials.slice(0, 4)])),
    [companies]
  );

  return (
    <div className="compare-page-shell">
      <header className="compare-page-header">
        <div>
          <h1 className="compare-page-title">Compare Companies</h1>
          <p className="compare-page-subtitle">
            Side-by-side statement history, derived operating metrics, and valuation outputs for up to five tickers.
          </p>
        </div>
        <div className="compare-toolbar">
          <span className="pill">Tickers {tickers.join(", ") || "Pending"}</span>
          {companies.length ? <span className="pill">Loaded {companies.length}</span> : null}
        </div>
      </header>

      {!tickers.length ? (
        <EmptyState
          title="No compare tickers provided"
          copy="Open the compare drawer from any company page or visit /compare?tickers=AAPL,MSFT to build a comparison view."
        />
      ) : null}

      {loading ? (
        <Panel title="Loading compare data" subtitle="Fetching financials, derived metrics, and model outputs for the requested tickers." variant="subtle">
          <div className="compare-compact-note">Compare payload is loading.</div>
        </Panel>
      ) : null}

      {error ? (
        <EmptyState title="Compare data unavailable" copy={error} />
      ) : null}

      {!loading && !error && companies.length ? (
        <>
          <section className="compare-company-grid" aria-label="Compared companies">
            {companies.map((company) => {
              const record = company.financials.company;
              return (
                <article key={company.ticker} className="compare-company-card">
                  <div className="compare-company-ticker">{company.ticker}</div>
                  <div className="compare-company-name">{record?.name ?? company.ticker}</div>
                  <div className="compare-company-meta">
                    <span>{record?.sector ?? record?.market_sector ?? "Sector pending"}</span>
                    <span>{record?.last_checked ? `Checked ${formatDate(record.last_checked)}` : "Awaiting cache"}</span>
                  </div>
                  <div className="compare-actions">
                    <Link href={`/company/${encodeURIComponent(company.ticker)}`} className="ticker-button utility-action-button utility-action-button-secondary utility-action-link-button">
                      Open Brief
                    </Link>
                  </div>
                </article>
              );
            })}
          </section>

          <Panel title="Financial Statements" subtitle="Revenue, operating income, net income, and free cash flow across the latest four visible periods. Values in USD (compact notation).">
            <div className="compare-table-shell">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th className="compare-table-row-label">Metric</th>
                    {companies.map((company) => {
                      const periods = periodsByTicker.get(company.ticker) ?? [];
                      return (
                        <th key={company.ticker} className="compare-table-company-head" colSpan={Math.max(periods.length, 1)}>
                          {company.ticker}
                        </th>
                      );
                    })}
                  </tr>
                  <tr>
                    <th className="compare-table-row-label">Period End</th>
                    {companies.flatMap((company) => {
                      const periods = periodsByTicker.get(company.ticker) ?? [];
                      if (!periods.length) {
                        return [<th key={`${company.ticker}-empty`} className="compare-table-period-head">No data</th>];
                      }
                      return periods.map((period) => (
                        <th key={`${company.ticker}-${period.period_end}`} className="compare-table-period-head">
                          {periodLabel(period)}
                        </th>
                      ));
                    })}
                  </tr>
                </thead>
                <tbody>
                  {STATEMENT_ROWS.map((row) => (
                    <tr key={row.key}>
                      <th className="compare-table-row-label"><MetricLabel metricKey={row.metricKey} label={row.label} /></th>
                      {companies.flatMap((company) => {
                        const periods = periodsByTicker.get(company.ticker) ?? [];
                        if (!periods.length) {
                          return [<td key={`${company.ticker}-${row.key}-empty`} className="compare-table-empty">No data</td>];
                        }
                        return periods.map((period) => (
                          <td key={`${company.ticker}-${row.key}-${period.period_end}`} className="compare-table-value is-numeric">
                            {row.formatter(getFinancialValue(period, row.key))}
                          </td>
                        ));
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Derived Metrics" subtitle="Margins, returns, leverage, and dilution from the latest summary payload. Margins and rates shown as % of revenue; leverage as total-debt/EBITDA proxy.">
            <div className="compare-table-shell">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th className="compare-table-row-label">Metric</th>
                    {companies.map((company) => (
                      <th key={company.ticker} className="compare-table-company-head">{company.ticker}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {DERIVED_ROWS.map((row) => (
                    <tr key={row.key}>
                      <th className="compare-table-row-label"><MetricLabel metricKey={row.key} label={row.label} /></th>
                      {companies.map((company) => {
                        const metric = getDerivedMetric(company, row.key);
                        return (
                          <td key={`${company.ticker}-${row.key}`} className="compare-table-value is-numeric">
                            <div className="compare-metric-cell">
                              <span>{row.formatter(metric?.metric_value)}</span>
                              {metric ? (
                                <MetricConfidenceBadge metadata={buildDerivedMetricConfidence(company, metric)} />
                              ) : null}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="Valuation Models" subtitle="DCF fair value (USD/share), Piotroski F-Score (0–9: ≥8 strong, ≤4 weak), and Altman Z (≥3 safe zone, ≤1.8 distress zone).">
            <div className="compare-table-shell">
              <table className="compare-table">
                <thead>
                  <tr>
                    <th className="compare-table-row-label">Metric</th>
                    {companies.map((company) => (
                      <th key={company.ticker} className="compare-table-company-head">{company.ticker}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th className="compare-table-row-label"><MetricLabel metricKey="fair_value_per_share" label="DCF Fair Value" /></th>
                    {companies.map((company) => {
                      const model = getModel(company, "dcf");
                      return (
                        <td key={`${company.ticker}-dcf`} className="compare-table-value is-numeric">
                          <div className="compare-metric-cell">
                            <span>{formatCurrency(getDcfFairValue(company))}</span>
                            {model ? <MetricConfidenceBadge metadata={buildModelConfidence(company, model)} /> : null}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <th className="compare-table-row-label"><MetricLabel metricKey="piotroski_score" label="Piotroski F-Score" /></th>
                    {companies.map((company) => {
                      const model = getModel(company, "piotroski");
                      return (
                        <td key={`${company.ticker}-piotroski`} className="compare-table-value is-numeric">
                          <div className="compare-metric-cell">
                            <span>{formatPiotroski(company)}</span>
                            {model ? <MetricConfidenceBadge metadata={buildModelConfidence(company, model)} /> : null}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                  <tr>
                    <th className="compare-table-row-label"><MetricLabel metricKey="altman_z_score" label="Altman Z" /></th>
                    {companies.map((company) => {
                      const model = getModel(company, "altman_z");
                      return (
                        <td key={`${company.ticker}-altman`} className="compare-table-value is-numeric">
                          <div className="compare-metric-cell">
                            <span>{formatRatio(getAltmanZ(company))}</span>
                            {model ? <MetricConfidenceBadge metadata={buildModelConfidence(company, model)} /> : null}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      ) : null}
    </div>
  );
}

function EmptyState({ title, copy }: { title: string; copy: string }) {
  return (
    <div className="compare-empty-state">
      <div className="compare-empty-title">{title}</div>
      <p className="compare-empty-copy">{copy}</p>
    </div>
  );
}

function periodLabel(period: Pick<FinancialPayload, "filing_type" | "period_end">): string {
  return `${period.filing_type} ${formatDate(period.period_end)}`;
}

function getFinancialValue(period: FinancialPayload, key: keyof FinancialPayload): number | null {
  const value = period[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function getDerivedMetric(company: CompanyCompareItemPayload, key: string): { metric_value: number | null; is_proxy: boolean; provenance: Record<string, unknown>; quality_flags: string[] } | null {
  const metric = company.metrics_summary.metrics.find((item) => item.metric_key === key);
  if (!metric) {
    return null;
  }

  return {
    metric_value: typeof metric.metric_value === "number" && Number.isFinite(metric.metric_value) ? metric.metric_value : null,
    is_proxy: Boolean(metric.is_proxy),
    provenance: toRecord(metric.provenance),
    quality_flags: metric.quality_flags ?? [],
  };
}

function getDerivedMetricValue(company: CompanyCompareItemPayload, key: string): number | null {
  const metric = getDerivedMetric(company, key);
  return metric?.metric_value ?? null;
}

function getModel(company: CompanyCompareItemPayload, modelName: string): ModelPayload | undefined {
  return company.models.models.find((model) => model.model_name === modelName);
}

function getDcfFairValue(company: CompanyCompareItemPayload): number | null {
  return asNumber(getModel(company, "dcf")?.result?.fair_value_per_share);
}

function getAltmanZ(company: CompanyCompareItemPayload): number | null {
  return asNumber(getModel(company, "altman_z")?.result?.z_score_approximate);
}

function formatPiotroski(company: CompanyCompareItemPayload): string {
  const state = resolvePiotroskiScoreState(getModel(company, "piotroski")?.result);
  if (state.rawScore === null) {
    return "—";
  }
  return state.isPartial && state.availableCriteria !== null
    ? `${state.rawScore.toFixed(1)}/${state.availableCriteria}`
    : `${state.rawScore.toFixed(1)}/${state.scoreMax}`;
}

function formatStatementValue(value: number | null | undefined): string {
  return formatCompactNumber(value);
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value);
}

function formatRatio(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return value.toFixed(2);
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function toRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }
  return value as Record<string, unknown>;
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function buildDerivedMetricConfidence(
  company: CompanyCompareItemPayload,
  metric: { is_proxy: boolean; provenance: Record<string, unknown>; quality_flags: string[] }
): MetricConfidenceMetadata {
  const missingInputs = asStringArray(metric.provenance.missing_inputs);
  const source = asString(
    metric.provenance.source_key ?? metric.provenance.statement_source ?? metric.provenance.price_source ?? metric.provenance.source
  );
  const formulaVersion = asString(metric.provenance.formula_version);
  const fallbackUsed =
    (typeof metric.provenance.fallback_used === "boolean" ? metric.provenance.fallback_used : null) ??
    metric.quality_flags.some((flag) => flag.includes("fallback")) ??
    false;

  return {
    freshness: company.metrics_summary.staleness_reason ? "stale" : "fresh",
    source,
    formulaVersion,
    missingInputsCount: missingInputs.length,
    missingInputs,
    proxyUsed: metric.is_proxy,
    fallbackUsed,
    qualityFlags: metric.quality_flags,
    stalenessReason: company.metrics_summary.staleness_reason,
  };
}

function buildModelConfidence(company: CompanyCompareItemPayload, model: ModelPayload): MetricConfidenceMetadata {
  const result = toRecord(model.result);
  const inputQuality = toRecord(result.input_quality);
  const priceSnapshot = toRecord(result.price_snapshot);
  const missingInputs = asStringArray(result.missing_inputs);
  const formulaVersion = asString(model.calculation_version) ?? model.model_version;
  const source = asString(priceSnapshot.price_source) ?? asString(result.source) ?? model.model_name;

  return {
    freshness: company.models.company?.cache_state === "stale" ? "stale" : "fresh",
    source,
    formulaVersion,
    missingInputsCount: missingInputs.length,
    missingInputs,
    proxyUsed:
      String(result.model_status ?? result.status ?? "supported") === "proxy" ||
      Boolean(inputQuality.capital_structure_proxied) ||
      Boolean(inputQuality.starting_cash_flow_proxied),
    fallbackUsed: false,
    stalenessReason: company.models.diagnostics?.stale_flags?.join(", ") || null,
  };
}
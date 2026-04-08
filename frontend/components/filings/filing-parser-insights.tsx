"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import { MetricLabel } from "@/components/ui/metric-label";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate } from "@/lib/format";
import type { FilingParserInsightPayload, RefreshState } from "@/lib/types";

interface FilingParserInsightsProps {
  insights: FilingParserInsightPayload[];
  loading?: boolean;
  error?: string | null;
  refresh?: RefreshState | null;
}

type SegmentRow = {
  name: string;
  revenue: number;
};

export function FilingParserInsights({
  insights,
  loading = false,
  error = null,
  refresh = null
}: FilingParserInsightsProps) {
  const orderedInsights = useMemo(
    () => [...insights].sort((left, right) => right.period_end.localeCompare(left.period_end)),
    [insights]
  );

  const latest = orderedInsights.length ? orderedInsights[0] : null;
  const chartData = useMemo(() => {
    return orderedInsights
      .slice(0, 6)
      .reverse()
      .map((insight) => ({
        period: insight.period_end.slice(0, 10),
        revenue: insight.revenue,
        operatingIncome: insight.operating_income,
        netIncome: insight.net_income
      }));
  }, [orderedInsights]);

  const segmentRows = useMemo(() => {
    if (!latest) {
      return [] as SegmentRow[];
    }

    return latest.segments
      .filter((segment) => Boolean(segment.name))
      .map((segment) => ({
        name: segment.name,
        revenue: segment.revenue == null ? 0 : segment.revenue
      }))
      .sort((left, right) => Math.abs(right.revenue) - Math.abs(left.revenue));
  }, [latest]);

  const maxSegmentValue = useMemo(
    () => segmentRows.reduce((maxValue, segment) => Math.max(maxValue, Math.abs(segment.revenue)), 0),
    [segmentRows]
  );
  const topFootnotes = useMemo(() => (latest?.footnotes ?? []).slice(0, 4), [latest?.footnotes]);
  const controlFlags = useMemo(() => {
    if (!latest) {
      return [] as string[];
    }
    const flags: string[] = [];
    if (latest.controls.material_weakness) {
      flags.push("material weakness");
    }
    if (latest.controls.ineffective_controls) {
      flags.push("ineffective controls");
    }
    if (latest.controls.non_reliance) {
      flags.push("non-reliance");
    }
    if (latest.controls.auditor_names.length) {
      flags.push(`auditor ${latest.controls.auditor_names.join(", ")}`);
    }
    return flags;
  }, [latest]);

  if (error) {
    return <div className="text-muted">{error}</div>;
  }

  if (loading && insights.length === 0) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">Filing parser</div>
        <div className="grid-empty-title">Parsing recent HTML filings</div>
        <div className="grid-empty-copy">Collecting revenue and profit metrics from the most recent 10-K and 10-Q filings.</div>
      </div>
    );
  }

  if (insights.length === 0) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 240 }}>
        <div className="grid-empty-kicker">Filing parser</div>
        <div className="grid-empty-title">No parsed filing snapshot yet</div>
        <div className="grid-empty-copy">
          {refresh?.triggered
            ? "The backend is parsing recent filings now. This view will populate once the run completes."
            : "Parsed filing snapshots appear after the latest 10-K or 10-Q HTML filings are cached."}
        </div>
      </div>
    );
  }

  return (
    <div className="filing-insights-shell">
      <div className="filing-insights-header">
        <div className="filing-insights-meta">
          <span className="pill">{latest?.filing_type ? latest.filing_type : "Filing"}</span>
          <span className="pill">Period {latest?.period_end ? formatDate(latest.period_end) : "Pending"}</span>
          <span className="pill">Updated {latest?.last_updated ? formatDate(latest.last_updated) : "Pending"}</span>
          {latest?.accession_number ? <span className="pill">Accession {latest.accession_number}</span> : null}
        </div>
        {latest?.source ? (
          <a className="filing-link" href={latest.source} target="_blank" rel="noreferrer">
            View SEC source
          </a>
        ) : null}
      </div>

      <div className="filing-insights-grid">
        <div className="filing-insights-card">
          <div className="filing-insights-card-title">Latest snapshot</div>
          <div className="filing-insights-card-subtitle">Extracted from HTML statement tables in the most recent filing.</div>
          <div className="filing-insights-metrics">
            <Metric label="Revenue" value={latest?.revenue} />
            <Metric label="Operating Income" value={latest?.operating_income} />
            <Metric label="Net Income" value={latest?.net_income} />
          </div>
          <div className="filing-insights-footnote">
            Non-GAAP mentions: {latest?.non_gaap.mention_count ?? 0} · Reconciliation mentions: {latest?.non_gaap.reconciliation_mentions ?? 0}
          </div>
          <div className="filing-insights-footnote">Coverage: {chartData.length} filings</div>
        </div>

        <div className="filing-insights-card">
          <div className="filing-insights-card-title">Revenue and profit trend</div>
          <div className="filing-insights-card-subtitle">Latest parsed filings ordered by period end.</div>
          <div className="filing-insights-chart-shell">
            {chartData.length ? (
              <ResponsiveContainer>
                <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                  <XAxis dataKey="period" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
                  <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
                  <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
                  <Legend formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                  <Line type="monotone" dataKey="revenue" stroke="var(--accent)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="operatingIncome" stroke="var(--positive)" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="netIncome" stroke="var(--warning)" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="sparkline-note">Trend data will appear once multiple parsed filings are available.</div>
            )}
          </div>
        </div>
      </div>

      <div className="filing-insights-card">
        <div className="filing-insights-card-title">Segment revenue</div>
        <div className="filing-insights-card-subtitle">Latest filing segment table extracted by the HTML parser.</div>
        {segmentRows.length ? (
          <div className="filing-insights-segment-list">
            {segmentRows.map((segment) => {
              const width = maxSegmentValue > 0 ? Math.min(100, Math.round((Math.abs(segment.revenue) / maxSegmentValue) * 100)) : 0;
              return (
                <div
                  key={segment.name}
                  className={`filing-insights-segment ${segment.revenue < 0 ? "is-negative" : "is-positive"}`}
                >
                  <div className="filing-insights-segment-row">
                    <span className="filing-insights-segment-name">{segment.name}</span>
                    <span className="filing-insights-segment-value">{formatCompactNumber(segment.revenue)}</span>
                  </div>
                  <div className="filing-insights-segment-bar">
                    <span style={{ width: `${width}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="sparkline-note">No segment revenue data was extracted from the latest filing.</div>
        )}
      </div>

      <div className="filing-insights-grid">
        <div className="filing-insights-card">
          <div className="filing-insights-card-title">MD&amp;A excerpt</div>
          <div className="filing-insights-card-subtitle">Latest management discussion excerpt from the primary SEC filing document.</div>
          {latest?.mdna?.excerpt ? (
            <>
              <div className="text-muted" style={{ fontSize: 13 }}>{latest.mdna.title ?? latest.mdna.label}</div>
              <div style={{ fontSize: 14, lineHeight: 1.6 }}>{latest.mdna.excerpt}</div>
              {latest.mdna.source ? (
                <a className="filing-link" href={latest.mdna.source} target="_blank" rel="noreferrer">
                  Open MD&amp;A evidence
                </a>
              ) : null}
            </>
          ) : (
            <div className="sparkline-note">No MD&amp;A section was extracted from the latest filing.</div>
          )}
        </div>

        <div className="filing-insights-card">
          <div className="filing-insights-card-title">Controls and non-GAAP signals</div>
          <div className="filing-insights-card-subtitle">Quick read on adjustment language and reporting-control disclosures.</div>
          <div className="filing-insights-metrics">
            <Metric label="Non-GAAP Terms" value={latest?.non_gaap.mention_count ?? 0} />
            <Metric label="Recon Mentions" value={latest?.non_gaap.reconciliation_mentions ?? 0} />
            <Metric label="Control Terms" value={latest?.controls.control_terms.length ?? 0} />
          </div>
          {latest?.non_gaap.excerpt ? <div className="filing-insights-footnote">{latest.non_gaap.excerpt}</div> : null}
          {controlFlags.length ? (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
              {controlFlags.map((flag) => (
                <span key={flag} className="pill">{flag}</span>
              ))}
            </div>
          ) : null}
          {latest?.controls.excerpt ? <div className="filing-insights-footnote">{latest.controls.excerpt}</div> : null}
        </div>
      </div>

      <div className="filing-insights-card">
        <div className="filing-insights-card-title">High-signal footnotes</div>
        <div className="filing-insights-card-subtitle">Selected note sections that usually carry higher underwriting signal than generic boilerplate.</div>
        {topFootnotes.length ? (
          <div className="filing-insights-segment-list">
            {topFootnotes.map((footnote) => (
              <div key={footnote.key} className="filing-insights-segment is-positive">
                <div className="filing-insights-segment-row">
                  <span className="filing-insights-segment-name">{footnote.label}</span>
                  {footnote.signal_terms.length ? <span className="filing-insights-segment-value">{footnote.signal_terms.slice(0, 2).join(" · ")}</span> : null}
                </div>
                {footnote.excerpt ? <div className="filing-insights-footnote">{footnote.excerpt}</div> : null}
                {footnote.source ? (
                  <a className="filing-link" href={footnote.source} target="_blank" rel="noreferrer">
                    Open note evidence
                  </a>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="sparkline-note">No selected high-signal footnotes were extracted from the latest filing.</div>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="filing-insights-metric">
      <div className="filing-insights-metric-label">
        <MetricLabel label={label} />
      </div>
      <div className="filing-insights-metric-value">{formatCompactNumber(value)}</div>
    </div>
  );
}


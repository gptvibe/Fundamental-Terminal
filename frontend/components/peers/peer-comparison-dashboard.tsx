"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { getCompanyPeers } from "@/lib/api";
import { CHART_AXIS_COLOR, CHART_GRID_COLOR, CHART_LEGEND_COLOR, chartLegendStyle, chartSeriesColor, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { CompanyPeersResponse, PeerMetricsPayload, PeerRevenuePoint } from "@/lib/types";
import { Panel } from "@/components/ui/panel";
import { MetricLabel } from "@/components/ui/metric-label";
import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { StatusPill } from "@/components/ui/status-pill";

const MAX_SELECTED_PEERS = 4;

type TooltipEntry = {
  color?: string;
  dataKey?: string;
  name?: string;
  payload?: Record<string, unknown>;
  value?: number;
};

interface PeerComparisonDashboardProps {
  ticker: string;
  reloadKey?: string;
}

interface SelectedPeerState {
  selectionKey: string;
  tickers: string[] | null;
}

type ScatterXAxisMetric = "revenue_growth" | "roic";
type ScatterYAxisMetric = "ev_to_ebitda" | "pe" | "fcf_yield";
type ScatterColorMode = "focus" | "sector";

type ScatterPoint = {
  ticker: string;
  name: string;
  is_focus: boolean;
  sector: string | null;
  x: number;
  y: number;
  size: number;
  sizeValue: number;
  sizeMode: "market_cap" | "proxy";
  fill: string;
};

type ScatterDotProps = {
  cx?: number;
  cy?: number;
  payload?: ScatterPoint;
};

type ScatterEnvelope = {
  points: ScatterPoint[];
  missingMetricsCount: number;
  sizeProxyCount: number;
  notes: string[];
};

const SCATTER_X_OPTIONS: Array<{ key: ScatterXAxisMetric; label: string }> = [
  { key: "revenue_growth", label: "Revenue Growth" },
  { key: "roic", label: "ROIC" },
];

const SCATTER_Y_OPTIONS: Array<{ key: ScatterYAxisMetric; label: string }> = [
  { key: "ev_to_ebitda", label: "EV/EBITDA" },
  { key: "pe", label: "P/E" },
  { key: "fcf_yield", label: "FCF Yield" },
];

export function PeerComparisonDashboard({ ticker, reloadKey }: PeerComparisonDashboardProps) {
  const selectionKey = `${ticker}:${reloadKey ?? ""}`;
  const [data, setData] = useState<CompanyPeersResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Scope transient peer selections to the current company so navigation falls back to fresh sector-based defaults.
  const [selectedPeerState, setSelectedPeerState] = useState<SelectedPeerState>({ selectionKey, tickers: null });
  const selectedTickers = selectedPeerState.selectionKey === selectionKey ? selectedPeerState.tickers : null;

  useEffect(() => {
    setSelectedPeerState((current) => (current.selectionKey === selectionKey ? current : { selectionKey, tickers: null }));
  }, [selectionKey]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const response = await getCompanyPeers(ticker, selectedTickers ?? undefined);
        if (cancelled) {
          return;
        }
        setData(response);
        if (selectedTickers === null) {
          setSelectedPeerState((current) => {
            if (current.selectionKey !== selectionKey || current.tickers !== null) {
              return current;
            }
            return { selectionKey, tickers: response.selected_tickers };
          });
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError instanceof Error ? nextError.message : "Unable to load peer comparison");
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
  }, [ticker, reloadKey, selectedTickers, selectionKey]);

  const peers = useMemo(() => data?.peers ?? [], [data?.peers]);
  const strictModeNote = data?.notes?.strict_official_mode ?? null;
  const activeTickers = useMemo(() => selectedTickers ?? data?.selected_tickers ?? [], [data?.selected_tickers, selectedTickers]);
  const displayedPeers = useMemo(
    () => peers.filter((peer) => peer.is_focus || activeTickers.includes(peer.ticker)),
    [activeTickers, peers]
  );
  const tickerColorMap = useMemo(() => buildTickerColorMap(displayedPeers), [displayedPeers]);
  const radarData = useMemo(() => buildRadarData(displayedPeers), [displayedPeers]);
  const barData = useMemo(() => buildBarData(displayedPeers), [displayedPeers]);
  const [scatterXAxis, setScatterXAxis] = useState<ScatterXAxisMetric>("revenue_growth");
  const [scatterYAxis, setScatterYAxis] = useState<ScatterYAxisMetric>("pe");
  const [scatterColorMode, setScatterColorMode] = useState<ScatterColorMode>("focus");
  const scatterEnvelope = useMemo(
    () => buildScatterEnvelope(displayedPeers, scatterXAxis, scatterYAxis, scatterColorMode),
    [displayedPeers, scatterColorMode, scatterXAxis, scatterYAxis]
  );
  const scatterPeers = useMemo(() => scatterEnvelope.points.filter((point) => !point.is_focus), [scatterEnvelope.points]);
  const scatterFocus = useMemo(() => scatterEnvelope.points.filter((point) => point.is_focus), [scatterEnvelope.points]);
  const [compareDrawerOpen, setCompareDrawerOpen] = useState(true);
  const [tableScrollTop, setTableScrollTop] = useState(0);
  const rowHeight = 44;
  const tableViewportHeight = 360;
  const overscan = 6;
  const visibleRowCount = Math.ceil(tableViewportHeight / rowHeight) + overscan * 2;
  const startIndex = Math.max(0, Math.floor(tableScrollTop / rowHeight) - overscan);
  const endIndex = Math.min(displayedPeers.length, startIndex + visibleRowCount);
  const visibleRows = displayedPeers.slice(startIndex, endIndex);
  const topSpacerHeight = startIndex * rowHeight;
  const bottomSpacerHeight = Math.max(0, (displayedPeers.length - endIndex) * rowHeight);

  function togglePeer(peerTicker: string) {
    setSelectedPeerState((current) => {
      const active = current.selectionKey === selectionKey ? current.tickers ?? data?.selected_tickers ?? [] : data?.selected_tickers ?? [];
      if (active.includes(peerTicker)) {
        return { selectionKey, tickers: active.filter((item) => item !== peerTicker) };
      }
      if (active.length >= MAX_SELECTED_PEERS) {
        return current;
      }
      return { selectionKey, tickers: [...active, peerTicker] };
    });
  }

  function resetPeers() {
    setSelectedPeerState({ selectionKey, tickers: [] });
  }

  return (
    <Panel
      title="Peer Comparison"
      subtitle={loading ? "Loading cached peer set..." : `Compare ${ticker} against ${data?.peer_basis ?? "cached peers"}`}
      aside={data ? <StatusPill state={data.refresh} /> : undefined}
    >
      {error ? (
        <div className="text-muted">{error}</div>
      ) : !loading && peers.length === 0 ? (
        <div className="grid-empty-state" style={{ minHeight: 220 }}>
          <div className="grid-empty-kicker">Peer cache</div>
          <div className="grid-empty-title">{strictModeNote ? "Peer comparison disabled in strict mode" : "No peer data available yet"}</div>
          <div className="grid-empty-copy">{strictModeNote ?? "Refresh more cached companies to unlock richer industry comparisons."}</div>
        </div>
      ) : (
        <div className="peer-dashboard-shell">
          <SourceFreshnessSummary
            provenance={data?.provenance}
            asOf={data?.as_of}
            lastRefreshedAt={data?.last_refreshed_at}
            sourceMix={data?.source_mix}
            confidenceFlags={data?.confidence_flags}
            emptyMessage="Peer source metadata will appear after the comparison payload loads."
          />

          {strictModeNote ? (
            <div className="grid-empty-state" style={{ minHeight: 220 }}>
              <div className="grid-empty-kicker">Strict official mode</div>
              <div className="grid-empty-title">Peer comparison disabled</div>
              <div className="grid-empty-copy">{strictModeNote}</div>
            </div>
          ) : null}

          {!strictModeNote ? <div className="peer-dashboard-header">
            <div className="peer-compare-tray">
              <div className="peer-compare-tray-header">
                <div>
                  <div className="peer-section-title">Compare Tray</div>
                  <div className="peer-section-subtitle">Focus company plus up to {MAX_SELECTED_PEERS} cached peers.</div>
                </div>
                <button
                  type="button"
                  className="ticker-button peer-compare-toggle"
                  aria-expanded={compareDrawerOpen}
                  onClick={() => setCompareDrawerOpen((current) => !current)}
                >
                  {compareDrawerOpen ? "Collapse compare tray" : "Open compare tray"}
                </button>
              </div>
              <div className="peer-compare-selection" aria-live="polite">
                <span className="pill">Selected {activeTickers.length}/{MAX_SELECTED_PEERS}</span>
                {displayedPeers.map((peer) => (
                  <span key={`${peer.ticker}:selected`} className={`peer-selection-pill${peer.is_focus ? " focus" : ""}`}>
                    {peer.ticker}
                  </span>
                ))}
              </div>
              {compareDrawerOpen ? (
                <div className="peer-chip-row" role="group" aria-label="Select peers to compare">
                  {data?.available_companies.map((company) => {
                    const active = company.is_focus || activeTickers.includes(company.ticker);
                    return (
                      <button
                        key={company.ticker}
                        type="button"
                        className={`peer-chip${active ? " active" : ""}${company.is_focus ? " focus" : ""}`}
                        onClick={() => {
                          if (!company.is_focus) {
                            togglePeer(company.ticker);
                          }
                        }}
                        aria-pressed={active}
                        title={`${company.ticker} — ${company.name}`}
                      >
                        <span className="peer-chip-ticker">{company.ticker}</span>
                        <span className="peer-chip-name">{company.name}</span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
            <div className="peer-dashboard-meta">
              <span className="pill">Up to {MAX_SELECTED_PEERS} peers</span>
              <button type="button" className="ticker-button" onClick={resetPeers}>
                Reset to Focus
              </button>
            </div>
          </div> : null}

          {!strictModeNote ? <div className="peer-chart-card">
            <div className="peer-section-title">Quality Radar</div>
            <div className="peer-section-subtitle">ROIC, implied growth, shareholder yield, and fair-value gap normalized for decision-grade peer comparison.</div>
            <div className="peer-chart-shell peer-chart-tall">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData} outerRadius="70%">
                  <PolarGrid stroke="var(--panel-border)" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: CHART_LEGEND_COLOR, fontSize: 12 }} />
                  <PolarRadiusAxis tick={false} axisLine={false} domain={[0, 100]} />
                  <Tooltip content={<RadarTooltip />} />
                  <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                  {peers.map((peer, index) => (
                    <Radar
                      key={peer.ticker}
                      name={peer.ticker}
                      dataKey={peer.ticker}
                      stroke={tickerColorMap[peer.ticker] ?? chartSeriesColor(index)}
                      fill={tickerColorMap[peer.ticker] ?? chartSeriesColor(index)}
                      fillOpacity={peer.is_focus ? 0.24 : 0.12}
                      strokeWidth={peer.is_focus ? 2.6 : 1.8}
                    />
                  ))}
                </RadarChart>
              </ResponsiveContainer>
            </div>
          </div> : null}

          {!strictModeNote ? <div className="peer-chart-card">
            <div className="peer-section-title">Valuation + Return Signals</div>
            <div className="peer-section-subtitle">Fair value gap, ROIC, and shareholder yield across the peer set.</div>
            <div className="peer-chart-shell peer-chart-medium">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={barData} layout="vertical" margin={{ top: 8, right: 24, left: 8, bottom: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} horizontal={false} />
                  <XAxis type="number" stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={formatPercentAxis} />
                  <YAxis dataKey="ticker" type="category" width={64} tick={{ fill: CHART_LEGEND_COLOR, fontSize: 12 }} />
                  <Tooltip content={<BarTooltip />} />
                  <Legend wrapperStyle={chartLegendStyle()} formatter={(value) => <span style={{ color: CHART_LEGEND_COLOR }}><MetricLabel label={String(value)} /></span>} />
                  <Bar dataKey="fairValueGap" name="Fair Value Gap" radius={[0, 8, 8, 0]}>
                    {barData.map((entry) => (
                      <Cell key={`${entry.ticker}-fvg`} fill={entry.is_focus ? "var(--positive)" : "var(--positive)"} />
                    ))}
                  </Bar>
                  <Bar dataKey="roic" name="ROIC" radius={[0, 8, 8, 0]}>
                    {barData.map((entry) => (
                      <Cell key={`${entry.ticker}-roic`} fill={entry.is_focus ? "var(--accent)" : "var(--accent)"} />
                    ))}
                  </Bar>
                  <Bar dataKey="shareholderYield" name="Shareholder Yield" radius={[0, 8, 8, 0]}>
                    {barData.map((entry) => (
                      <Cell key={`${entry.ticker}-sy`} fill={entry.is_focus ? "var(--warning)" : "var(--warning)"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div> : null}

          {!strictModeNote ? <div className="peer-chart-card">
            <div className="peer-section-title">Valuation Positioning Scatter</div>
            <div className="peer-section-subtitle">Visual view of whether {ticker} is cheap or expensive versus quality and growth.</div>

            <div className="peer-scatter-controls" role="group" aria-label="Peer scatter metric controls">
              <div className="peer-scatter-control-group">
                <span className="peer-scatter-control-label">X-axis</span>
                {SCATTER_X_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={`peer-scatter-option${scatterXAxis === option.key ? " active" : ""}`}
                    onClick={() => setScatterXAxis(option.key)}
                    aria-pressed={scatterXAxis === option.key}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <div className="peer-scatter-control-group">
                <span className="peer-scatter-control-label">Y-axis</span>
                {SCATTER_Y_OPTIONS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    className={`peer-scatter-option${scatterYAxis === option.key ? " active" : ""}`}
                    onClick={() => setScatterYAxis(option.key)}
                    aria-pressed={scatterYAxis === option.key}
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <div className="peer-scatter-control-group">
                <span className="peer-scatter-control-label">Color</span>
                <button
                  type="button"
                  className={`peer-scatter-option${scatterColorMode === "focus" ? " active" : ""}`}
                  onClick={() => setScatterColorMode("focus")}
                  aria-pressed={scatterColorMode === "focus"}
                >
                  Focus vs peers
                </button>
                <button
                  type="button"
                  className={`peer-scatter-option${scatterColorMode === "sector" ? " active" : ""}`}
                  onClick={() => setScatterColorMode("sector")}
                  aria-pressed={scatterColorMode === "sector"}
                >
                  Sector
                </button>
              </div>
            </div>

            {scatterEnvelope.points.length >= 2 ? (
              <>
                <div className="peer-chart-shell peer-chart-medium">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 8, right: 18, left: 10, bottom: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
                      <XAxis
                        type="number"
                        dataKey="x"
                        stroke={CHART_AXIS_COLOR}
                        tick={chartTick()}
                        tickFormatter={(value) => formatScatterValue(scatterXAxis, Number(value ?? 0))}
                        name={scatterXAxis === "roic" ? "ROIC" : "Revenue Growth"}
                      />
                      <YAxis
                        type="number"
                        dataKey="y"
                        stroke={CHART_AXIS_COLOR}
                        tick={chartTick()}
                        tickFormatter={(value) => formatScatterValue(scatterYAxis, Number(value ?? 0))}
                        name={scatterYAxis === "ev_to_ebitda" ? "EV/EBITDA" : scatterYAxis === "pe" ? "P/E" : "FCF Yield"}
                      />
                      <ZAxis type="number" dataKey="size" range={[70, 460]} name="Market cap" />
                      <Tooltip content={<ScatterTooltip xMetric={scatterXAxis} yMetric={scatterYAxis} />} />
                      <Scatter name="Peers" data={scatterPeers} shape={(props: ScatterDotProps) => renderScatterDot(props, false)} />
                      <Scatter name={`${ticker} (focus)`} data={scatterFocus} shape={(props: ScatterDotProps) => renderScatterDot(props, true)} />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>

                <div className="peer-scatter-legend-row">
                  <span className="peer-scatter-legend-item focus">Focus company</span>
                  <span className="peer-scatter-legend-item">Peers</span>
                </div>
              </>
            ) : (
              <div className="grid-empty-state grid-empty-state-tall">
                <div className="grid-empty-kicker">Scatter metrics</div>
                <div className="grid-empty-title">Insufficient peer metrics for scatter plot</div>
                <div className="grid-empty-copy">
                  Not enough peers have complete x/y valuation metrics to render this view. Try another metric combination.
                </div>
              </div>
            )}

            {scatterEnvelope.notes.map((note) => (
              <div key={note} className="peer-footnote">{note}</div>
            ))}

            {data?.source_mix?.official_only ? (
              <div className="peer-footnote">
                Official-only source mode may suppress vendor-derived valuation fields when no official price feed is available.
              </div>
            ) : null}
          </div> : null}

          {!strictModeNote ? <div className="peer-bottom-grid">
            <div className="peer-chart-card">
              <div className="peer-section-title">Revenue Growth Tracks</div>
              <div className="peer-section-subtitle">Small multiples show historical revenue growth from cached annual filings.</div>
              <div className="peer-mini-grid">
                {displayedPeers.map((peer) => (
                  <div key={peer.ticker} className={`peer-mini-card${peer.is_focus ? " focus" : ""}`}>
                    <div className="peer-mini-header">
                      <span>{peer.ticker}</span>
                      <span>{formatPercent(peer.revenue_growth)}</span>
                    </div>
                    <div className="peer-mini-shell">
                      {peer.revenue_history.length ? (
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={buildRevenueLineData(peer.revenue_history)} margin={{ top: 10, right: 6, left: 0, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID_COLOR} />
                            <XAxis dataKey="label" stroke={CHART_AXIS_COLOR} tick={chartTick(10)} />
                            <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick(10)} tickFormatter={formatMiniPercent} width={30} />
                            <Tooltip content={<RevenueTooltip ticker={peer.ticker} />} />
                            <Line
                              type="monotone"
                              dataKey="value"
                              stroke={tickerColorMap[peer.ticker] ?? "var(--positive)"}
                              strokeWidth={2.2}
                              dot={{ r: 2.6, fill: tickerColorMap[peer.ticker] ?? "var(--positive)", strokeWidth: 0 }}
                              activeDot={{ r: 4 }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      ) : (
                        <div className="text-muted">No revenue history</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="peer-chart-card">
              <div className="peer-section-title">Metrics Table</div>
              <div className="peer-section-subtitle">Sortable-at-a-glance values from cached prices, filings, and model results.</div>
              <div
                className="peer-table-shell"
                style={{ maxHeight: tableViewportHeight, overflowY: "auto" }}
                onScroll={(event) => setTableScrollTop(event.currentTarget.scrollTop)}
              >
                <table className="peer-metrics-table">
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>P/E</th>
                      <th>EV/EBIT*</th>
                      <th>P/FCF</th>
                      <th>ROE</th>
                      <th>ROIC</th>
                      <th>Revenue Growth</th>
                      <th>Implied Growth</th>
                      <th>Shareholder Yield</th>
                      <th>Fair Value Gap</th>
                      <th>Band Percentile</th>
                      <th>Piotroski</th>
                      <th>Altman Proxy</th>
                      <th>Price</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topSpacerHeight > 0 ? (
                      <tr aria-hidden>
                        <td colSpan={15} style={{ height: topSpacerHeight, padding: 0, border: "none" }} />
                      </tr>
                    ) : null}
                    {visibleRows.map((peer) => (
                      <tr key={peer.ticker} className={peer.is_focus ? "is-focus" : undefined}>
                        <td>
                          <div className="peer-table-company">
                      <span className="peer-table-ticker" style={{ color: tickerColorMap[peer.ticker] ?? "var(--text)" }}>
                              {peer.ticker}
                            </span>
                            <span className="peer-table-name">{peer.name}</span>
                          </div>
                        </td>
                        <td>{formatMultiple(peer.pe)}</td>
                        <td>{formatMultiple(peer.ev_to_ebit)}</td>
                        <td>{formatMultiple(peer.price_to_free_cash_flow)}</td>
                        <td>{formatPercent(peer.roe)}</td>
                        <td>{formatPercent(peer.roic)}</td>
                        <td>{formatPercent(peer.revenue_growth)}</td>
                        <td>{formatValuationMetric(peer.implied_growth, peer.reverse_dcf_model_status)}</td>
                        <td>{formatPercent(peer.shareholder_yield)}</td>
                        <td>{formatValuationMetric(peer.fair_value_gap, peer.dcf_model_status)}</td>
                        <td>{formatPercent(peer.valuation_band_percentile)}</td>
                        <td>{formatScore(peer.piotroski_score)}</td>
                        <td>{formatSigned(peer.altman_z_score)}</td>
                        <td>{formatCurrency(peer.latest_price)}</td>
                        <td>{peer.last_checked ? formatDate(peer.last_checked) : "—"}</td>
                      </tr>
                    ))}
                    {bottomSpacerHeight > 0 ? (
                      <tr aria-hidden>
                        <td colSpan={15} style={{ height: bottomSpacerHeight, padding: 0, border: "none" }} />
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
              <div className="peer-footnote">* {data?.notes.ev_to_ebit}</div>
              <div className="peer-footnote">{data?.notes.price_to_free_cash_flow}</div>
              {data?.notes.piotroski ? <div className="peer-footnote">{data.notes.piotroski}</div> : null}
            </div>
          </div> : null}
        </div>
      )}
    </Panel>
  );
}

function buildTickerColorMap(peers: PeerMetricsPayload[]): Record<string, string> {
  return Object.fromEntries(
    peers.map((peer, index) => [peer.ticker, peer.is_focus ? "var(--chart-series-1)" : chartSeriesColor(index + 1)])
  );
}

function buildRadarData(peers: PeerMetricsPayload[]) {
  const metrics = [
    { key: "roic", label: "ROIC", normalize: (value: number | null) => clamp((value ?? 0) * 250, 0, 100) },
    { key: "implied_growth", label: "Implied Growth", normalize: (value: number | null) => clamp((value ?? 0) * 200 + 40, 0, 100) },
    { key: "shareholder_yield", label: "Shareholder Yield", normalize: (value: number | null) => clamp((value ?? 0) * 350 + 30, 0, 100) },
    { key: "fair_value_gap", label: "Fair Value Gap", normalize: (value: number | null) => clamp((value ?? 0) * 200 + 50, 0, 100) }
  ] as const;

  return metrics.map((metric) => ({
    metric: metric.label,
    ...Object.fromEntries(
      peers.map((peer) => [peer.ticker, metric.normalize(peerMetricValue(peer, metric.key))])
    )
  }));
}

function peerMetricValue(
  peer: PeerMetricsPayload,
  key: "roic" | "implied_growth" | "shareholder_yield" | "fair_value_gap"
): number | null {
  switch (key) {
    case "roic":
      return peer.roic;
    case "implied_growth":
      return peer.reverse_dcf_model_status === "unsupported" ? null : peer.implied_growth;
    case "shareholder_yield":
      return peer.shareholder_yield;
    case "fair_value_gap":
      return peer.dcf_model_status === "unsupported" ? null : peer.fair_value_gap;
  }
}

function buildBarData(peers: PeerMetricsPayload[]) {
  return peers.map((peer) => ({
    ticker: peer.ticker,
    is_focus: peer.is_focus,
    fairValueGap: peer.dcf_model_status === "unsupported" ? null : peer.fair_value_gap,
    roic: peer.roic,
    shareholderYield: peer.shareholder_yield
  }));
}

function buildScatterEnvelope(
  peers: PeerMetricsPayload[],
  xMetric: ScatterXAxisMetric,
  yMetric: ScatterYAxisMetric,
  colorMode: ScatterColorMode
): ScatterEnvelope {
  const notes: string[] = [];
  const sectorColorMap = buildSectorColorMap(peers);
  let missingMetricsCount = 0;
  let sizeProxyCount = 0;

  const points: ScatterPoint[] = [];
  for (const peer of peers) {
    const x = resolveScatterMetric(peer, xMetric);
    const y = resolveScatterMetric(peer, yMetric);

    if (x == null || y == null) {
      missingMetricsCount += 1;
      continue;
    }

    const bubbleSize = resolvePeerBubbleSize(peer);
    if (!bubbleSize) {
      missingMetricsCount += 1;
      continue;
    }

    if (bubbleSize.mode === "proxy") {
      sizeProxyCount += 1;
    }

    const fill = colorMode === "sector"
      ? (sectorColorMap[peer.sector ?? "Unknown"] ?? chartSeriesColor(4))
      : (peer.is_focus ? "var(--chart-series-1)" : "var(--chart-series-3)");

    points.push({
      ticker: peer.ticker,
      name: peer.name,
      is_focus: peer.is_focus,
      sector: peer.sector,
      x,
      y,
      size: bubbleSize.normalizedSize,
      sizeValue: bubbleSize.rawSize,
      sizeMode: bubbleSize.mode,
      fill,
    });
  }

  if (missingMetricsCount > 0) {
    notes.push(`${missingMetricsCount} peer rows were omitted because selected scatter metrics were unavailable.`);
  }
  if (sizeProxyCount > 0) {
    notes.push(`${sizeProxyCount} bubble sizes use a price proxy because market-cap fields were unavailable.`);
  }

  return {
    points,
    missingMetricsCount,
    sizeProxyCount,
    notes,
  };
}

function buildSectorColorMap(peers: PeerMetricsPayload[]): Record<string, string> {
  const sectors = Array.from(new Set(peers.map((peer) => peer.sector ?? "Unknown")));
  return Object.fromEntries(sectors.map((sector, index) => [sector, chartSeriesColor(index + 2)]));
}

function resolveScatterMetric(peer: PeerMetricsPayload, metric: ScatterXAxisMetric | ScatterYAxisMetric): number | null {
  switch (metric) {
    case "revenue_growth":
      return asFiniteNumber(peer.revenue_growth);
    case "roic":
      return asFiniteNumber(peer.roic);
    case "pe":
      return asFiniteNumber(peer.pe);
    case "ev_to_ebitda":
      return asFiniteNumber(peer.ev_to_ebit);
    case "fcf_yield": {
      const multiple = asFiniteNumber(peer.price_to_free_cash_flow);
      if (multiple == null || multiple === 0) {
        return null;
      }
      return 1 / multiple;
    }
  }
}

function resolvePeerBubbleSize(peer: PeerMetricsPayload): { rawSize: number; normalizedSize: number; mode: "market_cap" | "proxy" } | null {
  const peerRecord = peer as unknown as Record<string, unknown>;
  const marketCap = asFiniteNumber(peerRecord.market_cap) ?? asFiniteNumber(peerRecord.market_cap_proxy);
  if (marketCap != null && marketCap > 0) {
    return {
      rawSize: marketCap,
      normalizedSize: normalizeBubbleSize(marketCap),
      mode: "market_cap",
    };
  }

  const price = asFiniteNumber(peer.latest_price);
  if (price == null || price <= 0) {
    return null;
  }

  return {
    rawSize: price,
    normalizedSize: normalizeBubbleSize(price),
    mode: "proxy",
  };
}

function normalizeBubbleSize(value: number): number {
  return clamp(Math.sqrt(Math.max(value, 0.0001)) * 6, 10, 90);
}

function renderScatterDot(
  props: ScatterDotProps,
  focus: boolean
) {
  const cx = props.cx ?? 0;
  const cy = props.cy ?? 0;
  const payload = props.payload;
  const radius = focus ? 8.8 : 6.4;
  const fill = payload?.fill ?? (focus ? "var(--chart-series-1)" : "var(--chart-series-3)");

  return (
    <g>
      <circle cx={cx} cy={cy} r={radius} fill={fill} fillOpacity={focus ? 0.96 : 0.8} stroke={focus ? "var(--text)" : "var(--panel)"} strokeWidth={focus ? 2.2 : 1.2} />
    </g>
  );
}

function formatScatterValue(metric: ScatterXAxisMetric | ScatterYAxisMetric, value: number): string {
  if (metric === "pe" || metric === "ev_to_ebitda") {
    return `${value.toFixed(0)}x`;
  }
  return `${(value * 100).toFixed(0)}%`;
}

function formatValuationMetric(value: number | null, status: string | null | undefined): string {
  if (status === "unsupported") {
    return "Unsupported";
  }
  return formatPercent(value);
}

function buildRevenueLineData(history: PeerRevenuePoint[]) {
  return history.map((point) => ({
    label: new Intl.DateTimeFormat("en-US", { year: "2-digit" }).format(new Date(point.period_end)),
    fullDate: point.period_end,
    revenue: point.revenue,
    value: point.revenue_growth === null ? null : point.revenue_growth * 100
  }));
}

function RadarTooltip({ active, payload }: { active?: boolean; payload?: TooltipEntry[] }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{String(payload[0]?.payload?.metric ?? "Metric")}</div>
      {payload.map((entry) => (
        <TooltipRow key={entry.name} label={String(entry.name ?? entry.dataKey ?? "Value")} value={`${Math.round(Number(entry.value ?? 0))}/100`} color={entry.color ?? "var(--positive)"} />
      ))}
    </div>
  );
}

function BarTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipEntry[]; label?: string }) {
  if (!active || !payload?.length) {
    return null;
  }

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{label}</div>
      {payload.map((entry) => (
        <TooltipRow key={entry.dataKey} label={String(entry.name ?? entry.dataKey ?? "Metric")} value={formatMultiple(asFiniteNumber(entry.value))} color={entry.color ?? "var(--positive)"} />
      ))}
    </div>
  );
}

function RevenueTooltip({ active, payload, label, ticker }: { active?: boolean; payload?: TooltipEntry[]; label?: string; ticker: string }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload ?? {};
  const revenue = asFiniteNumber(point.revenue);
  const growth = asFiniteNumber(point.value);

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{ticker} · {label}</div>
      <TooltipRow label="Revenue Growth" value={growth === null ? "—" : `${growth.toFixed(2)}%`} color="var(--accent)" />
      <TooltipRow label="Revenue" value={formatCompactNumber(revenue)} color="var(--positive)" />
      <TooltipRow label="Period End" value={typeof point.fullDate === "string" ? formatDate(point.fullDate) : "—"} color="var(--warning)" />
    </div>
  );
}

function ScatterTooltip({
  active,
  payload,
  xMetric,
  yMetric,
}: {
  active?: boolean;
  payload?: TooltipEntry[];
  xMetric: ScatterXAxisMetric;
  yMetric: ScatterYAxisMetric;
}) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload as ScatterPoint | undefined;
  if (!point) {
    return null;
  }

  const sizeLabel = point.sizeMode === "market_cap" ? "Market cap" : "Size proxy";

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-label">{point.ticker} · {point.name}</div>
      <TooltipRow label={xMetric === "roic" ? "ROIC" : "Revenue Growth"} value={formatScatterValue(xMetric, point.x)} color="var(--accent)" />
      <TooltipRow label={yMetric === "ev_to_ebitda" ? "EV/EBITDA" : yMetric === "pe" ? "P/E" : "FCF Yield"} value={formatScatterValue(yMetric, point.y)} color="var(--positive)" />
      <TooltipRow label={sizeLabel} value={formatCompactNumber(point.sizeValue)} color="var(--warning)" />
      <TooltipRow label="Sector" value={point.sector ?? "Unknown"} color="var(--text-muted)" />
    </div>
  );
}

function TooltipRow({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="chart-tooltip-row">
      <span className="chart-tooltip-key">
        <span className="chart-tooltip-dot" style={{ background: color }} />
        {label}
      </span>
      <span className="chart-tooltip-value">{value}</span>
    </div>
  );
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatMultiple(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return `${value.toFixed(Math.abs(value) >= 100 ? 0 : 2)}x`;
}

function formatAxisMultiple(value: number): string {
  return `${value.toFixed(0)}x`;
}

function formatPercentAxis(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function formatMiniPercent(value: number): string {
  return `${value.toFixed(0)}%`;
}

function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: value >= 100 ? 0 : 2
  }).format(value);
}

function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return `${value.toFixed(1)}/9`;
}

function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
    signDisplay: "exceptZero"
  }).format(value);
}

"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  Treemap,
  XAxis,
  YAxis
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, chartTick } from "@/lib/chart-theme";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import type {
  FinancialPayload,
  FinancialSegmentPayload,
  SegmentAnalysisPayload,
  SegmentDisclosurePayload,
  SegmentLensPayload,
} from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const SEGMENT_COLORS = ["var(--positive)", "var(--accent)", "var(--warning)", "var(--negative)", "#A855F7", "var(--positive)", "#64D2FF"];

type SegmentKind = "business" | "geographic";

type SegmentPoint = {
  id: string;
  name: string;
  axisLabel: string | null;
  kind: "business" | "geographic" | "other";
  revenue: number;
  share: number | null;
  growth: number | null;
  operatingIncome: number | null;
  assets: number | null;
  color: string;
};

type TooltipEntry = {
  payload?: SegmentPoint;
  value?: number | string;
  name?: string;
  color?: string;
};

interface BusinessSegmentBreakdownProps {
  financials: FinancialPayload[];
  segmentAnalysis?: SegmentAnalysisPayload | null;
}

export function BusinessSegmentBreakdown({ financials, segmentAnalysis = null }: BusinessSegmentBreakdownProps) {
  const noFinancials = financials.length === 0;
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  const availableKinds = useMemo(() => {
    const kinds = new Set<SegmentKind>();
    for (const statement of financials) {
      for (const segment of statement.segment_breakdown) {
        if ((segment.kind === "business" || segment.kind === "geographic") && typeof segment.revenue === "number" && segment.revenue > 0) {
          kinds.add(segment.kind);
        }
      }
    }
    if (segmentAnalysis?.business) {
      kinds.add("business");
    }
    if (segmentAnalysis?.geographic) {
      kinds.add("geographic");
    }
    return kinds;
  }, [financials, segmentAnalysis]);

  const preferredKind: SegmentKind = availableKinds.has("business") ? "business" : "geographic";
  const [activeKind, setActiveKind] = useState<SegmentKind>(preferredKind);

  useEffect(() => {
    if (!availableKinds.has(activeKind)) {
      setActiveKind(preferredKind);
    }
  }, [activeKind, availableKinds, preferredKind]);

  const segmentStatements = useMemo(() => {
    const statementsWithKind = financials.filter((statement) => hasKindSegments(statement, activeKind));
    const annual = statementsWithKind.filter((statement) => ANNUAL_FORMS.has(statement.filing_type));
    if (annual.length > 0) {
      return annual;
    }
    return statementsWithKind;
  }, [activeKind, financials]);

  const latestStatement = segmentStatements[0] ?? null;
  const previousStatement = segmentStatements[1] ?? null;
  const activeLens = activeKind === "business" ? segmentAnalysis?.business ?? null : segmentAnalysis?.geographic ?? null;

  const segmentPoints = useMemo(() => {
    if (!latestStatement) {
      return [] as SegmentPoint[];
    }

    const previousMap = new Map<string, FinancialSegmentPayload>(
      (previousStatement?.segment_breakdown ?? [])
        .filter((segment) => segment.kind === activeKind)
        .map((segment) => [segment.segment_id, segment])
    );

    const latestSegments = latestStatement.segment_breakdown
      .filter((segment) => segment.kind === activeKind && typeof segment.revenue === "number" && segment.revenue > 0)
      .sort((left, right) => (right.revenue ?? 0) - (left.revenue ?? 0));

    const totalRevenue = latestStatement.revenue ?? latestSegments.reduce((sum, segment) => sum + (segment.revenue ?? 0), 0);

    return latestSegments.map((segment, index) => {
      const currentRevenue = segment.revenue ?? 0;
      const previousRevenue = previousMap.get(segment.segment_id)?.revenue ?? null;
      const growth = previousRevenue && previousRevenue !== 0 ? (currentRevenue - previousRevenue) / Math.abs(previousRevenue) : null;

      return {
        id: segment.segment_id,
        name: segment.segment_name,
        axisLabel: segment.axis_label,
        kind: segment.kind,
        revenue: currentRevenue,
        share:
          segment.share_of_revenue ??
          (typeof totalRevenue === "number" && totalRevenue !== 0 ? currentRevenue / Math.abs(totalRevenue) : null),
        growth,
        operatingIncome: segment.operating_income ?? null,
        assets: segment.assets ?? null,
        color: SEGMENT_COLORS[index % SEGMENT_COLORS.length]
      } satisfies SegmentPoint;
    });
  }, [activeKind, latestStatement, previousStatement]);

  useEffect(() => {
    if (selectedSegmentId && !segmentPoints.some((segment) => segment.id === selectedSegmentId)) {
      setSelectedSegmentId(null);
    }
  }, [selectedSegmentId, segmentPoints]);

  const selectedSegment = useMemo(
    () => segmentPoints.find((segment) => segment.id === selectedSegmentId) ?? null,
    [segmentPoints, selectedSegmentId]
  );

  const growthChartData = useMemo(
    () => (selectedSegment ? [selectedSegment] : segmentPoints),
    [segmentPoints, selectedSegment]
  );

  const hasMarginData = useMemo(
    () => segmentPoints.some((segment) => segment.operatingIncome !== null),
    [segmentPoints]
  );

  const marginChartData = useMemo(
    () =>
      (selectedSegment ? [selectedSegment] : segmentPoints)
        .filter((segment) => segment.operatingIncome !== null)
        .map((segment) => ({
          ...segment,
          operatingMargin:
            segment.operatingIncome !== null && segment.revenue !== 0
              ? segment.operatingIncome / segment.revenue
              : null,
        })),
    [segmentPoints, selectedSegment]
  );

  const pieChartData = useMemo(() => {
    if (!selectedSegment) {
      return segmentPoints;
    }

    const otherRevenue = segmentPoints.reduce((sum, segment) => {
      if (segment.id === selectedSegment.id) {
        return sum;
      }
      return sum + segment.revenue;
    }, 0);

    return [
      selectedSegment,
      ...(otherRevenue > 0
        ? [
            {
              id: "other",
              name: "Other Segments",
              axisLabel: selectedSegment.axisLabel,
              kind: selectedSegment.kind,
              revenue: otherRevenue,
              share: otherRevenue / (otherRevenue + selectedSegment.revenue),
              growth: null,
              operatingIncome: null,
              assets: null,
              color: "var(--text-muted)"
            } satisfies SegmentPoint
          ]
        : [])
    ];
  }, [segmentPoints, selectedSegment]);

  function toggleSegment(segmentId: string) {
    setSelectedSegmentId((current) => (current === segmentId ? null : segmentId));
  }

  if (noFinancials) {
    return (
      <div className="sparkline-note">
        No business segment breakdowns are reported for this company. If segments become available in SEC filings, they will appear here automatically.
      </div>
    );
  }

  if (!segmentPoints.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 320 }}>
        <div className="grid-empty-kicker">Reported segments</div>
        <div className="grid-empty-title">No cached segment breakdown yet</div>
        <div className="grid-empty-copy">
          Refresh the cache to backfill reported segment revenue from SEC filings. Some issuers may only disclose limited or geographic breakdowns.
        </div>
      </div>
    );
  }

  return (
    <div className="segment-breakdown-shell">
      <div className="segment-breakdown-toolbar" style={{ gap: 14 }}>
        <div className="segment-filter-row">
          {[...availableKinds].map((kind) => (
            <button
              key={kind}
              type="button"
              className={`chart-chip ${activeKind === kind ? "chart-chip-active" : ""}`}
              onClick={() => {
                setActiveKind(kind);
                setSelectedSegmentId(null);
              }}
            >
              {kind === "business" ? "Business" : "Geography"}
            </button>
          ))}
        </div>

        <div className="segment-filter-row">
          <button
            type="button"
            className={`chart-chip ${selectedSegmentId === null ? "chart-chip-active" : ""}`}
            onClick={() => setSelectedSegmentId(null)}
          >
            All Segments
          </button>
          {segmentPoints.map((segment) => (
            <button
              key={segment.id}
              type="button"
              className={`chart-chip ${selectedSegmentId === segment.id ? "chart-chip-active" : ""}`}
              onClick={() => toggleSegment(segment.id)}
              style={{ borderColor: `${segment.color}55`, color: selectedSegmentId === segment.id ? "var(--bg)" : segment.color }}
            >
              {segment.name}
            </button>
          ))}
        </div>

        <div className="segment-meta-row">
          <span className="pill">{latestStatement?.filing_type ?? "Filing"}</span>
          <span className="pill">{latestStatement?.period_end ? formatDate(latestStatement.period_end) : "-"}</span>
          <span className="pill">Axis: {activeLens?.axis_label ?? segmentPoints[0]?.axisLabel ?? "Reported segments"}</span>
          <span className="pill">Focus: {selectedSegment?.name ?? "All segments"}</span>
        </div>
      </div>

      {activeLens ? <LensSummary lens={activeLens} /> : null}

      <div className="segment-breakdown-top-grid">
        <div className="segment-chart-card">
          <div className="segment-section-title">Revenue Treemap</div>
          <div className="segment-section-subtitle">Click a tile to focus the share and growth views.</div>
          <div className="segment-chart-shell segment-chart-shell-treemap">
            <ResponsiveContainer>
              <Treemap
                data={segmentPoints}
                dataKey="revenue"
                stroke="var(--panel-border)"
                isAnimationActive
                content={<SegmentTreemapNode selectedSegmentId={selectedSegmentId} onSelect={toggleSegment} />}
              >
                <Tooltip content={<SegmentTooltip />} />
              </Treemap>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="segment-chart-card">
          <div className="segment-section-title">Revenue Share</div>
          <div className="segment-section-subtitle">Hover for share, revenue, and the most recent year-over-year change.</div>
          <div className="segment-chart-shell segment-chart-shell-pie">
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={pieChartData}
                  dataKey="revenue"
                  nameKey="name"
                  innerRadius="48%"
                  outerRadius="82%"
                  paddingAngle={2}
                  stroke="var(--panel)"
                  strokeWidth={2}
                  onClick={(entry) => {
                    if (entry && typeof entry === "object" && "id" in entry && typeof entry.id === "string" && entry.id !== "other") {
                      toggleSegment(entry.id);
                    }
                  }}
                >
                  {pieChartData.map((segment) => (
                    <Cell key={segment.id} fill={segment.color} opacity={selectedSegmentId && selectedSegmentId !== segment.id ? 0.55 : 1} />
                  ))}
                </Pie>
                <Tooltip content={<SegmentTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="segment-chart-card">
        <div className="segment-section-title">{titleCase(activeKind)} Growth</div>
        <div className="segment-section-subtitle">
          Latest reported {activeKind} revenue growth versus {previousStatement ? `${previousStatement.filing_type} ${formatDate(previousStatement.period_end)}` : "the previous period"}.
        </div>
        <div className="segment-chart-shell segment-chart-shell-bar">
          <ResponsiveContainer>
            <BarChart data={growthChartData} margin={{ top: 12, right: 18, left: 6, bottom: 4 }}>
              <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
              <XAxis
                dataKey="name"
                stroke={CHART_AXIS_COLOR}
                tick={chartTick()}
                interval={0}
                angle={growthChartData.length > 3 ? -12 : 0}
                textAnchor={growthChartData.length > 3 ? "end" : "middle"}
                height={growthChartData.length > 3 ? 56 : 32}
              />
              <YAxis
                stroke={CHART_AXIS_COLOR}
                tick={chartTick()}
                tickFormatter={(value) => formatPercent(Number(value))}
              />
              <Tooltip content={<SegmentTooltip />} />
              <Bar dataKey="growth" radius={[2, 2, 0, 0]} onClick={(entry) => entry?.id && toggleSegment(String(entry.id))}>
                {growthChartData.map((segment) => (
                  <Cell key={segment.id} fill={segment.growth != null && segment.growth < 0 ? "var(--negative)" : segment.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {hasMarginData ? (
        <div className="segment-chart-card">
          <div className="segment-section-title">{titleCase(activeKind)} Operating Margin</div>
          <div className="segment-section-subtitle">
            Operating income as a percentage of reported segment revenue.
          </div>
          <div className="segment-chart-shell segment-chart-shell-bar">
            <ResponsiveContainer>
              <BarChart data={marginChartData} margin={{ top: 12, right: 18, left: 6, bottom: 4 }}>
                <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
                <XAxis
                  dataKey="name"
                  stroke={CHART_AXIS_COLOR}
                  tick={chartTick()}
                  interval={0}
                  angle={marginChartData.length > 3 ? -12 : 0}
                  textAnchor={marginChartData.length > 3 ? "end" : "middle"}
                  height={marginChartData.length > 3 ? 56 : 32}
                />
                <YAxis
                  stroke={CHART_AXIS_COLOR}
                  tick={chartTick()}
                  tickFormatter={(value) => formatPercent(Number(value))}
                />
                <Tooltip content={<SegmentTooltip />} />
                <Bar dataKey="operatingMargin" name="Op. Margin" radius={[2, 2, 0, 0]}
                  onClick={(entry) => entry?.id && toggleSegment(String(entry.id))}>
                  {marginChartData.map((segment) => (
                    <Cell
                      key={segment.id}
                      fill={segment.operatingMargin != null && segment.operatingMargin < 0 ? "var(--negative)" : segment.color}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function LensSummary({ lens }: { lens: SegmentLensPayload }) {
  return (
    <div style={{ display: "grid", gap: 12, marginBottom: 12 }}>
      <div className="segment-chart-card" style={{ display: "grid", gap: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ display: "grid", gap: 4 }}>
            <div className="segment-section-title">What Moved The {titleCase(lens.kind)} Mix</div>
            <div className="segment-section-subtitle">{lens.summary ?? "Recent disclosures are available, but there is not enough comparable history to explain the mix shift yet."}</div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <span className="pill">As of {formatDate(lens.as_of)}</span>
            <span className="pill">Refreshed {formatDate(lens.last_refreshed_at)}</span>
            <span className="pill">Confidence {formatPercent(lens.confidence_score)}</span>
          </div>
        </div>

        <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
          <MetricCard
            label="Top Line"
            value={lens.concentration.top_segment_name ? `${lens.concentration.top_segment_name} (${formatPercent(lens.concentration.top_segment_share)})` : "-"}
          />
          <MetricCard label="Top Two Share" value={formatPercent(lens.concentration.top_two_share)} />
          <MetricCard label="HHI" value={formatHhi(lens.concentration.hhi)} />
          <MetricCard label="Sources" value={lens.provenance_sources.join(", ") || "-"} />
        </div>

        {lens.top_mix_movers.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="segment-section-title" style={{ fontSize: 15 }}>Top Mix Movers</div>
            <div style={{ overflowX: "auto" }}>
              <table className="company-data-table" style={{ minWidth: 620 }}>
                <thead>
                  <tr>
                    <th align="left">Segment</th>
                    <th align="right">Share Delta</th>
                    <th align="right">Revenue Delta</th>
                    <th align="right">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lens.top_mix_movers.map((row) => (
                    <tr key={`${row.segment_id}:${row.status}`}>
                      <td>{row.segment_name}</td>
                      <td style={{ textAlign: "right", color: (row.share_delta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedPoints(row.share_delta)}
                      </td>
                      <td style={{ textAlign: "right", color: (row.revenue_delta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedCompactNumber(row.revenue_delta)}
                      </td>
                      <td style={{ textAlign: "right" }}>{titleCase(row.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {lens.top_margin_contributors.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="segment-section-title" style={{ fontSize: 15 }}>Margin Contribution</div>
            <div style={{ overflowX: "auto" }}>
              <table className="company-data-table" style={{ minWidth: 620 }}>
                <thead>
                  <tr>
                    <th align="left">Segment</th>
                    <th align="right">Op. Income Share</th>
                    <th align="right">Op. Margin</th>
                    <th align="right">Margin Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {lens.top_margin_contributors.map((row) => (
                    <tr key={`${row.segment_id}:margin`}>
                      <td>{row.segment_name}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.share_of_operating_income)}</td>
                      <td style={{ textAlign: "right" }}>{formatPercent(row.operating_margin)}</td>
                      <td style={{ textAlign: "right", color: (row.operating_margin_delta ?? 0) >= 0 ? "var(--positive)" : "var(--negative)" }}>
                        {formatSignedPoints(row.operating_margin_delta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {lens.unusual_disclosures.length ? (
          <div style={{ display: "grid", gap: 8 }}>
            <div className="segment-section-title" style={{ fontSize: 15 }}>Unusual Disclosures</div>
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
              {lens.unusual_disclosures.map((disclosure) => (
                <DisclosureCard key={disclosure.code} disclosure={disclosure} />
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ border: "1px solid var(--panel-border)", borderRadius: 6, padding: 12, background: "var(--panel)", display: "grid", gap: 4 }}>
      <div className="text-muted" style={{ fontSize: 12 }}>{label}</div>
      <div style={{ fontWeight: 700, wordBreak: "break-word", color: "var(--surface-strong-text)" }}>{value}</div>
    </div>
  );
}

function DisclosureCard({ disclosure }: { disclosure: SegmentDisclosurePayload }) {
  const palette = disclosure.severity === "high"
    ? { border: "color-mix(in srgb, var(--negative) 40%, var(--panel-border))", background: "color-mix(in srgb, var(--negative) 10%, var(--panel))", text: "var(--negative)" }
    : disclosure.severity === "medium"
      ? { border: "color-mix(in srgb, var(--warning) 40%, var(--panel-border))", background: "color-mix(in srgb, var(--warning) 10%, var(--panel))", text: "var(--warning)" }
      : { border: "var(--panel-border)", background: "var(--panel)", text: "var(--text-muted)" };

  return (
    <div style={{ border: `1px solid ${palette.border}`, background: palette.background, borderRadius: 6, padding: 12, display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <div style={{ fontWeight: 700 }}>{disclosure.label}</div>
        <span style={{ color: palette.text, fontSize: 12, fontWeight: 700 }}>{titleCase(disclosure.severity)}</span>
      </div>
      <div className="text-muted" style={{ fontSize: 13 }}>{disclosure.detail}</div>
    </div>
  );
}

function SegmentTreemapNode(
  props: {
    selectedSegmentId: string | null;
    onSelect: (segmentId: string) => void;
  } & Record<string, unknown>
) {
  const { selectedSegmentId, onSelect, depth, x, y, width, height } = props;
  const payloadCandidate =
    props.payload && typeof props.payload === "object"
      ? (((props.payload as { payload?: Partial<SegmentPoint> }).payload ?? props.payload) as Partial<SegmentPoint>)
      : null;
  const point = (payloadCandidate ?? (props as Partial<SegmentPoint>)) as Partial<SegmentPoint>;

  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    typeof height !== "number" ||
    typeof point.id !== "string" ||
    typeof point.name !== "string" ||
    typeof point.color !== "string" ||
    typeof point.revenue !== "number"
  ) {
    return null;
  }

  if ((typeof depth === "number" && depth !== 1) || width < 32 || height < 24) {
    return null;
  }

  const segmentPoint = point as SegmentPoint;
  const active = selectedSegmentId === null || selectedSegmentId === point.id;
  const focused = selectedSegmentId === point.id;

  return (
    <g onClick={() => onSelect(segmentPoint.id)} style={{ cursor: "pointer" }}>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        rx={12}
        ry={12}
        fill={segmentPoint.color}
        opacity={active ? 0.96 : 0.38}
        stroke={focused ? "var(--warning)" : "var(--panel-border)"}
        strokeWidth={focused ? 2.2 : 1}
      />
      {width > 88 && height > 56 ? (
        <>
          <text x={x + 10} y={y + 20} fill="var(--bg)" fontSize={12} fontWeight={700}>
            {trimLabel(segmentPoint.name, width > 120 ? 18 : 12)}
          </text>
          <text x={x + 10} y={y + 38} fill="var(--bg)" fontSize={11} opacity={0.78}>
            {formatCompactNumber(segmentPoint.revenue)}
          </text>
        </>
      ) : null}
    </g>
  );
}

function SegmentTooltip({ active, payload }: { active?: boolean; payload?: TooltipEntry[] }) {
  const point = payload?.find((entry) => entry?.payload)?.payload;
  if (!active || !point) {
    return null;
  }

  const operatingMargin =
    point.operatingIncome !== null && typeof point.operatingIncome === "number" && point.revenue !== 0
      ? point.operatingIncome / point.revenue
      : null;

  return (
    <div className="segment-tooltip-card">
      <div className="segment-tooltip-title">{point.name}</div>
      <div className="segment-tooltip-row">
        <span>Revenue</span>
        <strong>{formatCompactNumber(point.revenue)}</strong>
      </div>
      <div className="segment-tooltip-row">
        <span>Share</span>
        <strong>{formatPercent(point.share)}</strong>
      </div>
      {point.operatingIncome !== null ? (
        <div className="segment-tooltip-row">
          <span>Op. Income</span>
          <strong>{formatCompactNumber(point.operatingIncome)}</strong>
        </div>
      ) : null}
      {operatingMargin !== null ? (
        <div className="segment-tooltip-row">
          <span>Op. Margin</span>
          <strong>{formatPercent(operatingMargin)}</strong>
        </div>
      ) : null}
      {point.assets !== null ? (
        <div className="segment-tooltip-row">
          <span>Assets</span>
          <strong>{formatCompactNumber(point.assets)}</strong>
        </div>
      ) : null}
      <div className="segment-tooltip-row">
        <span>Growth</span>
        <strong>{formatPercent(point.growth)}</strong>
      </div>
      <div className="segment-tooltip-footnote">{point.axisLabel ?? "Reported segments"}</div>
    </div>
  );
}

function hasKindSegments(statement: FinancialPayload, kind: SegmentKind): boolean {
  return statement.segment_breakdown.some(
    (segment) => segment.kind === kind && typeof segment.revenue === "number" && segment.revenue > 0
  );
}

function formatSignedPoints(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)} pts`;
}

function formatSignedCompactNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatCompactNumber(value)}`;
}

function formatHhi(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(2);
}

function trimLabel(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 3))}...`;
}

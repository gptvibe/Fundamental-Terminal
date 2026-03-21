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
import { formatCompactNumber, formatDate, formatPercent } from "@/lib/format";
import type { FinancialPayload, FinancialSegmentPayload } from "@/lib/types";

const ANNUAL_FORMS = new Set(["10-K", "20-F", "40-F"]);
const SEGMENT_COLORS = ["#00FF41", "#00E5FF", "#FFD700", "#FF6B6B", "#A855F7", "#7CFFCB", "#64D2FF"];

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
}

export function BusinessSegmentBreakdown({ financials }: BusinessSegmentBreakdownProps) {
  const noFinancials = financials.length === 0;
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  const segmentStatements = useMemo(() => {
    const annual = financials.filter(
      (statement) => ANNUAL_FORMS.has(statement.filing_type) && statement.segment_breakdown.length > 0
    );
    if (annual.length > 0) {
      return annual;
    }
    return financials.filter((statement) => statement.segment_breakdown.length > 0);
  }, [financials]);

  const latestStatement = segmentStatements[0] ?? null;
  const previousStatement = segmentStatements[1] ?? null;

  const segmentPoints = useMemo(() => {
    if (!latestStatement) {
      return [] as SegmentPoint[];
    }

    const previousMap = new Map<string, FinancialSegmentPayload>(
      (previousStatement?.segment_breakdown ?? []).map((segment) => [segment.segment_id, segment])
    );

    const latestSegments = latestStatement.segment_breakdown
      .filter((segment) => typeof segment.revenue === "number" && segment.revenue > 0)
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
  }, [latestStatement, previousStatement]);

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
      (selectedSegment ? [selectedSegment] : segmentPoints).filter(
        (segment) => segment.operatingIncome !== null
      ).map((segment) => ({
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
              color: "rgba(255,255,255,0.18)"
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
      <div className="segment-breakdown-toolbar">
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
              style={{ borderColor: `${segment.color}55`, color: selectedSegmentId === segment.id ? "#0c0c0c" : segment.color }}
            >
              {segment.name}
            </button>
          ))}
        </div>

        <div className="segment-meta-row">
          <span className="pill">{latestStatement?.filing_type ?? "Filing"}</span>
          <span className="pill">{latestStatement?.period_end ? formatDate(latestStatement.period_end) : "—"}</span>
          <span className="pill">Axis: {segmentPoints[0]?.axisLabel ?? "Reported segments"}</span>
          <span className="pill">Focus: {selectedSegment?.name ?? "All segments"}</span>
        </div>
      </div>

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
        <div className="segment-section-title">Segment Growth</div>
        <div className="segment-section-subtitle">
          Latest reported segment revenue growth versus {previousStatement ? `${previousStatement.filing_type} ${formatDate(previousStatement.period_end)}` : "the previous period"}.
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
              <Bar dataKey="growth" radius={[8, 8, 0, 0]} onClick={(entry) => entry?.id && toggleSegment(String(entry.id))}>
                {growthChartData.map((segment) => (
                  <Cell key={segment.id} fill={segment.growth != null && segment.growth < 0 ? "#FF6B6B" : segment.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {hasMarginData ? (
        <div className="segment-chart-card">
          <div className="segment-section-title">Segment Operating Margin</div>
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
                <Bar dataKey="operatingMargin" name="Op. Margin" radius={[8, 8, 0, 0]}
                  onClick={(entry) => entry?.id && toggleSegment(String(entry.id))}>
                  {marginChartData.map((segment) => (
                    <Cell
                      key={segment.id}
                      fill={segment.operatingMargin != null && segment.operatingMargin < 0 ? "#FF6B6B" : segment.color}
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
        stroke={focused ? "#FFD700" : "var(--panel-border)"}
        strokeWidth={focused ? 2.2 : 1}
      />
      {width > 88 && height > 56 ? (
        <>
          <text x={x + 10} y={y + 20} fill="#0c0c0c" fontSize={12} fontWeight={700}>
            {trimLabel(segmentPoint.name, width > 120 ? 18 : 12)}
          </text>
          <text x={x + 10} y={y + 38} fill="rgba(12,12,12,0.78)" fontSize={11}>
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

function trimLabel(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(0, maxLength - 1))}…`;
}

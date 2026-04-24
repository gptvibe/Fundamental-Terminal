import * as React from "react";

import { CHART_SHARE_LAYOUTS, type ChartShareLayout, formatShareMetricValue } from "@/lib/chart-share";
import type {
  CompanyChartsProjectedRowPayload,
  CompanyChartsShareSnapshotChartPayload,
  CompanyChartsShareSnapshotPayload,
} from "@/lib/types";

type ChartShareCardProps = {
  snapshot: CompanyChartsShareSnapshotPayload;
  layout: ChartShareLayout;
};

export function ChartShareCard({ snapshot, layout }: ChartShareCardProps) {
  const frame = CHART_SHARE_LAYOUTS[layout];
  const isLandscape = layout === "landscape";
  const contentPadding = layout === "portrait" ? 56 : 48;
  const studioChart = snapshot.mode === "studio" ? buildStudioRevenueChart(snapshot) : null;
  const primaryChart = snapshot.mode === "outlook" ? snapshot.outlook?.primary_chart ?? null : studioChart;

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "linear-gradient(160deg, #0b1220 0%, #12263a 38%, #19324c 100%)",
        color: "#f7f4ed",
        padding: contentPadding,
        boxSizing: "border-box",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: isLandscape ? "62%" : "100%" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            <Badge>{snapshot.mode === "studio" ? "Projection Studio" : "Growth Outlook"}</Badge>
            <Badge subtle>{snapshot.source_badge}</Badge>
            <Badge subtle>{snapshot.provenance_badge}</Badge>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", fontSize: layout === "portrait" ? 60 : 52, fontWeight: 800, lineHeight: 1.02 }}>
              {snapshot.company_name ?? snapshot.ticker}
            </div>
            <div style={{ display: "flex", fontSize: layout === "portrait" ? 30 : 26, fontWeight: 600, color: "#cbd7e6" }}>{snapshot.title}</div>
            <div style={{ display: "flex", fontSize: 20, lineHeight: 1.45, color: "#dbe6f2" }}>
              {snapshot.mode === "studio"
                ? snapshot.studio?.summary ?? "Projection Studio snapshot"
                : snapshot.outlook?.thesis ?? "Growth outlook snapshot"}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: isLandscape ? "flex-end" : "flex-start", gap: 10 }}>
          <MetaLine label="Ticker" value={snapshot.ticker} />
          <MetaLine label="As Of" value={snapshot.as_of ?? "Pending"} />
          <MetaLine label="Trust" value={snapshot.trust_label ?? "Forecast trust pending"} />
          <MetaLine label="Labels" value={`${snapshot.actual_label} / ${snapshot.forecast_label}`} />
        </div>
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: isLandscape ? "row" : "column",
          gap: 24,
          marginTop: 28,
          flex: 1,
        }}
      >
        <div
          style={{
            flex: isLandscape ? "0 0 44%" : "0 0 auto",
            display: "flex",
            flexDirection: "column",
            gap: 18,
            padding: 26,
            borderRadius: 28,
            background: "rgba(10, 19, 31, 0.52)",
            border: "1px solid rgba(255,255,255,0.12)",
          }}
        >
          {snapshot.mode === "outlook" ? (
            <>
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ display: "flex", fontSize: 16, textTransform: "uppercase", letterSpacing: 1.2, color: "#97adbf" }}>
                    {snapshot.outlook?.headline ?? "Growth Outlook"}
                  </div>
                  <div style={{ display: "flex", fontSize: 18, color: "#d7e1ec" }}>Actual and projected states remain visually distinct.</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                  <div style={{ display: "flex", fontSize: 14, color: "#97adbf" }}>{snapshot.outlook?.primary_score.label ?? "Growth"}</div>
                  <div style={{ display: "flex", fontSize: 42, fontWeight: 800 }}>{Math.round(snapshot.outlook?.primary_score.score ?? 0)}</div>
                </div>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                {(snapshot.outlook?.secondary_scores ?? []).map((score) => (
                  <Pill key={score.key} label={score.label} value={score.score == null ? "—" : String(Math.round(score.score))} />
                ))}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {(snapshot.outlook?.summary_metrics ?? []).map((metric) => (
                  <MetricLine key={metric.key} label={metric.label} value={metric.value} />
                ))}
              </div>
            </>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div style={{ display: "flex", fontSize: 16, textTransform: "uppercase", letterSpacing: 1.2, color: "#97adbf" }}>
                    {snapshot.studio?.headline ?? "Projection Studio"}
                  </div>
                  <div style={{ display: "flex", fontSize: 30, fontWeight: 700 }}>
                    {snapshot.studio?.scenario_name ?? "Current Scenario"}
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>
                  <div style={{ display: "flex", fontSize: 14, color: "#97adbf" }}>Overrides</div>
                  <div style={{ display: "flex", fontSize: 40, fontWeight: 800 }}>{snapshot.studio?.override_count ?? 0}</div>
                </div>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                {(snapshot.studio?.metrics ?? []).map((metric) => (
                  <Pill key={metric.key} label={metric.label} value={metric.value} />
                ))}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
                {(snapshot.studio?.scenario_rows ?? []).map((row) => (
                  <div
                    key={row.key}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                      padding: "10px 0",
                      borderTop: "1px solid rgba(255,255,255,0.08)",
                      fontSize: 15,
                    }}
                  >
                    <span style={{ color: "#dce6f2" }}>{row.label}</span>
                    <span style={{ color: "#f8f6ef" }}>
                      B {formatShareMetricValue(row.base_value, row.unit)} | U {formatShareMetricValue(row.bull_value, row.unit)} | D {formatShareMetricValue(row.bear_value, row.unit)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 18,
            padding: 26,
            borderRadius: 28,
            background: "rgba(248, 244, 237, 0.08)",
            border: "1px solid rgba(255,255,255,0.1)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div style={{ display: "flex", fontSize: 18, fontWeight: 700 }}>{primaryChart?.title ?? "Forecast path"}</div>
              <div style={{ display: "flex", fontSize: 15, color: "#b9c7d6" }}>{`${snapshot.actual_label} stays solid. ${snapshot.forecast_label} stays dashed and labeled.`}</div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              <LegendDot color="#f4efe4" label={snapshot.actual_label} dashed={false} />
              <LegendDot color="#76e0a7" label={snapshot.forecast_label} dashed />
            </div>
          </div>

          <div
            style={{
              display: "flex",
              flex: 1,
              minHeight: layout === "portrait" ? 320 : 240,
              padding: 18,
              borderRadius: 20,
              background: "rgba(3, 10, 18, 0.42)",
              border: "1px solid rgba(255,255,255,0.06)",
            }}
          >
            <TrendChart chart={primaryChart} />
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-end" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
              <Badge subtle>{snapshot.source_badge}</Badge>
              <Badge subtle>{snapshot.provenance_badge}</Badge>
              {snapshot.trust_label ? <Badge subtle>{snapshot.trust_label}</Badge> : null}
            </div>
            <div style={{ display: "flex", fontSize: 14, color: "#9db0c3" }}>{`${frame.label} share layout`}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function buildStudioRevenueChart(snapshot: CompanyChartsShareSnapshotPayload): CompanyChartsShareSnapshotChartPayload | null {
  const studio = snapshot.chart_spec.studio?.projection_studio;
  if (!studio) {
    return null;
  }

  const revenueRow = findProjectionRow(studio.schedule_sections, "revenue");
  if (!revenueRow) {
    return null;
  }

  return {
    title: "Revenue Schedule",
    unit: revenueRow.unit,
    actual_points: Object.entries(revenueRow.reported_values)
      .sort(([left], [right]) => Number(left) - Number(right))
      .map(([year, value]) => ({ label: `FY${year}`, value, kind: "actual" as const })),
    forecast_points: Object.entries(revenueRow.projected_values)
      .sort(([left], [right]) => Number(left) - Number(right))
      .map(([year, value]) => ({ label: `FY${year}E`, value, kind: "forecast" as const })),
  };
}

function findProjectionRow(
  sections: Array<{ rows: CompanyChartsProjectedRowPayload[] }>,
  rowKey: string
): CompanyChartsProjectedRowPayload | null {
  for (const section of sections) {
    const row = section.rows.find((candidate) => candidate.key === rowKey);
    if (row) {
      return row;
    }
  }
  return null;
}

function TrendChart({ chart }: { chart: CompanyChartsShareSnapshotChartPayload | null }) {
  if (!chart) {
    return (
      <div style={{ display: "flex", flex: 1, alignItems: "center", justifyContent: "center", color: "#a8b9c7", fontSize: 16 }}>
        Snapshot data is still warming up.
      </div>
    );
  }

  const actualValues = chart.actual_points.map((point) => point.value ?? 0);
  const forecastValues = chart.forecast_points.map((point) => point.value ?? 0);
  const points = [...chart.actual_points, ...chart.forecast_points];
  const width = 620;
  const height = 260;
  const padding = 18;
  const allValues = [...actualValues, ...forecastValues].filter((value) => Number.isFinite(value));
  const minValue = allValues.length ? Math.min(...allValues) : 0;
  const maxValue = allValues.length ? Math.max(...allValues) : 1;
  const normalizedMax = maxValue === minValue ? maxValue + 1 : maxValue;
  const plotWidth = width - padding * 2;
  const plotHeight = height - padding * 2;

  const buildPath = (values: Array<number | null | undefined>, offset = 0) =>
    values
      .map((value, index) => {
        const x = padding + ((index + offset) / Math.max(points.length - 1, 1)) * plotWidth;
        const numeric = value ?? minValue;
        const y = padding + plotHeight - ((numeric - minValue) / (normalizedMax - minValue)) * plotHeight;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");

  return (
    <div style={{ display: "flex", flexDirection: "column", width: "100%", height: "100%", justifyContent: "space-between", gap: 12 }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: "100%", flex: 1 }}>
        <rect x="0" y="0" width={width} height={height} fill="none" />
        {[0, 0.5, 1].map((fraction) => (
          <line
            key={fraction}
            x1={padding}
            y1={padding + plotHeight * fraction}
            x2={width - padding}
            y2={padding + plotHeight * fraction}
            stroke="rgba(255,255,255,0.12)"
            strokeWidth="1"
          />
        ))}
        <path d={buildPath(chart.actual_points.map((point) => point.value))} fill="none" stroke="#f4efe4" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <path
          d={buildPath(chart.forecast_points.map((point) => point.value), Math.max(chart.actual_points.length - 1, 0))}
          fill="none"
          stroke="#76e0a7"
          strokeWidth="5"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray="14 10"
        />
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        {points.map((point, index) => (
          <span key={`${point.label}-${index}`} style={{ flex: 1, fontSize: 14, color: "#9fb2c3", textAlign: "center" }}>
            {point.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Badge({ children, subtle = false }: { children: React.ReactNode; subtle?: boolean }) {
  return (
    <span
      style={{
        display: "flex",
        alignItems: "center",
        padding: "8px 14px",
        borderRadius: 999,
        background: subtle ? "rgba(255,255,255,0.08)" : "rgba(118,224,167,0.16)",
        border: "1px solid rgba(255,255,255,0.12)",
        fontSize: 14,
        color: subtle ? "#d7e2ee" : "#86efb5",
      }}
    >
      {children}
    </span>
  );
}

function MetaLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2, alignItems: "flex-end" }}>
      <span style={{ fontSize: 13, textTransform: "uppercase", letterSpacing: 1.1, color: "#97adbf" }}>{label}</span>
      <span style={{ fontSize: 18, color: "#f8f5ee" }}>{value}</span>
    </div>
  );
}

function Pill({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 4,
        padding: "12px 14px",
        borderRadius: 18,
        background: "rgba(255,255,255,0.06)",
        minWidth: 112,
      }}
    >
      <span style={{ fontSize: 13, color: "#97adbf" }}>{label}</span>
      <span style={{ fontSize: 20, fontWeight: 700 }}>{value}</span>
    </div>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 14, paddingBottom: 10, borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
      <span style={{ color: "#9fb2c3", fontSize: 15 }}>{label}</span>
      <span style={{ color: "#f8f6ef", fontSize: 16, fontWeight: 600 }}>{value}</span>
    </div>
  );
}

function LegendDot({ color, label, dashed }: { color: string; label: string; dashed: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <svg width="22" height="10" viewBox="0 0 22 10">
        <line x1="1" y1="5" x2="21" y2="5" stroke={color} strokeWidth="2.5" strokeDasharray={dashed ? "5 4" : undefined} strokeLinecap="round" />
      </svg>
      <span style={{ fontSize: 14, color: "#d5e0eb" }}>{label}</span>
    </div>
  );
}

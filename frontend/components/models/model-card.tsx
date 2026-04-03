import { MetricLabel } from "@/components/ui/metric-label";
import { ModelPayload } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/format";

export function ModelCard({ model }: { model: ModelPayload }) {
  const rows = flattenModelResult(model.result).slice(0, 12);

  return (
    <div
      style={{
        display: "grid",
        gap: 14,
        padding: 16,
        borderRadius: 14,
        border: "1px solid var(--panel-border)",
        background: "var(--panel-alt)"
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
        <div>
          <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--accent)" }}>
            {titleCase(model.model_name)}
          </div>
          <div style={{ marginTop: 6, fontSize: 13, color: "var(--text-muted)" }}>
            v{model.model_version} · computed {formatDate(model.created_at)}
          </div>
        </div>
        <span className="pill">{String(model.result.status ?? "ready")}</span>
      </div>

      <div className="metric-grid">
        {rows.length ? (
          rows.map(([key, value]) => (
            <div key={key} className="metric-card">
              <div className="metric-label">
                <MetricLabel label={titleCase(key)} />
              </div>
              <div className="metric-value">{value}</div>
            </div>
          ))
        ) : (
          <div className="text-muted">No scalar outputs available.</div>
        )}
      </div>

      <pre
        style={{
          margin: 0,
          whiteSpace: "pre-wrap",
          fontSize: 12,
          lineHeight: 1.5,
          fontFamily: '"SFMono-Regular", Consolas, monospace',
          color: "var(--text-soft)",
          background: "var(--panel)",
          borderRadius: 12,
          padding: 12,
          border: "1px solid var(--panel-border)"
        }}
      >
        {JSON.stringify(model.result, null, 2)}
      </pre>
    </div>
  );
}

function flattenModelResult(
  value: Record<string, unknown>,
  prefix = ""
): Array<[string, string]> {
  const rows: Array<[string, string]> = [];

  for (const [key, entry] of Object.entries(value)) {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (typeof entry === "number") {
      rows.push([nextKey, formatScalar(entry)]);
    } else if (typeof entry === "string" || typeof entry === "boolean") {
      rows.push([nextKey, String(entry)]);
    } else if (entry && typeof entry === "object" && !Array.isArray(entry)) {
      rows.push(...flattenModelResult(entry as Record<string, unknown>, nextKey));
    }
  }

  return rows;
}

function formatScalar(value: number): string {
  if (Math.abs(value) >= 1000) {
    return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 2 }).format(value);
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

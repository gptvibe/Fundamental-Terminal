"use client";

import { SourceFreshnessSummary } from "@/components/ui/source-freshness-summary";
import { formatCompactNumber, formatDate, formatPercent, titleCase } from "@/lib/format";
import type { ModelEvaluationResponse } from "@/lib/types";

export function ModelEvaluationPanel({ evaluation }: { evaluation: ModelEvaluationResponse | null }) {
  if (!evaluation?.run) {
    return <div className="text-muted">No stored evaluation run is available yet. Run the evaluation CLI to persist the latest backtest summary.</div>;
  }

  const run = evaluation.run;
  const latestAsOf = typeof run.summary.latest_as_of === "string" ? run.summary.latest_as_of : evaluation.as_of;
  const provenanceMode = typeof run.summary.provenance_mode === "string" ? run.summary.provenance_mode : "historical_cache";

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span className="pill">Suite {run.suite_key}</span>
        <span className="pill">Candidate {run.candidate_label}</span>
        {run.baseline_label ? <span className="pill">Baseline {run.baseline_label}</span> : null}
        <span className="pill">Mode {provenanceMode.replaceAll("_", " ")}</span>
        {latestAsOf ? <span className="pill">Latest snapshot {formatDate(latestAsOf)}</span> : null}
        {run.completed_at ? <span className="pill">Completed {formatDate(run.completed_at)}</span> : null}
      </div>

      <div className="company-data-table-shell">
        <table className="company-data-table company-data-table-wide">
          <thead>
            <tr>
              <th>Model</th>
              <th className="is-numeric">Samples</th>
              <th className="is-numeric">Calibration</th>
              <th className="is-numeric">Stability</th>
              <th className="is-numeric">MAE</th>
              <th className="is-numeric">RMSE</th>
              <th className="is-numeric">Signed Error</th>
            </tr>
          </thead>
          <tbody>
            {run.models.map((model) => (
              <tr key={model.model_name}>
                <td>
                  <div style={{ display: "grid", gap: 4 }}>
                    <strong>{titleCase(model.model_name)}</strong>
                    <div className="text-muted" style={{ fontSize: 12 }}>
                      {model.status.replaceAll("_", " ")}
                      {run.deltas_present ? ` · ${formatDelta(model.delta.mean_absolute_error, true)} MAE delta` : ""}
                    </div>
                  </div>
                </td>
                <td className="is-numeric">{model.sample_count.toLocaleString()}</td>
                <td className="is-numeric">{formatPercent(model.calibration)}</td>
                <td className="is-numeric">{formatCompactNumber(model.stability)}</td>
                <td className="is-numeric">{formatCompactNumber(model.mean_absolute_error)}</td>
                <td className="is-numeric">{formatCompactNumber(model.root_mean_square_error)}</td>
                <td className="is-numeric">{formatDelta(model.mean_signed_error)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <SourceFreshnessSummary
        provenance={evaluation.provenance}
        asOf={evaluation.as_of}
        lastRefreshedAt={evaluation.last_refreshed_at}
        sourceMix={evaluation.source_mix}
        confidenceFlags={evaluation.confidence_flags}
      />
    </div>
  );
}

function formatDelta(value: number | null | undefined, alwaysShowSign = false): string {
  if (value == null) {
    return "—";
  }
  const formatted = formatCompactNumber(Math.abs(value));
  if (value > 0) {
    return `+${formatted}`;
  }
  if (value < 0) {
    return `-${formatted}`;
  }
  return alwaysShowSign ? `+${formatted}` : formatted;
}

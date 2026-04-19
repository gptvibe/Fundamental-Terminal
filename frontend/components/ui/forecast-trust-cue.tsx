import { SourceStateBadge } from "@/components/ui/source-state-badge";
import type { ForecastSourceState } from "@/lib/forecast-source-state";
import { formatPercent } from "@/lib/format";
import type { CompanyChartsForecastAccuracyResponse } from "@/lib/types";

interface ForecastTrustCueProps {
  sourceState: ForecastSourceState;
  accuracy: CompanyChartsForecastAccuracyResponse | null;
  loading?: boolean;
  error?: string | null;
}

export function ForecastTrustCue({
  sourceState,
  accuracy,
  loading = false,
  error = null,
}: ForecastTrustCueProps) {
  const showAccuracy = accuracy?.status === "ok";

  return (
    <div className="workspace-pill-row forecast-trust-cue" data-testid="forecast-trust-cue">
      <SourceStateBadge state={sourceState} />
      {showAccuracy ? (
        <>
          <span className="pill">MAPE {formatPercent(accuracy.aggregate.mean_absolute_percentage_error)}</span>
          <span className="pill">Directional {formatPercent(accuracy.aggregate.directional_accuracy)}</span>
        </>
      ) : null}
      {!showAccuracy && accuracy?.status === "insufficient_history" ? (
        <span className="pill">Track Record Building</span>
      ) : null}
      {!accuracy && loading ? <span className="pill">Track Record Loading</span> : null}
      {!accuracy && error ? <span className="pill">Track Record Unavailable</span> : null}
    </div>
  );
}

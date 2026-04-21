const DEFAULT_PIOTROSKI_SCORE_MAX = 9;

export interface PiotroskiScoreState {
  score: number | null;
  rawScore: number | null;
  scoreMax: number;
  availableCriteria: number | null;
  isComplete: boolean;
  isPartial: boolean;
}

export function resolvePiotroskiScoreState(result: unknown): PiotroskiScoreState {
  const record = asRecord(result);
  const scoreMax = asNumber(record.score_max) ?? DEFAULT_PIOTROSKI_SCORE_MAX;
  const availableCriteria = asNumber(record.available_criteria);
  const normalizedScoreOnNinePointScale =
    asNumber(record.score_on_9_point_scale) ??
    asNumber(record.normalized_score_9);
  const normalizedScoreRatio = asNumber(record.normalized_score_ratio);
  const rawScore = asNumber(record.score);
  const isComplete =
    normalizedScoreOnNinePointScale !== null || (availableCriteria === scoreMax && rawScore !== null);
  const isPartial = !isComplete && rawScore !== null && availableCriteria !== null && availableCriteria > 0 && availableCriteria < scoreMax;
  const comparisonScore =
    normalizedScoreOnNinePointScale ??
    (normalizedScoreRatio !== null ? normalizedScoreRatio * scoreMax : null) ??
    (isPartial && rawScore !== null && availableCriteria !== null && availableCriteria > 0
      ? (rawScore / availableCriteria) * scoreMax
      : rawScore);

  return {
    score: comparisonScore,
    rawScore,
    scoreMax,
    availableCriteria,
    isComplete,
    isPartial
  };
}

export function formatPiotroskiDisplay(state: PiotroskiScoreState): string {
  if (state.rawScore === null) {
    return "—";
  }

  if (state.isPartial && state.availableCriteria !== null) {
    return `${state.rawScore.toFixed(1)}/${state.availableCriteria} available`;
  }

  return `${state.rawScore.toFixed(1)}/${state.scoreMax}`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

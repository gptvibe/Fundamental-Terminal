import { describe, expect, it } from "vitest";

import { formatPiotroskiDisplay, resolvePiotroskiScoreState } from "@/lib/piotroski";

describe("resolvePiotroskiScoreState", () => {
  it("prefers the explicit comparable 9-point scale when present", () => {
    const state = resolvePiotroskiScoreState({
      score: 8,
      score_max: 9,
      available_criteria: 8,
      score_on_9_point_scale: 9,
      normalized_score_9: 9,
      normalized_score_ratio: 1,
    });

    expect(state.score).toBe(9);
    expect(state.rawScore).toBe(8);
    expect(state.availableCriteria).toBe(8);
    expect(state.isComplete).toBe(true);
    expect(state.isPartial).toBe(false);
    expect(formatPiotroskiDisplay(state)).toBe("8.0/9");
  });

  it("falls back to scaling the raw score when only partial criteria are available", () => {
    const state = resolvePiotroskiScoreState({
      score: 6,
      score_max: 9,
      available_criteria: 8,
    });

    expect(state.score).toBeCloseTo(6.75, 9);
    expect(state.rawScore).toBe(6);
    expect(state.isComplete).toBe(false);
    expect(state.isPartial).toBe(true);
    expect(formatPiotroskiDisplay(state)).toBe("6.0/8 available");
  });
});

import { afterEach, describe, expect, it } from "vitest";

import { getDemoFixtureResponse, isDemoModeEnabled } from "@/lib/api/demo-fixtures";

describe("demo fixtures", () => {
  const previousPublicDemoMode = process.env.NEXT_PUBLIC_DEMO_MODE;
  const previousDemoMode = process.env.DEMO_MODE;

  afterEach(() => {
    process.env.NEXT_PUBLIC_DEMO_MODE = previousPublicDemoMode;
    process.env.DEMO_MODE = previousDemoMode;
  });

  it("enables demo mode only when explicit env is true", () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = "false";
    process.env.DEMO_MODE = "false";
    expect(isDemoModeEnabled()).toBe(false);

    process.env.NEXT_PUBLIC_DEMO_MODE = "true";
    expect(isDemoModeEnabled()).toBe(true);

    process.env.NEXT_PUBLIC_DEMO_MODE = "false";
    process.env.DEMO_MODE = "true";
    expect(isDemoModeEnabled()).toBe(true);
  });

  it("labels workspace bootstrap payloads as demo fixtures", () => {
    const payload = getDemoFixtureResponse("/companies/AAPL/workspace-bootstrap") as Record<string, unknown>;
    expect(payload).toBeTruthy();

    const financials = payload.financials as Record<string, unknown>;
    expect(Array.isArray(financials.provenance)).toBe(true);

    const provenance = financials.provenance as Array<Record<string, unknown>>;
    expect(provenance[0]?.source_id).toBe("ft_demo_fixture_pack");
    expect(String(provenance[0]?.display_label ?? "")).toContain("Demo Fixture");

    const confidenceFlags = financials.confidence_flags as string[];
    expect(confidenceFlags).toContain("demo_fixture_data");
  });

  it("marks source registry with demo fixture source", () => {
    const payload = getDemoFixtureResponse("/source-registry") as Record<string, unknown>;
    const sources = payload.sources as Array<Record<string, unknown>>;

    expect(sources.some((source) => source.source_id === "ft_demo_fixture_pack")).toBe(true);
  });
});

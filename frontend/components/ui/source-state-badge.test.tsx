// @vitest-environment jsdom

import * as React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceStateBadge } from "@/components/ui/source-state-badge";

describe("SourceStateBadge", () => {
  it("renders all supported source states consistently", () => {
    render(
      React.createElement("div", null,
        React.createElement(SourceStateBadge, { state: "sec_default" }),
        React.createElement(SourceStateBadge, { state: "partial_default" }),
        React.createElement(SourceStateBadge, { state: "fallback" }),
        React.createElement(SourceStateBadge, { state: "user_scenario" })
      )
    );

    expect(screen.getByTestId("source-state-badge-sec_default").textContent).toBe("SEC Default");
    expect(screen.getByTestId("source-state-badge-partial_default").textContent).toBe("Partial Default");
    expect(screen.getByTestId("source-state-badge-fallback").textContent).toBe("Fallback");
    expect(screen.getByTestId("source-state-badge-user_scenario").textContent).toBe("User Scenario");
  });
});

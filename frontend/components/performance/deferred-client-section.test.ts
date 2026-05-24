// @vitest-environment jsdom

import * as React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DeferredClientSection } from "@/components/performance/deferred-client-section";

describe("DeferredClientSection", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders children immediately when IntersectionObserver is unavailable", () => {
    vi.stubGlobal("IntersectionObserver", undefined);

    render(
      React.createElement(
        DeferredClientSection,
        { placeholder: React.createElement("div", null, "placeholder") },
        React.createElement("div", null, "deferred-content")
      )
    );

    expect(screen.getByText("deferred-content")).toBeTruthy();
  });

  it("shows placeholder before observer intersection", () => {
    class IntersectionObserverMock {
      observe() {}
      disconnect() {}
    }

    vi.stubGlobal("IntersectionObserver", IntersectionObserverMock as unknown as typeof IntersectionObserver);

    render(
      React.createElement(
        DeferredClientSection,
        { placeholder: React.createElement("div", null, "placeholder") },
        React.createElement("div", null, "deferred-content")
      )
    );

    expect(screen.getByText("placeholder")).toBeTruthy();
  });

  it("reveals children after the fallback delay when observer intersection never fires", async () => {
    vi.useFakeTimers();

    class IntersectionObserverMock {
      observe() {}
      disconnect() {}
    }

    vi.stubGlobal("IntersectionObserver", IntersectionObserverMock as unknown as typeof IntersectionObserver);

    render(
      React.createElement(
        DeferredClientSection,
        { placeholder: React.createElement("div", null, "placeholder"), fallbackDelayMs: 50 },
        React.createElement("div", null, "deferred-content")
      )
    );

    expect(screen.getByText("placeholder")).toBeTruthy();

    await vi.advanceTimersByTimeAsync(60);

    expect(screen.getByText("deferred-content")).toBeTruthy();
    vi.useRealTimers();
  });
});

// @vitest-environment jsdom

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { __resetJobStreamStoreForTests, useJobStream } from "@/hooks/use-job-stream";
import type { JobStatusEvent } from "@/lib/types";

class MockEventSource {
  static instances: MockEventSource[] = [];

  readonly url: string;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = vi.fn();

  private readonly listeners = new Map<string, Set<EventListener>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener): void {
    const listeners = this.listeners.get(type) ?? new Set<EventListener>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  dispatchStatus(payload: JobStatusEvent): void {
    const listeners = this.listeners.get("status") ?? new Set<EventListener>();
    const event = { data: JSON.stringify(payload) } as MessageEvent<string>;
    listeners.forEach((listener) => listener(event));
  }

  dispatchOpen(): void {
    this.onopen?.(new Event("open"));
  }

  dispatchError(): void {
    this.onerror?.(new Event("error"));
  }
}

function buildStatusEvent(overrides: Partial<JobStatusEvent> = {}): JobStatusEvent {
  return {
    job_id: "job-1",
    trace_id: "job-1",
    sequence: 1,
    timestamp: "2026-04-22T00:00:00Z",
    ticker: "AAPL",
    kind: "refresh",
    stage: "sync",
    message: "Sync running",
    status: "running",
    level: "info",
    ...overrides,
  };
}

describe("useJobStream", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
  });

  afterEach(() => {
    __resetJobStreamStoreForTests();
    vi.unstubAllGlobals();
  });

  it("dedupes duplicate subscriptions for the same job id", async () => {
    const first = renderHook(() => useJobStream("job-1"));
    const second = renderHook(() => useJobStream("job-1"));

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0]?.url).toBe("/backend/api/jobs/job-1/events");

    act(() => {
      MockEventSource.instances[0]?.dispatchStatus(buildStatusEvent());
    });

    await waitFor(() => {
      expect(first.result.current.events).toHaveLength(1);
      expect(second.result.current.events).toHaveLength(1);
    });

    first.unmount();
    expect(MockEventSource.instances[0]?.close).not.toHaveBeenCalled();

    second.unmount();
    expect(MockEventSource.instances[0]?.close).toHaveBeenCalledTimes(1);
  });

  it("surfaces reconnect transitions without creating a second event source", async () => {
    const { result } = renderHook(() => useJobStream("job-1"));

    expect(MockEventSource.instances).toHaveLength(1);

    act(() => {
      MockEventSource.instances[0]?.dispatchError();
    });

    await waitFor(() => {
      expect(result.current.connectionState).toBe("error");
    });

    act(() => {
      MockEventSource.instances[0]?.dispatchOpen();
    });

    await waitFor(() => {
      expect(result.current.connectionState).toBe("open");
    });

    expect(MockEventSource.instances).toHaveLength(1);
  });

  it("closes the shared stream after a terminal event while preserving the final event", async () => {
    const { result } = renderHook(() => useJobStream("job-terminal"));

    act(() => {
      MockEventSource.instances[0]?.dispatchStatus(
        buildStatusEvent({
          job_id: "job-terminal",
          trace_id: "job-terminal",
          status: "completed",
          level: "success",
          stage: "complete",
          message: "Refresh complete",
        })
      );
    });

    await waitFor(() => {
      expect(result.current.connectionState).toBe("closed");
      expect(result.current.lastEvent?.status).toBe("completed");
    });

    expect(MockEventSource.instances[0]?.close).toHaveBeenCalledTimes(1);
  });
});

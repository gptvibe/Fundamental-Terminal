"use client";

import { useEffect, useMemo, useState } from "react";

import type { ConsoleEntry, JobStatusEvent } from "@/lib/types";

type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";

export function useJobStream(jobId: string | null | undefined) {
  const [events, setEvents] = useState<JobStatusEvent[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");

  useEffect(() => {
    if (!jobId) {
      setEvents([]);
      setConnectionState("idle");
      return;
    }

    let closed = false;
    setEvents([]);
    setConnectionState("connecting");

    const source = new EventSource(`/backend/api/jobs/${encodeURIComponent(jobId)}/events`);
    const onStatus = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as JobStatusEvent;
      setEvents((current) => {
        if (current.some((entry) => entry.sequence === payload.sequence)) {
          return current;
        }
        return [...current, payload];
      });
      setConnectionState(payload.status === "completed" || payload.status === "failed" ? "closed" : "open");
      if (payload.status === "completed" || payload.status === "failed") {
        closed = true;
        source.close();
      }
    };

    source.addEventListener("status", onStatus as EventListener);
    source.onopen = () => setConnectionState("open");
    source.onerror = () => {
      if (!closed) {
        setConnectionState("error");
      }
      source.close();
    };

    return () => {
      closed = true;
      source.removeEventListener("status", onStatus as EventListener);
      source.close();
      setConnectionState("closed");
    };
  }, [jobId]);

  const consoleEntries = useMemo<ConsoleEntry[]>(
    () =>
      events.map((event) => ({
        id: `${event.job_id}-${event.sequence}`,
        job_id: event.job_id,
        trace_id: event.trace_id,
        ticker: event.ticker,
        kind: event.kind,
        timestamp: event.timestamp,
        stage: event.stage,
        message: event.message,
        level: event.level,
        status: event.status,
        source: "backend"
      })),
    [events]
  );

  return {
    events,
    consoleEntries,
    connectionState,
    lastEvent: events.at(-1) ?? null
  };
}

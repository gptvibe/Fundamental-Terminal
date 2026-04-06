"use client";

import { useEffect, useMemo, useState } from "react";

import type { ConsoleEntry, JobStatusEvent } from "@/lib/types";

type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";

type JobStreamState = {
  events: JobStatusEvent[];
  connectionState: ConnectionState;
};

function normalizeJobIds(jobIds: readonly (string | null | undefined)[]): string[] {
  return [...new Set(jobIds.filter((jobId): jobId is string => Boolean(jobId)))].sort();
}

function isTerminalEvent(event: JobStatusEvent | null | undefined): event is JobStatusEvent {
  return event?.status === "completed" || event?.status === "failed";
}

function appendEvent(current: JobStatusEvent[], payload: JobStatusEvent): JobStatusEvent[] {
  if (current.some((entry) => entry.sequence === payload.sequence)) {
    return current;
  }

  return [...current, payload];
}

export function useJobStreams(jobIds: readonly (string | null | undefined)[]) {
  const normalizedJobIds = normalizeJobIds(jobIds);
  const jobIdsKey = normalizedJobIds.join("|");
  const [stateByJobId, setStateByJobId] = useState<Record<string, JobStreamState>>({});

  useEffect(() => {
    if (!normalizedJobIds.length) {
      setStateByJobId({});
      return;
    }

    setStateByJobId((current) =>
      Object.fromEntries(
        normalizedJobIds.map((jobId) => [jobId, current[jobId] ?? { events: [], connectionState: "connecting" as ConnectionState }])
      )
    );

    const cleanups = normalizedJobIds.map((jobId) => {
      let closed = false;
      const source = new EventSource(`/backend/api/jobs/${encodeURIComponent(jobId)}/events`);

      const onStatus = (event: MessageEvent<string>) => {
        const payload = JSON.parse(event.data) as JobStatusEvent;
        setStateByJobId((current) => {
          const existing = current[jobId] ?? { events: [], connectionState: "connecting" as ConnectionState };
          return {
            ...current,
            [jobId]: {
              events: appendEvent(existing.events, payload),
              connectionState: isTerminalEvent(payload) ? "closed" : "open",
            },
          };
        });

        if (isTerminalEvent(payload)) {
          closed = true;
          source.close();
        }
      };

      source.addEventListener("status", onStatus as EventListener);
      source.onopen = () => {
        setStateByJobId((current) => ({
          ...current,
          [jobId]: {
            events: current[jobId]?.events ?? [],
            connectionState: "open",
          },
        }));
      };
      source.onerror = () => {
        if (closed) {
          return;
        }

        setStateByJobId((current) => ({
          ...current,
          [jobId]: {
            events: current[jobId]?.events ?? [],
            connectionState: "error",
          },
        }));
      };

      return () => {
        closed = true;
        source.removeEventListener("status", onStatus as EventListener);
        source.close();
      };
    });

    return () => {
      cleanups.forEach((cleanup) => cleanup());
    };
  }, [jobIdsKey]);

  const eventsByJobId = useMemo(
    () => Object.fromEntries(normalizedJobIds.map((jobId) => [jobId, stateByJobId[jobId]?.events ?? []])),
    [jobIdsKey, normalizedJobIds, stateByJobId]
  );
  const connectionStateByJobId = useMemo(
    () => Object.fromEntries(normalizedJobIds.map((jobId) => [jobId, stateByJobId[jobId]?.connectionState ?? "idle"])),
    [jobIdsKey, normalizedJobIds, stateByJobId]
  );
  const lastEventByJobId = useMemo(
    () =>
      Object.fromEntries(
        normalizedJobIds.map((jobId) => {
          const events = stateByJobId[jobId]?.events ?? [];
          return [jobId, events.at(-1) ?? null];
        })
      ),
    [jobIdsKey, normalizedJobIds, stateByJobId]
  );
  const terminalEvents = useMemo(
    () =>
      Object.values(lastEventByJobId)
        .filter(isTerminalEvent)
        .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp)),
    [lastEventByJobId]
  );

  return {
    eventsByJobId,
    connectionStateByJobId,
    lastEventByJobId,
    lastTerminalEvent: terminalEvents.at(-1) ?? null,
  };
}

export function useJobStream(jobId: string | null | undefined) {
  const { eventsByJobId, connectionStateByJobId, lastEventByJobId } = useJobStreams(jobId ? [jobId] : []);
  const events = jobId ? eventsByJobId[jobId] ?? [] : [];
  const connectionState = jobId ? connectionStateByJobId[jobId] ?? "idle" : "idle";
  const lastEvent = jobId ? lastEventByJobId[jobId] ?? null : null;

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
    lastEvent,
  };
}

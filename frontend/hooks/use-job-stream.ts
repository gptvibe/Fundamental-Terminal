"use client";

import { useEffect, useMemo, useState } from "react";

import type { ConsoleEntry, JobStatusEvent } from "@/lib/types";

type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";

type JobStreamState = {
  events: JobStatusEvent[];
  connectionState: ConnectionState;
};

type JobStreamListener = () => void;

type SharedJobStreamRecord = {
  source: EventSource;
  state: JobStreamState;
  listeners: Map<JobStreamListener, number>;
  subscriptionCount: number;
  notifyScheduled: boolean;
  closed: boolean;
};

const INITIAL_JOB_STREAM_STATE: JobStreamState = {
  events: [],
  connectionState: "connecting",
};

const sharedJobStreams = new Map<string, SharedJobStreamRecord>();

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

function areStatesEqual(left: JobStreamState, right: JobStreamState): boolean {
  return left.connectionState === right.connectionState && left.events === right.events;
}

function notifyListeners(record: SharedJobStreamRecord): void {
  if (record.notifyScheduled) {
    return;
  }

  record.notifyScheduled = true;
  queueMicrotask(() => {
    record.notifyScheduled = false;
    for (const listener of record.listeners.keys()) {
      listener();
    }
  });
}

function updateSharedJobStream(jobId: string, updater: (current: JobStreamState) => JobStreamState): void {
  const record = sharedJobStreams.get(jobId);
  if (!record) {
    return;
  }

  const nextState = updater(record.state);
  if (areStatesEqual(record.state, nextState)) {
    return;
  }

  record.state = nextState;
  notifyListeners(record);
}

function closeSharedJobStream(jobId: string): void {
  const record = sharedJobStreams.get(jobId);
  if (!record) {
    return;
  }

  record.closed = true;
  record.source.close();
}

function createSharedJobStream(jobId: string): SharedJobStreamRecord {
  const source = new EventSource(`/backend/api/jobs/${encodeURIComponent(jobId)}/events`);
  const record: SharedJobStreamRecord = {
    source,
    state: INITIAL_JOB_STREAM_STATE,
    listeners: new Map<JobStreamListener, number>(),
    subscriptionCount: 0,
    notifyScheduled: false,
    closed: false,
  };

  source.addEventListener("status", ((event: MessageEvent<string>) => {
    const payload = JSON.parse(event.data) as JobStatusEvent;
    updateSharedJobStream(jobId, (current) => ({
      events: appendEvent(current.events, payload),
      connectionState: isTerminalEvent(payload) ? "closed" : "open",
    }));

    if (isTerminalEvent(payload)) {
      closeSharedJobStream(jobId);
    }
  }) as EventListener);

  source.onopen = () => {
    updateSharedJobStream(jobId, (current) => ({
      events: current.events,
      connectionState: "open",
    }));
  };

  source.onerror = () => {
    const activeRecord = sharedJobStreams.get(jobId);
    if (!activeRecord || activeRecord.closed) {
      return;
    }

    updateSharedJobStream(jobId, (current) => ({
      events: current.events,
      connectionState: "error",
    }));
  };

  return record;
}

function ensureSharedJobStream(jobId: string): SharedJobStreamRecord {
  const existing = sharedJobStreams.get(jobId);
  if (existing) {
    return existing;
  }

  const created = createSharedJobStream(jobId);
  sharedJobStreams.set(jobId, created);
  return created;
}

function subscribeToJobStream(jobId: string, listener: JobStreamListener): () => void {
  const record = ensureSharedJobStream(jobId);
  record.subscriptionCount += 1;
  record.listeners.set(listener, (record.listeners.get(listener) ?? 0) + 1);

  return () => {
    const activeRecord = sharedJobStreams.get(jobId);
    if (!activeRecord) {
      return;
    }

    activeRecord.subscriptionCount = Math.max(0, activeRecord.subscriptionCount - 1);

    const remainingListenerCount = (activeRecord.listeners.get(listener) ?? 0) - 1;
    if (remainingListenerCount > 0) {
      activeRecord.listeners.set(listener, remainingListenerCount);
    } else {
      activeRecord.listeners.delete(listener);
    }

    if (activeRecord.subscriptionCount > 0) {
      return;
    }

    activeRecord.closed = true;
    activeRecord.source.close();
    sharedJobStreams.delete(jobId);
  };
}

function subscribeToJobStreams(jobIds: readonly string[], listener: JobStreamListener): () => void {
  const cleanups = jobIds.map((jobId) => subscribeToJobStream(jobId, listener));
  return () => {
    cleanups.forEach((cleanup) => cleanup());
  };
}

function getJobStreamState(jobId: string): JobStreamState {
  return sharedJobStreams.get(jobId)?.state ?? INITIAL_JOB_STREAM_STATE;
}

function getJobStreamSnapshot(jobIds: readonly string[]): Record<string, JobStreamState> {
  return Object.fromEntries(jobIds.map((jobId) => [jobId, getJobStreamState(jobId)]));
}

export function useJobStreams(jobIds: readonly (string | null | undefined)[]) {
  const normalizedJobIds = useMemo(() => normalizeJobIds(jobIds), [jobIds]);
  const jobIdsKey = normalizedJobIds.join("|");
  const [stateByJobId, setStateByJobId] = useState<Record<string, JobStreamState>>(() => getJobStreamSnapshot(normalizedJobIds));

  useEffect(() => {
    setStateByJobId(getJobStreamSnapshot(normalizedJobIds));

    if (!normalizedJobIds.length) {
      return;
    }

    return subscribeToJobStreams(normalizedJobIds, () => {
      setStateByJobId(getJobStreamSnapshot(normalizedJobIds));
    });
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
        source: "backend",
        queue_position: event.queue_position,
        jobs_ahead: event.jobs_ahead,
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

export function __resetJobStreamStoreForTests(): void {
  for (const [jobId, record] of sharedJobStreams.entries()) {
    record.closed = true;
    record.source.close();
    sharedJobStreams.delete(jobId);
  }
}

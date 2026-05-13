export const INFLIGHT_REQUEST_TIMEOUT_MS = 45_000;

export const inflightRequests = new Map<string, { promise: Promise<unknown>; startedAt: number }>();

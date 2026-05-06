export const INFLIGHT_REQUEST_TIMEOUT_MS = 15_000;

export const inflightRequests = new Map<string, { promise: Promise<unknown>; startedAt: number }>();

export type PerformanceAuditContext = {
  scenario: string;
  pageRoute: string;
  source: string;
};

export type PerformanceAuditCacheDisposition =
  | "network"
  | "cache-bypass"
  | "fresh-cache-hit"
  | "stale-cache-hit"
  | "inflight-dedupe";

export type PerformanceAuditRequestRecord = {
  id: string;
  startedAt: string;
  method: string;
  path: string;
  scenario: string | null;
  pageRoute: string | null;
  source: string | null;
  cacheDisposition: PerformanceAuditCacheDisposition;
  networkRequest: boolean;
  backgroundRevalidate: boolean;
  statusCode: number | null;
  durationMs: number;
  responseBytes: number | null;
  error: string | null;
};

export type PerformanceAuditSnapshot = PerformanceAuditState & {
  enabled: boolean;
  pendingCount: number;
};

type PerformanceAuditState = {
  sessionId: string;
  phase: string;
  requests: PerformanceAuditRequestRecord[];
};

type PerformanceAuditApi = {
  reset: (options?: { phase?: string }) => PerformanceAuditState;
  setPhase: (phase: string) => string;
  snapshot: () => PerformanceAuditSnapshot;
};

declare global {
  interface Window {
    __FT_PERFORMANCE_AUDIT__?: PerformanceAuditApi;
  }
}

const STORAGE_KEY = "ft:performance-audit:v1";
const DEFAULT_PHASE = "default";
const MAX_RECORDS = 4000;

const contextStack: PerformanceAuditContext[] = [];
let pendingCount = 0;

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

export function isPerformanceAuditEnabled(): boolean {
  return isBrowser() && process.env.NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED === "true";
}

function buildSessionId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function defaultState(overrides?: Partial<PerformanceAuditState>): PerformanceAuditState {
  return {
    sessionId: overrides?.sessionId ?? buildSessionId(),
    phase: overrides?.phase ?? DEFAULT_PHASE,
    requests: overrides?.requests ?? [],
  };
}

function readState(): PerformanceAuditState {
  if (!isBrowser()) {
    return defaultState();
  }

  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return defaultState();
    }
    const parsed = JSON.parse(raw) as Partial<PerformanceAuditState>;
    return defaultState({
      sessionId: typeof parsed.sessionId === "string" ? parsed.sessionId : undefined,
      phase: typeof parsed.phase === "string" ? parsed.phase : undefined,
      requests: Array.isArray(parsed.requests) ? parsed.requests as PerformanceAuditRequestRecord[] : undefined,
    });
  } catch {
    return defaultState();
  }
}

function writeState(state: PerformanceAuditState): PerformanceAuditState {
  if (!isBrowser()) {
    return state;
  }

  const normalized: PerformanceAuditState = {
    sessionId: state.sessionId,
    phase: state.phase || DEFAULT_PHASE,
    requests: state.requests.slice(-MAX_RECORDS),
  };

  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
  } catch {
    // Ignore storage errors. Audit data is best-effort.
  }
  return normalized;
}

function ensureApiInstalled(): void {
  if (!isPerformanceAuditEnabled() || !isBrowser() || window.__FT_PERFORMANCE_AUDIT__) {
    return;
  }

  window.__FT_PERFORMANCE_AUDIT__ = {
    reset(options) {
      pendingCount = 0;
      return writeState(defaultState({ phase: options?.phase ?? DEFAULT_PHASE }));
    },
    setPhase(phase) {
      const state = readState();
      writeState({ ...state, phase: phase || DEFAULT_PHASE });
      return phase || DEFAULT_PHASE;
    },
    snapshot() {
      const state = readState();
      return {
        ...state,
        enabled: true,
        pendingCount,
      };
    },
  };
}

export function getCurrentPerformanceAuditContext(): PerformanceAuditContext | null {
  if (!isPerformanceAuditEnabled()) {
    return null;
  }
  ensureApiInstalled();
  return contextStack[contextStack.length - 1] ?? null;
}

export async function withPerformanceAuditSource<T>(context: PerformanceAuditContext, work: () => Promise<T>): Promise<T> {
  if (!isPerformanceAuditEnabled()) {
    return work();
  }

  ensureApiInstalled();
  contextStack.push(context);
  try {
    return await work();
  } finally {
    const current = contextStack[contextStack.length - 1];
    if (current === context) {
      contextStack.pop();
    } else {
      const index = contextStack.lastIndexOf(context);
      if (index >= 0) {
        contextStack.splice(index, 1);
      }
    }
  }
}

export function beginPerformanceAuditNetworkRequest(): void {
  if (!isPerformanceAuditEnabled()) {
    return;
  }
  ensureApiInstalled();
  pendingCount += 1;
}

export function endPerformanceAuditNetworkRequest(): void {
  if (!isPerformanceAuditEnabled()) {
    return;
  }
  pendingCount = Math.max(0, pendingCount - 1);
}

export function recordPerformanceAuditRequest(
  record: Omit<PerformanceAuditRequestRecord, "id" | "startedAt" | "scenario" | "pageRoute" | "source"> & {
    startedAt?: string;
    context?: PerformanceAuditContext | null;
  }
): void {
  if (!isPerformanceAuditEnabled()) {
    return;
  }

  ensureApiInstalled();
  const state = readState();
  const context = record.context ?? getCurrentPerformanceAuditContext();
  writeState({
    ...state,
    requests: [
      ...state.requests,
      {
        id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
        startedAt: record.startedAt ?? new Date().toISOString(),
        method: record.method,
        path: record.path,
        scenario: context?.scenario ?? null,
        pageRoute: context?.pageRoute ?? null,
        source: context?.source ?? null,
        cacheDisposition: record.cacheDisposition,
        networkRequest: record.networkRequest,
        backgroundRevalidate: record.backgroundRevalidate,
        statusCode: record.statusCode,
        durationMs: record.durationMs,
        responseBytes: record.responseBytes,
        error: record.error,
      },
    ],
  });
}

if (isBrowser()) {
  ensureApiInstalled();
}

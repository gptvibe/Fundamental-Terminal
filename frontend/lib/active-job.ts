export interface StoredActiveJob {
  jobId: string;
  ticker: string;
  storedAt: string;
}

export const ACTIVE_JOB_STORAGE_KEY = "ft-active-job";
export const ACTIVE_JOB_EVENT = "ft:active-job";

export function readStoredActiveJob(): StoredActiveJob | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawValue = window.sessionStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<StoredActiveJob>;
    if (!parsed.jobId || !parsed.ticker || !parsed.storedAt) {
      window.sessionStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
      return null;
    }

    return {
      jobId: parsed.jobId,
      ticker: parsed.ticker,
      storedAt: parsed.storedAt
    };
  } catch {
    window.sessionStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
    return null;
  }
}

export function rememberActiveJob(jobId: string, ticker: string): void {
  if (typeof window === "undefined") {
    return;
  }

  const nextValue: StoredActiveJob = {
    jobId,
    ticker,
    storedAt: new Date().toISOString()
  };
  window.sessionStorage.setItem(ACTIVE_JOB_STORAGE_KEY, JSON.stringify(nextValue));
  window.dispatchEvent(new CustomEvent(ACTIVE_JOB_EVENT, { detail: nextValue }));
}

export function clearStoredActiveJob(jobId?: string): void {
  if (typeof window === "undefined") {
    return;
  }

  const activeJob = readStoredActiveJob();
  if (jobId && activeJob?.jobId !== jobId) {
    return;
  }

  window.sessionStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
  window.dispatchEvent(new CustomEvent(ACTIVE_JOB_EVENT, { detail: null }));
}

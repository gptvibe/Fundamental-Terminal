import { readStoredActiveJob } from "@/lib/active-job";
import {
  getApiReadCacheState,
  getCompanyCharts,
  getCompanyFinancials,
  getCompanyModels,
  getCompanyPeers,
  type ApiReadCacheState,
} from "@/lib/api";
import { withPerformanceAuditSource } from "@/lib/performance-audit";

type PrefetchTrigger = "idle" | "hover" | "focus";

type PrefetchTargetKey = "financials" | "charts" | "models" | "peers";

type PrefetchTarget = {
  key: PrefetchTargetKey;
  path: string;
  load: () => Promise<unknown>;
};

export type PrefetchCompanyWorkspaceTabsOptions = {
  asOf?: string | null;
  trigger?: PrefetchTrigger;
  activeRefreshJobId?: string | null;
  pageRoute?: string;
  scenario?: string;
  maxConcurrency?: number;
  lowDataModeEnabled?: boolean;
};

const prefetchInflightByTicker = new Map<string, Promise<void>>();
const DEFAULT_PREFETCH_CONCURRENCY = 2;

export function prefetchCompanyWorkspaceTabs(
  ticker: string,
  options: PrefetchCompanyWorkspaceTabsOptions = {}
): Promise<void> {
  const normalizedTicker = ticker.trim().toUpperCase();
  if (!normalizedTicker) {
    return Promise.resolve();
  }

  const activeInflight = prefetchInflightByTicker.get(normalizedTicker);
  if (activeInflight) {
    return activeInflight;
  }

  const task = runPrefetch(normalizedTicker, options).finally(() => {
    prefetchInflightByTicker.delete(normalizedTicker);
  });
  prefetchInflightByTicker.set(normalizedTicker, task);
  return task;
}

async function runPrefetch(
  ticker: string,
  options: PrefetchCompanyWorkspaceTabsOptions
): Promise<void> {
  if (!shouldRunPrefetch(ticker, options)) {
    return;
  }

  const targets = await resolveTargetsToFetch(ticker, options.asOf ?? null);
  if (!targets.length) {
    return;
  }

  const maxConcurrency = clampConcurrency(options.maxConcurrency ?? DEFAULT_PREFETCH_CONCURRENCY);
  const trigger = options.trigger ?? "idle";
  const pageRoute = options.pageRoute ?? "/company/[ticker]";
  const scenario = options.scenario ?? "company_workspace_prefetch";

  await runWithConcurrency(targets, maxConcurrency, async (target) => {
    try {
      await withPerformanceAuditSource(
        {
          pageRoute,
          scenario,
          source: `prefetch:${trigger}:${target.key}`,
        },
        target.load
      );
    } catch {
      // Prefetch is best-effort; ignore target-level failures.
    }
  });
}

function shouldRunPrefetch(ticker: string, options: PrefetchCompanyWorkspaceTabsOptions): boolean {
  if (!isBrowserOnline()) {
    return false;
  }

  if (isLowDataModeEnabled(options)) {
    return false;
  }

  if (options.activeRefreshJobId) {
    return false;
  }

  const storedActiveJob = readStoredActiveJob();
  if (storedActiveJob?.jobId && storedActiveJob.ticker.toUpperCase() === ticker) {
    return false;
  }

  return true;
}

async function resolveTargetsToFetch(ticker: string, asOf: string | null): Promise<PrefetchTarget[]> {
  const encodedTicker = encodeURIComponent(ticker);
  const suffix = buildAsOfSuffix(asOf);

  const candidates: PrefetchTarget[] = [
    {
      key: "financials",
      path: `/companies/${encodedTicker}/financials${suffix}`,
      load: () => getCompanyFinancials(ticker, { asOf }),
    },
    {
      key: "charts",
      path: `/companies/${encodedTicker}/charts${suffix}`,
      load: () => getCompanyCharts(ticker, { asOf }),
    },
    {
      key: "models",
      path: `/companies/${encodedTicker}/models${suffix}`,
      load: () => getCompanyModels(ticker, undefined, { asOf }),
    },
    {
      key: "peers",
      path: `/companies/${encodedTicker}/peers${suffix}`,
      load: () => getCompanyPeers(ticker, undefined, { asOf }),
    },
  ];

  const states = await Promise.all(candidates.map((candidate) => getApiReadCacheState(candidate.path)));
  return candidates.filter((_, index) => shouldFetchForCacheState(states[index]));
}

function shouldFetchForCacheState(state: ApiReadCacheState): boolean {
  return state === "missing" || state === "stale";
}

function buildAsOfSuffix(asOf: string | null): string {
  const normalizedAsOf = asOf?.trim();
  if (!normalizedAsOf) {
    return "";
  }

  const params = new URLSearchParams();
  params.set("as_of", normalizedAsOf);
  return `?${params.toString()}`;
}

function isBrowserOnline(): boolean {
  if (typeof navigator === "undefined") {
    return true;
  }

  return navigator.onLine !== false;
}

function isLowDataModeEnabled(options: PrefetchCompanyWorkspaceTabsOptions): boolean {
  if (options.lowDataModeEnabled != null) {
    return options.lowDataModeEnabled;
  }

  if (typeof navigator === "undefined") {
    return false;
  }

  const networkNavigator = navigator as Navigator & {
    connection?: {
      saveData?: boolean;
    };
  };

  return Boolean(networkNavigator.connection?.saveData);
}

function clampConcurrency(value: number): number {
  if (!Number.isFinite(value)) {
    return DEFAULT_PREFETCH_CONCURRENCY;
  }

  return Math.max(1, Math.min(2, Math.trunc(value)));
}

async function runWithConcurrency<T>(
  items: T[],
  maxConcurrency: number,
  worker: (item: T) => Promise<void>
): Promise<void> {
  if (!items.length) {
    return;
  }

  let index = 0;
  const workers = Array.from({ length: Math.min(maxConcurrency, items.length) }, async () => {
    while (index < items.length) {
      const currentIndex = index;
      index += 1;
      await worker(items[currentIndex]);
    }
  });

  await Promise.all(workers);
}

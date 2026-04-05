import fs from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import process from "node:process";
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));


import { chromium } from "@playwright/test";


const DEFAULT_FRONTEND_URL = "http://127.0.0.1:3000";
const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";
const DEFAULT_TICKER = "AAPL";
const DEFAULT_ROUNDS = 8;
const MODEL_NAMES = ["ratios", "dupont", "dcf", "reverse_dcf", "roic", "capital_allocation"];
const LOCAL_USER_DATA_STORAGE_KEY = "ft-local-user-data";
const API_CACHE_STORAGE_PREFIX = "ft:api-cache:v2:";
const PERFORMANCE_AUDIT_STORAGE_KEY = "ft:performance-audit:v1";

const PAGE_SCENARIOS = [
  {
    key: "homepage_search",
    label: "Homepage search",
    pageRoute: "/",
    async run(page, config, phase) {
      await page.goto(config.frontendUrl, { waitUntil: "domcontentloaded" });
      await waitForFrontendAudit(page);
      await resetCollectors(page, config.backendUrl, phase);

      const input = page.getByRole("combobox", { name: /search by ticker, company, or cik/i });
      await input.fill("");
      await input.fill(config.ticker);
      await waitForAuditIdle(page);
      return collectScenarioResult(page, config.backendUrl, this.label, phase);
    },
  },
  {
    key: "company_overview",
    label: "/company/[ticker]",
    pageRoute: "/company/[ticker]",
    pathFor(config) {
      return `${config.frontendUrl}/company/${encodeURIComponent(config.ticker)}`;
    },
  },
  {
    key: "models_page",
    label: "Models",
    pageRoute: "/company/[ticker]/models",
    pathFor(config) {
      return `${config.frontendUrl}/company/${encodeURIComponent(config.ticker)}/models`;
    },
  },
  {
    key: "financials_page",
    label: "Financials",
    pageRoute: "/company/[ticker]/financials",
    pathFor(config) {
      return `${config.frontendUrl}/company/${encodeURIComponent(config.ticker)}/financials`;
    },
  },
  {
    key: "watchlist_page",
    label: "Watchlist",
    pageRoute: "/watchlist",
    pathFor(config) {
      return `${config.frontendUrl}/watchlist`;
    },
  },
];

const HOT_ROUTE_CASES = [
  {
    label: "Company search",
    url: (config) => `${config.backendUrl}/api/companies/search?query=${encodeURIComponent(config.ticker)}&refresh=false`,
  },
  {
    label: "Company financials",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/financials`,
  },
  {
    label: "Insider trades",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/insider-trades`,
  },
  {
    label: "Institutional holdings",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/institutional-holdings`,
  },
  {
    label: "Activity overview",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/activity-overview`,
  },
  {
    label: "Changes since last filing",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/changes-since-last-filing`,
  },
  {
    label: "Earnings summary",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/earnings/summary`,
  },
  {
    label: "Capital structure",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/capital-structure?max_periods=6`,
  },
  {
    label: "Capital markets summary",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/capital-markets/summary`,
  },
  {
    label: "Governance summary",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/governance/summary`,
  },
  {
    label: "Beneficial ownership summary",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/beneficial-ownership/summary`,
  },
  {
    label: "Models payload",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/models?model=${encodeURIComponent(MODEL_NAMES.join(","))}&dupont_mode=auto`,
  },
  {
    label: "Peers payload",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/peers`,
  },
  {
    label: "Market context",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/market-context`,
  },
  {
    label: "Sector context",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/sector-context`,
  },
  {
    label: "Model evaluation",
    url: (config) => `${config.backendUrl}/api/model-evaluations/latest`,
  },
  {
    label: "Global market context",
    url: (config) => `${config.backendUrl}/api/market-context`,
  },
  {
    label: "Source registry",
    url: (config) => `${config.backendUrl}/api/source-registry`,
  },
  {
    label: "Watchlist summary",
    url: (config) => `${config.backendUrl}/api/watchlist/summary`,
    options: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: [configTickerPlaceholder(), "MSFT"] }),
    },
  },
  {
    label: "Watchlist calendar",
    url: (config) => `${config.backendUrl}/api/watchlist/calendar?tickers=${encodeURIComponent(config.ticker)}&tickers=MSFT`,
  },
  {
    label: "Refresh queue",
    url: (config) => `${config.backendUrl}/api/companies/${encodeURIComponent(config.ticker)}/refresh?force=true`,
    options: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    },
  },
];


async function main() {
  const config = parseArgs(process.argv.slice(2));
  const docsDir = path.resolve(config.repoRoot, "docs");
  const jsonOutputPath = path.join(docsDir, "performance-baseline.json");
  const markdownOutputPath = path.join(docsDir, "performance-baseline.md");

  await assertBackendAudit(config.backendUrl);

  const browser = await chromium.launch({ headless: true });

  const scenarioResults = [];
  for (const scenario of PAGE_SCENARIOS) {
    if (typeof scenario.run === "function") {
      scenarioResults.push(await runScenarioPhase(browser, config, scenario, "cold"));
      scenarioResults.push(await runScenarioPhase(browser, config, scenario, "warm"));
      continue;
    }

    scenarioResults.push(await runScenarioPhase(browser, config, scenario, "cold"));
    scenarioResults.push(await runScenarioPhase(browser, config, scenario, "warm"));
  }

  const benchmarkResults = [];
  for (const routeCase of HOT_ROUTE_CASES) {
    benchmarkResults.push(await benchmarkRouteCase(config, routeCase));
  }

  await browser.close();

  const summary = buildSummary(config, scenarioResults, benchmarkResults);
  await fs.writeFile(jsonOutputPath, JSON.stringify(summary, null, 2));
  await fs.writeFile(markdownOutputPath, buildMarkdown(summary), "utf8");

  process.stdout.write(`Wrote ${path.relative(config.repoRoot, markdownOutputPath)} and ${path.relative(config.repoRoot, jsonOutputPath)}\n`);
}


function parseArgs(args) {
  const values = new Map();
  for (let index = 0; index < args.length; index += 1) {
    const token = args[index];
    if (!token.startsWith("--")) {
      continue;
    }
    values.set(token.slice(2), args[index + 1]);
    index += 1;
  }

  return {
    backendUrl: values.get("backend-url") ?? DEFAULT_BACKEND_URL,
    frontendUrl: values.get("frontend-url") ?? DEFAULT_FRONTEND_URL,
    ticker: String(values.get("ticker") ?? DEFAULT_TICKER).trim().toUpperCase(),
    rounds: Number.parseInt(values.get("rounds") ?? String(DEFAULT_ROUNDS), 10),
    repoRoot: path.resolve(SCRIPT_DIR, "..", ".."),
  };
}


async function assertBackendAudit(backendUrl) {
  const response = await fetch(`${backendUrl}/api/internal/performance-audit`);
  if (!response.ok) {
    throw new Error(`Backend audit endpoint unavailable at ${backendUrl}. Start the backend with PERFORMANCE_AUDIT_ENABLED=true.`);
  }
  const payload = await response.json();
  if (!payload.enabled) {
    throw new Error("Backend audit endpoint is reachable, but PERFORMANCE_AUDIT_ENABLED is false.");
  }
}


async function waitForFrontendAudit(page) {
  await page.waitForFunction(
    () => typeof window.__FT_PERFORMANCE_AUDIT__?.reset === "function" && typeof window.__FT_PERFORMANCE_AUDIT__?.snapshot === "function",
    null,
    { timeout: 15000 }
  );
}


async function newAuditContext(browser, config) {
  const context = await browser.newContext();
  await context.addInitScript(
    ({ storageKey, ticker, auditStorageKey, apiCachePrefix }) => {
      const payload = {
        watchlist: [
          { ticker, name: ticker, sector: null, savedAt: new Date().toISOString() },
          { ticker: "MSFT", name: "Microsoft", sector: null, savedAt: new Date(Date.now() - 1000).toISOString() },
        ],
        notes: {},
      };
      window.localStorage.setItem(storageKey, JSON.stringify(payload));
      window.sessionStorage.removeItem(auditStorageKey);
      for (const key of Object.keys(window.localStorage)) {
        if (key.startsWith(apiCachePrefix)) {
          window.localStorage.removeItem(key);
        }
      }
    },
    {
      storageKey: LOCAL_USER_DATA_STORAGE_KEY,
      ticker: config.ticker,
      auditStorageKey: PERFORMANCE_AUDIT_STORAGE_KEY,
      apiCachePrefix: API_CACHE_STORAGE_PREFIX,
    }
  );
  return context;
}


async function runScenarioPhase(browser, config, scenario, phase) {
  const context = await newAuditContext(browser, config);
  const page = await context.newPage();

  try {
    if (phase === "cold") {
      if (typeof scenario.run === "function") {
        return await scenario.run(page, config, phase);
      }
      return await runNavigationScenario(page, config, scenario, phase);
    }

    if (typeof scenario.run === "function") {
      await scenario.run(page, config, "cold");
      return await scenario.run(page, config, phase);
    }

    await runNavigationScenario(page, config, scenario, "cold");
    return await runNavigationScenario(page, config, scenario, phase);
  } finally {
    await context.close();
  }
}


async function resetCollectors(page, backendUrl, phase) {
  await page.evaluate((nextPhase) => window.__FT_PERFORMANCE_AUDIT__.reset({ phase: nextPhase }), phase);
  const response = await fetch(`${backendUrl}/api/internal/performance-audit/reset`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Unable to reset backend audit collector: ${response.status}`);
  }
}


async function waitForAuditIdle(page, options = {}) {
  await waitForFrontendAudit(page);
  const stableForMs = options.stableForMs ?? 800;
  const timeoutMs = options.timeoutMs ?? 20000;
  const startedAt = Date.now();
  let lastSignature = "";
  let lastChangedAt = Date.now();

  while (Date.now() - startedAt < timeoutMs) {
    const snapshot = await page.evaluate(() => window.__FT_PERFORMANCE_AUDIT__.snapshot());
    const signature = `${snapshot.pendingCount}:${snapshot.requests.length}`;
    if (signature !== lastSignature) {
      lastSignature = signature;
      lastChangedAt = Date.now();
    }
    if (snapshot.pendingCount === 0 && Date.now() - lastChangedAt >= stableForMs) {
      return snapshot;
    }
    await page.waitForTimeout(200);
  }

  return page.evaluate(() => window.__FT_PERFORMANCE_AUDIT__.snapshot());
}


async function collectScenarioResult(page, backendUrl, label, phase) {
  await waitForFrontendAudit(page);
  const frontendSnapshot = await page.evaluate(() => window.__FT_PERFORMANCE_AUDIT__.snapshot());
  const backendSnapshotResponse = await fetch(`${backendUrl}/api/internal/performance-audit`);
  const backendSnapshot = await backendSnapshotResponse.json();
  return summarizeScenario(label, phase, frontendSnapshot, backendSnapshot);
}


async function runNavigationScenario(page, config, scenario, phase) {
  await page.goto(config.frontendUrl, { waitUntil: "domcontentloaded" });
  await waitForFrontendAudit(page);
  await resetCollectors(page, config.backendUrl, phase);
  await page.goto(scenario.pathFor(config), { waitUntil: "domcontentloaded" });
  await waitForFrontendAudit(page);
  await waitForAuditIdle(page);
  return collectScenarioResult(page, config.backendUrl, scenario.label, phase);
}


function summarizeScenario(label, phase, frontendSnapshot, backendSnapshot) {
  const requests = frontendSnapshot.requests;
  const blockingRequests = requests.filter((record) => !record.backgroundRevalidate);
  const networkRequests = blockingRequests.filter((record) => record.networkRequest);
  const cacheHits = blockingRequests.filter((record) => !record.networkRequest);
  const duplicateSources = Object.values(
    blockingRequests.reduce((accumulator, record) => {
      const key = `${record.source ?? "unknown"}|${record.path}`;
      accumulator[key] ??= {
        source: record.source ?? "unknown",
        path: record.path,
        count: 0,
      };
      accumulator[key].count += 1;
      return accumulator;
    }, {})
  ).filter((entry) => entry.count > 1);

  const pageElapsedMs = derivePageElapsedMs(blockingRequests);
  const backendRecords = Array.isArray(backendSnapshot.records) ? backendSnapshot.records : [];
  const totalSqlQueries = backendRecords.reduce((sum, record) => sum + Number(record.sql_query_count ?? 0), 0);
  const totalSqlElapsedMs = backendRecords.reduce((sum, record) => sum + Number(record.sql_elapsed_ms ?? 0), 0);
  const totalResponseBytes = backendRecords.reduce((sum, record) => sum + Number(record.response_bytes ?? 0), 0);
  const totalSerializationMs = backendRecords.reduce((sum, record) => sum + Number(record.serialization_ms ?? 0), 0);

  return {
    label,
    phase,
    pageElapsedMs,
    frontend: {
      requestCount: blockingRequests.length,
      networkRequestCount: networkRequests.length,
      cacheHitCount: cacheHits.length,
      backgroundRevalidateCount: requests.filter((record) => record.backgroundRevalidate).length,
      duplicateSources: duplicateSources.sort((left, right) => right.count - left.count),
      requests: blockingRequests,
    },
    backend: {
      requestCount: backendRecords.length,
      totalSqlQueries,
      totalSqlElapsedMs: round(totalSqlElapsedMs),
      totalResponseBytes,
      totalSerializationMs: round(totalSerializationMs),
      routeSummaries: Array.isArray(backendSnapshot.route_summaries) ? backendSnapshot.route_summaries : [],
    },
  };
}


function derivePageElapsedMs(requests) {
  if (!requests.length) {
    return 0;
  }

  const startedAt = requests
    .map((record) => Date.parse(record.startedAt))
    .filter((value) => Number.isFinite(value));
  if (!startedAt.length) {
    return round(requests.reduce((sum, record) => sum + Number(record.durationMs ?? 0), 0));
  }
  const earliest = Math.min(...startedAt);
  const latest = Math.max(
    ...requests.map((record) => Date.parse(record.startedAt) + Number(record.durationMs ?? 0)).filter((value) => Number.isFinite(value))
  );
  return round(Math.max(0, latest - earliest));
}


async function benchmarkRouteCase(config, routeCase) {
  await fetch(`${config.backendUrl}/api/internal/performance-audit/reset`, { method: "POST" });

  for (let roundIndex = 0; roundIndex < config.rounds; roundIndex += 1) {
    const response = await fetch(routeCase.url(config), materializeFetchOptions(routeCase.options, config));
    await response.text();
    if (!response.ok) {
      throw new Error(`${routeCase.label} failed with ${response.status} ${response.statusText}`);
    }
  }

  const snapshotResponse = await fetch(`${config.backendUrl}/api/internal/performance-audit`);
  const snapshot = await snapshotResponse.json();
  const records = Array.isArray(snapshot.records) ? snapshot.records : [];
  if (!records.length) {
    throw new Error(`No backend records captured for ${routeCase.label}`);
  }

  const coldRecord = records[0];
  const warmRecords = records.slice(1);
  return {
    label: routeCase.label,
    routePath: coldRecord.route_path ?? coldRecord.path,
    requestKind: coldRecord.request_kind ?? "read",
    cold: summarizeRecord(coldRecord),
    warm: summarizeRecords(warmRecords),
  };
}


function summarizeRecord(record) {
  return {
    latencyMs: round(Number(record.duration_ms ?? 0)),
    sqlQueryCount: Number(record.sql_query_count ?? 0),
    sqlElapsedMs: round(Number(record.sql_elapsed_ms ?? 0)),
    serializationMs: round(Number(record.serialization_ms ?? 0)),
    responseBytes: Number(record.response_bytes ?? 0),
  };
}


function summarizeRecords(records) {
  if (!records.length) {
    return {
      count: 0,
      latencyMs: { p50: 0, p95: 0 },
      sqlQueryCount: { avg: 0, p95: 0 },
      sqlElapsedMs: { avg: 0, p95: 0 },
      serializationMs: { avg: 0, p95: 0 },
      responseBytes: { avg: 0, max: 0 },
    };
  }

  const latencies = records.map((record) => Number(record.duration_ms ?? 0));
  const sqlCounts = records.map((record) => Number(record.sql_query_count ?? 0));
  const sqlElapsed = records.map((record) => Number(record.sql_elapsed_ms ?? 0));
  const serialization = records.map((record) => Number(record.serialization_ms ?? 0));
  const responseBytes = records.map((record) => Number(record.response_bytes ?? 0));

  return {
    count: records.length,
    latencyMs: { p50: round(percentile(latencies, 0.5)), p95: round(percentile(latencies, 0.95)) },
    sqlQueryCount: { avg: round(average(sqlCounts)), p95: round(percentile(sqlCounts, 0.95)) },
    sqlElapsedMs: { avg: round(average(sqlElapsed)), p95: round(percentile(sqlElapsed, 0.95)) },
    serializationMs: { avg: round(average(serialization)), p95: round(percentile(serialization, 0.95)) },
    responseBytes: { avg: round(average(responseBytes)), max: Math.max(...responseBytes) },
  };
}


function buildSummary(config, scenarioResults, benchmarkResults) {
  const coldWarmPairs = PAGE_SCENARIOS.map((scenario) => {
    const cold = scenarioResults.find((result) => result.label === scenario.label && result.phase === "cold");
    const warm = scenarioResults.find((result) => result.label === scenario.label && result.phase === "warm");
    return {
      label: scenario.label,
      cold,
      warm,
    };
  });

  const slowestRoutes = [...benchmarkResults]
    .sort((left, right) => right.warm.latencyMs.p95 - left.warm.latencyMs.p95)
    .slice(0, 10);

  const mostOverFetchedFlows = [...scenarioResults]
    .sort((left, right) => {
      if (right.frontend.requestCount !== left.frontend.requestCount) {
        return right.frontend.requestCount - left.frontend.requestCount;
      }
      return right.backend.totalSqlQueries - left.backend.totalSqlQueries;
    })
    .slice(0, 10);

  const duplicateSources = [...scenarioResults.flatMap((result) =>
    result.frontend.duplicateSources.map((entry) => ({
      label: result.label,
      phase: result.phase,
      ...entry,
    }))
  )]
    .sort((left, right) => right.count - left.count)
    .slice(0, 10);

  return {
    generatedAt: new Date().toISOString(),
    command: `npm --prefix frontend run audit:performance -- --ticker ${config.ticker}`,
    config,
    pageFlows: scenarioResults,
    coldWarmPairs,
    slowestRoutes,
    mostOverFetchedFlows,
    duplicateSources,
    benchmarkResults,
  };
}


function buildMarkdown(summary) {
  const lines = [];
  lines.push("# Performance Baseline");
  lines.push("");
  lines.push(`Generated: ${summary.generatedAt}`);
  lines.push("");
  lines.push("## Run Command");
  lines.push("");
  lines.push("```bash");
  lines.push(summary.command);
  lines.push("```");
  lines.push("");
  lines.push("Prerequisites:");
  lines.push("- Start the backend with `PERFORMANCE_AUDIT_ENABLED=true`.");
  lines.push("- Start the frontend with `NEXT_PUBLIC_PERFORMANCE_AUDIT_ENABLED=true`.");
  lines.push("- Keep the services on the default local ports or pass `--frontend-url` / `--backend-url`.");
  lines.push("");
  lines.push("## Top 10 Slowest Routes");
  lines.push("");
  lines.push("| Route | Kind | Warm p50 (ms) | Warm p95 (ms) | Avg SQL Count | Avg SQL (ms) | Avg Serialize (ms) | Avg Payload (KB) |");
  lines.push("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |");
  for (const route of summary.slowestRoutes) {
    lines.push(`| ${route.routePath} | ${route.requestKind} | ${route.warm.latencyMs.p50} | ${route.warm.latencyMs.p95} | ${route.warm.sqlQueryCount.avg} | ${route.warm.sqlElapsedMs.avg} | ${route.warm.serializationMs.avg} | ${round(route.warm.responseBytes.avg / 1024)} |`);
  }
  lines.push("");
  lines.push("## Top 10 Most Over-Fetched Page Flows");
  lines.push("");
  lines.push("| Flow | Phase | Requests | Network | Cache Hits | Backend SQL Queries | Serialize (ms) | Payload (KB) | Page Elapsed (ms) |");
  lines.push("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |");
  for (const flow of summary.mostOverFetchedFlows) {
    lines.push(`| ${flow.label} | ${flow.phase} | ${flow.frontend.requestCount} | ${flow.frontend.networkRequestCount} | ${flow.frontend.cacheHitCount} | ${flow.backend.totalSqlQueries} | ${flow.backend.totalSerializationMs} | ${round(flow.backend.totalResponseBytes / 1024)} | ${flow.pageElapsedMs} |`);
  }
  lines.push("");
  lines.push("## Duplicate Request Sources");
  lines.push("");
  lines.push("| Flow | Phase | Source | Route | Count |");
  lines.push("| --- | --- | --- | --- | ---: |");
  for (const duplicate of summary.duplicateSources) {
    lines.push(`| ${duplicate.label} | ${duplicate.phase} | ${duplicate.source} | ${duplicate.path} | ${duplicate.count} |`);
  }
  if (!summary.duplicateSources.length) {
    lines.push("No duplicate request sources were captured in the audited flows.");
  }
  lines.push("");
  lines.push("## Cold vs Warm Timings");
  lines.push("");
  lines.push("| Flow | Cold (ms) | Warm (ms) | Cold Requests | Warm Requests | Warm Cache Hits |");
  lines.push("| --- | ---: | ---: | ---: | ---: | ---: |");
  for (const pair of summary.coldWarmPairs) {
    lines.push(`| ${pair.label} | ${pair.cold?.pageElapsedMs ?? 0} | ${pair.warm?.pageElapsedMs ?? 0} | ${pair.cold?.frontend.requestCount ?? 0} | ${pair.warm?.frontend.requestCount ?? 0} | ${pair.warm?.frontend.cacheHitCount ?? 0} |`);
  }
  lines.push("");
  lines.push("## Recommendations By Expected Impact");
  lines.push("");
  lines.push("### High Impact");
  lines.push("- Collapse the company overview research-brief fan-out into one server-composed workspace payload. The overview flow currently pays for multiple summary endpoints in parallel even after the base financial payload lands.");
  lines.push("- Reuse tab-shared company payloads across overview, models, and financials. The models and financials pages repeat financial and capital-structure reads that the overview path already fetched.");
  lines.push("- Trim the heaviest route payloads before touching the public contract. Large default arrays are driving both response bytes and server-side serialization cost on the slowest read routes.");
  lines.push("");
  lines.push("### Medium Impact");
  lines.push("- Stop watchlist dual-fetch and polling from competing with the rest of the page. Summary and calendar are always requested together and the three-second poll loop can keep the page chatty.");
  lines.push("- Treat stale-cache returns separately from background revalidation in the UI. A page can feel slow even when network fan-out is lower because the client still fans out many logical reads and background revalidators.");
  lines.push("- Memoize or batch homepage search follow-ups. The audit makes it visible when autocomplete search and resolve-style lookup happen back-to-back for the same input.");
  lines.push("");
  lines.push("### Lower Impact");
  lines.push("- Increase the visibility of route-level payload and serialization metrics in local developer workflows so regressions show up before they reach UI review.");
  lines.push("- Keep the internal audit collector enabled only for local measurement runs. It is structured and low-risk, but it still adds measurable overhead when active.");
  lines.push("");
  return `${lines.join("\n")}\n`;
}


function percentile(values, quantile) {
  if (!values.length) {
    return 0;
  }
  const ordered = [...values].sort((left, right) => left - right);
  const index = Math.max(0, Math.min(ordered.length - 1, Math.round((ordered.length - 1) * quantile)));
  return ordered[index];
}


function average(values) {
  if (!values.length) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}


function round(value) {
  return Math.round(value * 100) / 100;
}


function configTickerPlaceholder() {
  return "__CONFIG_TICKER__";
}


function materializeFetchOptions(options, config) {
  if (!options) {
    return undefined;
  }

  const materialized = { ...options };
  if (typeof materialized.body === "string") {
    materialized.body = materialized.body.replaceAll(`"${configTickerPlaceholder()}"`, `"${config.ticker}"`);
  }
  return materialized;
}


main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
  process.exitCode = 1;
});
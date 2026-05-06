import type {
  ResearchWorkspaceDeleteResponse,
  ResearchWorkspaceImportLocalRequest,
  ResearchWorkspacePayload,
  ResearchWorkspaceUpsertRequest,
  WatchlistCalendarResponse,
  WatchlistSummaryResponse,
} from "@/lib/types";
import { fetchJson } from "./client";

export function getWatchlistSummary(tickers: string[]): Promise<WatchlistSummaryResponse> {
  return fetchJson("/watchlist/summary", {
    method: "POST",
    body: JSON.stringify({ tickers }),
  });
}

export function getWatchlistCalendar(tickers: string[]): Promise<WatchlistCalendarResponse> {
  const params = new URLSearchParams();
  for (const ticker of tickers) {
    params.append("tickers", ticker);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/watchlist/calendar${suffix}`);
}

export function getResearchWorkspace(workspaceKey?: string): Promise<ResearchWorkspacePayload> {
  const params = new URLSearchParams();
  if (workspaceKey?.trim()) {
    params.set("workspace_key", workspaceKey.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/research-workspace${suffix}`);
}

export function saveResearchWorkspace(
  payload: ResearchWorkspaceUpsertRequest,
  options?: { workspaceKey?: string }
): Promise<ResearchWorkspacePayload> {
  const params = new URLSearchParams();
  if (options?.workspaceKey?.trim()) {
    params.set("workspace_key", options.workspaceKey.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/research-workspace/save${suffix}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteResearchWorkspace(workspaceKey?: string): Promise<ResearchWorkspaceDeleteResponse> {
  const params = new URLSearchParams();
  if (workspaceKey?.trim()) {
    params.set("workspace_key", workspaceKey.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/research-workspace/delete${suffix}`, {
    method: "POST",
  });
}

export function importLocalResearchWorkspace(
  payload: ResearchWorkspaceImportLocalRequest,
  options?: { workspaceKey?: string }
): Promise<ResearchWorkspacePayload> {
  const params = new URLSearchParams();
  if (options?.workspaceKey?.trim()) {
    params.set("workspace_key", options.workspaceKey.trim());
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/research-workspace/import-local${suffix}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

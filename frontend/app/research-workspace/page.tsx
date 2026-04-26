"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Panel } from "@/components/ui/panel";
import { useLocalUserData } from "@/hooks/use-local-user-data";
import {
  deleteResearchWorkspace,
  getResearchWorkspace,
  importLocalResearchWorkspace,
  saveResearchWorkspace,
} from "@/lib/api";
import { showAppToast } from "@/lib/app-toast";
import type {
  ResearchWorkspaceCompareBasketPayload,
  ResearchWorkspacePayload,
  ResearchWorkspaceUpsertRequest,
} from "@/lib/types";

function emptyWorkspace(workspaceKey: string): ResearchWorkspacePayload {
  return {
    workspace_key: workspaceKey,
    saved_companies: [],
    notes: [],
    pinned_metrics: [],
    pinned_charts: [],
    compare_baskets: [],
    memo_draft: null,
    updated_at: new Date(0).toISOString(),
  };
}

export default function ResearchWorkspacePage() {
  const { exportData, importData } = useLocalUserData();
  const [workspaceKey, setWorkspaceKey] = useState("default");
  const [workspace, setWorkspace] = useState<ResearchWorkspacePayload>(emptyWorkspace("default"));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedTicker, setSavedTicker] = useState("");
  const [noteTicker, setNoteTicker] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [metricKey, setMetricKey] = useState("");
  const [chartKey, setChartKey] = useState("");
  const [basketName, setBasketName] = useState("");
  const [basketTickers, setBasketTickers] = useState("");
  const [memoDraft, setMemoDraft] = useState("");

  const loadWorkspace = useCallback(async () => {
    const normalizedWorkspaceKey = workspaceKey.trim() || "default";
    try {
      setLoading(true);
      const response = await getResearchWorkspace(normalizedWorkspaceKey);
      setWorkspace(response);
      setMemoDraft(response.memo_draft ?? "");
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to load workspace.", tone: "danger" });
    } finally {
      setLoading(false);
    }
  }, [workspaceKey]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const savePayload = useMemo<ResearchWorkspaceUpsertRequest>(
    () => ({
      saved_companies: workspace.saved_companies,
      notes: workspace.notes,
      pinned_metrics: workspace.pinned_metrics,
      pinned_charts: workspace.pinned_charts,
      compare_baskets: workspace.compare_baskets,
      memo_draft: memoDraft.trim() ? memoDraft : null,
    }),
    [memoDraft, workspace]
  );

  async function persistWorkspace() {
    const normalizedWorkspaceKey = workspaceKey.trim() || "default";
    try {
      setSaving(true);
      const response = await saveResearchWorkspace(savePayload, { workspaceKey: normalizedWorkspaceKey });
      setWorkspace(response);
      setMemoDraft(response.memo_draft ?? "");
      showAppToast({ message: `Workspace ${response.workspace_key} saved.`, tone: "info" });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to save workspace.", tone: "danger" });
    } finally {
      setSaving(false);
    }
  }

  async function clearWorkspaceOnServer() {
    const normalizedWorkspaceKey = workspaceKey.trim() || "default";
    try {
      setSaving(true);
      await deleteResearchWorkspace(normalizedWorkspaceKey);
      const cleared = emptyWorkspace(normalizedWorkspaceKey);
      setWorkspace(cleared);
      setMemoDraft("");
      showAppToast({ message: `Workspace ${normalizedWorkspaceKey} cleared on server.`, tone: "info" });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to clear workspace.", tone: "danger" });
    } finally {
      setSaving(false);
    }
  }

  async function importLocalToServer(mode: "merge" | "replace") {
    const normalizedWorkspaceKey = workspaceKey.trim() || "default";
    try {
      setSaving(true);
      const localData = exportData();
      const response = await importLocalResearchWorkspace(
        {
          watchlist: localData.watchlist,
          notes: localData.notes,
          mode,
        },
        { workspaceKey: normalizedWorkspaceKey }
      );
      setWorkspace(response);
      setMemoDraft(response.memo_draft ?? "");
      showAppToast({ message: `Imported local data to ${response.workspace_key} (${mode}).`, tone: "info" });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to import local data.", tone: "danger" });
    } finally {
      setSaving(false);
    }
  }

  function applyServerToLocal() {
    const payload = {
      watchlist: workspace.saved_companies.map((item) => ({
        ticker: item.ticker,
        name: item.name,
        sector: item.sector,
        savedAt: item.saved_at,
      })),
      notes: Object.fromEntries(
        workspace.notes.map((note) => [
          note.ticker,
          {
            ticker: note.ticker,
            name: note.name,
            sector: note.sector,
            note: note.note,
            updatedAt: note.updated_at,
          },
        ])
      ),
      monitoring: {},
      savedWatchlistViews: [],
    };
    importData(JSON.stringify(payload), { mode: "merge" });
    showAppToast({ message: "Server workspace data merged into local browser data.", tone: "info" });
  }

  function addSavedCompany() {
    const ticker = savedTicker.trim().toUpperCase();
    if (!ticker) {
      return;
    }
    const now = new Date().toISOString();
    const next = workspace.saved_companies.filter((item) => item.ticker !== ticker);
    next.unshift({ ticker, name: null, sector: null, saved_at: now, updated_at: now });
    setWorkspace((current) => ({ ...current, saved_companies: next }));
    setSavedTicker("");
  }

  function addOrUpdateNote() {
    const ticker = noteTicker.trim().toUpperCase();
    const body = noteBody.trim();
    if (!ticker || !body) {
      return;
    }
    const now = new Date().toISOString();
    const next = workspace.notes.filter((item) => item.ticker !== ticker);
    next.unshift({ ticker, name: null, sector: null, note: body, updated_at: now });
    setWorkspace((current) => ({ ...current, notes: next }));
    setNoteTicker("");
    setNoteBody("");
  }

  function addPinnedMetric() {
    const key = metricKey.trim();
    if (!key) {
      return;
    }
    const now = new Date().toISOString();
    const next = workspace.pinned_metrics.filter((item) => item.metric_key !== key);
    next.unshift({ metric_key: key, label: null, updated_at: now });
    setWorkspace((current) => ({ ...current, pinned_metrics: next }));
    setMetricKey("");
  }

  function addPinnedChart() {
    const key = chartKey.trim();
    if (!key) {
      return;
    }
    const now = new Date().toISOString();
    const next = workspace.pinned_charts.filter((item) => item.chart_key !== key);
    next.unshift({ chart_key: key, label: null, updated_at: now });
    setWorkspace((current) => ({ ...current, pinned_charts: next }));
    setChartKey("");
  }

  function addCompareBasket() {
    const name = basketName.trim();
    if (!name) {
      return;
    }
    const tickers = basketTickers
      .split(",")
      .map((item) => item.trim().toUpperCase())
      .filter(Boolean);
    const now = new Date().toISOString();
    const basket: ResearchWorkspaceCompareBasketPayload = {
      basket_id: `${name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${Date.now()}`,
      name,
      tickers: [...new Set(tickers)],
      updated_at: now,
    };
    setWorkspace((current) => ({ ...current, compare_baskets: [basket, ...current.compare_baskets] }));
    setBasketName("");
    setBasketTickers("");
  }

  return (
    <div className="watchlist-page-grid">
      <Panel title="Research Workspace" subtitle="Server-side workspace for saved companies, notes, pinned metrics/charts, compare baskets, and memo drafts." variant="subtle">
        <div className="watchlist-summary-strip workspace-toolbar">
          <label className="pill workspace-key-pill">
            Workspace key
            <input value={workspaceKey} onChange={(event) => setWorkspaceKey(event.target.value)} className="workspace-key-input workspace-key-input-wide" />
          </label>
          <button type="button" className="ticker-button" onClick={() => void loadWorkspace()} disabled={loading || saving}>Load</button>
          <button type="button" className="ticker-button" onClick={() => void persistWorkspace()} disabled={saving}>Save</button>
          <button type="button" className="ticker-button" onClick={() => void clearWorkspaceOnServer()} disabled={saving}>Clear Server</button>
          <button type="button" className="ticker-button" onClick={() => void importLocalToServer("merge")} disabled={saving}>Import Local (Merge)</button>
          <button type="button" className="ticker-button" onClick={() => void importLocalToServer("replace")} disabled={saving}>Import Local (Replace)</button>
          <button type="button" className="ticker-button" onClick={applyServerToLocal}>Apply Server To Local</button>
        </div>

        <div className="saved-companies-summary">
          <span className="pill">Saved companies: {workspace.saved_companies.length}</span>
          <span className="pill">Notes: {workspace.notes.length}</span>
          <span className="pill">Pinned metrics: {workspace.pinned_metrics.length}</span>
          <span className="pill">Pinned charts: {workspace.pinned_charts.length}</span>
          <span className="pill">Compare baskets: {workspace.compare_baskets.length}</span>
          <span className="pill">Updated: {workspace.updated_at}</span>
        </div>

        <div className="saved-companies-transfer-actions workspace-row-spaced">
          <input value={savedTicker} onChange={(event) => setSavedTicker(event.target.value)} placeholder="Add saved ticker (AAPL)" />
          <button type="button" className="ticker-button" onClick={addSavedCompany}>Add Saved Company</button>
        </div>

        <div className="saved-companies-transfer-actions workspace-row-spaced">
          <input value={noteTicker} onChange={(event) => setNoteTicker(event.target.value)} placeholder="Note ticker" />
          <input value={noteBody} onChange={(event) => setNoteBody(event.target.value)} placeholder="Research note" className="workspace-input-wide" />
          <button type="button" className="ticker-button" onClick={addOrUpdateNote}>Upsert Note</button>
        </div>

        <div className="saved-companies-transfer-actions workspace-row-spaced">
          <input value={metricKey} onChange={(event) => setMetricKey(event.target.value)} placeholder="Pinned metric key" />
          <button type="button" className="ticker-button" onClick={addPinnedMetric}>Pin Metric</button>
          <input value={chartKey} onChange={(event) => setChartKey(event.target.value)} placeholder="Pinned chart key" />
          <button type="button" className="ticker-button" onClick={addPinnedChart}>Pin Chart</button>
        </div>

        <div className="saved-companies-transfer-actions workspace-row-spaced">
          <input value={basketName} onChange={(event) => setBasketName(event.target.value)} placeholder="Basket name" />
          <input value={basketTickers} onChange={(event) => setBasketTickers(event.target.value)} placeholder="Basket tickers (AAPL,MSFT,NVDA)" className="workspace-input-wide" />
          <button type="button" className="ticker-button" onClick={addCompareBasket}>Add Basket</button>
        </div>

        <div className="workspace-row-spaced">
          <textarea
            value={memoDraft}
            onChange={(event) => setMemoDraft(event.target.value)}
            placeholder="Memo draft for your current research thesis..."
            className="workspace-memo"
          />
        </div>
      </Panel>
    </div>
  );
}

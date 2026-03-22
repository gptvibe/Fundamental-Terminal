"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { useRouter } from "next/navigation";

import { useLocalUserData } from "@/hooks/use-local-user-data";
import { showAppToast } from "@/lib/app-toast";
import { formatDate } from "@/lib/format";

export function HomeSavedCompaniesPanel() {
  const router = useRouter();
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importMode, setImportMode] = useState<"merge" | "replace">("merge");
  const { savedCompanies, watchlistCount, noteCount, removeFromWatchlist, clearNote, exportData, importData, clearAll } = useLocalUserData();

  function handleExport() {
    try {
      const payload = exportData();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const timestamp = new Date().toISOString().replace(/[:]/g, "-");
      anchor.download = `fundamental-terminal-local-user-data-${timestamp}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      showAppToast({ message: "Saved companies exported as JSON.", tone: "info" });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to export saved companies.", tone: "danger" });
    }
  }

  async function handleImport(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    try {
      const text = await file.text();
      const imported = importData(text, { mode: importMode });
      showAppToast({
        message: `${importMode === "merge" ? "Merged" : "Replaced with"} ${imported.watchlist.length.toLocaleString()} watchlist items and ${Object.keys(imported.notes).length.toLocaleString()} notes.`,
        tone: "info"
      });
    } catch (error) {
      showAppToast({ message: error instanceof Error ? error.message : "Unable to import JSON file.", tone: "danger" });
    } finally {
      event.target.value = "";
    }
  }

  function handleClearAll() {
    const confirmed = window.confirm("Clear all saved companies and notes from this browser? This cannot be undone unless you exported a backup JSON.");
    if (!confirmed) {
      return;
    }
    clearAll();
    showAppToast({ message: "Cleared all saved companies and notes from this browser.", tone: "info" });
  }

  if (!savedCompanies.length) {
    return (
      <div className="saved-companies-empty">
        <div className="grid-empty-kicker">Saved on this device</div>
        <div className="grid-empty-title">Your list is empty for now</div>
        <div className="grid-empty-copy">
          Open any company page, then use <span className="neon-green">Save to My Watchlist</span> or write a quick note. Data stays only in this browser unless you export it as JSON.
        </div>
        <div className="saved-companies-transfer-actions">
          <button type="button" className="ticker-button" onClick={handleExport}>Export JSON</button>
          <button type="button" className="ticker-button" onClick={() => importInputRef.current?.click()}>Import JSON</button>
        </div>
        <div className="saved-companies-summary" style={{ marginTop: 12 }}>
          <span className="pill">Import mode: merge (default)</span>
        </div>
        <input
          ref={importInputRef}
          type="file"
          accept="application/json,.json"
          onChange={handleImport}
          style={{ display: "none" }}
          aria-label="Import saved companies JSON"
        />
      </div>
    );
  }

  return (
    <div className="saved-companies-shell">
      <div className="device-panel-privacy">Stored only on this browser on this device. Export JSON to back it up or move it.</div>

      <div className="saved-companies-summary">
        <span className="pill">{savedCompanies.length} companies</span>
        <span className="pill">{watchlistCount} watchlist saves</span>
        <span className="pill">{noteCount} private notes</span>
      </div>

      <div className="saved-companies-transfer-actions">
        <button type="button" className="ticker-button" onClick={handleExport}>Export JSON</button>
        <button type="button" className="ticker-button" onClick={() => importInputRef.current?.click()}>Import JSON</button>
        <button type="button" className="ticker-button" onClick={handleClearAll}>Clear All</button>
      </div>

      <div className="saved-companies-summary">
        <span className="pill">Import behavior</span>
        <label className="pill" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input
            type="radio"
            name="import-mode"
            checked={importMode === "merge"}
            onChange={() => setImportMode("merge")}
          />
          Merge with existing
        </label>
        <label className="pill" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input
            type="radio"
            name="import-mode"
            checked={importMode === "replace"}
            onChange={() => setImportMode("replace")}
          />
          Replace everything
        </label>
      </div>

      <input
        ref={importInputRef}
        type="file"
        accept="application/json,.json"
        onChange={handleImport}
        style={{ display: "none" }}
        aria-label="Import saved companies JSON"
      />

      <div className="saved-companies-list">
        {savedCompanies.map((item) => (
          <article key={item.ticker} className="saved-company-card">
            <div className="saved-company-card-header">
              <div className="saved-company-card-headline">
                <div className="saved-company-card-ticker">{item.ticker}</div>
                <div className="saved-company-card-name">{item.name ?? "Saved company"}</div>
              </div>
              <div className="saved-company-card-pills">
                {item.isInWatchlist ? <span className="pill device-pill-saved">Watchlist</span> : null}
                {item.hasNote ? <span className="pill device-pill-noted">Note</span> : null}
                {item.sector ? <span className="pill">{item.sector}</span> : null}
              </div>
            </div>

            <div className="saved-company-card-meta">
              {item.savedAt ? <span>Saved {formatDate(item.savedAt)}</span> : null}
              {item.noteUpdatedAt ? <span>Note updated {formatDate(item.noteUpdatedAt)}</span> : null}
            </div>

            <div className={`saved-company-card-note${item.note ? " has-note" : ""}`}>
              {item.note ?? "No note yet. Add one from the company page so your future self remembers the setup."}
            </div>

            <div className="saved-company-card-actions">
              <button type="button" className="ticker-button" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}`)}>
                Open Workspace
              </button>
              <button type="button" className="ticker-button" onClick={() => router.push(`/company/${encodeURIComponent(item.ticker)}/models`)}>
                Models
              </button>
            </div>

            <div className="saved-company-card-secondary-actions">
              {item.isInWatchlist ? (
                <button
                  type="button"
                  className="device-inline-action"
                  onClick={() => {
                    removeFromWatchlist(item.ticker);
                    showAppToast({ message: `${item.ticker} was removed from your watchlist on this device.`, tone: "info" });
                  }}
                >
                  Remove from watchlist
                </button>
              ) : null}

              {item.hasNote ? (
                <button
                  type="button"
                  className="device-inline-action"
                  onClick={() => {
                    clearNote(item.ticker);
                    showAppToast({ message: `Your note for ${item.ticker} was cleared from this device.`, tone: "info" });
                  }}
                >
                  Clear note
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

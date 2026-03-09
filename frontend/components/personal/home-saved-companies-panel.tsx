"use client";

import { useRouter } from "next/navigation";

import { useLocalUserData } from "@/hooks/use-local-user-data";
import { showAppToast } from "@/lib/app-toast";
import { formatDate } from "@/lib/format";

export function HomeSavedCompaniesPanel() {
  const router = useRouter();
  const { savedCompanies, watchlistCount, noteCount, removeFromWatchlist, clearNote } = useLocalUserData();

  if (!savedCompanies.length) {
    return (
      <div className="saved-companies-empty">
        <div className="grid-empty-kicker">Saved on this device</div>
        <div className="grid-empty-title">Your list is empty for now</div>
        <div className="grid-empty-copy">
          Open any company page, then use <span className="neon-green">Save to My Watchlist</span> or write a quick note. Everything stays on this browser and does not need an account.
        </div>
      </div>
    );
  }

  return (
    <div className="saved-companies-shell">
      <div className="device-panel-privacy">Stored only on this browser on this device</div>

      <div className="saved-companies-summary">
        <span className="pill">{savedCompanies.length} companies</span>
        <span className="pill">{watchlistCount} watchlist saves</span>
        <span className="pill">{noteCount} private notes</span>
      </div>

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

"use client";

import { useEffect, useMemo, useState } from "react";

import { useLocalUserData } from "@/hooks/use-local-user-data";
import { showAppToast } from "@/lib/app-toast";
import type { LocalCompanySnapshot } from "@/lib/local-user-data";

interface CompanyDevicePanelProps {
  ticker: string;
  companyName?: string | null;
  sector?: string | null;
}

const NOTE_AUTOSAVE_DELAY_MS = 450;

export function CompanyDevicePanel({ ticker, companyName = null, sector = null }: CompanyDevicePanelProps) {
  const normalizedTicker = ticker.trim().toUpperCase();
  const snapshot = useMemo<LocalCompanySnapshot>(
    () => ({
      ticker: normalizedTicker,
      name: companyName,
      sector
    }),
    [companyName, normalizedTicker, sector]
  );
  const { isSaved, getNote, toggleWatchlist, clearNote, saveNote, syncMetadata } = useLocalUserData();
  const noteEntry = getNote(normalizedTicker);
  const storedNote = noteEntry?.note ?? "";
  const [draft, setDraft] = useState(storedNote);

  useEffect(() => {
    setDraft(storedNote);
  }, [storedNote, normalizedTicker]);

  useEffect(() => {
    syncMetadata(snapshot);
  }, [snapshot, syncMetadata]);

  useEffect(() => {
    if (draft === storedNote) {
      return;
    }

    const timer = window.setTimeout(() => {
      saveNote(snapshot, draft);
    }, NOTE_AUTOSAVE_DELAY_MS);

    return () => window.clearTimeout(timer);
  }, [draft, saveNote, snapshot, storedNote]);

  const saved = isSaved(normalizedTicker);
  const hasNote = Boolean(storedNote.trim());
  const noteStatus = draft !== storedNote ? "Saving locally..." : hasNote ? `Saved on this device ${formatDateTime(noteEntry?.updatedAt ?? null)}` : "No note yet";

  function handleWatchlistToggle() {
    const nowSaved = toggleWatchlist(snapshot);
    showAppToast({
      message: nowSaved
        ? `${normalizedTicker} is now in your watchlist on this device.`
        : `${normalizedTicker} was removed from your watchlist on this device.`,
      tone: "info"
    });
  }

  function handleClearNote() {
    setDraft("");
    clearNote(normalizedTicker);
    showAppToast({ message: `Your note for ${normalizedTicker} was cleared from this device.`, tone: "info" });
  }

  return (
    <div className="device-panel-shell">
      <div className="device-panel-badges">
        <span className={`pill ${saved ? "device-pill-saved" : ""}`}>{saved ? "In watchlist" : "Not in watchlist"}</span>
        <span className={`pill ${hasNote ? "device-pill-noted" : ""}`}>{hasNote ? "Private note saved" : "No note saved"}</span>
      </div>

      <div className="device-panel-copy">
        <div className="device-panel-title">Keep your own shortlist here</div>
        <div className="device-panel-subtitle">No sign-in needed. Your watchlist and notes are saved only in this browser on this device.</div>
        <div className="device-panel-privacy">Browser-only storage: use Export JSON on the home page to back up or move this data.</div>
      </div>

      <button
        type="button"
        className={`ticker-button device-panel-watchlist-button${saved ? " is-saved" : ""}`}
        onClick={handleWatchlistToggle}
      >
        {saved ? "Saved to My Watchlist" : "Save to My Watchlist"}
      </button>

      <div className="device-panel-note-shell">
        <label htmlFor={`device-note-${normalizedTicker}`} className="device-panel-note-label">
          My note for future me
        </label>
        <textarea
          id={`device-note-${normalizedTicker}`}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="device-panel-textarea"
          rows={6}
          placeholder="Write a simple note to yourself: why this company matters, what price would make it interesting, or what risk you want to revisit later."
        />
        <div className="device-panel-note-footer">
          <span className="sparkline-note">{noteStatus}</span>
          <button
            type="button"
            className="device-panel-clear-button"
            onClick={handleClearNote}
            disabled={!draft.trim() && !storedNote.trim()}
          >
            Clear note
          </button>
        </div>
      </div>
    </div>
  );
}

function formatDateTime(value: string | null) {
  if (!value) {
    return "";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "numeric",
    minute: "2-digit"
  }).format(new Date(value));
}

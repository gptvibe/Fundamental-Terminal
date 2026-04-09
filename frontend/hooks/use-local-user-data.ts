"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearAllLocalUserData,
  clearCompanyNote,
  deleteWatchlistSavedView,
  exportLocalUserData,
  importLocalUserData,
  readLocalUserData,
  removeWatchlistCompany,
  saveCompanyNote,
  saveWatchlistMonitoringEntry,
  saveWatchlistSavedView,
  subscribeLocalUserData,
  syncLocalCompanyMetadata,
  toggleWatchlistCompany,
  type LocalCompanySnapshot,
  type LocalCompanyNote,
  type LocalUserData,
  type LocalImportMode,
  type LocalWatchlistItem
} from "@/lib/local-user-data";
import type { LocalWatchlistMonitoringEntry, LocalWatchlistSavedView, WatchlistSavedViewCriteria } from "@/lib/watchlist-monitoring";

export interface LocalSavedCompany {
  ticker: string;
  name: string | null;
  sector: string | null;
  savedAt: string | null;
  note: string | null;
  noteUpdatedAt: string | null;
  isInWatchlist: boolean;
  hasNote: boolean;
  activityAt: string;
}

interface UseLocalUserDataResult {
  watchlist: LocalWatchlistItem[];
  notesByTicker: Record<string, LocalCompanyNote>;
  monitoringByTicker: Record<string, LocalWatchlistMonitoringEntry>;
  savedWatchlistViews: LocalWatchlistSavedView[];
  savedCompanies: LocalSavedCompany[];
  watchlistCount: number;
  noteCount: number;
  savedCompanyCount: number;
  isSaved: (ticker: string) => boolean;
  getNote: (ticker: string) => LocalCompanyNote | null;
  toggleWatchlist: (snapshot: LocalCompanySnapshot) => boolean;
  removeFromWatchlist: (ticker: string) => void;
  saveNote: (snapshot: LocalCompanySnapshot, note: string) => void;
  clearNote: (ticker: string) => void;
  saveMonitoringEntry: (entry: LocalWatchlistMonitoringEntry) => void;
  saveWatchlistView: (view: { id?: string; name: string; criteria: WatchlistSavedViewCriteria }) => void;
  deleteWatchlistView: (id: string) => void;
  exportData: () => LocalUserData;
  importData: (rawJson: string, options?: { mode?: LocalImportMode }) => LocalUserData;
  clearAll: () => void;
  syncMetadata: (snapshot: LocalCompanySnapshot) => void;
}

const EMPTY_DATA: LocalUserData = {
  watchlist: [],
  notes: {},
  monitoring: {},
  savedWatchlistViews: [],
};

export function useLocalUserData(): UseLocalUserDataResult {
  const [data, setData] = useState<LocalUserData>(EMPTY_DATA);

  useEffect(() => {
    setData(readLocalUserData());
    return subscribeLocalUserData(() => {
      setData(readLocalUserData());
    });
  }, []);

  const watchlist = data.watchlist;
  const notesByTicker = data.notes;
  const monitoringByTicker = data.monitoring;
  const savedWatchlistViews = data.savedWatchlistViews;

  const watchlistMap = useMemo(
    () => new Map(watchlist.map((item) => [item.ticker, item])),
    [watchlist]
  );

  const savedCompanies = useMemo<LocalSavedCompany[]>(() => {
    const allTickers = new Set<string>([...watchlistMap.keys(), ...Object.keys(notesByTicker)]);
    return [...allTickers]
      .map((ticker) => {
        const watchlistItem = watchlistMap.get(ticker) ?? null;
        const note = notesByTicker[ticker] ?? null;
        return {
          ticker,
          name: watchlistItem?.name ?? note?.name ?? null,
          sector: watchlistItem?.sector ?? note?.sector ?? null,
          savedAt: watchlistItem?.savedAt ?? null,
          note: note?.note ?? null,
          noteUpdatedAt: note?.updatedAt ?? null,
          isInWatchlist: Boolean(watchlistItem),
          hasNote: Boolean(note?.note),
          activityAt: note?.updatedAt ?? watchlistItem?.savedAt ?? new Date(0).toISOString()
        };
      })
      .sort((left, right) => right.activityAt.localeCompare(left.activityAt));
  }, [notesByTicker, watchlistMap]);

  const isSaved = useCallback(
    (ticker: string) => watchlistMap.has(ticker.trim().toUpperCase()),
    [watchlistMap]
  );

  const getNote = useCallback(
    (ticker: string) => notesByTicker[ticker.trim().toUpperCase()] ?? null,
    [notesByTicker]
  );

  const toggleWatchlist = useCallback((snapshot: LocalCompanySnapshot) => toggleWatchlistCompany(snapshot).saved, []);
  const removeFromWatchlist = useCallback((ticker: string) => {
    removeWatchlistCompany(ticker);
  }, []);
  const saveNote = useCallback((snapshot: LocalCompanySnapshot, note: string) => {
    saveCompanyNote(snapshot, note);
  }, []);
  const clearNote = useCallback((ticker: string) => {
    clearCompanyNote(ticker);
  }, []);
  const saveMonitoringEntry = useCallback((entry: LocalWatchlistMonitoringEntry) => {
    saveWatchlistMonitoringEntry(entry);
  }, []);
  const saveWatchlistView = useCallback((view: { id?: string; name: string; criteria: WatchlistSavedViewCriteria }) => {
    saveWatchlistSavedView(view);
  }, []);
  const deleteWatchlistView = useCallback((id: string) => {
    deleteWatchlistSavedView(id);
  }, []);
  const exportData = useCallback(() => exportLocalUserData(), []);
  const importData = useCallback((rawJson: string, options?: { mode?: LocalImportMode }) => importLocalUserData(rawJson, options), []);
  const clearAll = useCallback(() => {
    clearAllLocalUserData();
  }, []);
  const syncMetadata = useCallback((snapshot: LocalCompanySnapshot) => {
    syncLocalCompanyMetadata(snapshot);
  }, []);

  return {
    watchlist,
    notesByTicker,
    monitoringByTicker,
    savedWatchlistViews,
    savedCompanies,
    watchlistCount: watchlist.length,
    noteCount: Object.keys(notesByTicker).length,
    savedCompanyCount: savedCompanies.length,
    isSaved,
    getNote,
    toggleWatchlist,
    removeFromWatchlist,
    saveNote,
    clearNote,
    saveMonitoringEntry,
    saveWatchlistView,
    deleteWatchlistView,
    exportData,
    importData,
    clearAll,
    syncMetadata
  };
}

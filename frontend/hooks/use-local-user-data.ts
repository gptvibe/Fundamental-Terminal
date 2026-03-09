"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  clearCompanyNote,
  readLocalUserData,
  removeWatchlistCompany,
  saveCompanyNote,
  subscribeLocalUserData,
  syncLocalCompanyMetadata,
  toggleWatchlistCompany,
  type LocalCompanySnapshot,
  type LocalCompanyNote,
  type LocalUserData,
  type LocalWatchlistItem
} from "@/lib/local-user-data";

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
  syncMetadata: (snapshot: LocalCompanySnapshot) => void;
}

const EMPTY_DATA: LocalUserData = {
  watchlist: [],
  notes: {}
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
  const syncMetadata = useCallback((snapshot: LocalCompanySnapshot) => {
    syncLocalCompanyMetadata(snapshot);
  }, []);

  return {
    watchlist,
    notesByTicker,
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
    syncMetadata
  };
}

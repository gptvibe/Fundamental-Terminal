"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  addCompareCompanies,
  buildCompareHref,
  clearCompareCompanies,
  readLocalCompareSet,
  removeCompareCompany,
  subscribeLocalCompareSet,
  syncCompareCompanyMetadata,
  toggleCompareCompany,
  type LocalCompareCompany,
  type LocalCompareSnapshot,
} from "@/lib/local-compare-set";

interface UseLocalCompareSetResult {
  compareCompanies: LocalCompareCompany[];
  compareTickers: string[];
  compareHref: string;
  hasTicker: (ticker: string) => boolean;
  addCompanies: (snapshots: LocalCompareSnapshot[]) => LocalCompareCompany[];
  toggleCompany: (snapshot: LocalCompareSnapshot) => boolean;
  removeCompany: (ticker: string) => void;
  clearCompareSet: () => void;
  syncMetadata: (snapshot: LocalCompareSnapshot) => void;
}

export function useLocalCompareSet(): UseLocalCompareSetResult {
  const [compareCompanies, setCompareCompanies] = useState<LocalCompareCompany[]>([]);

  useEffect(() => {
    setCompareCompanies(readLocalCompareSet());
    return subscribeLocalCompareSet(() => {
      setCompareCompanies(readLocalCompareSet());
    });
  }, []);

  const compareTickers = useMemo(() => compareCompanies.map((item) => item.ticker), [compareCompanies]);
  const compareHref = useMemo(() => buildCompareHref(compareTickers), [compareTickers]);

  const hasTicker = useCallback(
    (ticker: string) => compareTickers.includes(ticker.trim().toUpperCase()),
    [compareTickers]
  );
  const addCompanies = useCallback((snapshots: LocalCompareSnapshot[]) => addCompareCompanies(snapshots), []);
  const toggleCompany = useCallback((snapshot: LocalCompareSnapshot) => toggleCompareCompany(snapshot).saved, []);
  const removeCompany = useCallback((ticker: string) => {
    removeCompareCompany(ticker);
  }, []);
  const clearCompareSet = useCallback(() => {
    clearCompareCompanies();
  }, []);
  const syncMetadata = useCallback((snapshot: LocalCompareSnapshot) => {
    syncCompareCompanyMetadata(snapshot);
  }, []);

  return {
    compareCompanies,
    compareTickers,
    compareHref,
    hasTicker,
    addCompanies,
    toggleCompany,
    removeCompany,
    clearCompareSet,
    syncMetadata,
  };
}
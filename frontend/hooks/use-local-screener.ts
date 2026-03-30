"use client";

import { useCallback, useEffect, useState } from "react";

import {
  DEFAULT_LOCAL_SCREENER_DRAFT,
  deleteLocalScreenerPreset,
  readLocalScreenerState,
  resetLocalScreenerDraft,
  saveLocalScreenerDraft,
  saveLocalScreenerPreset,
  subscribeLocalScreener,
  type LocalScreenerDraft,
  type LocalScreenerPreset,
} from "@/lib/local-screener";

interface UseLocalScreenerResult {
  hydrated: boolean;
  draft: LocalScreenerDraft;
  presets: LocalScreenerPreset[];
  presetCount: number;
  updateDraft: (updater: LocalScreenerDraft | ((current: LocalScreenerDraft) => LocalScreenerDraft)) => void;
  resetDraft: () => void;
  savePreset: (name: string) => void;
  deletePreset: (presetId: string) => void;
  applyPreset: (presetId: string) => LocalScreenerDraft | null;
}

export function useLocalScreener(): UseLocalScreenerResult {
  const [hydrated, setHydrated] = useState(false);
  const [draft, setDraft] = useState<LocalScreenerDraft>(DEFAULT_LOCAL_SCREENER_DRAFT);
  const [presets, setPresets] = useState<LocalScreenerPreset[]>([]);

  useEffect(() => {
    function sync() {
      const nextState = readLocalScreenerState();
      setDraft(nextState.draft);
      setPresets(nextState.presets);
      setHydrated(true);
    }

    sync();
    return subscribeLocalScreener(sync);
  }, []);

  const updateDraft = useCallback((updater: LocalScreenerDraft | ((current: LocalScreenerDraft) => LocalScreenerDraft)) => {
    const nextDraft = typeof updater === "function" ? updater(readLocalScreenerState().draft) : updater;
    saveLocalScreenerDraft(nextDraft);
  }, []);

  const resetDraft = useCallback(() => {
    resetLocalScreenerDraft();
  }, []);

  const savePreset = useCallback((name: string) => {
    saveLocalScreenerPreset(name, readLocalScreenerState().draft);
  }, []);

  const deletePreset = useCallback((presetId: string) => {
    deleteLocalScreenerPreset(presetId);
  }, []);

  const applyPreset = useCallback(
    (presetId: string) => {
      const preset = presets.find((item) => item.id === presetId) ?? null;
      if (!preset) {
        return null;
      }

      const nextDraft = {
        ...preset.draft,
        offset: 0,
      };
      saveLocalScreenerDraft(nextDraft);
      return nextDraft;
    },
    [presets]
  );

  return {
    hydrated,
    draft,
    presets,
    presetCount: presets.length,
    updateDraft,
    resetDraft,
    savePreset,
    deletePreset,
    applyPreset,
  };
}
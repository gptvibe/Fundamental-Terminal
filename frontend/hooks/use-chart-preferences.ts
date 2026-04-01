"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ChartCadenceMode, ChartTimeframeMode, ChartType } from "@/lib/chart-capabilities";

export const CHART_PREFERENCES_STORAGE_KEY = "ft-chart-preferences";
const CHART_PREFERENCES_EVENT = "ft:chart-preferences";

type ChartPreferenceRecord = {
  chartType?: ChartType;
  timeframeMode?: ChartTimeframeMode;
  cadenceMode?: ChartCadenceMode;
};

type ChartPreferencesStore = Record<string, ChartPreferenceRecord>;

interface UseChartPreferencesOptions {
  chartFamily: string;
  defaultChartType?: ChartType;
  defaultTimeframeMode?: ChartTimeframeMode;
  defaultCadenceMode?: ChartCadenceMode;
  allowedChartTypes?: readonly ChartType[];
  allowedTimeframeModes?: readonly ChartTimeframeMode[];
  allowedCadenceModes?: readonly ChartCadenceMode[];
}

interface UseChartPreferencesResult {
  chartType?: ChartType;
  timeframeMode?: ChartTimeframeMode;
  cadenceMode?: ChartCadenceMode;
  setChartType: (chartType: ChartType) => void;
  setTimeframeMode: (timeframeMode: ChartTimeframeMode) => void;
  setCadenceMode: (cadenceMode: ChartCadenceMode) => void;
}

export function useChartPreferences(options: UseChartPreferencesOptions): UseChartPreferencesResult {
  const allowedCadenceModesKey = toDependencyKey(options.allowedCadenceModes);
  const allowedChartTypesKey = toDependencyKey(options.allowedChartTypes);
  const allowedTimeframeModesKey = toDependencyKey(options.allowedTimeframeModes);

  const resolvedDefaults = useMemo(
    () => ({
      chartType: resolveAllowedValue(options.defaultChartType, options.allowedChartTypes),
      timeframeMode: resolveAllowedValue(options.defaultTimeframeMode, options.allowedTimeframeModes),
      cadenceMode: resolveAllowedValue(options.defaultCadenceMode, options.allowedCadenceModes),
    }),
    [
      options.defaultCadenceMode,
      options.defaultChartType,
      options.defaultTimeframeMode,
      allowedCadenceModesKey,
      allowedChartTypesKey,
      allowedTimeframeModesKey,
    ]
  );

  const [preferences, setPreferences] = useState<ChartPreferenceRecord>(() =>
    resolveChartPreferenceRecord(readChartPreferencesStore()[options.chartFamily], options, resolvedDefaults)
  );

  useEffect(() => {
    setPreferences(resolveChartPreferenceRecord(readChartPreferencesStore()[options.chartFamily], options, resolvedDefaults));

    return subscribeChartPreferencesStore(() => {
      setPreferences(resolveChartPreferenceRecord(readChartPreferencesStore()[options.chartFamily], options, resolvedDefaults));
    });
  }, [
    options.chartFamily,
    options.defaultCadenceMode,
    options.defaultChartType,
    options.defaultTimeframeMode,
    allowedCadenceModesKey,
    allowedChartTypesKey,
    allowedTimeframeModesKey,
    resolvedDefaults,
  ]);

  const setChartType = useCallback(
    (chartType: ChartType) => {
      setPreferencesForFamily(options.chartFamily, { chartType }, options, resolvedDefaults);
    },
    [options.chartFamily, options, resolvedDefaults]
  );

  const setTimeframeMode = useCallback(
    (timeframeMode: ChartTimeframeMode) => {
      setPreferencesForFamily(options.chartFamily, { timeframeMode }, options, resolvedDefaults);
    },
    [options.chartFamily, options, resolvedDefaults]
  );

  const setCadenceMode = useCallback(
    (cadenceMode: ChartCadenceMode) => {
      setPreferencesForFamily(options.chartFamily, { cadenceMode }, options, resolvedDefaults);
    },
    [options.chartFamily, options, resolvedDefaults]
  );

  return {
    chartType: preferences.chartType,
    timeframeMode: preferences.timeframeMode,
    cadenceMode: preferences.cadenceMode,
    setChartType,
    setTimeframeMode,
    setCadenceMode,
  };
}

function setPreferencesForFamily(
  chartFamily: string,
  partialPreferences: Partial<ChartPreferenceRecord>,
  options: UseChartPreferencesOptions,
  resolvedDefaults: ChartPreferenceRecord
) {
  updateChartPreferencesStore((currentStore) => {
    const currentPreferences = currentStore[chartFamily] ?? {};
    return {
      ...currentStore,
      [chartFamily]: resolveChartPreferenceRecord(
        { ...currentPreferences, ...partialPreferences },
        options,
        resolvedDefaults
      ),
    };
  });
}

function resolveChartPreferenceRecord(
  currentPreferences: ChartPreferenceRecord | undefined,
  options: UseChartPreferencesOptions,
  resolvedDefaults: ChartPreferenceRecord
): ChartPreferenceRecord {
  return {
    chartType: resolveAllowedValue(
      currentPreferences?.chartType,
      options.allowedChartTypes,
      resolvedDefaults.chartType
    ),
    timeframeMode: resolveAllowedValue(
      currentPreferences?.timeframeMode,
      options.allowedTimeframeModes,
      resolvedDefaults.timeframeMode
    ),
    cadenceMode: resolveAllowedValue(
      currentPreferences?.cadenceMode,
      options.allowedCadenceModes,
      resolvedDefaults.cadenceMode
    ),
  };
}

function resolveAllowedValue<T extends string>(
  value: T | undefined,
  allowedValues?: readonly T[],
  fallbackValue?: T
): T | undefined {
  if (allowedValues?.length) {
    if (value && allowedValues.includes(value)) {
      return value;
    }
    if (fallbackValue && allowedValues.includes(fallbackValue)) {
      return fallbackValue;
    }
    return allowedValues[0];
  }

  return value ?? fallbackValue;
}

function readChartPreferencesStore(): ChartPreferencesStore {
  if (!canUseStorage()) {
    return {};
  }

  const rawValue = window.localStorage.getItem(CHART_PREFERENCES_STORAGE_KEY);
  if (!rawValue) {
    return {};
  }

  try {
    const parsed = JSON.parse(rawValue);
    return normalizeChartPreferencesStore(parsed);
  } catch {
    window.localStorage.removeItem(CHART_PREFERENCES_STORAGE_KEY);
    return {};
  }
}

function updateChartPreferencesStore(updater: (currentStore: ChartPreferencesStore) => ChartPreferencesStore) {
  const nextStore = normalizeChartPreferencesStore(updater(readChartPreferencesStore()));
  writeChartPreferencesStore(nextStore);
}

function writeChartPreferencesStore(store: ChartPreferencesStore) {
  if (!canUseStorage()) {
    return;
  }

  window.localStorage.setItem(CHART_PREFERENCES_STORAGE_KEY, JSON.stringify(store));
  window.dispatchEvent(new CustomEvent(CHART_PREFERENCES_EVENT, { detail: store }));
}

function subscribeChartPreferencesStore(onChange: () => void): () => void {
  if (!canUseStorage()) {
    return () => undefined;
  }

  function handleStorage(event: StorageEvent) {
    if (event.key === CHART_PREFERENCES_STORAGE_KEY) {
      onChange();
    }
  }

  window.addEventListener(CHART_PREFERENCES_EVENT, onChange as EventListener);
  window.addEventListener("storage", handleStorage);

  return () => {
    window.removeEventListener(CHART_PREFERENCES_EVENT, onChange as EventListener);
    window.removeEventListener("storage", handleStorage);
  };
}

function normalizeChartPreferencesStore(value: unknown): ChartPreferencesStore {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {};
  }

  return Object.entries(value).reduce<ChartPreferencesStore>((result, [chartFamily, rawPreferences]) => {
    if (!chartFamily || !rawPreferences || typeof rawPreferences !== "object" || Array.isArray(rawPreferences)) {
      return result;
    }

    const candidate = rawPreferences as ChartPreferenceRecord;
    result[chartFamily] = {
      chartType: typeof candidate.chartType === "string" ? candidate.chartType : undefined,
      timeframeMode: typeof candidate.timeframeMode === "string" ? candidate.timeframeMode : undefined,
      cadenceMode: typeof candidate.cadenceMode === "string" ? candidate.cadenceMode : undefined,
    };
    return result;
  }, {});
}

function toDependencyKey(values?: readonly string[]): string {
  return values?.join("|") ?? "";
}

function canUseStorage() {
  return typeof window !== "undefined";
}
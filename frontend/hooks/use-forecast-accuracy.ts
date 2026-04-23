"use client";

import { useCallback, useEffect, useState } from "react";

import { getCompanyChartsForecastAccuracy } from "@/lib/api";
import type { CompanyChartsForecastAccuracyResponse } from "@/lib/types";

interface UseForecastAccuracyOptions {
  asOf?: string | null;
  enabled?: boolean;
}

interface UseForecastAccuracyState {
  data: CompanyChartsForecastAccuracyResponse | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

export function useForecastAccuracy(
  ticker: string,
  options: UseForecastAccuracyOptions = {}
): UseForecastAccuracyState {
  const [data, setData] = useState<CompanyChartsForecastAccuracyResponse | null>(null);
  const [loading, setLoading] = useState(Boolean(options.enabled ?? true));
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!(options.enabled ?? true)) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload = await getCompanyChartsForecastAccuracy(ticker, {
        asOf: options.asOf,
        signal,
      });
      setData(payload);
    } catch (nextError) {
      if (isAbortError(nextError)) {
        return;
      }
      setData(null);
      const message =
        nextError instanceof Error
          ? nextError.message
          : "Unable to load forecast accuracy.";
      setError(message || "Unable to load forecast accuracy.");
    } finally {
      setLoading(false);
    }
  }, [options.asOf, options.enabled, ticker]);

  useEffect(() => {
    const controller = new AbortController();

    async function run() {
      if (!(options.enabled ?? true)) {
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const payload = await getCompanyChartsForecastAccuracy(ticker, {
          asOf: options.asOf,
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setData(payload);
        }
      } catch (nextError) {
        if (!isAbortError(nextError) && !controller.signal.aborted) {
          setData(null);
          const message =
            nextError instanceof Error
              ? nextError.message
              : "Unable to load forecast accuracy.";
          setError(message || "Unable to load forecast accuracy.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    void run();

    return () => {
      controller.abort();
    };
  }, [options.asOf, options.enabled, ticker]);

  return {
    data,
    loading,
    error,
    reload: () => load(),
  };
}

function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== "undefined" && error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

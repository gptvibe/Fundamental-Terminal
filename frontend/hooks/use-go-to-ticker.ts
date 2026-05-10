"use client";

import { useCallback } from "react";
import { useRouter } from "next/navigation";

import { useLocalUserData } from "@/hooks/use-local-user-data";
import { recordRecentCompany, type RecentCompanySnapshot } from "@/lib/recent-companies";

export function useGoToTicker() {
  const router = useRouter();
  const { syncMetadata } = useLocalUserData();

  return useCallback(
    (ticker: string, destination: "company" | "models" = "company", snapshot?: RecentCompanySnapshot | null) => {
      const normalizedTicker = ticker.trim().toUpperCase();
      if (!normalizedTicker) {
        return;
      }

      const recentSnapshot: RecentCompanySnapshot = {
        ticker: normalizedTicker,
        name: snapshot?.name ?? null,
        sector: snapshot?.sector ?? snapshot?.market_sector ?? null,
      };

      recordRecentCompany(recentSnapshot);

      if (recentSnapshot.name || recentSnapshot.sector) {
        syncMetadata(recentSnapshot);
      }

      const suffix = destination === "models" ? "/models" : "";
      router.push(`/company/${encodeURIComponent(normalizedTicker)}${suffix}`);
    },
    [router, syncMetadata]
  );
}

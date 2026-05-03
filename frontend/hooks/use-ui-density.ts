"use client";

import { useCallback, useEffect, useState } from "react";

import {
  readUIDensity,
  writeUIDensity,
  type UIDensity,
} from "@/lib/ui-density";

export interface UseUIDensityResult {
  density: UIDensity;
  isBeginnerMode: boolean;
  setDensity: (next: UIDensity) => void;
  toggleDensity: () => void;
}

export const UI_DENSITY_CHANGE_EVENT = "ft:ui-density-change";

export function useUIDensity(): UseUIDensityResult {
  const [density, setDensityState] = useState<UIDensity>(readUIDensity);

  useEffect(() => {
    function onExternalChange(event: Event) {
      const customEvent = event as CustomEvent<{ density: UIDensity }>;
      if (customEvent.detail?.density) {
        setDensityState(customEvent.detail.density);
      }
    }

    window.addEventListener(UI_DENSITY_CHANGE_EVENT, onExternalChange as EventListener);
    return () => window.removeEventListener(UI_DENSITY_CHANGE_EVENT, onExternalChange as EventListener);
  }, []);

  const setDensity = useCallback((next: UIDensity) => {
    writeUIDensity(next);
    setDensityState(next);
    window.dispatchEvent(
      new CustomEvent(UI_DENSITY_CHANGE_EVENT, { detail: { density: next } })
    );
  }, []);

  const toggleDensity = useCallback(() => {
    setDensity(density === "beginner" ? "pro" : "beginner");
  }, [density, setDensity]);

  return {
    density,
    isBeginnerMode: density === "beginner",
    setDensity,
    toggleDensity,
  };
}

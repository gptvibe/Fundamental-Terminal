"use client";

import { useEffect, useRef, useState } from "react";

import {
  BRIEF_SECTION_IDS,
  RESEARCH_BRIEF_SECTION_STORAGE_PREFIX,
} from "../_lib/research-brief-types";
import {
  createDefaultResearchBriefSectionState,
  mergeResearchBriefSectionState,
  persistResearchBriefSectionState,
} from "../_lib/research-brief-utils";

export function useActiveBriefSection(sectionIds: string[]): string {
  const [activeSectionId, setActiveSectionId] = useState(sectionIds[0] ?? "snapshot");

  useEffect(() => {
    const elements = sectionIds
      .map((sectionId) => document.getElementById(sectionId))
      .filter((element): element is HTMLElement => Boolean(element));

    if (!elements.length) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];

        if (visible?.target instanceof HTMLElement) {
          setActiveSectionId(visible.target.id);
        }
      },
      {
        rootMargin: "-28% 0px -56% 0px",
        threshold: [0.05, 0.2, 0.45],
      }
    );

    elements.forEach((element) => observer.observe(element));

    return () => {
      observer.disconnect();
    };
  }, [sectionIds]);

  return activeSectionId;
}

export function useResearchBriefSectionPreferences(ticker: string): {
  expandedSections: Record<string, boolean>;
  toggleSection: (sectionId: string) => void;
} {
  const storageKey = `${RESEARCH_BRIEF_SECTION_STORAGE_PREFIX}:${ticker}`;
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(() =>
    createDefaultResearchBriefSectionState()
  );
  const [hasLoadedPreferences, setHasLoadedPreferences] = useState(false);
  const canPersistPreferencesRef = useRef(true);

  useEffect(() => {
    const defaultState = createDefaultResearchBriefSectionState();

    try {
      const rawState = window.localStorage.getItem(storageKey);

      if (!rawState) {
        setExpandedSections(defaultState);
        setHasLoadedPreferences(true);
        return;
      }

      const parsedState = JSON.parse(rawState) as unknown;
      setExpandedSections(mergeResearchBriefSectionState(defaultState, parsedState, BRIEF_SECTION_IDS));
    } catch {
      setExpandedSections(defaultState);
    } finally {
      setHasLoadedPreferences(true);
    }
  }, [storageKey]);

  useEffect(() => {
    if (!hasLoadedPreferences) {
      return;
    }

    if (!canPersistPreferencesRef.current) {
      return;
    }

    if (!persistResearchBriefSectionState(storageKey, expandedSections, BRIEF_SECTION_IDS)) {
      canPersistPreferencesRef.current = false;
    }
  }, [expandedSections, hasLoadedPreferences, storageKey]);

  function toggleSection(sectionId: string) {
    setExpandedSections((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }));
  }

  return { expandedSections, toggleSection };
}

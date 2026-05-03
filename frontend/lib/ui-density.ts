export type UIDensity = "beginner" | "pro";

export const UI_DENSITY_STORAGE_KEY = "ft-ui-density";
export const UI_DENSITY_DEFAULT: UIDensity = "pro";

export function isValidUIDensity(value: unknown): value is UIDensity {
  return value === "beginner" || value === "pro";
}

export function readUIDensity(): UIDensity {
  if (typeof window === "undefined") {
    return UI_DENSITY_DEFAULT;
  }

  try {
    const stored = window.localStorage.getItem(UI_DENSITY_STORAGE_KEY);
    return isValidUIDensity(stored) ? stored : UI_DENSITY_DEFAULT;
  } catch {
    return UI_DENSITY_DEFAULT;
  }
}

export function writeUIDensity(density: UIDensity): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(UI_DENSITY_STORAGE_KEY, density);
  } catch {
    // ignore storage errors
  }
}

/**
 * In beginner mode, sections that are primarily for advanced/debug inspection
 * start collapsed by default. Returns the list of section IDs that should
 * default to collapsed when density is "beginner".
 */
export const BEGINNER_COLLAPSED_SECTIONS = ["monitor", "data-quality"] as const;

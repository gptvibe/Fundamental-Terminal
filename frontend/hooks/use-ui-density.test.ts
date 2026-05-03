// @vitest-environment jsdom

import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import {
  isValidUIDensity,
  readUIDensity,
  UI_DENSITY_DEFAULT,
  UI_DENSITY_STORAGE_KEY,
  writeUIDensity,
} from "@/lib/ui-density";
import { UI_DENSITY_CHANGE_EVENT, useUIDensity } from "@/hooks/use-ui-density";

describe("ui-density lib", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("validates known density values", () => {
    expect(isValidUIDensity("beginner")).toBe(true);
    expect(isValidUIDensity("pro")).toBe(true);
    expect(isValidUIDensity("expert")).toBe(false);
    expect(isValidUIDensity(null)).toBe(false);
    expect(isValidUIDensity(undefined)).toBe(false);
    expect(isValidUIDensity(42)).toBe(false);
  });

  it("returns the default density when nothing is stored", () => {
    expect(readUIDensity()).toBe(UI_DENSITY_DEFAULT);
  });

  it("returns the stored density when it is valid", () => {
    window.localStorage.setItem(UI_DENSITY_STORAGE_KEY, "beginner");
    expect(readUIDensity()).toBe("beginner");
  });

  it("falls back to default when stored value is invalid", () => {
    window.localStorage.setItem(UI_DENSITY_STORAGE_KEY, "superuser");
    expect(readUIDensity()).toBe(UI_DENSITY_DEFAULT);
  });

  it("persists the density value to localStorage", () => {
    writeUIDensity("beginner");
    expect(window.localStorage.getItem(UI_DENSITY_STORAGE_KEY)).toBe("beginner");

    writeUIDensity("pro");
    expect(window.localStorage.getItem(UI_DENSITY_STORAGE_KEY)).toBe("pro");
  });
});

describe("useUIDensity hook", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("initialises with the stored density value", () => {
    window.localStorage.setItem(UI_DENSITY_STORAGE_KEY, "beginner");
    const { result } = renderHook(() => useUIDensity());
    expect(result.current.density).toBe("beginner");
    expect(result.current.isBeginnerMode).toBe(true);
  });

  it("initialises with the default when nothing is stored", () => {
    const { result } = renderHook(() => useUIDensity());
    expect(result.current.density).toBe(UI_DENSITY_DEFAULT);
  });

  it("setDensity persists the new value and updates state", () => {
    const { result } = renderHook(() => useUIDensity());

    act(() => {
      result.current.setDensity("beginner");
    });

    expect(result.current.density).toBe("beginner");
    expect(result.current.isBeginnerMode).toBe(true);
    expect(window.localStorage.getItem(UI_DENSITY_STORAGE_KEY)).toBe("beginner");
  });

  it("toggleDensity switches between beginner and pro", () => {
    window.localStorage.setItem(UI_DENSITY_STORAGE_KEY, "beginner");
    const { result } = renderHook(() => useUIDensity());

    act(() => {
      result.current.toggleDensity();
    });

    expect(result.current.density).toBe("pro");
    expect(result.current.isBeginnerMode).toBe(false);
    expect(window.localStorage.getItem(UI_DENSITY_STORAGE_KEY)).toBe("pro");

    act(() => {
      result.current.toggleDensity();
    });

    expect(result.current.density).toBe("beginner");
  });

  it("syncs state when another instance emits the change event", () => {
    const { result } = renderHook(() => useUIDensity());

    act(() => {
      window.dispatchEvent(
        new CustomEvent(UI_DENSITY_CHANGE_EVENT, { detail: { density: "beginner" } })
      );
    });

    expect(result.current.density).toBe("beginner");
    expect(result.current.isBeginnerMode).toBe(true);
  });

  it("isBeginnerMode is false when density is pro", () => {
    window.localStorage.setItem(UI_DENSITY_STORAGE_KEY, "pro");
    const { result } = renderHook(() => useUIDensity());
    expect(result.current.isBeginnerMode).toBe(false);
  });
});

describe("density preference persistence across mounts", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("persists the selection between hook unmount and remount", () => {
    const { result, unmount } = renderHook(() => useUIDensity());

    act(() => {
      result.current.setDensity("beginner");
    });

    unmount();

    const { result: result2 } = renderHook(() => useUIDensity());
    expect(result2.current.density).toBe("beginner");
  });

  it("layout is affected: isBeginnerMode changes after toggling", () => {
    const { result } = renderHook(() => useUIDensity());
    expect(result.current.isBeginnerMode).toBe(false);

    act(() => {
      result.current.setDensity("beginner");
    });
    expect(result.current.isBeginnerMode).toBe(true);

    act(() => {
      result.current.setDensity("pro");
    });
    expect(result.current.isBeginnerMode).toBe(false);
  });
});

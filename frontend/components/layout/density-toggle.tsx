"use client";

import { useUIDensity } from "@/hooks/use-ui-density";

export function DensityToggle() {
  const { density, setDensity } = useUIDensity();

  return (
    <div className="app-density-switcher" role="group" aria-label="Layout density">
      <span className="app-tools-label">View</span>
      <button
        type="button"
        className={`app-theme-option${density === "beginner" ? " is-active" : ""}`}
        onClick={() => setDensity("beginner")}
        aria-pressed={density === "beginner"}
        title="Beginner: guided layout with collapsed advanced panels and helpful explanations"
      >
        Simple
      </button>
      <button
        type="button"
        className={`app-theme-option${density === "pro" ? " is-active" : ""}`}
        onClick={() => setDensity("pro")}
        aria-pressed={density === "pro"}
        title="Pro: full dense layout with all research panels visible"
      >
        Detailed
      </button>
    </div>
  );
}

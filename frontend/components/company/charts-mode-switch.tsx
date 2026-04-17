"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type ChartsMode = "outlook" | "studio";

export function ChartsModeSwitch({ activeMode, studioEnabled }: { activeMode: ChartsMode; studioEnabled: boolean }) {
  const pathname = usePathname();

  return (
    <nav className="charts-mode-switch" aria-label="Charts modes">
      <Link
        href={pathname}
        className={`charts-mode-switch-link ${activeMode === "outlook" ? "is-active" : ""}`}
        aria-current={activeMode === "outlook" ? "page" : undefined}
      >
        Growth Outlook
      </Link>
      {studioEnabled ? (
        <Link
          href={`${pathname}?mode=studio`}
          className={`charts-mode-switch-link ${activeMode === "studio" ? "is-active" : ""}`}
          aria-current={activeMode === "studio" ? "page" : undefined}
        >
          Projection Studio
        </Link>
      ) : (
        <span className="charts-mode-switch-link is-disabled" aria-disabled="true">
          Projection Studio
        </span>
      )}
    </nav>
  );
}
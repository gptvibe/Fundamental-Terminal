"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

type ChartsMode = "outlook" | "studio";

export function ChartsModeSwitch({ activeMode, studioEnabled }: { activeMode: ChartsMode; studioEnabled: boolean }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const outlookParams = new URLSearchParams(searchParams?.toString() ?? "");
  const studioParams = new URLSearchParams(searchParams?.toString() ?? "");

  outlookParams.delete("mode");
  studioParams.set("mode", "studio");

  const outlookHref = buildHref(pathname, outlookParams);
  const studioHref = buildHref(pathname, studioParams);

  return (
    <nav className="charts-mode-switch" aria-label="Charts modes">
      <Link
        href={outlookHref}
        className={`charts-mode-switch-link ${activeMode === "outlook" ? "is-active" : ""}`}
        aria-current={activeMode === "outlook" ? "page" : undefined}
      >
        Growth Outlook
      </Link>
      {studioEnabled ? (
        <Link
          href={studioHref}
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

function buildHref(pathname: string, params: URLSearchParams): string {
  const query = params.toString();
  if (!query) {
    return pathname;
  }
  return `${pathname}?${query}`;
}
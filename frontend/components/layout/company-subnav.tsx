"use client";

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";

interface CompanySubnavProps {
  ticker: string;
}

const tabs: Array<{ key: string; label: string; suffix: string; exact?: boolean; group: "core" | "research" }> = [
  { key: "overview", label: "Overview", suffix: "", exact: true, group: "core" },
  { key: "financials", label: "Financials", suffix: "/financials", group: "core" },
  { key: "models", label: "Models", suffix: "/models", group: "core" },
  { key: "peers", label: "Peers", suffix: "/peers", group: "core" },
  { key: "earnings", label: "Earnings", suffix: "/earnings", group: "core" },
  { key: "filings", label: "Filings", suffix: "/filings", group: "research" },
  { key: "events", label: "Events", suffix: "/events", group: "research" },
  { key: "capital-markets", label: "Capital Markets", suffix: "/capital-markets", group: "research" },
  { key: "sec-feed", label: "SEC Feed", suffix: "/sec-feed", group: "research" },
  { key: "governance", label: "Governance", suffix: "/governance", group: "research" },
  { key: "ownership-changes", label: "Stake Changes", suffix: "/ownership-changes", group: "research" },
  { key: "ownership", label: "Ownership", suffix: "/ownership", group: "research" },
  { key: "insiders", label: "Insiders", suffix: "/insiders", group: "research" }
];

export function CompanySubnav({ ticker }: CompanySubnavProps) {
  const pathname = usePathname();
  const baseHref = `/company/${encodeURIComponent(ticker)}`;

  function focusAt(currentTarget: HTMLAnchorElement, targetIndex: number) {
    const links = Array.from(currentTarget.closest("nav")?.querySelectorAll<HTMLAnchorElement>("a.company-subnav-link") ?? []);
    links[targetIndex]?.focus();
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLAnchorElement>) {
    const links = Array.from(event.currentTarget.closest("nav")?.querySelectorAll<HTMLAnchorElement>("a.company-subnav-link") ?? []);
    const currentIndex = links.indexOf(event.currentTarget);
    if (currentIndex === -1) {
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusAt(event.currentTarget, (currentIndex + 1) % links.length);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusAt(event.currentTarget, (currentIndex - 1 + links.length) % links.length);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      focusAt(event.currentTarget, 0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      focusAt(event.currentTarget, links.length - 1);
    }
  }

  return (
    <div className="company-subnav">
      <div className="company-subnav-meta">
        <span className="company-subnav-kicker">{ticker}</span>
        <span className="company-subnav-copy">Company workspace</span>
      </div>
      <nav className="company-subnav-track" aria-label="Company workspace sections">
        {(["core", "research"] as const).map((group) => (
          <div key={group} className="company-subnav-group">
            <span className="company-subnav-group-label">{group === "core" ? "Core views" : "Research feeds"}</span>
            <div className="company-subnav-links">
              {tabs.map((tab, index) => {
                if (tab.group !== group) {
                  return null;
                }

                const href = `${baseHref}${tab.suffix}`;
                const isActive = tab.exact ? pathname === href : pathname === href || pathname?.startsWith(`${href}/`);

                return (
                  <Link
                    key={tab.key}
                    href={href}
                    className={clsx("company-subnav-link", isActive && "is-active")}
                    aria-current={isActive ? "page" : undefined}
                    onKeyDown={handleKeyDown}
                  >
                    {tab.label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";

interface CompanySubnavProps {
  ticker: string;
}

const tabs: Array<{ key: string; label: string; suffix: string; exact?: boolean }> = [
  { key: "overview", label: "Overview", suffix: "", exact: true },
  { key: "financials", label: "Financials", suffix: "/financials" },
  { key: "ownership", label: "Ownership", suffix: "/ownership" },
  { key: "insiders", label: "Insiders", suffix: "/insiders" },
  { key: "models", label: "Models", suffix: "/models" }
];

export function CompanySubnav({ ticker }: CompanySubnavProps) {
  const pathname = usePathname();
  const baseHref = `/company/${encodeURIComponent(ticker)}`;

  return (
    <div className="company-subnav">
      <div className="company-subnav-meta">
        <span className="company-subnav-kicker">{ticker}</span>
        <span className="company-subnav-copy">Company workspace</span>
      </div>
      <nav className="company-subnav-track" aria-label="Company workspace sections">
        {tabs.map((tab) => {
          const href = `${baseHref}${tab.suffix}`;
          const isActive = tab.exact ? pathname === href : pathname === href || pathname?.startsWith(`${href}/`);

          return (
            <Link key={tab.key} href={href} className={clsx("company-subnav-link", isActive && "is-active")} aria-current={isActive ? "page" : undefined}>
              {tab.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

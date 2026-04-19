"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";

import { useCompanyLayoutContext } from "@/components/layout/company-layout-context";
import { getCompanyFinancials, getCompanyOverview } from "@/lib/api";
import { companySupportsOilWorkspace } from "@/lib/oil-workspace";

interface CompanySubnavProps {
  ticker: string;
}

type CompanySubnavMatcher = {
  suffix: string;
  exact?: boolean;
};

type CompanySubnavTab = {
  key: string;
  label: string;
  suffix: string;
  section: "primary" | "more";
  matchers?: CompanySubnavMatcher[];
};

const baseTabs: CompanySubnavTab[] = [
  {
    key: "brief",
    label: "Brief",
    suffix: "",
    section: "primary",
    matchers: [
      { suffix: "", exact: true },
      { suffix: "/overview", exact: true }
    ]
  },
  { key: "financials", label: "Financials", suffix: "/financials", section: "primary" },
  { key: "charts", label: "Charts", suffix: "/charts", section: "primary" },
  { key: "models", label: "Models", suffix: "/models", section: "primary" },
  { key: "peers", label: "Peers", suffix: "/peers", section: "primary" },
  { key: "earnings", label: "Earnings", suffix: "/earnings", section: "more" },
  { key: "filings", label: "Filings", suffix: "/filings", section: "more" },
  { key: "events", label: "Events", suffix: "/events", section: "more" },
  { key: "capital-markets", label: "Capital Markets", suffix: "/capital-markets", section: "more" },
  { key: "governance", label: "Governance", suffix: "/governance", section: "more" },
  {
    key: "ownership-stakes",
    label: "Ownership & Stakes",
    suffix: "/stakes",
    section: "more",
    matchers: [{ suffix: "/stakes" }, { suffix: "/ownership" }, { suffix: "/ownership-changes" }]
  },
  { key: "insiders", label: "Insiders", suffix: "/insiders", section: "more" },
  { key: "sec-feed", label: "SEC Feed", suffix: "/sec-feed", section: "more" }
];

const oilTab: CompanySubnavTab = { key: "oil", label: "Oil", suffix: "/oil", section: "primary" };

export function CompanySubnav({ ticker }: CompanySubnavProps) {
  const pathname = usePathname();
  const companyLayout = useCompanyLayoutContext();
  const moreRef = useRef<HTMLDivElement>(null);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const moreMenuRef = useRef<HTMLDivElement>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [showOilTab, setShowOilTab] = useState(false);
  const baseHref = `/company/${encodeURIComponent(ticker)}`;
  const sharedCompany = companyLayout?.company?.ticker === ticker ? companyLayout.company : null;
  const sharedPublisherCount = companyLayout?.publisherCount ?? 0;
  const tabs = showOilTab ? [...baseTabs.slice(0, 3), oilTab, ...baseTabs.slice(3)] : baseTabs;
  const tabLinks = tabs.map((tab) => ({
    ...tab,
    href: `${baseHref}${tab.suffix}`
  }));
  const activeTab = tabLinks.find((tab) => isTabActive(pathname, baseHref, tab)) ?? tabLinks[0];
  const primaryTabs = tabLinks.filter((tab) => tab.section === "primary");
  const moreTabs = tabLinks.filter((tab) => tab.section === "more");

  useEffect(() => {
    setMoreOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (sharedCompany) {
      setShowOilTab(companySupportsOilWorkspace(sharedCompany));
      return;
    }

    if (sharedPublisherCount > 0 || shouldAwaitWorkspaceCompany(pathname, baseHref)) {
      setShowOilTab(false);
      return;
    }

    let cancelled = false;

    async function loadOilTabVisibility() {
      try {
        const company = isOverviewRoute(pathname, baseHref)
          ? await getCompanyOverview(ticker, { financialsView: "core_segments" }).then((overviewData) => overviewData.company ?? overviewData.financials.company)
          : await getCompanyFinancials(ticker, { view: "core" }).then((financialData) => financialData.company);
        if (!cancelled) {
          setShowOilTab(companySupportsOilWorkspace(company));
        }
      } catch {
        if (!cancelled) {
          setShowOilTab(false);
        }
      }
    }

    void loadOilTabVisibility();
    return () => {
      cancelled = true;
    };
  }, [baseHref, pathname, sharedCompany, sharedPublisherCount, ticker]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as Node | null;
      if (target && !moreRef.current?.contains(target)) {
        setMoreOpen(false);
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function focusTrackItem(currentTarget: HTMLElement, targetIndex: number) {
    const links = Array.from(currentTarget.closest("nav")?.querySelectorAll<HTMLElement>("a.company-subnav-link, button.company-subnav-link") ?? []);
    links[targetIndex]?.focus();
  }

  function focusMoreMenuItem(targetIndex: number) {
    window.requestAnimationFrame(() => {
      const items = Array.from(moreMenuRef.current?.querySelectorAll<HTMLAnchorElement>("a.company-subnav-more-link") ?? []);
      items[targetIndex]?.focus();
    });
  }

  function handleTrackKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    const links = Array.from(event.currentTarget.closest("nav")?.querySelectorAll<HTMLElement>("a.company-subnav-link, button.company-subnav-link") ?? []);
    const currentIndex = links.indexOf(event.currentTarget);
    if (currentIndex === -1) {
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusTrackItem(event.currentTarget, (currentIndex + 1) % links.length);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusTrackItem(event.currentTarget, (currentIndex - 1 + links.length) % links.length);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      focusTrackItem(event.currentTarget, 0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      focusTrackItem(event.currentTarget, links.length - 1);
    }
  }

  function handleMoreTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setMoreOpen(true);
      focusMoreMenuItem(0);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (moreOpen) {
        setMoreOpen(false);
        return;
      }

      setMoreOpen(true);
      focusMoreMenuItem(0);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      setMoreOpen(false);
      return;
    }

    handleTrackKeyDown(event);
  }

  function handleMoreMenuKeyDown(event: ReactKeyboardEvent<HTMLAnchorElement>) {
    const items = Array.from(moreMenuRef.current?.querySelectorAll<HTMLAnchorElement>("a.company-subnav-more-link") ?? []);
    const currentIndex = items.indexOf(event.currentTarget);
    if (currentIndex === -1) {
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      items[(currentIndex + 1) % items.length]?.focus();
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      items[(currentIndex - 1 + items.length) % items.length]?.focus();
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      items[0]?.focus();
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      items[items.length - 1]?.focus();
      return;
    }

    if (event.key === "Escape" || event.key === "ArrowLeft") {
      event.preventDefault();
      setMoreOpen(false);
      moreButtonRef.current?.focus();
    }
  }

  return (
    <div className="company-subnav">
      <div className="company-subnav-meta">
        <span className="company-subnav-kicker">{ticker}</span>
        <span className="company-subnav-copy">Company workspace</span>
      </div>
      <nav className="company-subnav-track company-subnav-track-desktop" aria-label="Company workspace sections">
        {tabLinks.map((tab) => {
          const isActive = isTabActive(pathname, baseHref, tab);

          return (
            <Link
              key={tab.key}
              href={tab.href}
              className={clsx("company-subnav-link", isActive && "is-active")}
              aria-current={isActive ? "page" : undefined}
              onKeyDown={handleTrackKeyDown}
            >
              {tab.label}
            </Link>
          );
        })}
      </nav>
      <nav className="company-subnav-track company-subnav-track-mobile" aria-label="Company workspace quick sections">
        <div className="company-subnav-primary-links">
          {primaryTabs.map((tab) => {
            const isActive = isTabActive(pathname, baseHref, tab);

            return (
              <Link
                key={tab.key}
                href={tab.href}
                className={clsx("company-subnav-link", isActive && "is-active")}
                aria-current={isActive ? "page" : undefined}
                onKeyDown={handleTrackKeyDown}
              >
                {tab.label}
              </Link>
            );
          })}
        </div>
        <div ref={moreRef} className="company-subnav-more">
          <button
            ref={moreButtonRef}
            type="button"
            className={clsx("company-subnav-link", "company-subnav-more-trigger", activeTab.section === "more" && "is-active", moreOpen && "is-open")}
            aria-haspopup="menu"
            aria-controls="company-subnav-more-menu"
            onClick={() => setMoreOpen((current) => !current)}
            onKeyDown={handleMoreTriggerKeyDown}
          >
            More
            <span className="company-subnav-more-caret" aria-hidden="true" />
          </button>
          {moreOpen ? (
            <div ref={moreMenuRef} id="company-subnav-more-menu" className="company-subnav-more-menu" aria-label="More company sections">
              {moreTabs.map((tab) => {
                const isActive = isTabActive(pathname, baseHref, tab);

                return (
                  <Link
                    key={tab.key}
                    href={tab.href}
                    className={clsx("company-subnav-more-link", isActive && "is-active")}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => setMoreOpen(false)}
                    onKeyDown={handleMoreMenuKeyDown}
                  >
                    {tab.label}
                  </Link>
                );
              })}
            </div>
          ) : null}
        </div>
      </nav>
    </div>
  );
}

function isOverviewRoute(pathname: string | null, baseHref: string): boolean {
  return pathname === baseHref || pathname === `${baseHref}/overview`;
}

function shouldAwaitWorkspaceCompany(pathname: string | null, baseHref: string): boolean {
  if (!pathname) {
    return false;
  }

  return [
    "",
    "/overview",
    "/financials",
    "/capital-markets",
    "/earnings",
    "/events",
    "/filings",
    "/governance",
    "/insiders",
    "/oil",
    "/ownership",
    "/ownership-changes",
    "/peers",
    "/sec-feed",
    "/stakes",
  ].some((suffix) => pathname === `${baseHref}${suffix}`);
}

function isTabActive(pathname: string | null, baseHref: string, tab: CompanySubnavTab): boolean {
  const matchers = tab.matchers ?? [{ suffix: tab.suffix }];

  return matchers.some((matcher) => {
    const href = `${baseHref}${matcher.suffix}`;
    if (matcher.exact) {
      return pathname === href;
    }

    return pathname === href || pathname?.startsWith(`${href}/`);
  });
}

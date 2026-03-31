"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clsx } from "clsx";

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

const tabs: CompanySubnavTab[] = [
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

export function CompanySubnav({ ticker }: CompanySubnavProps) {
  const pathname = usePathname();
  const router = useRouter();
  const moreRef = useRef<HTMLDivElement>(null);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const moreMenuRef = useRef<HTMLDivElement>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const baseHref = `/company/${encodeURIComponent(ticker)}`;
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
      <div className="company-subnav-mobile-picker">
        <label className="company-subnav-select-label" htmlFor="company-subnav-select">
          Section
        </label>
        <select
          id="company-subnav-select"
          className="company-subnav-select"
          value={activeTab.key}
          onChange={(event) => {
            const nextTab = tabLinks.find((tab) => tab.key === event.target.value);
            if (nextTab) {
              router.push(nextTab.href);
            }
          }}
        >
          {tabLinks.map((tab) => (
            <option key={tab.key} value={tab.key}>
              {tab.section === "more" ? `More · ${tab.label}` : tab.label}
            </option>
          ))}
        </select>
      </div>
      <nav className="company-subnav-track" aria-label="Company workspace sections">
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
            aria-expanded={moreOpen}
            aria-controls="company-subnav-more-menu"
            onClick={() => setMoreOpen((current) => !current)}
            onKeyDown={handleMoreTriggerKeyDown}
          >
            More
            <span className="company-subnav-more-caret" aria-hidden="true" />
          </button>
          {moreOpen ? (
            <div ref={moreMenuRef} id="company-subnav-more-menu" className="company-subnav-more-menu" role="menu" aria-label="More company sections">
              {moreTabs.map((tab) => {
                const isActive = isTabActive(pathname, baseHref, tab);

                return (
                  <Link
                    key={tab.key}
                    href={tab.href}
                    role="menuitem"
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

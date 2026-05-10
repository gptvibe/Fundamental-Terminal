"use client";

import type { ReactNode } from "react";
import { clsx } from "clsx";
import { useCallback } from "react";
import Link from "next/link";

export interface TabDefinition {
  id: string;
  label: string;
  icon?: ReactNode;
  badge?: string | number;
  disabled?: boolean;
  panelId?: string;
  description?: string;
  href?: string;
}

export interface ResearchBriefTabsProps {
  tabs: TabDefinition[];
  activeTabId: string;
  onTabChange: (tabId: string) => void;
  className?: string;
}

export function ResearchBriefTabs({
  tabs,
  activeTabId,
  onTabChange,
  className,
}: ResearchBriefTabsProps) {
  const handleTabClick = useCallback(
    (tabId: string) => {
      const tab = tabs.find((t) => t.id === tabId);
      if (tab && !tab.disabled) {
        if (tab.href) {
          document.getElementById(`tab-${tabId}`)?.focus();
          return;
        }
        onTabChange(tabId);
        window.setTimeout(() => document.getElementById(`tab-${tabId}`)?.focus(), 0);
      }
    },
    [tabs, onTabChange]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const currentIndex = tabs.findIndex((t) => t.id === activeTabId);

      const findEnabledTab = (direction: 1 | -1): TabDefinition | undefined => {
        for (let index = currentIndex + direction; index >= 0 && index < tabs.length; index += direction) {
          const candidate = tabs[index];
          if (!candidate.disabled) {
            return candidate;
          }
        }
        return undefined;
      };

      if (e.key === "ArrowLeft" && currentIndex > 0) {
        e.preventDefault();
        const prevTab = findEnabledTab(-1);
        if (prevTab) {
          handleTabClick(prevTab.id);
        }
      } else if (e.key === "ArrowRight" && currentIndex < tabs.length - 1) {
        e.preventDefault();
        const nextTab = findEnabledTab(1);
        if (nextTab) {
          handleTabClick(nextTab.id);
        }
      } else if (e.key === "Home") {
        e.preventDefault();
        const firstTab = tabs.find((t) => !t.disabled);
        if (firstTab) {
          handleTabClick(firstTab.id);
        }
      } else if (e.key === "End") {
        e.preventDefault();
        const lastTab = [...tabs].reverse().find((t) => !t.disabled);
        if (lastTab) {
          handleTabClick(lastTab.id);
        }
      }
    },
    [activeTabId, tabs, handleTabClick]
  );

  return (
    <div className={clsx("research-brief-tabs", className)}>
      <div
        className="tabs-list"
        role="tablist"
        aria-orientation="horizontal"
        aria-label="Research brief sections"
        onKeyDown={handleKeyDown}
      >
        {tabs.map((tab) => {
          const tabClassName = clsx(
            "tab",
            tab.id === activeTabId && "tab-active",
            tab.disabled && "tab-disabled"
          );
          const tabContent = (
            <>
              {tab.icon && <span className="tab-icon">{tab.icon}</span>}
              <span className="tab-label">{tab.label}</span>
              {tab.badge && (
                <span className="tab-badge" aria-label={`${tab.label}: ${tab.badge}`}>
                  {tab.badge}
                </span>
              )}
            </>
          );

          if (tab.href) {
            return (
              <Link
                key={tab.id}
                href={tab.href}
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={tab.id === activeTabId}
                aria-controls={tab.panelId}
                aria-disabled={tab.disabled}
                title={tab.description}
                tabIndex={tab.id === activeTabId ? 0 : -1}
                className={tabClassName}
                onClick={(event) => {
                  if (tab.disabled) {
                    event.preventDefault();
                  }
                }}
              >
                {tabContent}
              </Link>
            );
          }

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={tab.id === activeTabId}
              aria-controls={tab.panelId}
              aria-disabled={tab.disabled}
              title={tab.description}
              disabled={tab.disabled}
              tabIndex={tab.id === activeTabId ? 0 : -1}
              className={tabClassName}
              onClick={() => handleTabClick(tab.id)}
            >
              {tabContent}
            </button>
          );
        })}
      </div>
    </div>
  );
}

"use client";

type ResearchBriefNavSection = {
  id: string;
  title: string;
  href: string;
  activeIds: string[];
};

const RESEARCH_BRIEF_NAV_SECTIONS: ResearchBriefNavSection[] = [
  { id: "snapshot", title: "Snapshot", href: "#snapshot", activeIds: ["snapshot"] },
  {
    id: "understand-business",
    title: "Understand Business",
    href: "#understand-business",
    activeIds: ["understand-business"],
  },
  { id: "what-changed", title: "What Changed", href: "#what-changed", activeIds: ["what-changed"] },
  {
    id: "business-quality",
    title: "Business Quality",
    href: "#business-quality",
    activeIds: ["business-quality"],
  },
  { id: "capital-risk", title: "Capital & Risk", href: "#capital-risk", activeIds: ["capital-risk"] },
  {
    id: "compare-value",
    title: "Compare & Value",
    href: "#compare-value",
    activeIds: ["compare-value", "valuation"],
  },
  { id: "monitor", title: "Monitor", href: "#monitor", activeIds: ["monitor"] },
];

export function ResearchBriefSectionNav({ activeSectionId }: { activeSectionId: string }) {
  return (
    <nav className="research-brief-nav" aria-label="Research brief sections">
      {RESEARCH_BRIEF_NAV_SECTIONS.map((section) => {
        const isActive = section.activeIds.includes(activeSectionId);

        return (
        <a
          key={section.id}
          href={section.href}
          className={`research-brief-nav-link${isActive ? " is-active" : ""}`}
          aria-current={isActive ? "location" : undefined}
        >
          {section.title}
        </a>
        );
      })}
    </nav>
  );
}

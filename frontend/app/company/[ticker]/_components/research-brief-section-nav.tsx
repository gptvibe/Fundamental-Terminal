"use client";

import { BRIEF_SECTIONS } from "../_lib/research-brief-types";

export function ResearchBriefSectionNav({ activeSectionId }: { activeSectionId: string }) {
  return (
    <nav className="research-brief-nav" aria-label="Research brief sections">
      {BRIEF_SECTIONS.map((section) => (
        <a
          key={section.id}
          href={`#${section.id}`}
          className={`research-brief-nav-link${activeSectionId === section.id ? " is-active" : ""}`}
        >
          {section.title}
        </a>
      ))}
    </nav>
  );
}

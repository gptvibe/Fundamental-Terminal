"use client";

import { useUIDensity } from "@/hooks/use-ui-density";

const CONCEPT_GLOSSARY = [
  {
    term: "Revenue",
    definition: "Total income from selling goods or services before any costs are subtracted.",
  },
  {
    term: "Free Cash Flow",
    definition: "Cash a company generates after paying for operations and capital expenditures — the money truly available to owners.",
  },
  {
    term: "Gross Margin",
    definition: "Percentage of revenue remaining after the direct cost of goods sold. Higher is generally better.",
  },
  {
    term: "EV / EBITDA",
    definition: "Enterprise Value divided by earnings before interest, taxes, depreciation, and amortisation — a common valuation multiple.",
  },
];

export function BeginnerGuidanceBanner() {
  const { isBeginnerMode, setDensity } = useUIDensity();

  if (!isBeginnerMode) {
    return null;
  }

  return (
    <aside className="beginner-guidance-banner" role="note" aria-label="Simple view guidance">
      <div className="beginner-guidance-header">
        <span className="beginner-guidance-kicker">Simple View</span>
        <p className="beginner-guidance-tagline">
          Advanced methodology and source-detail panels are collapsed. Switch to{" "}
          <button
            type="button"
            className="beginner-guidance-switch-link"
            onClick={() => setDensity("pro")}
          >
            Detailed view
          </button>{" "}
          to reveal all panels.
        </p>
      </div>

      <dl className="beginner-glossary">
        {CONCEPT_GLOSSARY.map(({ term, definition }) => (
          <div key={term} className="beginner-glossary-entry">
            <dt className="beginner-glossary-term">{term}</dt>
            <dd className="beginner-glossary-def">{definition}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}

import type { ReactNode } from "react";

interface PlainEnglishScorecardProps {
  title: string;
  label: string;
  tone: "bullish" | "bearish" | "neutral" | "high" | "medium" | "low";
  summary: string;
  explanation: string;
  chips?: ReactNode[];
}

export function PlainEnglishScorecard({ title, label, tone, summary, explanation, chips = [] }: PlainEnglishScorecardProps) {
  return (
    <div className={`plain-english-scorecard plain-english-scorecard-${tone}`}>
      <div className="plain-english-scorecard-header">
        <div className="plain-english-scorecard-title">{title}</div>
        <span className={`plain-english-scorecard-badge plain-english-scorecard-badge-${tone}`}>{label}</span>
      </div>

      <div className="plain-english-scorecard-summary">{summary}</div>
      <div className="plain-english-scorecard-explanation">{explanation}</div>

      {chips.length ? (
        <div className="plain-english-scorecard-chips">
          {chips.map((chip, index) => (
            <span key={typeof chip === "string" ? chip : `chip-${index}`} className="plain-english-scorecard-chip">
              {chip}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
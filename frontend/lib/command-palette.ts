export interface CommandPaletteEntry {
  id: string;
  title: string;
  keywords?: string[];
}

export interface RankedCommandPaletteEntry {
  entry: CommandPaletteEntry;
  score: number;
}

export function rankCommandPaletteEntries(entries: CommandPaletteEntry[], query: string): RankedCommandPaletteEntry[] {
  const normalizedQuery = normalizeCommandQuery(query);
  if (!normalizedQuery) {
    return entries.map((entry, index) => ({ entry, score: 10_000 - index }));
  }

  return entries
    .map((entry) => {
      const haystack = `${entry.title} ${(entry.keywords ?? []).join(" ")}`;
      const score = fuzzySubsequenceScore(normalizedQuery, normalizeCommandQuery(haystack));
      if (score === null) {
        return null;
      }

      return { entry, score };
    })
    .filter((item): item is RankedCommandPaletteEntry => item !== null)
    .sort((left, right) => right.score - left.score || left.entry.title.localeCompare(right.entry.title));
}

function fuzzySubsequenceScore(query: string, text: string): number | null {
  let score = 0;
  let queryIndex = 0;
  let lastMatchIndex = -1;

  for (let i = 0; i < text.length && queryIndex < query.length; i += 1) {
    if (query[queryIndex] !== text[i]) {
      continue;
    }

    const contiguousBonus = lastMatchIndex === i - 1 ? 8 : 0;
    const boundaryBonus = i === 0 || text[i - 1] === " " ? 12 : 0;
    score += 16 + contiguousBonus + boundaryBonus;
    if (lastMatchIndex >= 0) {
      score -= Math.max(0, i - lastMatchIndex - 1);
    }
    lastMatchIndex = i;
    queryIndex += 1;
  }

  if (queryIndex !== query.length) {
    return null;
  }

  return score - Math.max(0, text.length - query.length);
}

function normalizeCommandQuery(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").trim();
}

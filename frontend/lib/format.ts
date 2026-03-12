export function formatCompactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "\u2014";
  }

  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "\u2014";
  }

  return `${(value * 100).toFixed(2)}%`;
}

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function parseDateValue(value: string): { date: Date; isDateOnly: boolean } {
  if (DATE_ONLY_PATTERN.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return { date: new Date(Date.UTC(year, month - 1, day)), isDateOnly: true };
  }
  return { date: new Date(value), isDateOnly: false };
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "\u2014";
  }

  const { date, isDateOnly } = parseDateValue(value);
  if (Number.isNaN(date.getTime())) {
    return "\u2014";
  }

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    year: "numeric",
    ...(isDateOnly ? { timeZone: "UTC" } : {})
  }).format(date);
}

export function titleCase(value: string): string {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

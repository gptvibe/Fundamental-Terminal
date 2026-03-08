import type { InstitutionalHoldingPayload } from "@/lib/types";

export interface SmartMoneySummaryResult {
  sentiment: "bullish" | "neutral" | "bearish";
  net_institutional_flow: number;
  fund_increasing: number;
  fund_decreasing: number;
  total_buy_value: number;
  total_sell_value: number;
  summary_text: string;
  summary_lines: string[];
}

export interface SmartMoneyFlowDatum {
  quarterKey: string;
  quarterLabel: string;
  quarterDate: string;
  institutionalBuyValue: number;
  institutionalSellValue: number;
  netSmartMoneyFlow: number;
  fundsBuying: number;
  fundsSelling: number;
  totalValueTraded: number;
}

interface InstitutionalChange {
  fund_name: string;
  previous_shares: number;
  current_shares: number;
  price: number;
  share_change: number;
  value_change: number;
}

interface InstitutionalAggregate {
  total_buy_value: number;
  total_sell_value: number;
  net_institutional_flow: number;
  fund_increasing: number;
  fund_decreasing: number;
}

interface QuarterlyInstitutionalChange {
  fund_name: string;
  reporting_date: string;
  share_change: number;
  value_change: number;
}

const DEFAULT_NEUTRAL_THRESHOLD = 500_000;

export function buildSmartMoneySummary(
  institutionalHoldings: InstitutionalHoldingPayload[],
  _asOfInput?: string | Date
): SmartMoneySummaryResult | null {
  const institutionalChanges = buildInstitutionalChanges(institutionalHoldings);
  const institutional = aggregateInstitutionalChanges(institutionalChanges);

  if (!institutionalChanges.length) {
    return null;
  }

  const threshold = computeNeutralThreshold(institutional.total_buy_value, institutional.total_sell_value);

  let sentiment: SmartMoneySummaryResult["sentiment"] = "neutral";
  if (Math.abs(institutional.net_institutional_flow) < threshold) {
    sentiment = "neutral";
  } else if (
    institutional.net_institutional_flow > 0 &&
    institutional.fund_increasing > institutional.fund_decreasing
  ) {
    sentiment = "bullish";
  } else if (
    institutional.net_institutional_flow < 0 &&
    institutional.fund_decreasing > institutional.fund_increasing
  ) {
    sentiment = "bearish";
  }

  const summary_lines = buildSummaryLines(sentiment, institutional, institutionalChanges.length > 0);

  return {
    sentiment,
    net_institutional_flow: roundMoney(institutional.net_institutional_flow),
    fund_increasing: institutional.fund_increasing,
    fund_decreasing: institutional.fund_decreasing,
    total_buy_value: roundMoney(institutional.total_buy_value),
    total_sell_value: roundMoney(institutional.total_sell_value),
    summary_text: summary_lines.join(" "),
    summary_lines
  };
}

export function buildSmartMoneyFlowTrend(institutionalHoldings: InstitutionalHoldingPayload[]): SmartMoneyFlowDatum[] {
  const quarterlyChanges = buildQuarterlyInstitutionalChanges(institutionalHoldings);
  const grouped = new Map<
    string,
    {
      quarterLabel: string;
      quarterDate: string;
      institutionalBuyValue: number;
      institutionalSellValue: number;
      fundsBuying: Set<string>;
      fundsSelling: Set<string>;
    }
  >();

  for (const change of quarterlyChanges) {
    const bucket =
      grouped.get(change.reporting_date) ??
      {
        quarterLabel: formatQuarter(change.reporting_date),
        quarterDate: change.reporting_date,
        institutionalBuyValue: 0,
        institutionalSellValue: 0,
        fundsBuying: new Set<string>(),
        fundsSelling: new Set<string>()
      };

    if (change.share_change > 0) {
      bucket.institutionalBuyValue += Math.abs(change.value_change);
      bucket.fundsBuying.add(change.fund_name.toLowerCase());
    } else if (change.share_change < 0) {
      bucket.institutionalSellValue += Math.abs(change.value_change);
      bucket.fundsSelling.add(change.fund_name.toLowerCase());
    }

    grouped.set(change.reporting_date, bucket);
  }

  return Array.from(grouped.entries())
    .sort(([leftDate], [rightDate]) => Date.parse(leftDate) - Date.parse(rightDate))
    .map(([quarterKey, bucket]) => ({
      quarterKey,
      quarterLabel: bucket.quarterLabel,
      quarterDate: bucket.quarterDate,
      institutionalBuyValue: roundMoney(bucket.institutionalBuyValue),
      institutionalSellValue: roundMoney(bucket.institutionalSellValue),
      netSmartMoneyFlow: roundMoney(bucket.institutionalBuyValue - bucket.institutionalSellValue),
      fundsBuying: bucket.fundsBuying.size,
      fundsSelling: bucket.fundsSelling.size,
      totalValueTraded: roundMoney(bucket.institutionalBuyValue + bucket.institutionalSellValue)
    }));
}

function buildInstitutionalChanges(holdings: InstitutionalHoldingPayload[]) {
  const grouped = new Map<string, InstitutionalHoldingPayload[]>();

  for (const holding of holdings) {
    const rows = grouped.get(holding.fund_name) ?? [];
    rows.push(holding);
    grouped.set(holding.fund_name, rows);
  }

  const changes: InstitutionalChange[] = [];
  for (const [fund_name, rows] of grouped.entries()) {
    const sortedRows = [...rows].sort((left, right) => Date.parse(right.reporting_date) - Date.parse(left.reporting_date));
    const current = sortedRows[0];
    const previous = sortedRows[1] ?? null;

    const currentShares = current?.shares_held ?? null;
    const previousShares =
      previous?.shares_held ??
      derivePreviousShares(current?.shares_held ?? null, current?.change_in_shares ?? null);

    if (currentShares == null || previousShares == null) {
      continue;
    }

    const share_change = currentShares - previousShares;
    const price = resolveHoldingPrice(current) ?? resolveHoldingPrice(previous) ?? 0;
    const value_change = share_change * price;

    changes.push({
      fund_name,
      previous_shares: previousShares,
      current_shares: currentShares,
      price,
      share_change,
      value_change
    });
  }

  return changes;
}

function buildQuarterlyInstitutionalChanges(holdings: InstitutionalHoldingPayload[]): QuarterlyInstitutionalChange[] {
  const grouped = new Map<string, InstitutionalHoldingPayload[]>();

  for (const holding of holdings) {
    const rows = grouped.get(holding.fund_name) ?? [];
    rows.push(holding);
    grouped.set(holding.fund_name, rows);
  }

  const changes: QuarterlyInstitutionalChange[] = [];
  for (const [fund_name, rows] of grouped.entries()) {
    const sortedRows = [...rows].sort((left, right) => Date.parse(right.reporting_date) - Date.parse(left.reporting_date));

    for (let index = 0; index < sortedRows.length; index += 1) {
      const current = sortedRows[index];
      const previous = sortedRows[index + 1] ?? null;
      const currentShares = current?.shares_held ?? null;
      const previousShares = previous?.shares_held ?? derivePreviousShares(current?.shares_held ?? null, current?.change_in_shares ?? null);

      if (currentShares == null || previousShares == null) {
        continue;
      }

      const share_change = currentShares - previousShares;
      if (!Number.isFinite(share_change) || share_change === 0) {
        continue;
      }

      const price = resolveHoldingPrice(current) ?? resolveHoldingPrice(previous) ?? 0;
      changes.push({
        fund_name,
        reporting_date: current.reporting_date,
        share_change,
        value_change: share_change * price
      });
    }
  }

  return changes;
}

function aggregateInstitutionalChanges(changes: InstitutionalChange[]): InstitutionalAggregate {
  let total_buy_value = 0;
  let total_sell_value = 0;
  let fund_increasing = 0;
  let fund_decreasing = 0;

  for (const change of changes) {
    if (change.share_change > 0) {
      fund_increasing += 1;
      total_buy_value += Math.abs(change.value_change);
    } else if (change.share_change < 0) {
      fund_decreasing += 1;
      total_sell_value += Math.abs(change.value_change);
    }
  }

  return {
    total_buy_value,
    total_sell_value,
    net_institutional_flow: total_buy_value - total_sell_value,
    fund_increasing,
    fund_decreasing
  };
}

function buildSummaryLines(
  sentiment: SmartMoneySummaryResult["sentiment"],
  institutional: InstitutionalAggregate,
  hasInstitutionalChanges: boolean
) {
  const lines: string[] = [];

  if (!hasInstitutionalChanges) {
    lines.push("Institutional ownership data is still warming in cache.");
    lines.push("No quarter-over-quarter 13F position deltas are available yet.");
  } else if (sentiment === "bullish") {
    lines.push("Smart money accumulating shares.");
    lines.push(`Funds added approximately ${formatCurrencyCompact(institutional.total_buy_value)}.`);
    lines.push(`${institutional.fund_increasing} funds increased positions while ${institutional.fund_decreasing} reduced.`);
  } else if (sentiment === "bearish") {
    lines.push("Funds reducing exposure.");
    lines.push(`Net institutional selling of approximately ${formatCurrencyCompact(Math.abs(institutional.net_institutional_flow))}.`);
    lines.push(`${institutional.fund_decreasing} funds reduced positions while ${institutional.fund_increasing} increased.`);
  } else {
    lines.push("Institutional ownership appears stable.");
    lines.push("Minor portfolio adjustments detected.");
    lines.push(`${institutional.fund_increasing} funds increased positions while ${institutional.fund_decreasing} reduced.`);
  }

  if (hasInstitutionalChanges && institutional.fund_increasing === 0 && institutional.fund_decreasing === 0) {
    lines.push("No major institutional position changes were detected across the latest cached 13F filings.");
  } else if (hasInstitutionalChanges && Math.abs(institutional.net_institutional_flow) < computeNeutralThreshold(institutional.total_buy_value, institutional.total_sell_value)) {
    lines.push("Net institutional flow remains close to flat despite normal portfolio rebalancing.");
  }

  return dedupeLines(lines).slice(0, 4);
}

function resolveHoldingPrice(holding: InstitutionalHoldingPayload | null | undefined) {
  if (!holding || holding.market_value == null || holding.shares_held == null || holding.shares_held === 0) {
    return null;
  }
  return Math.abs(holding.market_value / holding.shares_held);
}

function derivePreviousShares(currentShares: number | null, changeInShares: number | null) {
  if (currentShares == null || changeInShares == null) {
    return null;
  }
  return currentShares - changeInShares;
}

function computeNeutralThreshold(totalBuyValue: number, totalSellValue: number) {
  return Math.max(DEFAULT_NEUTRAL_THRESHOLD, (totalBuyValue + totalSellValue) * 0.1);
}

function formatQuarter(value: string) {
  const dateValue = new Date(value);
  const quarter = Math.floor(dateValue.getUTCMonth() / 3) + 1;
  return `Q${quarter} ${dateValue.getUTCFullYear()}`;
}

function formatCurrencyCompact(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: Math.abs(value) >= 1_000 ? "compact" : "standard",
    maximumFractionDigits: 2
  }).format(value);
}

function roundMoney(value: number) {
  return Math.round(value * 100) / 100;
}

function dedupeLines(lines: string[]) {
  const seen = new Set<string>();
  return lines.filter((line) => {
    const normalized = line.trim();
    if (!normalized || seen.has(normalized)) {
      return false;
    }
    seen.add(normalized);
    return true;
  });
}

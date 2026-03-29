"use client";

import { useMemo } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { CHART_AXIS_COLOR, CHART_GRID_COLOR, RECHARTS_TOOLTIP_PROPS, chartTick } from "@/lib/chart-theme";
import type { InsiderTradePayload } from "@/lib/types";
import { formatCompactNumber } from "@/lib/format";

type RoleDatum = {
  role: string;
  buys: number;
  sells: number;
  net: number;
  trades: number;
};

export function InsiderRoleActivityChart({ trades }: { trades: InsiderTradePayload[] }) {
  const data = useMemo(() => buildRoleData(trades), [trades]);

  if (!data.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">Role activity</div>
        <div className="grid-empty-title">No role-based insider signal yet</div>
        <div className="grid-empty-copy">Role activity appears here when open-market Form 4 buy or sell signals are cached.</div>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: 320 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke={CHART_GRID_COLOR} vertical={false} />
          <XAxis dataKey="role" stroke={CHART_AXIS_COLOR} tick={chartTick()} />
          <YAxis stroke={CHART_AXIS_COLOR} tick={chartTick()} tickFormatter={(value) => formatCompactNumber(Number(value))} />
          <Tooltip {...RECHARTS_TOOLTIP_PROPS} formatter={(value: number) => formatCompactNumber(value)} />
          <Bar dataKey="buys" name="Buy Value" fill="var(--positive)" radius={[2, 2, 0, 0]} />
          <Bar dataKey="sells" name="Sell Value" fill="var(--negative)" radius={[2, 2, 0, 0]} />
          <Line type="monotone" dataKey="net" name="Net Value" stroke="var(--accent)" strokeWidth={2.4} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function buildRoleData(trades: InsiderTradePayload[]): RoleDatum[] {
  const buckets = new Map<string, RoleDatum>();

  for (const trade of trades) {
    if (!isSignalBuy(trade) && !isSignalSell(trade)) {
      continue;
    }

    const role = normalizeRole(trade.role);
    const bucket = buckets.get(role) ?? { role, buys: 0, sells: 0, net: 0, trades: 0 };
    const value = resolveTransactionValue(trade);

    if (isSignalBuy(trade)) {
      bucket.buys += value;
      bucket.net += value;
    } else {
      bucket.sells += value;
      bucket.net -= value;
    }
    bucket.trades += 1;
    buckets.set(role, bucket);
  }

  return [...buckets.values()]
    .sort((left, right) => Math.abs(right.net) - Math.abs(left.net) || right.trades - left.trades)
    .slice(0, 6)
    .map((row) => ({
      ...row,
      buys: round(row.buys),
      sells: round(row.sells),
      net: round(row.net),
    }));
}

function normalizeRole(role: string | null) {
  const normalized = (role ?? "").toUpperCase();
  if (normalized.includes("CEO") || normalized.includes("CHIEF EXECUTIVE")) {
    return "CEO";
  }
  if (normalized.includes("CFO") || normalized.includes("CHIEF FINANCIAL")) {
    return "CFO";
  }
  if (normalized.includes("DIRECTOR")) {
    return "Director";
  }
  if (normalized.includes("OFFICER") || normalized.includes("CHIEF")) {
    return "Executive";
  }
  return role?.trim() || "Other";
}

function isSignalBuy(trade: InsiderTradePayload) {
  const code = (trade.transaction_code ?? "").trim().toUpperCase();
  if (code) {
    return code === "P";
  }
  return trade.action.trim().toLowerCase() === "buy";
}

function isSignalSell(trade: InsiderTradePayload) {
  const code = (trade.transaction_code ?? "").trim().toUpperCase();
  if (code) {
    return code === "S";
  }
  return trade.action.trim().toLowerCase() === "sell";
}

function resolveTransactionValue(trade: InsiderTradePayload) {
  if (typeof trade.value === "number" && Number.isFinite(trade.value)) {
    return Math.abs(trade.value);
  }
  if (typeof trade.shares === "number" && Number.isFinite(trade.shares) && typeof trade.price === "number" && Number.isFinite(trade.price)) {
    return Math.abs(trade.shares * trade.price);
  }
  return 0;
}

function round(value: number) {
  return Math.round(value * 100) / 100;
}
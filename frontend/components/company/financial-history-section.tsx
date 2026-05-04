"use client";

import { useEffect, useMemo, useState } from "react";

import { FinancialHistoryLineChart } from "@/components/charts/financial-history-line-chart";
import { getCompanyFinancialHistory } from "@/lib/api";
import { formatCompactNumber } from "@/lib/format";
import type { FinancialHistoryPoint } from "@/lib/types";

interface FinancialHistorySectionProps {
  cik: string | null;
}

type MetricConfig = {
  key: "revenue" | "net_income" | "eps" | "operating_cash_flow";
  label: string;
  color: string;
  description: string;
  format?: (value: number | null) => string;
};

const METRICS: MetricConfig[] = [
  { key: "revenue", label: "Revenue", color: "var(--accent)", description: "Is the company growing its top line? Sustained revenue growth signals expanding customer demand.", format: formatCompactNumber },
  { key: "net_income", label: "Net Income", color: "var(--positive)", description: "Is growth translating to profit? Rising net income shows the business is converting revenue into earnings.", format: formatCompactNumber },
  {
    key: "eps",
    label: "EPS (Diluted)",
    color: "var(--warning)",
    description: "How much profit does each share earn? Diluted EPS accounts for stock options and convertibles — watch for dilution eating into growth.",
    format: (value) => (value == null ? "—" : value.toFixed(2))
  },
  { key: "operating_cash_flow", label: "Operating Cash Flow", color: "#8B5CF6", description: "Is reported profit backed by real cash? Operating cash flow shows whether earnings quality is high or propped up by accruals.", format: formatCompactNumber }
];

export function FinancialHistorySection({ cik }: FinancialHistorySectionProps) {
  const [data, setData] = useState<FinancialHistoryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!cik) {
      setData([]);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    getCompanyFinancialHistory(cik, { signal: controller.signal })
      .then((payload) => setData(payload))
      .catch((nextError) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(nextError instanceof Error ? nextError.message : "Unable to load SEC financial history");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [cik]);

  const rows = useMemo(() => [...data].sort((left, right) => left.year - right.year), [data]);
  const historyMessage = useMemo(() => {
    if (rows.length < 10) {
      return `Showing ${rows.length} fiscal years from SEC companyfacts.`;
    }
    return "Showing the last 10 fiscal years from SEC companyfacts.";
  }, [rows.length]);

  if (!cik) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">10-Year Financial History</div>
        <div className="grid-empty-title">CIK not available yet</div>
        <div className="grid-empty-copy">Company facts appear once the SEC identifier resolves.</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">10-Year Financial History</div>
        <div className="grid-empty-title">Loading SEC companyfacts…</div>
        <div className="grid-empty-copy">Fetching the latest fiscal year history directly from EDGAR.</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">10-Year Financial History</div>
        <div className="grid-empty-title">Unable to load SEC history</div>
        <div className="grid-empty-copy">{error}</div>
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div className="grid-empty-state" style={{ minHeight: 220 }}>
        <div className="grid-empty-kicker">10-Year Financial History</div>
        <div className="grid-empty-title">No annual companyfacts found</div>
        <div className="grid-empty-copy">The SEC payload did not return FY values for these metrics.</div>
      </div>
    );
  }

  return (
    <div className="financial-history-shell">
      <div className="financial-history-note">{historyMessage}</div>
      <div className="financial-history-table-shell">
        <table className="financial-table">
          <thead>
            <tr>
              <th>Fiscal Year</th>
              <th>Revenue</th>
              <th>Net Income</th>
              <th>EPS (Diluted)</th>
              <th>Operating Cash Flow</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.year}>
                <td className="form-cell">FY {row.year}</td>
                <td>{formatCompactNumber(row.revenue)}</td>
                <td>{formatCompactNumber(row.net_income)}</td>
                <td>{row.eps == null ? "—" : row.eps.toFixed(2)}</td>
                <td>{formatCompactNumber(row.operating_cash_flow)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="financial-history-chart-grid">
        {METRICS.map((metric) => (
          <FinancialHistoryLineChart
            key={metric.key}
            data={rows}
            metric={metric.key}
            color={metric.color}
            label={metric.label}
            subtitle={metric.description}
            valueFormatter={metric.format}
          />
        ))}
      </div>
    </div>
  );
}










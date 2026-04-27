from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.services.derived_metrics as derived_metrics


def benchmark_price_matching(
    *,
    financial_rows: int,
    price_rows: int,
    rounds: int,
) -> dict[str, Any]:
    statements = _build_financial_statements(financial_rows)
    prices = _build_price_history(price_rows)

    optimized_timings_ms: list[float] = []
    baseline_timings_ms: list[float] = []
    baseline_index_rebuild_operations = 0

    optimized_series = None
    baseline_series = None

    for _ in range(rounds):
        started = time.perf_counter()
        optimized_series = derived_metrics.build_metrics_timeseries(statements, prices)
        optimized_timings_ms.append((time.perf_counter() - started) * 1000.0)

        started = time.perf_counter()
        baseline_series, index_operations = _build_metrics_timeseries_legacy(statements, prices)
        baseline_timings_ms.append((time.perf_counter() - started) * 1000.0)
        baseline_index_rebuild_operations += index_operations

    assert optimized_series is not None
    assert baseline_series is not None

    equivalent = optimized_series == baseline_series
    avg_optimized_ms = statistics.fmean(optimized_timings_ms)
    avg_baseline_ms = statistics.fmean(baseline_timings_ms)
    speedup_ratio = (avg_baseline_ms / avg_optimized_ms) if avg_optimized_ms > 0 else None

    return {
        "schema_version": "derived_metrics_price_matching_benchmark_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "financial_rows": financial_rows,
            "price_rows": price_rows,
            "rounds": rounds,
        },
        "equivalent_output": equivalent,
        "optimized": {
            "avg_ms": round(avg_optimized_ms, 3),
            "min_ms": round(min(optimized_timings_ms), 3),
            "max_ms": round(max(optimized_timings_ms), 3),
            "price_index_build_operations": price_rows * rounds,
        },
        "baseline_legacy": {
            "avg_ms": round(avg_baseline_ms, 3),
            "min_ms": round(min(baseline_timings_ms), 3),
            "max_ms": round(max(baseline_timings_ms), 3),
            "price_index_build_operations": baseline_index_rebuild_operations,
        },
        "comparison": {
            "avg_ms_delta": round(avg_baseline_ms - avg_optimized_ms, 3),
            "avg_ms_reduction_pct": round(((avg_baseline_ms - avg_optimized_ms) / avg_baseline_ms) * 100.0, 2) if avg_baseline_ms > 0 else None,
            "index_operation_reduction_pct": round(
                ((baseline_index_rebuild_operations - (price_rows * rounds)) / baseline_index_rebuild_operations) * 100.0,
                2,
            )
            if baseline_index_rebuild_operations > 0
            else None,
            "speedup_ratio": round(speedup_ratio, 3) if speedup_ratio is not None else None,
        },
    }


def _build_metrics_timeseries_legacy(
    financials: list[Any],
    price_history: list[Any],
) -> tuple[list[dict[str, Any]], int]:
    rows = derived_metrics._normalize_financial_rows(financials)
    prices = derived_metrics._normalize_price_rows(price_history)

    annual_rows = [row for row in rows if row["filing_type"] in derived_metrics.ANNUAL_FORMS]
    quarterly_rows = [row for row in rows if row["filing_type"] in derived_metrics.QUARTERLY_FORMS]

    index_rebuild_operations = 0
    output: list[dict[str, Any]] = []

    annual_points, annual_ops = _build_cadence_points_legacy(annual_rows, "annual", prices)
    output.extend(annual_points)
    index_rebuild_operations += annual_ops

    quarterly_points, quarterly_ops = _build_cadence_points_legacy(quarterly_rows, "quarterly", prices)
    output.extend(quarterly_points)
    index_rebuild_operations += quarterly_ops

    ttm_rows = derived_metrics._build_ttm_rows(quarterly_rows, annual_rows)
    ttm_points, ttm_ops = _build_cadence_points_legacy(ttm_rows, "ttm", prices, filing_type="TTM")
    output.extend(ttm_points)
    index_rebuild_operations += ttm_ops

    series = sorted(output, key=lambda item: (item["period_end"], item["cadence"]))
    return series, index_rebuild_operations


def _build_cadence_points_legacy(
    rows: list[dict[str, Any]],
    cadence: str,
    prices: list[dict[str, Any]],
    *,
    filing_type: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    output: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    index_operations = 0

    for row in rows:
        matched_price = _price_on_or_before_legacy(prices, row["period_end"])
        index_operations += len(prices)

        metrics = derived_metrics._compute_metrics(
            row["data"],
            previous["data"] if previous else None,
            matched_price,
            cadence=cadence,
            statement_type=row["statement_type"],
        )
        quality_flags = list(metrics["flags"])
        if cadence == "ttm":
            quality_flags.extend(row.get("ttm_validation_flags", []))
            quality_flags = sorted(set(quality_flags))
        output.append(
            {
                "cadence": cadence,
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "filing_type": filing_type or row["filing_type"],
                "metrics": metrics["values"],
                "provenance": {
                    "statement_type": row["statement_type"],
                    "statement_source": row["source"],
                    "price_source": matched_price["source"] if matched_price else None,
                    "formula_version": derived_metrics.FORMULA_VERSION,
                    "formula_ids": derived_metrics.formula_ids_for_derived_metrics(derived_metrics.METRIC_KEYS),
                    "metric_semantics": derived_metrics._metric_semantics(cadence, row["statement_type"]),
                    "market_cap_share_source": metrics["market_cap_share_source"],
                    "market_cap_share_source_is_proxy": metrics["market_cap_share_source_is_proxy"],
                    "per_share_metric_share_source": metrics["per_share_metric_share_source"],
                    "per_share_metric_share_source_is_proxy": metrics["per_share_metric_share_source_is_proxy"],
                },
                "quality": {
                    "available_metrics": metrics["available_metrics"],
                    "missing_metrics": metrics["missing_metrics"],
                    "coverage_ratio": metrics["coverage_ratio"],
                    "flags": quality_flags,
                },
            }
        )
        if cadence == "ttm":
            output[-1]["provenance"].update(
                {
                    "ttm_validation_status": row.get("ttm_validation_status", "valid"),
                    "ttm_construction": row.get("ttm_construction", "four_reported_quarters"),
                    "ttm_formula": "sum(Q1..Q4 comparable fiscal quarters) or annual - (Q1+Q2+Q3) for derived Q4",
                    "ttm_component_period_ends": [
                        component.isoformat() if hasattr(component, "isoformat") else component
                        for component in row.get("ttm_component_period_ends", [])
                    ],
                    "ttm_component_filing_types": row.get("ttm_component_filing_types", []),
                    "ttm_component_statement_ids": row.get("ttm_component_statement_ids", []),
                }
            )
        previous = row

    return output, index_operations


def _price_on_or_before_legacy(prices: list[dict[str, Any]], period_end: date) -> dict[str, Any] | None:
    if not prices:
        return None
    date_index = [entry["trade_date"] for entry in prices]
    insertion = bisect_right(date_index, period_end)
    if insertion <= 0:
        return None
    return prices[insertion - 1]


def _build_financial_statements(count: int) -> list[Any]:
    base_start = date(2010, 1, 1)
    statements: list[Any] = []
    for index in range(count):
        period_start = base_start + timedelta(days=90 * index)
        period_end = period_start + timedelta(days=89)
        revenue = 1000.0 + (index * 5.0)
        shares = 100.0 + (index * 0.1)

        statements.append(
            SimpleNamespace(
                id=index + 1,
                period_start=period_start,
                period_end=period_end,
                filing_type="10-Q",
                statement_type="canonical_xbrl",
                source="https://data.sec.gov/example",
                last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc),
                data={
                    "revenue": revenue,
                    "gross_profit": revenue * 0.4,
                    "operating_income": revenue * 0.2,
                    "net_income": revenue * 0.15,
                    "operating_cash_flow": revenue * 0.18,
                    "free_cash_flow": revenue * 0.12,
                    "total_assets": revenue * 2.0,
                    "current_assets": revenue * 0.7,
                    "current_liabilities": revenue * 0.4,
                    "current_debt": revenue * 0.05,
                    "long_term_debt": revenue * 0.3,
                    "stockholders_equity": revenue * 0.9,
                    "shares_outstanding": shares,
                    "weighted_average_diluted_shares": shares,
                    "stock_based_compensation": revenue * 0.03,
                    "share_buybacks": -(revenue * 0.02),
                    "dividends": -(revenue * 0.01),
                    "accounts_receivable": revenue * 0.2,
                    "inventory": revenue * 0.08,
                    "accounts_payable": revenue * 0.12,
                    "segment_breakdown": [
                        {"segment_name": "Products", "revenue": revenue * 0.7},
                        {"segment_name": "Services", "revenue": revenue * 0.3},
                    ],
                },
            )
        )
    return statements


def _build_price_history(count: int) -> list[Any]:
    base_date = date(2010, 1, 1)
    prices: list[Any] = []
    for index in range(count):
        prices.append(
            SimpleNamespace(
                trade_date=base_date + timedelta(days=index),
                close=50.0 + (index * 0.02),
                source="yahoo_finance",
            )
        )
    return prices


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Microbenchmark derived metrics price matching with and without cached date index")
    parser.add_argument("--financial-rows", type=int, default=240, help="Synthetic financial statement row count")
    parser.add_argument("--price-rows", type=int, default=20000, help="Synthetic price history row count")
    parser.add_argument("--rounds", type=int, default=5, help="Benchmark rounds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = benchmark_price_matching(
        financial_rows=args.financial_rows,
        price_rows=args.price_rows,
        rounds=args.rounds,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

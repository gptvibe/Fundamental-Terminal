from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import app.model_engine.models.dcf as dcf_model
import app.model_engine.models.reverse_dcf as reverse_dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.registry import MODEL_REGISTRY
from app.model_engine.types import CompanyDataset, FinancialPoint, MarketSnapshot


def build_benchmark_dataset() -> CompanyDataset:
    points = [
        _point(
            2025,
            {
                "revenue": 1250,
                "operating_income": 260,
                "net_income": 190,
                "income_tax_expense": 42,
                "free_cash_flow": 210,
                "operating_cash_flow": 280,
                "capex": 70,
                "cash_and_short_term_investments": 340,
                "cash_and_cash_equivalents": 280,
                "short_term_investments": 60,
                "current_debt": 90,
                "long_term_debt": 410,
                "shares_outstanding": 120,
                "weighted_average_diluted_shares": 118,
                "stockholders_equity": 980,
                "dividends": 45,
                "share_buybacks": 65,
                "debt_changes": -20,
                "stock_based_compensation": 30,
                "eps": 6.0,
            },
        ),
        _point(
            2024,
            {
                "revenue": 1160,
                "operating_income": 235,
                "net_income": 170,
                "income_tax_expense": 39,
                "free_cash_flow": 190,
                "operating_cash_flow": 258,
                "capex": 68,
                "cash_and_short_term_investments": 320,
                "cash_and_cash_equivalents": 265,
                "short_term_investments": 55,
                "current_debt": 95,
                "long_term_debt": 420,
                "shares_outstanding": 121,
                "weighted_average_diluted_shares": 119,
                "stockholders_equity": 930,
                "dividends": 40,
                "share_buybacks": 58,
                "debt_changes": -15,
                "stock_based_compensation": 28,
                "eps": 5.6,
            },
        ),
        _point(
            2023,
            {
                "revenue": 1085,
                "operating_income": 220,
                "net_income": 160,
                "income_tax_expense": 35,
                "free_cash_flow": 175,
                "operating_cash_flow": 245,
                "capex": 66,
                "cash_and_short_term_investments": 300,
                "cash_and_cash_equivalents": 246,
                "short_term_investments": 54,
                "current_debt": 105,
                "long_term_debt": 430,
                "shares_outstanding": 122,
                "weighted_average_diluted_shares": 120,
                "stockholders_equity": 900,
                "dividends": 36,
                "share_buybacks": 52,
                "debt_changes": -10,
                "stock_based_compensation": 26,
                "eps": 5.2,
            },
        ),
    ]
    return CompanyDataset(
        company_id=1,
        ticker="ACME",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
        market_snapshot=MarketSnapshot(
            latest_price=85.0,
            price_date=date(2026, 3, 21),
            price_source="yahoo_finance",
        ),
        financials=tuple(points),
    )


def benchmark_models(model_names: list[str] | None = None, *, rounds: int = 10) -> dict[str, Any]:
    _install_risk_free_mocks()
    dataset = build_benchmark_dataset()
    selected_names = model_names or ["dcf", "reverse_dcf", "roic", "capital_allocation", "dupont", "piotroski", "altman_z", "ratios"]
    results: list[dict[str, Any]] = []

    for model_name in selected_names:
        definition = MODEL_REGISTRY[model_name]
        timings_ms: list[float] = []
        last_result: dict[str, Any] | None = None
        for _ in range(rounds):
            started = time.perf_counter()
            computed = definition.compute(dataset)
            timings_ms.append((time.perf_counter() - started) * 1000.0)
            last_result = computed if isinstance(computed, dict) else None
        ordered = sorted(timings_ms)
        p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered))) - 1))
        results.append(
            {
                "model_name": definition.name,
                "model_version": definition.version,
                "rounds": rounds,
                "latency_ms": {
                    "min": round(min(timings_ms), 2),
                    "p50": round(statistics.median(timings_ms), 2),
                    "p95": round(ordered[p95_index], 2),
                    "max": round(max(timings_ms), 2),
                    "avg": round(statistics.mean(timings_ms), 2),
                },
                "model_status": (last_result or {}).get("model_status") or (last_result or {}).get("status") or "unknown",
            }
        )

    return {"ticker": dataset.ticker, "rounds": rounds, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark in-process model computation using cached SEC-first datasets")
    parser.add_argument("--models", default="", help="Comma-separated model names")
    parser.add_argument("--rounds", type=int, default=10, help="Benchmark rounds per model")
    args = parser.parse_args()

    requested_models = [item.strip().lower() for item in args.models.split(",") if item.strip()] or None
    payload = benchmark_models(requested_models, rounds=args.rounds)
    print(json.dumps(payload, indent=2))
    return 0


def _install_risk_free_mocks() -> None:
    dcf_model.get_latest_risk_free_rate = _mock_risk_free  # type: ignore[assignment]
    reverse_dcf_model.get_latest_risk_free_rate = _mock_risk_free  # type: ignore[assignment]
    roic_model.get_latest_risk_free_rate = _mock_risk_free  # type: ignore[assignment]


def _mock_risk_free(*_args: Any, **_kwargs: Any):
    return SimpleNamespace(
        source_name="U.S. Treasury Daily Par Yield Curve",
        tenor="10y",
        observation_date=date(2026, 3, 20),
        rate_used=0.042,
        fetched_at=datetime(2026, 3, 21, tzinfo=timezone.utc),
    )


def _point(year: int, data: dict[str, float | int | None]) -> FinancialPoint:
    return FinancialPoint(
        statement_id=year,
        filing_type="10-K",
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        source="sec",
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        data=data,
    )


if __name__ == "__main__":
    raise SystemExit(main())
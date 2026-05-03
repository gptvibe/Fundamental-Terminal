from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import sqrt
from statistics import fmean
from types import SimpleNamespace
from typing import Any, Callable, Iterator, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

import app.model_engine.models.dcf as dcf_model
import app.model_engine.engine as model_engine_module
import app.model_engine.models.residual_income as residual_income_model
import app.model_engine.models.reverse_dcf as reverse_dcf_model
import app.model_engine.models.roic as roic_model
from app.model_engine.engine import ModelEngine, build_company_dataset, build_market_snapshot
from app.models import Company, CompanyOilScenarioOverlaySnapshot, EarningsModelPoint, FinancialStatement, ModelEvaluationRun, PriceHistory
from app.services.cache_queries import latest_price_as_of, select_point_in_time_financials
from app.services.oil_overlay_engine import OilCurveYearPoint, OilOverlayEngineInputs, compute_oil_fair_value_overlay
from app.services.oil_scenario import _annualize_curve_series, _resolve_default_long_term_anchor, _resolve_realized_spread_defaults, _resolve_selected_benchmark_id, _resolve_sensitivity_source, _validated_direct_company_evidence
from app.services.risk_free_rate import RiskFreeRateSnapshot

SUPPORTED_EVALUATION_MODELS = ("dcf", "reverse_dcf", "residual_income", "roic", "earnings")
FIXTURE_SUITE_KEY = "historical_fixture_v1"
FIXTURE_CANDIDATE_LABEL = "fixture_baseline_v1"
OIL_OVERLAY_FIXTURE_SUITE_KEY = "oil_overlay_point_in_time_v1"
OIL_OVERLAY_FIXTURE_CANDIDATE_LABEL = "oil_overlay_fixture_v1"
OIL_OVERLAY_BASE_MODEL = "oil_overlay_base"
OIL_OVERLAY_ADJUSTED_MODEL = "oil_overlay_adjusted"
FIXTURE_RISK_FREE_RATE = 0.042
FIXTURE_RISK_FREE_OBSERVATION_DATE = date(2026, 3, 20)
DEFAULT_HORIZON_DAYS = 420
DEFAULT_EARNINGS_HORIZON_DAYS = 30
METRIC_KEYS = (
    "sample_count",
    "calibration",
    "stability",
    "mean_absolute_error",
    "root_mean_square_error",
    "mean_signed_error",
)


@dataclass(frozen=True, slots=True)
class EvaluationCompanyBundle:
    company: Any
    financials: tuple[Any, ...]
    prices: tuple[Any, ...]
    earnings_points: tuple[Any, ...]
    oil_overlay_snapshots: tuple[Any, ...] = tuple()


def normalize_requested_models(model_names: Sequence[str] | None) -> list[str]:
    if not model_names:
        return list(SUPPORTED_EVALUATION_MODELS)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_name in model_names:
        model_name = str(raw_name).strip().lower()
        if not model_name:
            continue
        if model_name not in SUPPORTED_EVALUATION_MODELS:
            raise ValueError(f"Unsupported evaluation model '{raw_name}'")
        if model_name in seen:
            continue
        seen.add(model_name)
        normalized.append(model_name)
    return normalized


def load_fixture_bundles(suite_key: str = FIXTURE_SUITE_KEY) -> list[EvaluationCompanyBundle]:
    if suite_key != FIXTURE_SUITE_KEY:
        raise ValueError(f"Unsupported fixture suite '{suite_key}'")

    company_specs = [
        {
            "id": 101,
            "ticker": "ACME",
            "name": "Acme Systems",
            "sector": "Technology",
            "industry": "Software",
            "annuals": [
                (2019, 820.0, 120.0, 96.0, 102.0, 140.0, 38.0, 240.0, 55.0, 210.0, 116.0),
                (2020, 875.0, 132.0, 104.0, 111.0, 148.0, 37.0, 256.0, 54.0, 228.0, 115.0),
                (2021, 940.0, 146.0, 116.0, 124.0, 162.0, 38.0, 278.0, 52.0, 246.0, 114.0),
                (2022, 1015.0, 164.0, 130.0, 141.0, 181.0, 40.0, 304.0, 50.0, 268.0, 113.0),
                (2023, 1105.0, 186.0, 149.0, 159.0, 202.0, 43.0, 334.0, 48.0, 294.0, 112.0),
                (2024, 1208.0, 212.0, 170.0, 181.0, 229.0, 47.0, 368.0, 46.0, 322.0, 111.0),
            ],
            "prices": [
                (date(2022, 1, 31), 72.0),
                (date(2022, 4, 30), 76.0),
                (date(2022, 7, 31), 81.0),
                (date(2022, 10, 31), 84.0),
                (date(2023, 1, 31), 86.0),
                (date(2023, 4, 30), 91.0),
                (date(2023, 7, 31), 96.0),
                (date(2023, 10, 31), 101.0),
                (date(2024, 1, 31), 106.0),
                (date(2024, 4, 30), 112.0),
                (date(2024, 7, 31), 119.0),
                (date(2024, 10, 31), 124.0),
                (date(2025, 1, 31), 129.0),
                (date(2025, 4, 30), 136.0),
                (date(2025, 7, 31), 142.0),
                (date(2025, 10, 31), 149.0),
                (date(2026, 1, 31), 155.0),
            ],
            "earnings": [
                (date(2023, 3, 31), date(2023, 5, 10), 66.0, 4.0, 0.08),
                (date(2023, 6, 30), date(2023, 8, 9), 69.0, 3.0, 0.09),
                (date(2023, 9, 30), date(2023, 11, 8), 71.0, 2.0, 0.11),
                (date(2023, 12, 31), date(2024, 2, 14), 75.0, 4.0, 0.13),
                (date(2024, 3, 31), date(2024, 5, 8), 77.0, 2.0, 0.15),
                (date(2024, 6, 30), date(2024, 8, 7), 80.0, 3.0, 0.16),
            ],
        },
        {
            "id": 202,
            "ticker": "BOLT",
            "name": "Bolt Industrial",
            "sector": "Industrials",
            "industry": "Electrical Equipment",
            "annuals": [
                (2019, 640.0, 88.0, 70.0, 76.0, 122.0, 34.0, 196.0, 44.0, 174.0, 92.0),
                (2020, 684.0, 94.0, 74.0, 81.0, 129.0, 35.0, 205.0, 44.0, 182.0, 92.0),
                (2021, 733.0, 103.0, 81.0, 90.0, 138.0, 35.0, 216.0, 43.0, 191.0, 91.0),
                (2022, 791.0, 114.0, 90.0, 100.0, 149.0, 36.0, 229.0, 42.0, 203.0, 90.0),
                (2023, 858.0, 128.0, 101.0, 112.0, 164.0, 38.0, 244.0, 40.0, 216.0, 89.0),
                (2024, 932.0, 144.0, 114.0, 126.0, 182.0, 40.0, 262.0, 39.0, 232.0, 88.0),
            ],
            "prices": [
                (date(2022, 1, 31), 58.0),
                (date(2022, 4, 30), 61.0),
                (date(2022, 7, 31), 65.0),
                (date(2022, 10, 31), 67.0),
                (date(2023, 1, 31), 69.0),
                (date(2023, 4, 30), 72.0),
                (date(2023, 7, 31), 76.0),
                (date(2023, 10, 31), 79.0),
                (date(2024, 1, 31), 83.0),
                (date(2024, 4, 30), 87.0),
                (date(2024, 7, 31), 92.0),
                (date(2024, 10, 31), 95.0),
                (date(2025, 1, 31), 99.0),
                (date(2025, 4, 30), 103.0),
                (date(2025, 7, 31), 108.0),
                (date(2025, 10, 31), 112.0),
                (date(2026, 1, 31), 117.0),
            ],
            "earnings": [
                (date(2023, 3, 31), date(2023, 5, 9), 58.0, 2.0, 0.05),
                (date(2023, 6, 30), date(2023, 8, 8), 61.0, 3.0, 0.06),
                (date(2023, 9, 30), date(2023, 11, 7), 63.0, 2.0, 0.07),
                (date(2023, 12, 31), date(2024, 2, 13), 66.0, 3.0, 0.08),
                (date(2024, 3, 31), date(2024, 5, 7), 68.0, 2.0, 0.09),
                (date(2024, 6, 30), date(2024, 8, 6), 70.0, 2.0, 0.10),
            ],
        },
    ]

    bundles: list[EvaluationCompanyBundle] = []
    for spec in company_specs:
        company = SimpleNamespace(
            id=spec["id"],
            ticker=spec["ticker"],
            cik=f"{spec['id']:010d}",
            name=spec["name"],
            sector=spec["sector"],
            market_sector=spec["sector"],
            market_industry=spec["industry"],
        )
        financials = []
        for index, annual in enumerate(spec["annuals"], start=1):
            year, revenue, operating_income, net_income, free_cash_flow, operating_cash_flow, capex, equity, current_debt, long_term_debt, shares = annual
            acceptance_at = datetime(year + 1, 2, 15, 14, tzinfo=timezone.utc)
            financials.append(
                SimpleNamespace(
                    id=spec["id"] * 100 + index,
                    company_id=spec["id"],
                    filing_type="10-K",
                    statement_type="canonical_xbrl",
                    period_start=date(year, 1, 1),
                    period_end=date(year, 12, 31),
                    source="https://data.sec.gov/api/xbrl/companyfacts/example.json",
                    last_updated=acceptance_at,
                    last_checked=acceptance_at,
                    filing_acceptance_at=acceptance_at,
                    fetch_timestamp=acceptance_at,
                    data={
                        "revenue": revenue,
                        "operating_income": operating_income,
                        "net_income": net_income,
                        "income_tax_expense": round(operating_income * 0.18, 4),
                        "free_cash_flow": free_cash_flow,
                        "operating_cash_flow": operating_cash_flow,
                        "capex": capex,
                        "cash_and_short_term_investments": round(120 + year * 4.5, 4),
                        "cash_and_cash_equivalents": round(110 + year * 4.0, 4),
                        "short_term_investments": round(10 + year * 0.5, 4),
                        "current_debt": current_debt,
                        "long_term_debt": long_term_debt,
                        "shares_outstanding": shares,
                        "weighted_average_diluted_shares": shares - 1,
                        "stockholders_equity": equity,
                        "total_assets": round(equity + current_debt + long_term_debt + 180, 4),
                        "total_liabilities": round(current_debt + long_term_debt + 140, 4),
                        "dividends": round(net_income * 0.15, 4),
                        "share_buybacks": round(free_cash_flow * 0.12, 4),
                        "debt_changes": -6.0,
                        "stock_based_compensation": round(revenue * 0.015, 4),
                        "eps": round(net_income / shares, 4),
                        "segment_breakdown": [],
                    },
                )
            )

        prices = []
        for index, (trade_date, close) in enumerate(spec["prices"], start=1):
            observed_at = datetime.combine(trade_date, time.max, tzinfo=timezone.utc)
            prices.append(
                SimpleNamespace(
                    id=spec["id"] * 1000 + index,
                    company_id=spec["id"],
                    trade_date=trade_date,
                    close=close,
                    volume=1_500_000 + index * 10_000,
                    source="yahoo_finance",
                    last_updated=observed_at,
                    fetch_timestamp=observed_at,
                    last_checked=observed_at,
                )
            )

        earnings_points = []
        for index, (period_end, checked_at_date, quality_score, quality_delta, eps_drift) in enumerate(spec["earnings"], start=1):
            checked_at = datetime.combine(checked_at_date, time.max, tzinfo=timezone.utc)
            earnings_points.append(
                SimpleNamespace(
                    id=spec["id"] * 10000 + index,
                    company_id=spec["id"],
                    period_start=date(period_end.year, max(period_end.month - 2, 1), 1),
                    period_end=period_end,
                    filing_type="10-Q",
                    quality_score=quality_score,
                    quality_score_delta=quality_delta,
                    eps_drift=eps_drift,
                    earnings_momentum_drift=round(eps_drift * 1.15, 6),
                    segment_contribution_delta=0.03,
                    release_statement_coverage_ratio=0.92,
                    fallback_ratio=0.0,
                    stale_period_warning=False,
                    explainability={
                        "formula_version": "sec_earnings_intel_v1",
                        "period_end": period_end.isoformat(),
                        "quality_formula": "quality_score_delta + cash_conversion",
                        "eps_drift_formula": "reported_eps - implied_eps",
                    },
                    quality_flags=[],
                    source_statement_ids=[index],
                    source_release_ids=[index],
                    last_updated=checked_at,
                    last_checked=checked_at,
                )
            )

        bundles.append(
            EvaluationCompanyBundle(
                company=company,
                financials=tuple(sorted(financials, key=lambda item: item.period_end, reverse=True)),
                prices=tuple(sorted(prices, key=lambda item: item.trade_date)),
                earnings_points=tuple(sorted(earnings_points, key=lambda item: item.period_end)),
            )
        )

    return bundles


def load_company_bundles(session: Session, tickers: Sequence[str]) -> list[EvaluationCompanyBundle]:
    normalized = [ticker.strip().upper() for ticker in tickers if ticker.strip()]
    if not normalized:
        return []

    companies = list(
        session.execute(
            select(Company).where(Company.ticker.in_(normalized)).order_by(Company.ticker.asc())
        ).scalars()
    )
    company_ids = [company.id for company in companies]
    if not company_ids:
        return []

    financial_rows = list(
        session.execute(
            select(FinancialStatement)
            .where(
                FinancialStatement.company_id.in_(company_ids),
                FinancialStatement.statement_type == "canonical_xbrl",
            )
            .order_by(FinancialStatement.company_id.asc(), FinancialStatement.period_end.desc(), FinancialStatement.id.desc())
        ).scalars()
    )
    price_rows = list(
        session.execute(
            select(PriceHistory)
            .where(PriceHistory.company_id.in_(company_ids))
            .order_by(PriceHistory.company_id.asc(), PriceHistory.trade_date.asc(), PriceHistory.id.asc())
        ).scalars()
    )
    earnings_rows = list(
        session.execute(
            select(EarningsModelPoint)
            .where(EarningsModelPoint.company_id.in_(company_ids))
            .order_by(EarningsModelPoint.company_id.asc(), EarningsModelPoint.period_end.asc(), EarningsModelPoint.id.asc())
        ).scalars()
    )
    oil_overlay_rows = list(
        session.execute(
            select(CompanyOilScenarioOverlaySnapshot)
            .where(CompanyOilScenarioOverlaySnapshot.company_id.in_(company_ids))
            .order_by(
                CompanyOilScenarioOverlaySnapshot.company_id.asc(),
                CompanyOilScenarioOverlaySnapshot.snapshot_date.asc(),
                CompanyOilScenarioOverlaySnapshot.id.asc(),
            )
        ).scalars()
    )

    financials_by_company: dict[int, list[Any]] = defaultdict(list)
    prices_by_company: dict[int, list[Any]] = defaultdict(list)
    earnings_by_company: dict[int, list[Any]] = defaultdict(list)
    oil_overlays_by_company: dict[int, list[Any]] = defaultdict(list)
    for row in financial_rows:
        financials_by_company[row.company_id].append(row)
    for row in price_rows:
        prices_by_company[row.company_id].append(row)
    for row in earnings_rows:
        earnings_by_company[row.company_id].append(row)
    for row in oil_overlay_rows:
        oil_overlays_by_company[row.company_id].append(row)

    bundles: list[EvaluationCompanyBundle] = []
    by_ticker = {company.ticker.upper(): company for company in companies}
    for ticker in normalized:
        company = by_ticker.get(ticker)
        if company is None:
            continue
        bundles.append(
            EvaluationCompanyBundle(
                company=company,
                financials=tuple(financials_by_company.get(company.id, [])),
                prices=tuple(prices_by_company.get(company.id, [])),
                earnings_points=tuple(earnings_by_company.get(company.id, [])),
                oil_overlay_snapshots=tuple(oil_overlays_by_company.get(company.id, [])),
            )
        )
    return bundles


def load_oil_overlay_fixture_bundles(suite_key: str = OIL_OVERLAY_FIXTURE_SUITE_KEY) -> list[EvaluationCompanyBundle]:
    if suite_key != OIL_OVERLAY_FIXTURE_SUITE_KEY:
        raise ValueError(f"Unsupported oil overlay fixture suite '{suite_key}'")

    def _price_row(company_id: int, trade_date: date, close: float, index: int) -> Any:
        observed_at = datetime.combine(trade_date, time.max, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=company_id * 1000 + index,
            company_id=company_id,
            trade_date=trade_date,
            close=close,
            volume=2_000_000 + index * 10_000,
            source="yahoo_finance",
            last_updated=observed_at,
            fetch_timestamp=observed_at,
            last_checked=observed_at,
        )

    def _snapshot_row(company_id: int, snapshot_date: date, payload: dict[str, Any], index: int) -> Any:
        fetched_at = datetime.combine(snapshot_date, time.max, tzinfo=timezone.utc)
        return SimpleNamespace(
            id=company_id * 100 + index,
            company_id=company_id,
            snapshot_date=snapshot_date,
            payload=payload,
            is_stale=False,
            fetched_at=fetched_at,
            created_at=fetched_at,
        )

    xom_company = SimpleNamespace(
        id=401,
        ticker="XOMF",
        cik="0000034088",
        name="Fixture Exxon Integrated",
        sector="Energy",
        market_sector="Energy",
        market_industry="Oil & Gas Integrated",
    )
    oxy_company = SimpleNamespace(
        id=402,
        ticker="OXYF",
        cik="0000797468",
        name="Fixture Occidental Upstream",
        sector="Energy",
        market_sector="Energy",
        market_industry="Oil & Gas E&P",
    )

    xom_prices = tuple(
        _price_row(401, trade_date, close, index)
        for index, (trade_date, close) in enumerate(
            [
                (date(2024, 5, 15), 100.0),
                (date(2024, 11, 15), 110.0),
                (date(2025, 5, 15), 118.0),
                (date(2025, 11, 15), 124.0),
                (date(2026, 5, 15), 130.0),
            ],
            start=1,
        )
    )
    oxy_prices = tuple(
        _price_row(402, trade_date, close, index)
        for index, (trade_date, close) in enumerate(
            [
                (date(2024, 5, 15), 60.0),
                (date(2024, 11, 15), 68.0),
                (date(2025, 5, 15), 74.0),
                (date(2025, 11, 15), 79.0),
                (date(2026, 5, 15), 84.0),
            ],
            start=1,
        )
    )

    xom_snapshots = (
        _snapshot_row(
            401,
            date(2024, 5, 15),
            _fixture_oil_overlay_payload(
                as_of="2024-05-15",
                oil_exposure_type="integrated",
                oil_support_status="supported",
                oil_support_reasons=["integrated_oil_supported_v1"],
                benchmark="brent",
                spot_points=[("2024-03-15", 78.0), ("2024-04-15", 80.0), ("2024-05-15", 82.0)],
                baseline_points=[("2024-06", 85.0), ("2025-01", 88.0), ("2026-01", 84.0)],
                annual_after_tax_sensitivity=650_000_000.0,
                sensitivity_kind="disclosed",
                diluted_shares=4_200_000_000.0,
                current_realized_spread=-2.0,
                evaluation_base_fair_value_per_share=108.0,
            ),
            1,
        ),
        _snapshot_row(
            401,
            date(2025, 5, 15),
            _fixture_oil_overlay_payload(
                as_of="2025-05-15",
                oil_exposure_type="integrated",
                oil_support_status="supported",
                oil_support_reasons=["integrated_oil_supported_v1"],
                benchmark="brent",
                spot_points=[("2025-03-15", 72.0), ("2025-04-15", 74.0), ("2025-05-15", 75.0)],
                baseline_points=[("2025-06", 78.0), ("2026-01", 81.0), ("2027-01", 79.0)],
                annual_after_tax_sensitivity=650_000_000.0,
                sensitivity_kind="disclosed",
                diluted_shares=4_150_000_000.0,
                current_realized_spread=-1.5,
                evaluation_base_fair_value_per_share=120.0,
            ),
            2,
        ),
    )
    oxy_snapshots = (
        _snapshot_row(
            402,
            date(2024, 5, 15),
            _fixture_oil_overlay_payload(
                as_of="2024-05-15",
                oil_exposure_type="upstream",
                oil_support_status="supported",
                oil_support_reasons=["upstream_oil_supported_v1"],
                benchmark="wti",
                spot_points=[("2024-03-15", 74.0), ("2024-04-15", 76.0), ("2024-05-15", 77.0)],
                baseline_points=[("2024-06", 81.0), ("2025-01", 83.0), ("2026-01", 80.0)],
                annual_after_tax_sensitivity=420_000_000.0,
                sensitivity_kind="derived_from_official",
                diluted_shares=950_000_000.0,
                current_realized_spread=-3.5,
                evaluation_base_fair_value_per_share=66.0,
            ),
            1,
        ),
        _snapshot_row(
            402,
            date(2025, 5, 15),
            _fixture_oil_overlay_payload(
                as_of="2025-05-15",
                oil_exposure_type="upstream",
                oil_support_status="supported",
                oil_support_reasons=["upstream_oil_supported_v1"],
                benchmark="wti",
                spot_points=[("2025-03-15", 69.0), ("2025-04-15", 70.0), ("2025-05-15", 71.0)],
                baseline_points=[("2025-06", 75.0), ("2026-01", 77.0), ("2027-01", 76.0)],
                annual_after_tax_sensitivity=440_000_000.0,
                sensitivity_kind="derived_from_official",
                diluted_shares=940_000_000.0,
                current_realized_spread=-3.0,
                evaluation_base_fair_value_per_share=72.0,
            ),
            2,
        ),
    )

    return [
        EvaluationCompanyBundle(company=xom_company, financials=tuple(), prices=xom_prices, earnings_points=tuple(), oil_overlay_snapshots=xom_snapshots),
        EvaluationCompanyBundle(company=oxy_company, financials=tuple(), prices=oxy_prices, earnings_points=tuple(), oil_overlay_snapshots=oxy_snapshots),
    ]


def build_fixed_risk_free_provider(
    *,
    rate_used: float = FIXTURE_RISK_FREE_RATE,
    observation_date: date = FIXTURE_RISK_FREE_OBSERVATION_DATE,
) -> Callable[[date | None], RiskFreeRateSnapshot]:
    def _provider(as_of: date | None = None) -> RiskFreeRateSnapshot:
        effective_date = as_of or observation_date
        return RiskFreeRateSnapshot(
            source_name="Model Evaluation Synthetic Treasury Curve",
            tenor="10y_fixture",
            observation_date=effective_date,
            rate_used=rate_used,
            fetched_at=datetime.combine(effective_date, time.max, tzinfo=timezone.utc),
        )

    return _provider


def run_model_evaluation(
    *,
    bundles: Sequence[EvaluationCompanyBundle],
    suite_key: str,
    candidate_label: str,
    baseline: dict[str, Any] | None = None,
    model_names: Sequence[str] | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    earnings_horizon_days: int = DEFAULT_EARNINGS_HORIZON_DAYS,
    persist_session: Session | None = None,
    risk_free_rate_provider: Callable[[date | None], RiskFreeRateSnapshot] | None = None,
) -> dict[str, Any]:
    normalized_models = normalize_requested_models(model_names)
    valuation_models = [model_name for model_name in normalized_models if model_name != "earnings"]
    samples_by_model: dict[str, list[dict[str, Any]]] = {model_name: [] for model_name in normalized_models}
    company_count = 0
    snapshot_count = 0
    all_as_of_values: list[str] = []
    all_future_as_of_values: list[str] = []

    patch_context = _patched_risk_free_provider(risk_free_rate_provider) if risk_free_rate_provider is not None else nullcontext()
    with patch_context:
        for bundle in bundles:
            company_count += 1
            if valuation_models:
                valuation_samples = _collect_valuation_samples(
                    bundle=bundle,
                    model_names=valuation_models,
                    horizon_days=horizon_days,
                )
                snapshot_count += valuation_samples.pop("__snapshot_count__", 0)
                for model_name, model_samples in valuation_samples.items():
                    samples_by_model[model_name].extend(model_samples)
                    all_as_of_values.extend(
                        [str(sample["as_of"]) for sample in model_samples if sample.get("as_of")]
                    )
                    all_future_as_of_values.extend(
                        [str(sample["future_as_of"]) for sample in model_samples if sample.get("future_as_of")]
                    )

            if "earnings" in normalized_models:
                earnings_samples = _collect_earnings_samples(bundle=bundle, horizon_days=earnings_horizon_days)
                samples_by_model["earnings"].extend(earnings_samples)
                all_as_of_values.extend(
                    [str(sample["as_of"]) for sample in earnings_samples if sample.get("as_of")]
                )
                all_future_as_of_values.extend(
                    [str(sample["future_as_of"]) for sample in earnings_samples if sample.get("future_as_of")]
                )

    metrics = {
        model_name: _aggregate_samples(samples_by_model[model_name])
        for model_name in normalized_models
    }
    deltas = _compute_metric_deltas(metrics, baseline.get("metrics") if isinstance(baseline, dict) else None)
    summary = {
        "company_count": company_count,
        "snapshot_count": snapshot_count,
        "model_count": len(normalized_models),
        "provenance_mode": "synthetic_fixture" if suite_key == FIXTURE_SUITE_KEY else "historical_cache",
        "earliest_as_of": min(all_as_of_values) if all_as_of_values else None,
        "latest_as_of": max(all_as_of_values) if all_as_of_values else None,
        "latest_future_as_of": max(all_future_as_of_values) if all_future_as_of_values else None,
    }
    artifacts = {
        "top_errors": {
            model_name: _top_error_samples(samples_by_model[model_name])
            for model_name in normalized_models
        }
    }
    completed_at = datetime.now(timezone.utc)
    payload = {
        "suite_key": suite_key,
        "candidate_label": candidate_label,
        "baseline_label": baseline.get("candidate_label") if isinstance(baseline, dict) else None,
        "status": "completed",
        "model_names": normalized_models,
        "configuration": {
            "horizon_days": horizon_days,
            "earnings_horizon_days": earnings_horizon_days,
            "bundle_count": len(bundles),
        },
        "summary": summary,
        "metrics": metrics,
        "deltas": deltas,
        "artifacts": artifacts,
        "completed_at": completed_at,
        "deltas_present": _deltas_present(deltas),
    }

    if persist_session is not None:
        run = ModelEvaluationRun(
            suite_key=suite_key,
            candidate_label=candidate_label,
            baseline_label=payload["baseline_label"],
            status="completed",
            model_names=normalized_models,
            configuration=payload["configuration"],
            summary=summary,
            metrics=metrics,
            deltas=deltas,
            artifacts=artifacts,
            completed_at=completed_at,
        )
        persist_session.add(run)
        persist_session.flush()
        payload["id"] = run.id
    else:
        payload["id"] = None

    return payload


def build_baseline_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "suite_key": result.get("suite_key"),
        "candidate_label": result.get("candidate_label"),
        "configuration": result.get("configuration") or {},
        "metrics": result.get("metrics") or {},
    }


def serialize_model_evaluation_run(run: ModelEvaluationRun | dict[str, Any]) -> dict[str, Any]:
    if isinstance(run, dict):
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        deltas = run.get("deltas") if isinstance(run.get("deltas"), dict) else {}
        return {
            "id": run.get("id"),
            "suite_key": str(run.get("suite_key") or ""),
            "candidate_label": str(run.get("candidate_label") or ""),
            "baseline_label": run.get("baseline_label"),
            "status": str(run.get("status") or "completed"),
            "completed_at": run.get("completed_at"),
            "configuration": run.get("configuration") if isinstance(run.get("configuration"), dict) else {},
            "summary": run.get("summary") if isinstance(run.get("summary"), dict) else {},
            "artifacts": run.get("artifacts") if isinstance(run.get("artifacts"), dict) else {},
            "models": _serialize_metrics(metrics, deltas),
            "deltas_present": _deltas_present(deltas),
        }

    return {
        "id": run.id,
        "suite_key": run.suite_key,
        "candidate_label": run.candidate_label,
        "baseline_label": run.baseline_label,
        "status": run.status,
        "completed_at": run.completed_at,
        "configuration": run.configuration if isinstance(run.configuration, dict) else {},
        "summary": run.summary if isinstance(run.summary, dict) else {},
        "artifacts": run.artifacts if isinstance(run.artifacts, dict) else {},
        "models": _serialize_metrics(run.metrics if isinstance(run.metrics, dict) else {}, run.deltas if isinstance(run.deltas, dict) else {}),
        "deltas_present": _deltas_present(run.deltas if isinstance(run.deltas, dict) else {}),
    }


def get_latest_model_evaluation_run(session: Session, suite_key: str | None = None) -> ModelEvaluationRun | None:
    statement = select(ModelEvaluationRun).where(ModelEvaluationRun.status == "completed")
    if suite_key:
        statement = statement.where(ModelEvaluationRun.suite_key == suite_key)
    statement = statement.order_by(ModelEvaluationRun.completed_at.desc().nullslast(), ModelEvaluationRun.created_at.desc(), ModelEvaluationRun.id.desc()).limit(1)
    return session.execute(statement).scalar_one_or_none()


def run_oil_overlay_point_in_time_evaluation(
    *,
    bundles: Sequence[EvaluationCompanyBundle],
    suite_key: str = OIL_OVERLAY_FIXTURE_SUITE_KEY,
    candidate_label: str = OIL_OVERLAY_FIXTURE_CANDIDATE_LABEL,
    baseline: dict[str, Any] | None = None,
    horizon_days: int = DEFAULT_HORIZON_DAYS,
    persist_session: Session | None = None,
) -> dict[str, Any]:
    base_samples: list[dict[str, Any]] = []
    overlay_samples: list[dict[str, Any]] = []
    comparison_samples: list[dict[str, Any]] = []
    all_as_of_values: list[str] = []
    all_future_as_of_values: list[str] = []
    company_summaries: dict[str, Any] = {}
    company_count = len(bundles)
    eligible_company_count = 0

    for bundle in bundles:
        previous_base_signal: float | None = None
        previous_overlay_signal: float | None = None
        company_base_samples: list[dict[str, Any]] = []
        company_overlay_samples: list[dict[str, Any]] = []
        company_flags: set[str] = set()

        for snapshot in bundle.oil_overlay_snapshots:
            sample = _build_oil_overlay_point_in_time_sample(
                bundle=bundle,
                snapshot=snapshot,
                horizon_days=horizon_days,
                previous_base_signal=previous_base_signal,
                previous_overlay_signal=previous_overlay_signal,
            )
            if sample is None:
                continue
            eligible_company_count += 1 if not company_base_samples and not company_overlay_samples else 0
            base_samples.append(sample["base"])
            overlay_samples.append(sample["overlay"])
            comparison_samples.append(sample["comparison"])
            company_base_samples.append(sample["base"])
            company_overlay_samples.append(sample["overlay"])
            company_flags.update(sample["comparison"].get("confidence_flags") or [])
            previous_base_signal = _as_float(sample["base"].get("predicted_signal"))
            previous_overlay_signal = _as_float(sample["overlay"].get("predicted_signal"))
            all_as_of_values.append(str(sample["base"]["as_of"]))
            all_future_as_of_values.append(str(sample["base"]["future_as_of"]))

        if company_base_samples and company_overlay_samples:
            company_summaries[bundle.company.ticker] = _build_company_oil_overlay_summary(
                ticker=bundle.company.ticker,
                base_samples=company_base_samples,
                overlay_samples=company_overlay_samples,
                confidence_flags=sorted(company_flags),
            )

    metrics = {
        OIL_OVERLAY_BASE_MODEL: _aggregate_samples(base_samples),
        OIL_OVERLAY_ADJUSTED_MODEL: _aggregate_samples(overlay_samples),
    }
    deltas = _compute_metric_deltas(metrics, baseline.get("metrics") if isinstance(baseline, dict) else None)
    comparison_summary = _build_oil_overlay_comparison_summary(base_samples, overlay_samples, comparison_samples)
    summary = {
        "company_count": company_count,
        "eligible_company_count": len(company_summaries),
        "snapshot_count": len(base_samples),
        "model_count": 2,
        "evaluation_focus": "oil_overlay",
        "provenance_mode": "synthetic_fixture" if suite_key == OIL_OVERLAY_FIXTURE_SUITE_KEY else "historical_cache",
        "earliest_as_of": min(all_as_of_values) if all_as_of_values else None,
        "latest_as_of": max(all_as_of_values) if all_as_of_values else None,
        "latest_future_as_of": max(all_future_as_of_values) if all_future_as_of_values else None,
        "comparison": comparison_summary,
    }
    artifacts = {
        "comparison": comparison_summary,
        "company_summaries": company_summaries,
        "top_errors": {
            OIL_OVERLAY_BASE_MODEL: _top_error_samples(base_samples),
            OIL_OVERLAY_ADJUSTED_MODEL: _top_error_samples(overlay_samples),
        },
    }
    completed_at = datetime.now(timezone.utc)
    payload = {
        "suite_key": suite_key,
        "candidate_label": candidate_label,
        "baseline_label": baseline.get("candidate_label") if isinstance(baseline, dict) else None,
        "status": "completed",
        "model_names": [OIL_OVERLAY_BASE_MODEL, OIL_OVERLAY_ADJUSTED_MODEL],
        "configuration": {
            "horizon_days": horizon_days,
            "bundle_count": len(bundles),
            "evaluation_focus": "oil_overlay",
        },
        "summary": summary,
        "metrics": metrics,
        "deltas": deltas,
        "artifacts": artifacts,
        "completed_at": completed_at,
        "deltas_present": _deltas_present(deltas),
    }

    if persist_session is not None:
        run = ModelEvaluationRun(
            suite_key=suite_key,
            candidate_label=candidate_label,
            baseline_label=payload["baseline_label"],
            status="completed",
            model_names=payload["model_names"],
            configuration=payload["configuration"],
            summary=summary,
            metrics=metrics,
            deltas=deltas,
            artifacts=artifacts,
            completed_at=completed_at,
        )
        persist_session.add(run)
        persist_session.flush()
        payload["id"] = run.id
    else:
        payload["id"] = None

    return payload


def _build_oil_overlay_point_in_time_sample(
    *,
    bundle: EvaluationCompanyBundle,
    snapshot: Any,
    horizon_days: int,
    previous_base_signal: float | None,
    previous_overlay_signal: float | None,
) -> dict[str, Any] | None:
    payload = dict(getattr(snapshot, "payload", {}) or {})
    exposure_profile = payload.get("exposure_profile") if isinstance(payload.get("exposure_profile"), dict) else {}
    if str(exposure_profile.get("oil_support_status") or "").lower() != "supported":
        return None

    as_of = _snapshot_as_of(snapshot)
    current_price_row = latest_price_as_of(list(bundle.prices), as_of)
    future_as_of = as_of + timedelta(days=horizon_days)
    future_price_row = latest_price_as_of(list(bundle.prices), future_as_of)
    if current_price_row is None or future_price_row is None:
        return None

    overlay_inputs = _build_oil_overlay_inputs_from_snapshot(
        bundle=bundle,
        payload=payload,
        as_of=as_of,
        current_share_price=float(current_price_row.close),
    )
    if overlay_inputs is None:
        return None

    overlay_result = compute_oil_fair_value_overlay(overlay_inputs)
    if overlay_result.scenario_fair_value_per_share is None:
        return None

    base_fair_value = float(overlay_inputs.base_fair_value_per_share)
    current_share_price = float(current_price_row.close)
    future_share_price = float(future_price_row.close)
    base_signal = safe_ratio(base_fair_value - current_share_price, current_share_price)
    overlay_signal = safe_ratio(overlay_result.scenario_fair_value_per_share - current_share_price, current_share_price)
    actual_signal = safe_ratio(future_share_price - current_share_price, current_share_price)
    if base_signal is None or overlay_signal is None or actual_signal is None:
        return None

    base_sample = _build_oil_overlay_metric_sample(
        ticker=bundle.company.ticker,
        as_of=as_of,
        future_as_of=future_as_of,
        predicted_signal=base_signal,
        actual_signal=actual_signal,
        previous_signal=previous_base_signal,
    )
    overlay_sample = _build_oil_overlay_metric_sample(
        ticker=bundle.company.ticker,
        as_of=as_of,
        future_as_of=future_as_of,
        predicted_signal=overlay_signal,
        actual_signal=actual_signal,
        previous_signal=previous_overlay_signal,
    )
    comparison = {
        "ticker": bundle.company.ticker,
        "as_of": as_of.date().isoformat(),
        "future_as_of": future_as_of.date().isoformat(),
        "base_abs_error": base_sample["abs_error"],
        "overlay_abs_error": overlay_sample["abs_error"],
        "overlay_improved": float(overlay_sample["abs_error"] or 0.0) < float(base_sample["abs_error"] or 0.0),
        "base_fair_value_per_share": _round_number(base_fair_value),
        "overlay_fair_value_per_share": _round_number(overlay_result.scenario_fair_value_per_share),
        "current_share_price": _round_number(current_share_price),
        "future_share_price": _round_number(future_share_price),
        "confidence_flags": list(overlay_result.confidence_flags),
    }
    return {"base": base_sample, "overlay": overlay_sample, "comparison": comparison}


def _build_oil_overlay_inputs_from_snapshot(
    *,
    bundle: EvaluationCompanyBundle,
    payload: dict[str, Any],
    as_of: datetime,
    current_share_price: float,
) -> OilOverlayEngineInputs | None:
    benchmark_series = [item for item in (payload.get("benchmark_series") or []) if isinstance(item, dict)]
    direct_company_evidence = _validated_direct_company_evidence(payload.get("direct_company_evidence"))
    benchmark_id = _resolve_selected_benchmark_id(benchmark_series, direct_company_evidence)
    benchmark_hint = str(benchmark_id or "").lower()
    base_series = next(
        (series for series in benchmark_series if benchmark_hint and "spot_history" in str(series.get("series_id") or "").lower() and benchmark_hint.split("_")[0] in str(series.get("series_id") or "").lower()),
        None,
    )
    if base_series is None:
        base_series = next((series for series in benchmark_series if "spot_history" in str(series.get("series_id") or "").lower()), None)
    scenario_series = next((series for series in benchmark_series if series.get("series_id") == benchmark_id), None)
    official_base_curve = _annualize_curve_series(base_series)
    scenario_curve = _annualize_curve_series(scenario_series)
    if not official_base_curve or not scenario_curve:
        return None

    raw_sensitivity = payload.get("sensitivity") if isinstance(payload.get("sensitivity"), dict) else None
    sensitivity_source_kind, sensitivity_value, sensitivity_payload = _resolve_sensitivity_source(raw_sensitivity, direct_company_evidence)
    if sensitivity_value is None:
        return None

    diluted_shares = _resolve_snapshot_diluted_shares(bundle=bundle, payload=payload, direct_company_evidence=direct_company_evidence, as_of=as_of)
    if diluted_shares in (None, 0):
        return None

    long_term_anchor = _resolve_default_long_term_anchor(scenario_curve)
    if long_term_anchor is None:
        return None

    realized_spread_defaults = _resolve_realized_spread_defaults(
        payload.get("exposure_profile") if isinstance(payload.get("exposure_profile"), dict) else {},
        direct_company_evidence,
    )
    base_fair_value_per_share = _resolve_snapshot_base_fair_value(bundle=bundle, payload=payload, as_of=as_of, current_share_price=current_share_price)
    if base_fair_value_per_share is None:
        return None

    confidence_flags = [str(flag) for flag in (payload.get("confidence_flags") or []) if isinstance(flag, str)]
    if isinstance(sensitivity_payload, dict):
        confidence_flags.extend(str(flag) for flag in (sensitivity_payload.get("confidence_flags") or []) if isinstance(flag, str))

    return OilOverlayEngineInputs(
        base_fair_value_per_share=base_fair_value_per_share,
        official_base_curve=tuple(OilCurveYearPoint(year=int(point["year"]), price=float(point["price"])) for point in official_base_curve),
        user_edited_short_term_curve=tuple(OilCurveYearPoint(year=int(point["year"]), price=float(point["price"])) for point in scenario_curve),
        user_long_term_anchor=long_term_anchor,
        fade_years=2,
        annual_after_tax_oil_sensitivity=sensitivity_value,
        diluted_shares=diluted_shares,
        sensitivity_source_kind=sensitivity_source_kind,
        current_share_price=current_share_price,
        realized_spread_mode=str(realized_spread_defaults.get("mode") or "benchmark_only"),
        current_realized_spread=_as_float(realized_spread_defaults.get("current_realized_spread")),
        custom_realized_spread=_as_float(realized_spread_defaults.get("custom_realized_spread")),
        mean_reversion_target_spread=_as_float(realized_spread_defaults.get("mean_reversion_target_spread")) or 0.0,
        mean_reversion_years=int(realized_spread_defaults.get("mean_reversion_years") or 0),
        realized_spread_reference_benchmark=(
            str(realized_spread_defaults.get("reference_benchmark")) if realized_spread_defaults.get("reference_benchmark") is not None else None
        ),
        oil_support_status="supported",
        confidence_flags=tuple(sorted(set(confidence_flags))),
    )


def _resolve_snapshot_base_fair_value(*, bundle: EvaluationCompanyBundle, payload: dict[str, Any], as_of: datetime, current_share_price: float) -> float | None:
    embedded = _as_float(payload.get("evaluation_base_fair_value_per_share"))
    if embedded is not None:
        return embedded

    visible_financials = select_point_in_time_financials(list(bundle.financials), as_of)
    if not visible_financials:
        return None
    dataset = build_company_dataset(bundle.company, visible_financials, build_market_snapshot(SimpleNamespace(close=current_share_price)), as_of_date=as_of)
    results = {
        item["model_name"]: item["result"]
        for item in ModelEngine(None).evaluate_models(dataset, model_names=["dcf", "residual_income"], created_at=as_of)
    }
    dcf_result = results.get("dcf") if isinstance(results.get("dcf"), dict) else None
    dcf_fair_value = _as_float((dcf_result or {}).get("fair_value_per_share"))
    if dcf_fair_value is not None:
        return dcf_fair_value
    residual_result = results.get("residual_income") if isinstance(results.get("residual_income"), dict) else None
    intrinsic_value = residual_result.get("intrinsic_value") if isinstance((residual_result or {}).get("intrinsic_value"), dict) else {}
    return _as_float(intrinsic_value.get("intrinsic_value_per_share"))


def _resolve_snapshot_diluted_shares(*, bundle: EvaluationCompanyBundle, payload: dict[str, Any], direct_company_evidence: dict[str, Any], as_of: datetime) -> float | None:
    evidence_shares = _as_float((direct_company_evidence.get("diluted_shares") or {}).get("value"))
    if evidence_shares is not None:
        return evidence_shares
    visible_financials = select_point_in_time_financials(list(bundle.financials), as_of)
    latest = visible_financials[0] if visible_financials else None
    if latest is None:
        return None
    data = getattr(latest, "data", None) if isinstance(getattr(latest, "data", None), dict) else {}
    return _as_float(data.get("weighted_average_diluted_shares")) or _as_float(data.get("shares_outstanding"))


def _build_oil_overlay_metric_sample(
    *,
    ticker: str,
    as_of: datetime,
    future_as_of: datetime,
    predicted_signal: float,
    actual_signal: float,
    previous_signal: float | None,
) -> dict[str, Any]:
    abs_error = abs(predicted_signal - actual_signal)
    stability = abs(predicted_signal - previous_signal) if previous_signal is not None else None
    return {
        "ticker": ticker,
        "as_of": as_of.date().isoformat(),
        "future_as_of": future_as_of.date().isoformat(),
        "predicted_signal": _round_number(predicted_signal),
        "actual_signal": _round_number(actual_signal),
        "abs_error": _round_number(abs_error),
        "signed_error": _round_number(predicted_signal - actual_signal),
        "calibration_hit": _sign(predicted_signal) == _sign(actual_signal),
        "stability_delta": _round_number(stability),
    }


def _build_oil_overlay_comparison_summary(
    base_samples: Sequence[dict[str, Any]],
    overlay_samples: Sequence[dict[str, Any]],
    comparison_samples: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    base_metrics = _aggregate_samples(base_samples)
    overlay_metrics = _aggregate_samples(overlay_samples)
    improved_count = sum(1 for item in comparison_samples if item.get("overlay_improved") is True)
    sample_count = len(comparison_samples)
    base_mae = _as_float(base_metrics.get("mean_absolute_error"))
    overlay_mae = _as_float(overlay_metrics.get("mean_absolute_error"))
    return {
        "sample_count": sample_count,
        "improved_sample_count": improved_count,
        "improvement_rate": _round_number(improved_count / sample_count) if sample_count else None,
        "base_mean_absolute_error": base_mae,
        "overlay_mean_absolute_error": overlay_mae,
        "mean_absolute_error_lift": _round_number(base_mae - overlay_mae) if base_mae is not None and overlay_mae is not None else None,
        "base_calibration": base_metrics.get("calibration"),
        "overlay_calibration": overlay_metrics.get("calibration"),
    }


def _build_company_oil_overlay_summary(
    *,
    ticker: str,
    base_samples: Sequence[dict[str, Any]],
    overlay_samples: Sequence[dict[str, Any]],
    confidence_flags: Sequence[str],
) -> dict[str, Any]:
    comparison = _build_oil_overlay_comparison_summary(base_samples, overlay_samples, [])
    comparison["sample_count"] = len(base_samples)
    comparison["ticker"] = ticker
    comparison["latest_as_of"] = max((str(item.get("as_of")) for item in overlay_samples if item.get("as_of")), default=None)
    comparison["confidence_flags"] = list(confidence_flags)
    return comparison


def _snapshot_as_of(snapshot: Any) -> datetime:
    fetched_at = _normalize_datetime(getattr(snapshot, "fetched_at", None))
    if fetched_at is not None:
        return fetched_at
    snapshot_date = getattr(snapshot, "snapshot_date", None)
    if isinstance(snapshot_date, date):
        return datetime.combine(snapshot_date, time.max, tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _fixture_oil_overlay_payload(
    *,
    as_of: str,
    oil_exposure_type: str,
    oil_support_status: str,
    oil_support_reasons: list[str],
    benchmark: str,
    spot_points: list[tuple[str, float]],
    baseline_points: list[tuple[str, float]],
    annual_after_tax_sensitivity: float,
    sensitivity_kind: str,
    diluted_shares: float,
    current_realized_spread: float,
    evaluation_base_fair_value_per_share: float,
) -> dict[str, Any]:
    benchmark_lower = benchmark.lower()
    series_prefix = "brent" if benchmark_lower == "brent" else "wti"
    sensitivity_status = "disclosed" if sensitivity_kind == "disclosed" else "ok"
    disclosed_sensitivity = {
        "status": "available" if sensitivity_kind == "disclosed" else "not_available",
        "reason": None if sensitivity_kind == "disclosed" else "No explicit annual oil sensitivity was disclosed.",
        "benchmark": benchmark_lower if sensitivity_kind == "disclosed" else None,
        "oil_price_change_per_bbl": 1.0 if sensitivity_kind == "disclosed" else None,
        "annual_after_tax_earnings_change": annual_after_tax_sensitivity if sensitivity_kind == "disclosed" else None,
        "annual_after_tax_sensitivity": annual_after_tax_sensitivity if sensitivity_kind == "disclosed" else None,
        "metric_basis": "annual_after_tax_earnings_usd" if sensitivity_kind == "disclosed" else None,
        "source_url": "https://www.sec.gov/Archives/edgar/data/example/oil.htm" if sensitivity_kind == "disclosed" else None,
        "accession_number": "0000000000-24-000001" if sensitivity_kind == "disclosed" else None,
        "filing_form": "10-K" if sensitivity_kind == "disclosed" else None,
        "confidence_flags": ["oil_sensitivity_disclosed"] if sensitivity_kind == "disclosed" else ["oil_sensitivity_not_available"],
        "provenance_sources": ["sec_edgar"],
    }
    realized_price_comparison = {
        "status": "available",
        "reason": None,
        "benchmark": benchmark_lower,
        "rows": [
            {
                "period_label": str(baseline_points[0][0])[:4],
                "benchmark": benchmark_lower,
                "realized_price": baseline_points[0][1] + current_realized_spread,
                "benchmark_price": baseline_points[0][1],
                "realized_percent_of_benchmark": _round_number(((baseline_points[0][1] + current_realized_spread) / baseline_points[0][1]) * 100.0),
                "premium_discount": current_realized_spread,
            }
        ],
        "confidence_flags": ["realized_vs_benchmark_available"],
        "provenance_sources": ["sec_edgar"],
    }
    return {
        "status": oil_support_status,
        "fetched_at": f"{as_of}T23:59:59Z",
        "as_of": as_of,
        "last_refreshed_at": f"{as_of}T23:59:59Z",
        "strict_official_mode": False,
        "exposure_profile": {
            "profile_id": oil_exposure_type,
            "label": oil_exposure_type.replace("_", " ").title(),
            "oil_exposure_type": oil_exposure_type,
            "oil_support_status": oil_support_status,
            "oil_support_reasons": oil_support_reasons,
            "relevance_reasons": oil_support_reasons,
            "hedging_signal": "unknown",
            "pass_through_signal": "unknown",
            "evidence": [],
        },
        "benchmark_series": [
            {
                "series_id": f"{series_prefix}_spot_history",
                "label": f"{series_prefix.upper()} spot history",
                "units": "usd_per_barrel",
                "status": "ok",
                "points": [
                    {"label": label, "value": value, "units": "usd_per_barrel", "observation_date": label}
                    for label, value in spot_points
                ],
                "latest_value": spot_points[-1][1],
                "latest_observation_date": spot_points[-1][0],
            },
            {
                "series_id": f"{series_prefix}_short_term_baseline",
                "label": f"{series_prefix.upper()} short-term official baseline",
                "units": "usd_per_barrel",
                "status": "ok",
                "points": [
                    {"label": label, "value": value, "units": "usd_per_barrel", "observation_date": label}
                    for label, value in baseline_points
                ],
                "latest_value": baseline_points[-1][1],
                "latest_observation_date": baseline_points[-1][0],
            },
        ],
        "sensitivity": {
            "metric_basis": "annual_after_tax_earnings_usd",
            "lookback_quarters": 4,
            "elasticity": annual_after_tax_sensitivity if sensitivity_kind != "disclosed" else None,
            "r_squared": 0.62 if sensitivity_kind != "disclosed" else None,
            "sample_size": 4 if sensitivity_kind != "disclosed" else 1,
            "direction": "positive_with_higher_oil",
            "status": sensitivity_status,
            "confidence_flags": ["derived_from_official"] if sensitivity_kind != "disclosed" else ["oil_sensitivity_disclosed"],
        },
        "direct_company_evidence": {
            "status": "available",
            "checked_at": f"{as_of}T23:59:59Z",
            "parser_confidence_flags": ["weighted_average_diluted_shares_companyfacts", "realized_vs_benchmark_available"],
            "disclosed_sensitivity": disclosed_sensitivity,
            "diluted_shares": {
                "status": "available",
                "reason": None,
                "source_url": "https://data.sec.gov/api/xbrl/companyfacts/example.json",
                "accession_number": "0000000000-24-000001",
                "filing_form": "10-K",
                "confidence_flags": ["weighted_average_diluted_shares_companyfacts"],
                "provenance_sources": ["sec_companyfacts"],
                "value": diluted_shares,
                "unit": "shares",
                "taxonomy": "us-gaap",
                "tag": "WeightedAverageNumberOfDilutedSharesOutstanding",
            },
            "realized_price_comparison": realized_price_comparison,
        },
        "confidence_flags": ["fixture_oil_overlay_snapshot"],
        "evaluation_base_fair_value_per_share": evaluation_base_fair_value_per_share,
    }


def _collect_valuation_samples(
    *,
    bundle: EvaluationCompanyBundle,
    model_names: Sequence[str],
    horizon_days: int,
) -> dict[str, Any]:
    samples: dict[str, list[dict[str, Any]]] = {model_name: [] for model_name in model_names}
    previous_signals: dict[str, float] = {}
    snapshot_count = 0

    for as_of in _snapshot_cutoffs(bundle.financials, bundle.prices, horizon_days):
        visible_financials = select_point_in_time_financials(list(bundle.financials), as_of)
        current_price = latest_price_as_of(list(bundle.prices), as_of)
        if not visible_financials or current_price is None:
            continue
        future_as_of = as_of + timedelta(days=horizon_days)
        future_price = latest_price_as_of(list(bundle.prices), future_as_of)
        future_financials = select_point_in_time_financials(list(bundle.financials), future_as_of)
        if future_price is None or not future_financials:
            continue

        current_dataset = build_company_dataset(
            bundle.company,
            visible_financials,
            build_market_snapshot(current_price),
            as_of_date=as_of,
        )
        future_dataset = build_company_dataset(
            bundle.company,
            future_financials,
            build_market_snapshot(future_price),
            as_of_date=future_as_of,
        )
        current_results = {
            item["model_name"]: item["result"]
            for item in ModelEngine(None).evaluate_models(current_dataset, model_names=list(model_names), created_at=as_of)
        }
        future_results = {
            item["model_name"]: item["result"]
            for item in ModelEngine(None).evaluate_models(future_dataset, model_names=list(model_names), created_at=future_as_of)
        }
        snapshot_count += 1

        for model_name in model_names:
            current_result = current_results.get(model_name)
            if not isinstance(current_result, dict):
                continue
            sample = _build_valuation_sample(
                model_name=model_name,
                company=bundle.company,
                as_of=as_of,
                future_as_of=future_as_of,
                current_price=float(current_price.close),
                future_price=float(future_price.close),
                current_financials=visible_financials,
                future_financials=future_financials,
                current_result=current_result,
                future_result=future_results.get(model_name) if isinstance(future_results.get(model_name), dict) else None,
                previous_signal=previous_signals.get(model_name),
            )
            if sample is None:
                continue
            samples[model_name].append(sample)
            if sample.get("predicted_signal") is not None:
                previous_signals[model_name] = float(sample["predicted_signal"])

    samples["__snapshot_count__"] = snapshot_count
    return samples


def _collect_earnings_samples(*, bundle: EvaluationCompanyBundle, horizon_days: int) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    previous_signal: float | None = None
    prices = list(bundle.prices)

    for point in bundle.earnings_points:
        checked_at = _normalize_datetime(getattr(point, "last_checked", None))
        if checked_at is None:
            continue
        current_price = latest_price_as_of(prices, checked_at)
        future_price = latest_price_as_of(prices, checked_at + timedelta(days=horizon_days))
        if current_price is None or future_price is None:
            continue

        quality_delta = _as_float(getattr(point, "quality_score_delta", None))
        eps_drift = _as_float(getattr(point, "eps_drift", None))
        if quality_delta is None and eps_drift is None:
            continue

        predicted_signal = 0.0
        if quality_delta is not None:
            predicted_signal += quality_delta / 100.0
        if eps_drift is not None:
            predicted_signal += eps_drift
        actual_signal = safe_ratio(float(future_price.close) - float(current_price.close), float(current_price.close))
        if actual_signal is None:
            continue

        abs_error = abs(predicted_signal - actual_signal)
        stability = abs(predicted_signal - previous_signal) if previous_signal is not None else None
        samples.append(
            {
                "ticker": bundle.company.ticker,
                "as_of": checked_at.date().isoformat(),
                "future_as_of": (checked_at + timedelta(days=horizon_days)).date().isoformat(),
                "predicted_signal": _round_number(predicted_signal),
                "actual_signal": _round_number(actual_signal),
                "abs_error": _round_number(abs_error),
                "signed_error": _round_number(predicted_signal - actual_signal),
                "calibration_hit": _sign(predicted_signal) == _sign(actual_signal),
                "stability_delta": _round_number(stability),
            }
        )
        previous_signal = predicted_signal

    return samples


def _build_valuation_sample(
    *,
    model_name: str,
    company: Any,
    as_of: datetime,
    future_as_of: datetime,
    current_price: float,
    future_price: float,
    current_financials: Sequence[Any],
    future_financials: Sequence[Any],
    current_result: dict[str, Any],
    future_result: dict[str, Any] | None,
    previous_signal: float | None,
) -> dict[str, Any] | None:
    if model_name in {"dcf", "residual_income"}:
        if model_name == "dcf":
            fair_value = _as_float(current_result.get("fair_value_per_share"))
        else:
            intrinsic_value = current_result.get("intrinsic_value")
            fair_value = _as_float((intrinsic_value or {}).get("intrinsic_value_per_share")) if isinstance(intrinsic_value, dict) else None
        if fair_value is None or current_price == 0:
            return None
        predicted_signal = safe_ratio(fair_value - current_price, current_price)
        actual_signal = safe_ratio(future_price - current_price, current_price)
    elif model_name == "reverse_dcf":
        predicted_signal = _as_float(current_result.get("implied_growth"))
        actual_signal = _realized_revenue_growth(current_financials, future_financials)
    elif model_name == "roic":
        predicted_signal = _as_float(current_result.get("spread_vs_capital_cost_proxy"))
        actual_signal = _as_float((future_result or {}).get("spread_vs_capital_cost_proxy"))
    else:
        return None

    if predicted_signal is None or actual_signal is None:
        return None

    abs_error = abs(predicted_signal - actual_signal)
    stability = abs(predicted_signal - previous_signal) if previous_signal is not None else None
    return {
        "ticker": company.ticker,
        "as_of": as_of.date().isoformat(),
        "future_as_of": future_as_of.date().isoformat(),
        "predicted_signal": _round_number(predicted_signal),
        "actual_signal": _round_number(actual_signal),
        "abs_error": _round_number(abs_error),
        "signed_error": _round_number(predicted_signal - actual_signal),
        "calibration_hit": _sign(predicted_signal) == _sign(actual_signal),
        "stability_delta": _round_number(stability),
    }


def _snapshot_cutoffs(financials: Sequence[Any], prices: Sequence[Any], horizon_days: int) -> list[datetime]:
    latest_trade_date = max((price.trade_date for price in prices), default=None)
    if latest_trade_date is None:
        return []
    final_cutoff = datetime.combine(latest_trade_date, time.max, tzinfo=timezone.utc) - timedelta(days=horizon_days)
    cutoffs: list[datetime] = []
    for statement in financials:
        effective_at = _normalize_datetime(getattr(statement, "filing_acceptance_at", None))
        if effective_at is None:
            continue
        if effective_at > final_cutoff:
            continue
        cutoffs.append(effective_at)
    return sorted({cutoff for cutoff in cutoffs})


def _aggregate_samples(samples: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "sample_count": 0,
            "calibration": None,
            "stability": None,
            "mean_absolute_error": None,
            "root_mean_square_error": None,
            "mean_signed_error": None,
            "status": "no_samples",
        }

    abs_errors = [float(sample["abs_error"]) for sample in samples if sample.get("abs_error") is not None]
    signed_errors = [float(sample["signed_error"]) for sample in samples if sample.get("signed_error") is not None]
    stability = [float(sample["stability_delta"]) for sample in samples if sample.get("stability_delta") is not None]
    calibration = [1.0 for sample in samples if sample.get("calibration_hit") is True]
    calibration_total = [sample for sample in samples if sample.get("calibration_hit") is not None]

    return {
        "sample_count": len(samples),
        "calibration": _round_number(sum(calibration) / len(calibration_total)) if calibration_total else None,
        "stability": _round_number(fmean(stability)) if stability else None,
        "mean_absolute_error": _round_number(fmean(abs_errors)) if abs_errors else None,
        "root_mean_square_error": _round_number(sqrt(fmean([value * value for value in abs_errors]))) if abs_errors else None,
        "mean_signed_error": _round_number(fmean(signed_errors)) if signed_errors else None,
        "status": "ok",
    }


def _compute_metric_deltas(
    metrics: dict[str, dict[str, Any]],
    baseline_metrics: dict[str, Any] | None,
) -> dict[str, dict[str, float | None]]:
    deltas: dict[str, dict[str, float | None]] = {}
    baseline_root = baseline_metrics if isinstance(baseline_metrics, dict) else {}
    for model_name, model_metrics in metrics.items():
        baseline_model = baseline_root.get(model_name) if isinstance(baseline_root.get(model_name), dict) else {}
        model_delta: dict[str, float | None] = {}
        for key in METRIC_KEYS:
            current_value = model_metrics.get(key)
            baseline_value = baseline_model.get(key)
            if current_value is None or baseline_value is None:
                model_delta[key] = None if current_value is None and baseline_value is None else _round_number((_as_float(current_value) or 0.0) - (_as_float(baseline_value) or 0.0))
            else:
                model_delta[key] = _round_number(float(current_value) - float(baseline_value))
        deltas[model_name] = model_delta
    return deltas


def _serialize_metrics(metrics: dict[str, Any], deltas: dict[str, Any]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    ordered_model_names = [model_name for model_name in SUPPORTED_EVALUATION_MODELS if model_name in metrics]
    ordered_model_names.extend(sorted(str(model_name) for model_name in metrics.keys() if str(model_name) not in ordered_model_names))
    for model_name in ordered_model_names:
        model_metrics = metrics.get(model_name) if isinstance(metrics.get(model_name), dict) else {}
        model_delta = deltas.get(model_name) if isinstance(deltas.get(model_name), dict) else {}
        payloads.append(
            {
                "model_name": model_name,
                "sample_count": int(model_metrics.get("sample_count") or 0),
                "calibration": model_metrics.get("calibration"),
                "stability": model_metrics.get("stability"),
                "mean_absolute_error": model_metrics.get("mean_absolute_error"),
                "root_mean_square_error": model_metrics.get("root_mean_square_error"),
                "mean_signed_error": model_metrics.get("mean_signed_error"),
                "status": str(model_metrics.get("status") or "no_samples"),
                "delta": {
                    "calibration": model_delta.get("calibration"),
                    "stability": model_delta.get("stability"),
                    "mean_absolute_error": model_delta.get("mean_absolute_error"),
                    "root_mean_square_error": model_delta.get("root_mean_square_error"),
                    "mean_signed_error": model_delta.get("mean_signed_error"),
                    "sample_count": model_delta.get("sample_count"),
                },
            }
        )
    return payloads


def _top_error_samples(samples: Sequence[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(samples, key=lambda item: float(item.get("abs_error") or 0.0), reverse=True)
    return [
        {
            "ticker": item.get("ticker"),
            "as_of": item.get("as_of"),
            "future_as_of": item.get("future_as_of"),
            "abs_error": item.get("abs_error"),
            "predicted_signal": item.get("predicted_signal"),
            "actual_signal": item.get("actual_signal"),
        }
        for item in ranked[:limit]
    ]


def _realized_revenue_growth(current_financials: Sequence[Any], future_financials: Sequence[Any]) -> float | None:
    current_latest = current_financials[0] if current_financials else None
    future_latest = future_financials[0] if future_financials else None
    if current_latest is None or future_latest is None:
        return None
    current_revenue = _as_float((current_latest.data or {}).get("revenue"))
    future_revenue = _as_float((future_latest.data or {}).get("revenue"))
    if current_revenue in (None, 0.0) or future_revenue is None:
        return None
    if future_latest.period_end <= current_latest.period_end:
        return None
    day_span = (future_latest.period_end - current_latest.period_end).days
    if day_span <= 0:
        return None
    years = day_span / 365.25
    if years <= 0:
        return None
    return (future_revenue / current_revenue) ** (1 / years) - 1


def _deltas_present(deltas: dict[str, Any]) -> bool:
    for model_delta in deltas.values():
        if not isinstance(model_delta, dict):
            continue
        for value in model_delta.values():
            if value not in (None, 0, 0.0):
                return True
    return False


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _round_number(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


@contextmanager
def _patched_risk_free_provider(
    provider: Callable[[date | None], RiskFreeRateSnapshot],
) -> Iterator[None]:
    modules = (dcf_model, reverse_dcf_model, residual_income_model, roic_model, model_engine_module)
    originals = [module.get_latest_risk_free_rate for module in modules]
    try:
        for module in modules:
            module.get_latest_risk_free_rate = provider
        yield
    finally:
        for module, original in zip(modules, originals, strict=True):
            module.get_latest_risk_free_rate = original

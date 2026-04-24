from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from math import isfinite
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.services import company_charts_dashboard as charts_dashboard
from app.services import company_charts_driver_model as driver_model


GOLDEN_SNAPSHOT_PATH = Path("tests/golden/charts_driver_forecast_golden.json")


@dataclass(frozen=True)
class ValidationCase:
    ticker: str
    company_name: str
    category: str
    sector: str
    market_sector: str
    market_industry: str
    revenue_history: tuple[float, ...]
    revenue_growth_path: tuple[float, ...]
    operating_margin: float
    net_margin: float
    fcf_margin: float
    capex_ratio: float
    sbc_ratio: float
    dso: float
    dio: float
    dpo: float
    share_count_start: float
    share_count_step: float
    guidance_growth: float | None
    actual_next_year_revenue: float
    actual_next_year_eps: float
    force_regulated_markers: bool = False


def build_validation_basket() -> list[ValidationCase]:
    # Representative basket requested by product:
    # megacap tech, cyclical industrial, retailer, capital-light software,
    # bank/financial, and biotech/high-volatility.
    return [
        ValidationCase(
            ticker="AAPL",
            company_name="Apple Inc.",
            category="megacap_tech",
            sector="Technology",
            market_sector="Technology",
            market_industry="Consumer Electronics",
            revenue_history=(320.0, 340.0, 365.0, 390.0, 420.0),
            revenue_growth_path=(0.05, 0.06, 0.07),
            operating_margin=0.30,
            net_margin=0.25,
            fcf_margin=0.23,
            capex_ratio=0.05,
            sbc_ratio=0.03,
            dso=26.0,
            dio=8.0,
            dpo=32.0,
            share_count_start=16.0,
            share_count_step=-0.15,
            guidance_growth=0.06,
            actual_next_year_revenue=447.0,
            actual_next_year_eps=7.35,
        ),
        ValidationCase(
            ticker="CAT",
            company_name="Caterpillar Inc.",
            category="cyclical_industrial",
            sector="Industrials",
            market_sector="Industrials",
            market_industry="Farm & Heavy Construction Machinery",
            revenue_history=(50.0, 57.0, 61.0, 58.0, 64.0),
            revenue_growth_path=(0.10, -0.05, 0.12),
            operating_margin=0.18,
            net_margin=0.12,
            fcf_margin=0.10,
            capex_ratio=0.07,
            sbc_ratio=0.01,
            dso=58.0,
            dio=62.0,
            dpo=54.0,
            share_count_start=0.53,
            share_count_step=-0.006,
            guidance_growth=0.04,
            actual_next_year_revenue=66.5,
            actual_next_year_eps=11.4,
        ),
        ValidationCase(
            ticker="WMT",
            company_name="Walmart Inc.",
            category="retailer",
            sector="Consumer Defensive",
            market_sector="Consumer Defensive",
            market_industry="Discount Stores",
            revenue_history=(560.0, 580.0, 600.0, 620.0, 645.0),
            revenue_growth_path=(0.03, 0.03, 0.04),
            operating_margin=0.05,
            net_margin=0.03,
            fcf_margin=0.04,
            capex_ratio=0.03,
            sbc_ratio=0.004,
            dso=15.0,
            dio=42.0,
            dpo=48.0,
            share_count_start=2.90,
            share_count_step=-0.03,
            guidance_growth=0.035,
            actual_next_year_revenue=668.0,
            actual_next_year_eps=2.55,
        ),
        ValidationCase(
            ticker="ADBE",
            company_name="Adobe Inc.",
            category="capital_light_software",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software - Infrastructure",
            revenue_history=(15.0, 18.0, 21.0, 24.0, 28.0),
            revenue_growth_path=(0.18, 0.15, 0.16),
            operating_margin=0.35,
            net_margin=0.28,
            fcf_margin=0.34,
            capex_ratio=0.02,
            sbc_ratio=0.05,
            dso=34.0,
            dio=1.0,
            dpo=20.0,
            share_count_start=0.49,
            share_count_step=-0.005,
            guidance_growth=0.14,
            actual_next_year_revenue=31.8,
            actual_next_year_eps=17.1,
        ),
        ValidationCase(
            ticker="JPM",
            company_name="JPMorgan Chase & Co.",
            category="bank_financial",
            sector="Financial Services",
            market_sector="Financial Services",
            market_industry="Banks - Diversified",
            revenue_history=(120.0, 128.0, 136.0, 142.0, 150.0),
            revenue_growth_path=(0.06, 0.05, 0.05),
            operating_margin=0.31,
            net_margin=0.24,
            fcf_margin=0.14,
            capex_ratio=0.03,
            sbc_ratio=0.02,
            dso=45.0,
            dio=0.0,
            dpo=35.0,
            share_count_start=3.10,
            share_count_step=-0.025,
            guidance_growth=None,
            actual_next_year_revenue=157.0,
            actual_next_year_eps=16.2,
            force_regulated_markers=True,
        ),
        ValidationCase(
            ticker="MRNA",
            company_name="Moderna, Inc.",
            category="biotech_high_volatility",
            sector="Healthcare",
            market_sector="Healthcare",
            market_industry="Biotechnology",
            revenue_history=(18.0, 9.0, 28.0, 7.5, 12.0),
            revenue_growth_path=(-0.50, 2.10, -0.73),
            operating_margin=0.10,
            net_margin=0.06,
            fcf_margin=0.04,
            capex_ratio=0.09,
            sbc_ratio=0.06,
            dso=70.0,
            dio=12.0,
            dpo=35.0,
            share_count_start=0.39,
            share_count_step=0.008,
            guidance_growth=None,
            actual_next_year_revenue=10.0,
            actual_next_year_eps=1.42,
        ),
    ]


def build_statements_for_case(case: ValidationCase) -> list[SimpleNamespace]:
    years = [2021, 2022, 2023, 2024, 2025]
    if len(case.revenue_history) != len(years):
        raise ValueError(f"{case.ticker} revenue history must contain {len(years)} points")

    statements: list[SimpleNamespace] = []
    shares = case.share_count_start
    for year, revenue in zip(years, case.revenue_history):
        cost_of_revenue = revenue * max(0.1, min(0.92, 1.0 - (case.operating_margin + 0.08)))
        gross_profit = revenue - cost_of_revenue
        operating_income = revenue * case.operating_margin
        pretax_income = operating_income * 0.94
        income_tax_expense = pretax_income * 0.21
        net_income = revenue * case.net_margin
        depreciation = revenue * max(0.01, min(0.12, case.capex_ratio * 0.65))
        capex = revenue * case.capex_ratio
        operating_cash_flow = capex + revenue * case.fcf_margin
        free_cash_flow = operating_cash_flow - capex
        cost_base = revenue - operating_income - depreciation

        accounts_receivable = _days_to_balance(revenue, case.dso)
        inventory = _days_to_balance(cost_of_revenue, case.dio)
        accounts_payable = _days_to_balance(cost_of_revenue, case.dpo)

        cash_and_short_term = revenue * 0.18
        current_debt = revenue * 0.02
        long_term_debt = revenue * 0.14
        total_assets = revenue * 1.25

        data: dict[str, float | str | None] = {
            "revenue": revenue,
            "cost_of_revenue": cost_of_revenue,
            "gross_profit": gross_profit,
            "operating_income": operating_income,
            "pretax_income": pretax_income,
            "income_tax_expense": income_tax_expense,
            "net_income": net_income,
            "operating_cash_flow": operating_cash_flow,
            "free_cash_flow": free_cash_flow,
            "capex": capex,
            "depreciation_and_amortization": depreciation,
            "weighted_average_diluted_shares": shares,
            "shares_outstanding": shares,
            "stock_based_compensation": revenue * case.sbc_ratio,
            "share_buybacks": max(0.0, (-case.share_count_step) * 3.0),
            "accounts_receivable": accounts_receivable,
            "inventory": inventory,
            "accounts_payable": accounts_payable,
            "deferred_revenue": _days_to_balance(revenue, 4.0),
            "accrued_operating_liabilities": _days_to_balance(cost_base, 3.0),
            "cash_and_cash_equivalents": cash_and_short_term * 0.8,
            "cash_and_short_term_investments": cash_and_short_term,
            "short_term_investments": cash_and_short_term * 0.2,
            "current_debt": current_debt,
            "long_term_debt": long_term_debt,
            "total_debt": current_debt + long_term_debt,
            "interest_expense": (current_debt + long_term_debt) * 0.045,
            "interest_income": cash_and_short_term * 0.015,
            "other_income_expense": -(revenue * 0.002),
            "current_assets": cash_and_short_term + accounts_receivable + inventory,
            "current_liabilities": accounts_payable + current_debt,
            "total_assets": total_assets,
            "total_liabilities": accounts_payable + current_debt + long_term_debt,
            "retained_earnings": total_assets * 0.32,
            "net_ppe": revenue * 0.42,
            "ppe_disposals": revenue * 0.005,
            "eps": _safe_divide(net_income, shares),
            "cash_taxes_paid": max(0.0, income_tax_expense),
            "current_tax_expense": max(0.0, income_tax_expense * 0.85),
            "deferred_tax_expense": income_tax_expense * 0.15,
            "deferred_tax_asset": max(0.0, income_tax_expense * 0.3),
        }
        if case.force_regulated_markers:
            data["source_id"] = "fdic_bankfind_financials"
            data["reporting_basis"] = "fdic_call_report"
            data["net_interest_income"] = revenue * 0.42
            data["deposits_total"] = revenue * 2.4

        statements.append(
            SimpleNamespace(
                period_end=date(year, 12, 31),
                filing_type="10-K",
                last_checked=datetime(2026, 4, 23, tzinfo=timezone.utc),
                data=data,
            )
        )
        shares = max(0.05, shares + case.share_count_step)

    return statements


def build_releases_for_case(case: ValidationCase) -> list[SimpleNamespace]:
    if case.guidance_growth is None:
        return []

    latest_revenue = case.revenue_history[-1]
    guidance_anchor = latest_revenue * (1.0 + case.guidance_growth)
    return [
        SimpleNamespace(
            id=1,
            filing_acceptance_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            filing_date=date(2026, 2, 1),
            reported_period_end=date(2025, 12, 31),
            revenue_guidance_low=guidance_anchor,
            revenue_guidance_high=guidance_anchor,
            last_checked=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
    ]


def build_company_for_case(case: ValidationCase) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        ticker=case.ticker,
        cik=f"{abs(hash(case.ticker)) % 1_000_000:06d}",
        name=case.company_name,
        sector=case.sector,
        market_sector=case.market_sector,
        market_industry=case.market_industry,
    )


def build_driver_bundle_for_case(case: ValidationCase, overrides: dict[str, float] | None = None) -> driver_model.DriverForecastBundle | None:
    return driver_model.build_driver_forecast_bundle(
        build_statements_for_case(case),
        build_releases_for_case(case),
        overrides=overrides,
        company=build_company_for_case(case),
    )


def compute_golden_snapshot(cases: list[ValidationCase] | None = None) -> dict[str, Any]:
    basket = cases or build_validation_basket()
    snapshot: dict[str, Any] = {}
    for case in basket:
        bundle = build_driver_bundle_for_case(case)
        if bundle is None:
            snapshot[case.ticker] = {
                "engine_mode": "missing",
            }
            continue

        scenarios = getattr(bundle, "scenarios", {}) or {}
        base = scenarios.get("base") if isinstance(scenarios, dict) else None
        first_revenue = _first_value(getattr(getattr(base, "revenue", None), "values", []))
        first_eps = _first_value(getattr(getattr(base, "eps", None), "values", []))
        first_growth = _first_value(getattr(getattr(base, "revenue_growth", None), "values", []))
        snapshot[case.ticker] = {
            "engine_mode": getattr(bundle, "engine_mode", "unknown"),
            "entity_routing": getattr(bundle, "entity_routing", "unknown"),
            "base_next_year_revenue": _round_or_none(first_revenue, 6),
            "base_next_year_eps": _round_or_none(first_eps, 6),
            "base_next_year_growth": _round_or_none(first_growth, 6),
            "guidance_anchor": _round_or_none(getattr(bundle, "guidance_anchor", None), 6),
        }
    return snapshot


def validate_labeling_consistency(case: ValidationCase) -> list[str]:
    issues: list[str] = []
    bundle = build_driver_bundle_for_case(case)
    if bundle is None:
        return ["bundle unavailable"]

    scenarios = getattr(bundle, "scenarios", {}) or {}
    base = scenarios.get("base") if isinstance(scenarios, dict) else None
    projected_years = list(getattr(getattr(base, "revenue", None), "years", [])) if base is not None else []
    reported_years = [statement.period_end.year for statement in build_statements_for_case(case)]

    overlap = sorted(set(projected_years).intersection(reported_years))
    if overlap:
        issues.append(f"projected years overlap reported years: {overlap}")

    expected_first_projected = max(reported_years) + 1
    if projected_years and projected_years[0] != expected_first_projected:
        issues.append(
            f"first projected year {projected_years[0]} does not follow reported year {max(reported_years)}"
        )

    return issues


def validate_accounting_identities(case: ValidationCase) -> list[str]:
    issues: list[str] = []
    bundle = build_driver_bundle_for_case(case)
    if bundle is None:
        return ["bundle unavailable"]

    scenarios = getattr(bundle, "scenarios", {}) or {}
    base = scenarios.get("base") if isinstance(scenarios, dict) else None
    if base is None:
        return []

    revenue_line = getattr(base, "revenue", None)
    operating_income_line = getattr(base, "operating_income", None)
    net_income_line = getattr(base, "net_income", None)
    shares_line = getattr(base, "diluted_shares", None)
    eps_line = getattr(base, "eps", None)
    free_cash_flow_line = getattr(base, "free_cash_flow", None)
    ocf_line = getattr(base, "operating_cash_flow", None)
    capex_line = getattr(base, "capex", None)

    for index, year in enumerate(getattr(revenue_line, "years", [])):
        revenue = _value_at(revenue_line, index)
        operating_income = _value_at(operating_income_line, index)
        net_income = _value_at(net_income_line, index)
        diluted_shares = _value_at(shares_line, index)
        eps = _value_at(eps_line, index)
        fcf = _value_at(free_cash_flow_line, index)
        ocf = _value_at(ocf_line, index)
        capex = _value_at(capex_line, index)

        if revenue is not None and operating_income is not None and operating_income > revenue * 1.05:
            issues.append(f"{year}: operating income exceeds revenue")

        if diluted_shares is not None and diluted_shares <= 0:
            issues.append(f"{year}: diluted shares non-positive")

        if net_income is not None and diluted_shares not in (None, 0) and eps is not None:
            implied_eps = net_income / diluted_shares
            if abs(implied_eps - eps) > 1e-5:
                issues.append(f"{year}: EPS mismatch (expected {implied_eps:.6f}, got {eps:.6f})")

        if fcf is not None and ocf is not None and capex is not None:
            if abs((ocf - capex) - fcf) > 1e-5:
                issues.append(f"{year}: FCF mismatch (expected OCF - Capex)")

    return issues


def validate_override_clipping(case: ValidationCase) -> list[str]:
    issues: list[str] = []
    extreme_overrides = {
        "price_growth": 0.9,
        "residual_demand_growth": -0.9,
        "dso": 500.0,
        "sales_to_capital": -3.0,
    }
    bundle = build_driver_bundle_for_case(case, overrides=extreme_overrides)
    if bundle is None:
        return ["bundle unavailable"]

    if getattr(bundle, "engine_mode", "") != driver_model.ENGINE_MODE_DRIVER:
        # Regulated-financial routing intentionally bypasses driver overrides.
        return []

    context = getattr(bundle, "override_context", None)
    if context is None:
        return ["override context missing"]

    clipped = list(getattr(context, "clipped", []))
    if not clipped:
        issues.append("expected clipped overrides but found none")

    for item in getattr(context, "applied", []):
        applied_value = float(getattr(item, "applied_value", 0.0))
        min_value = float(getattr(item, "min_value", 0.0))
        max_value = float(getattr(item, "max_value", 0.0))
        if applied_value < min_value - 1e-9 or applied_value > max_value + 1e-9:
            issues.append(f"override {getattr(item, 'key', 'unknown')} escaped clipping bounds")

    return issues


def validate_sensitivity_matrix(case: ValidationCase) -> list[str]:
    issues: list[str] = []
    bundle = build_driver_bundle_for_case(case)
    if bundle is None:
        return ["bundle unavailable"]

    if getattr(bundle, "engine_mode", "") != driver_model.ENGINE_MODE_DRIVER:
        # Regulated-financial routing cases are intentionally excluded.
        return []

    annuals = build_statements_for_case(case)
    line_traces = getattr(bundle, "line_traces", None) or {}
    matrix = charts_dashboard._build_projection_studio_sensitivity_matrix(annuals, bundle, line_traces)
    if len(matrix) != 25:
        return [f"expected 25 sensitivity cells, found {len(matrix)}"]

    grid: dict[tuple[int, int], float | None] = {
        (cell.row_index, cell.column_index): cell.eps for cell in matrix
    }

    # Column monotonicity: for a fixed margin row, EPS should be non-decreasing
    # as revenue growth increases across columns.
    for row_index in range(5):
        previous = None
        for column_index in range(5):
            eps = grid.get((row_index, column_index))
            if eps is None:
                continue
            if previous is not None and eps + 1e-9 < previous:
                issues.append(
                    f"row {row_index} EPS not monotonic by growth at column {column_index}"
                )
            previous = eps

    # Row monotonicity: for a fixed growth column, EPS should be non-decreasing
    # as operating margin increases down rows.
    for column_index in range(5):
        previous = None
        for row_index in range(5):
            eps = grid.get((row_index, column_index))
            if eps is None:
                continue
            if previous is not None and eps + 1e-9 < previous:
                issues.append(
                    f"column {column_index} EPS not monotonic by margin at row {row_index}"
                )
            previous = eps

    base_cells = [cell for cell in matrix if cell.is_base]
    if len(base_cells) != 1:
        issues.append(f"expected exactly one base sensitivity cell, found {len(base_cells)}")

    return issues


def benchmark_case_against_baselines(case: ValidationCase) -> dict[str, Any]:
    bundle = build_driver_bundle_for_case(case)
    predicted_revenue = None
    predicted_eps = None
    if bundle is not None:
        scenarios = getattr(bundle, "scenarios", {}) or {}
        base = scenarios.get("base") if isinstance(scenarios, dict) else None
        predicted_revenue = _first_value(getattr(getattr(base, "revenue", None), "values", []))
        predicted_eps = _first_value(getattr(getattr(base, "eps", None), "values", []))

    last_revenue = case.revenue_history[-1]
    last_eps = _safe_divide(last_revenue * case.net_margin, case.share_count_start + case.share_count_step * 4)
    trailing_cagr = _trailing_cagr(case.revenue_history)
    cagr_revenue = last_revenue * (1.0 + trailing_cagr)

    guidance_revenue = None
    if case.guidance_growth is not None:
        guidance_revenue = last_revenue * (1.0 + case.guidance_growth)

    return {
        "ticker": case.ticker,
        "category": case.category,
        "engine_mode": getattr(bundle, "engine_mode", "missing") if bundle is not None else "missing",
        "actual_next_year": {
            "revenue": case.actual_next_year_revenue,
            "eps": case.actual_next_year_eps,
        },
        "model": {
            "revenue": predicted_revenue,
            "eps": predicted_eps,
            "revenue_abs_pct_error": _abs_pct_error(predicted_revenue, case.actual_next_year_revenue),
            "eps_abs_pct_error": _abs_pct_error(predicted_eps, case.actual_next_year_eps),
        },
        "baselines": {
            "last_value_carry_forward": {
                "revenue": last_revenue,
                "eps": last_eps,
                "revenue_abs_pct_error": _abs_pct_error(last_revenue, case.actual_next_year_revenue),
                "eps_abs_pct_error": _abs_pct_error(last_eps, case.actual_next_year_eps),
            },
            "trailing_cagr": {
                "revenue": cagr_revenue,
                "revenue_abs_pct_error": _abs_pct_error(cagr_revenue, case.actual_next_year_revenue),
            },
            "management_guidance": {
                "revenue": guidance_revenue,
                "revenue_abs_pct_error": _abs_pct_error(guidance_revenue, case.actual_next_year_revenue),
            },
        },
    }


def build_validation_summary() -> dict[str, Any]:
    basket = build_validation_basket()
    benchmark_rows = [benchmark_case_against_baselines(case) for case in basket]

    label_issues: dict[str, list[str]] = {}
    identity_issues: dict[str, list[str]] = {}
    clipping_issues: dict[str, list[str]] = {}
    sensitivity_issues: dict[str, list[str]] = {}

    for case in basket:
        label_issues[case.ticker] = validate_labeling_consistency(case)
        identity_issues[case.ticker] = validate_accounting_identities(case)
        clipping_issues[case.ticker] = validate_override_clipping(case)
        sensitivity_issues[case.ticker] = validate_sensitivity_matrix(case)

    non_regulated_rows = [
        row for row in benchmark_rows if row["engine_mode"] == driver_model.ENGINE_MODE_DRIVER
    ]

    model_better_than_last = 0
    model_better_than_cagr = 0
    model_better_than_guidance = 0
    guidance_available = 0

    for row in non_regulated_rows:
        model_error = row["model"]["revenue_abs_pct_error"]
        last_error = row["baselines"]["last_value_carry_forward"]["revenue_abs_pct_error"]
        cagr_error = row["baselines"]["trailing_cagr"]["revenue_abs_pct_error"]
        guidance_error = row["baselines"]["management_guidance"]["revenue_abs_pct_error"]

        if _is_better(model_error, last_error):
            model_better_than_last += 1
        if _is_better(model_error, cagr_error):
            model_better_than_cagr += 1
        if guidance_error is not None:
            guidance_available += 1
            if _is_better(model_error, guidance_error):
                model_better_than_guidance += 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "golden_snapshot": compute_golden_snapshot(basket),
        "labels": label_issues,
        "accounting_identities": identity_issues,
        "override_clipping": clipping_issues,
        "sensitivity_matrix": sensitivity_issues,
        "benchmarks": benchmark_rows,
        "benchmark_summary": {
            "non_regulated_case_count": len(non_regulated_rows),
            "model_better_than_last_value_count": model_better_than_last,
            "model_better_than_trailing_cagr_count": model_better_than_cagr,
            "guidance_available_count": guidance_available,
            "model_better_than_guidance_count": model_better_than_guidance,
        },
    }


def render_validation_summary_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Charts + Driver Forecast Validation Summary")
    lines.append("")
    lines.append(f"Generated: {summary.get('generated_at', 'unknown')}")
    lines.append("")

    benchmark_summary = summary.get("benchmark_summary", {})
    lines.append("## Benchmark Snapshot")
    lines.append("")
    lines.append(f"- Non-regulated cases: {benchmark_summary.get('non_regulated_case_count', 0)}")
    lines.append(
        f"- Model beats last-value baseline (revenue APE): {benchmark_summary.get('model_better_than_last_value_count', 0)}"
    )
    lines.append(
        f"- Model beats trailing-CAGR baseline (revenue APE): {benchmark_summary.get('model_better_than_trailing_cagr_count', 0)}"
    )
    lines.append(f"- Cases with guidance baseline: {benchmark_summary.get('guidance_available_count', 0)}")
    lines.append(
        f"- Model beats guidance baseline (revenue APE): {benchmark_summary.get('model_better_than_guidance_count', 0)}"
    )
    lines.append("")

    lines.append("## Property Check Status")
    lines.append("")
    for section_key, title in (
        ("labels", "Reported vs Projected Labeling"),
        ("accounting_identities", "Accounting Identity Checks"),
        ("override_clipping", "Override Clipping"),
        ("sensitivity_matrix", "Sensitivity Matrix Shape + Monotonicity"),
    ):
        lines.append(f"### {title}")
        checks = summary.get(section_key, {})
        any_issue = False
        for ticker, issues in checks.items():
            if issues:
                any_issue = True
                lines.append(f"- {ticker}: FAIL ({'; '.join(issues)})")
            else:
                lines.append(f"- {ticker}: PASS")
        if not checks:
            lines.append("- No checks recorded")
        if not any_issue:
            lines.append("- Overall: PASS")
        lines.append("")

    lines.append("## Per-Case Benchmarks")
    lines.append("")
    for row in summary.get("benchmarks", []):
        ticker = row.get("ticker", "unknown")
        category = row.get("category", "unknown")
        model_error = row.get("model", {}).get("revenue_abs_pct_error")
        last_error = row.get("baselines", {}).get("last_value_carry_forward", {}).get("revenue_abs_pct_error")
        cagr_error = row.get("baselines", {}).get("trailing_cagr", {}).get("revenue_abs_pct_error")
        guidance_error = row.get("baselines", {}).get("management_guidance", {}).get("revenue_abs_pct_error")
        lines.append(
            f"- {ticker} ({category}): model={_fmt(model_error)} last={_fmt(last_error)} cagr={_fmt(cagr_error)} guidance={_fmt(guidance_error)}"
        )

    lines.append("")
    return "\n".join(lines)


def _days_to_balance(annual_flow: float | None, days: float | None) -> float | None:
    if annual_flow is None or days is None:
        return None
    return float(annual_flow) * float(days) / 365.0


def _trailing_cagr(values: tuple[float, ...]) -> float:
    if len(values) < 2:
        return 0.0
    start = values[-4] if len(values) >= 4 else values[0]
    end = values[-1]
    periods = 3 if len(values) >= 4 else max(1, len(values) - 1)
    if start <= 0 or end <= 0:
        return 0.0
    return (end / start) ** (1.0 / periods) - 1.0


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def _first_value(values: list[Any] | tuple[Any, ...] | None) -> float | None:
    if not values:
        return None
    value = values[0]
    if value is None:
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _value_at(line: Any, index: int) -> float | None:
    if line is None:
        return None
    values = getattr(line, "values", None) or []
    if index >= len(values):
        return None
    value = values[index]
    if value is None:
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _abs_pct_error(predicted: float | None, actual: float | None) -> float | None:
    if predicted is None or actual in (None, 0):
        return None
    return abs((float(predicted) - float(actual)) / float(actual))


def _is_better(left: float | None, right: float | None) -> bool:
    if left is None:
        return False
    if right is None:
        return True
    return left < right


def _round_or_none(value: float | None, digits: int) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.2f}%"

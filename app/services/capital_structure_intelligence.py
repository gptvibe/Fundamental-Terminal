from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.model_engine.utils import average, json_number, safe_divide
from app.models import CapitalStructureSnapshot, FinancialStatement
from app.services.refresh_state import mark_dataset_checked

CANONICAL_STATEMENT_TYPE = "canonical_xbrl"
FORMULA_VERSION = "capital_structure_v1"

DEBT_MATURITY_BUCKETS: list[tuple[str, str]] = [
    ("debt_maturity_due_next_twelve_months", "Next 12 months"),
    ("debt_maturity_due_year_two", "Year 2"),
    ("debt_maturity_due_year_three", "Year 3"),
    ("debt_maturity_due_year_four", "Year 4"),
    ("debt_maturity_due_year_five", "Year 5"),
    ("debt_maturity_due_thereafter", "Thereafter"),
]

LEASE_OBLIGATION_BUCKETS: list[tuple[str, str]] = [
    ("lease_due_next_twelve_months", "Next 12 months"),
    ("lease_due_year_two", "Year 2"),
    ("lease_due_year_three", "Year 3"),
    ("lease_due_year_four", "Year 4"),
    ("lease_due_year_five", "Year 5"),
    ("lease_due_thereafter", "Thereafter"),
]


def recompute_and_persist_company_capital_structure(
    session: Session,
    company_id: int,
    *,
    checked_at: datetime | None = None,
) -> int:
    financials = list(
        session.execute(
            select(FinancialStatement).where(
                FinancialStatement.company_id == company_id,
                FinancialStatement.statement_type == CANONICAL_STATEMENT_TYPE,
            )
        ).scalars()
    )
    snapshots = build_capital_structure_snapshots(financials)
    timestamp = checked_at or datetime.now(timezone.utc)

    session.execute(delete(CapitalStructureSnapshot).where(CapitalStructureSnapshot.company_id == company_id))

    if not snapshots:
        mark_dataset_checked(session, company_id, "capital_structure", checked_at=timestamp, success=True)
        return 0

    payloads = [
        {
            "company_id": company_id,
            "accession_number": row["accession_number"],
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "filing_type": row["filing_type"],
            "statement_type": row["statement_type"],
            "source": row["source"],
            "filing_acceptance_at": row["filing_acceptance_at"],
            "data": row["data"],
            "provenance": row["provenance"],
            "source_statement_ids": row["source_statement_ids"],
            "quality_flags": row["quality_flags"],
            "confidence_score": row["confidence_score"],
            "last_updated": timestamp,
            "last_checked": timestamp,
        }
        for row in snapshots
    ]

    statement = insert(CapitalStructureSnapshot).values(payloads)
    statement = statement.on_conflict_do_update(
        constraint="uq_capital_structure_snapshots_company_period_filing",
        set_={
            "accession_number": statement.excluded.accession_number,
            "period_start": statement.excluded.period_start,
            "statement_type": statement.excluded.statement_type,
            "source": statement.excluded.source,
            "filing_acceptance_at": statement.excluded.filing_acceptance_at,
            "data": statement.excluded.data,
            "provenance": statement.excluded.provenance,
            "source_statement_ids": statement.excluded.source_statement_ids,
            "quality_flags": statement.excluded.quality_flags,
            "confidence_score": statement.excluded.confidence_score,
            "last_updated": statement.excluded.last_updated,
            "last_checked": statement.excluded.last_checked,
        },
    )
    session.execute(statement)
    mark_dataset_checked(session, company_id, "capital_structure", checked_at=timestamp, success=True)
    return len(payloads)


def build_capital_structure_snapshots(financials: list[FinancialStatement]) -> list[dict[str, Any]]:
    rows = _normalize_financial_rows(financials)
    if not rows:
        return []

    snapshots: list[dict[str, Any]] = []
    previous_row: dict[str, Any] | None = None
    for row in rows:
        data = row["data"]
        quality_flags = set(row.get("quality_flags") or [])

        total_debt = _sum_non_null(_to_float(data.get("current_debt")), _to_float(data.get("long_term_debt")))
        previous_total_debt = None if previous_row is None else _sum_non_null(
            _to_float(previous_row["data"].get("current_debt")),
            _to_float(previous_row["data"].get("long_term_debt")),
        )
        lease_liabilities = _to_float(data.get("lease_liabilities"))

        debt_maturity_buckets = _build_bucket_rows(data, DEBT_MATURITY_BUCKETS)
        debt_maturity_flags = _bucket_flags("debt_maturity_ladder", debt_maturity_buckets, len(DEBT_MATURITY_BUCKETS))
        quality_flags.update(debt_maturity_flags)

        lease_obligation_buckets = _build_bucket_rows(data, LEASE_OBLIGATION_BUCKETS)
        lease_flags = _bucket_flags("lease_obligations", lease_obligation_buckets, len(LEASE_OBLIGATION_BUCKETS))
        quality_flags.update(lease_flags)

        debt_issuance = _abs_number(data.get("debt_issuance"))
        debt_repayment = _abs_number(data.get("debt_repayment"))
        net_debt_change = _to_float(data.get("debt_changes"))
        if net_debt_change is None and debt_issuance is not None and debt_repayment is not None:
            net_debt_change = debt_issuance - debt_repayment

        unexplained_debt_change = None
        if total_debt is not None and previous_total_debt is not None and debt_issuance is not None and debt_repayment is not None:
            unexplained_debt_change = total_debt - previous_total_debt - debt_issuance + debt_repayment

        debt_rollforward_flags = _missing_flags(
            {
                "opening_total_debt": previous_total_debt,
                "ending_total_debt": total_debt,
                "debt_issued": debt_issuance,
                "debt_repaid": debt_repayment,
            },
            prefix="debt_rollforward",
        )
        quality_flags.update(debt_rollforward_flags)

        interest_expense = _abs_number(data.get("interest_expense"))
        average_debt = average(previous_total_debt, total_debt) if previous_total_debt is not None else total_debt
        interest_to_average_debt = safe_divide(interest_expense, average_debt)
        interest_to_revenue = safe_divide(interest_expense, _to_float(data.get("revenue")))
        interest_to_operating_cash_flow = safe_divide(interest_expense, _abs_number(data.get("operating_cash_flow")))
        interest_coverage_proxy = safe_divide(_to_float(data.get("operating_income")), interest_expense)
        interest_flags = _missing_flags(
            {
                "interest_expense": interest_expense,
                "average_debt": average_debt,
                "interest_to_average_debt": interest_to_average_debt,
            },
            prefix="interest_burden",
        )
        quality_flags.update(interest_flags)

        dividends = _abs_number(data.get("dividends"))
        share_repurchases = _abs_number(data.get("share_buybacks"))
        stock_based_compensation = _abs_number(data.get("stock_based_compensation"))
        gross_shareholder_payout = _sum_non_null(dividends, share_repurchases)
        net_shareholder_payout = _sum_non_null(gross_shareholder_payout, -stock_based_compensation if stock_based_compensation is not None else None)
        payout_base = _sum_non_null(dividends, share_repurchases, stock_based_compensation)
        capital_returns_flags = _missing_flags(
            {
                "dividends": dividends,
                "share_repurchases": share_repurchases,
                "stock_based_compensation": stock_based_compensation,
            },
            prefix="capital_returns",
        )
        quality_flags.update(capital_returns_flags)

        opening_shares = None if previous_row is None else _to_float(previous_row["data"].get("shares_outstanding"))
        ending_shares = _to_float(data.get("shares_outstanding"))
        shares_issued = _abs_number(data.get("shares_issued"))
        shares_repurchased = _abs_number(data.get("shares_repurchased"))
        weighted_average_diluted_shares = _to_float(data.get("weighted_average_diluted_shares"))
        gross_dilution_proxy_shares = None
        dilution_flags: list[str] = []
        if shares_issued is None and weighted_average_diluted_shares is not None and ending_shares is not None:
            gross_dilution_proxy_shares = max(weighted_average_diluted_shares - ending_shares, 0.0)
            dilution_flags.append("net_dilution_bridge_shares_issued_proxy")

        other_share_change = None
        effective_issued = shares_issued if shares_issued is not None else gross_dilution_proxy_shares
        if opening_shares is not None and ending_shares is not None and effective_issued is not None:
            other_share_change = ending_shares - opening_shares - effective_issued + float(shares_repurchased or 0.0)
        net_share_change = None if opening_shares is None or ending_shares is None else ending_shares - opening_shares
        net_dilution_ratio = safe_divide(net_share_change, opening_shares)
        dilution_flags.extend(
            _missing_flags(
                {
                    "opening_shares": opening_shares,
                    "ending_shares": ending_shares,
                    "weighted_average_diluted_shares": weighted_average_diluted_shares,
                },
                prefix="net_dilution_bridge",
            )
        )
        quality_flags.update(dilution_flags)

        debt_maturity_meta = _section_meta(
            row["period_end"],
            row["last_checked"],
            ["sec_companyfacts", "ft_capital_structure_intelligence"],
            debt_maturity_flags,
            len(debt_maturity_buckets),
            len(DEBT_MATURITY_BUCKETS),
        )
        lease_meta = _section_meta(
            row["period_end"],
            row["last_checked"],
            ["sec_companyfacts", "ft_capital_structure_intelligence"],
            lease_flags,
            len(lease_obligation_buckets),
            len(LEASE_OBLIGATION_BUCKETS),
        )
        debt_rollforward_meta = _section_meta(
            row["period_end"],
            row["last_checked"],
            ["sec_companyfacts", "ft_capital_structure_intelligence"],
            debt_rollforward_flags,
            _present_count(previous_total_debt, total_debt, debt_issuance, debt_repayment),
            4,
        )
        interest_meta = _section_meta(
            row["period_end"],
            row["last_checked"],
            ["sec_companyfacts", "ft_capital_structure_intelligence"],
            interest_flags,
            _present_count(interest_expense, average_debt, interest_to_average_debt, interest_coverage_proxy),
            4,
        )
        capital_returns_meta = _section_meta(
            row["period_end"],
            row["last_checked"],
            ["sec_companyfacts", "ft_capital_structure_intelligence"],
            capital_returns_flags,
            _present_count(dividends, share_repurchases, stock_based_compensation),
            3,
        )
        net_dilution_meta = _section_meta(
            row["period_end"],
            row["last_checked"],
            ["sec_companyfacts", "ft_capital_structure_intelligence"],
            dilution_flags,
            _present_count(opening_shares, ending_shares, weighted_average_diluted_shares, effective_issued),
            4,
        )

        overall_confidence = average(
            debt_maturity_meta["confidence_score"],
            lease_meta["confidence_score"],
            debt_rollforward_meta["confidence_score"],
            interest_meta["confidence_score"],
            capital_returns_meta["confidence_score"],
            net_dilution_meta["confidence_score"],
        )

        snapshots.append(
            {
                "accession_number": row["accession_number"],
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "filing_type": row["filing_type"],
                "statement_type": row["statement_type"],
                "source": row["source"],
                "filing_acceptance_at": row["filing_acceptance_at"],
                "data": {
                    "summary": {
                        "total_debt": json_number(total_debt),
                        "lease_liabilities": json_number(lease_liabilities),
                        "interest_expense": json_number(interest_expense),
                        "debt_due_next_twelve_months": _bucket_amount(debt_maturity_buckets, "debt_maturity_due_next_twelve_months"),
                        "lease_due_next_twelve_months": _bucket_amount(lease_obligation_buckets, "lease_due_next_twelve_months"),
                        "gross_shareholder_payout": json_number(gross_shareholder_payout),
                        "net_shareholder_payout": json_number(net_shareholder_payout),
                        "net_share_change": json_number(net_share_change),
                        "net_dilution_ratio": json_number(net_dilution_ratio),
                    },
                    "debt_maturity_ladder": {
                        "buckets": debt_maturity_buckets,
                        "meta": debt_maturity_meta,
                    },
                    "lease_obligations": {
                        "buckets": lease_obligation_buckets,
                        "meta": lease_meta,
                    },
                    "debt_rollforward": {
                        "opening_total_debt": json_number(previous_total_debt),
                        "ending_total_debt": json_number(total_debt),
                        "debt_issued": json_number(debt_issuance),
                        "debt_repaid": json_number(debt_repayment),
                        "net_debt_change": json_number(net_debt_change),
                        "unexplained_change": json_number(unexplained_debt_change),
                        "meta": debt_rollforward_meta,
                    },
                    "interest_burden": {
                        "interest_expense": json_number(interest_expense),
                        "average_total_debt": json_number(average_debt),
                        "interest_to_average_debt": json_number(interest_to_average_debt),
                        "interest_to_revenue": json_number(interest_to_revenue),
                        "interest_to_operating_cash_flow": json_number(interest_to_operating_cash_flow),
                        "interest_coverage_proxy": json_number(interest_coverage_proxy),
                        "meta": interest_meta,
                    },
                    "capital_returns": {
                        "dividends": json_number(dividends),
                        "share_repurchases": json_number(share_repurchases),
                        "stock_based_compensation": json_number(stock_based_compensation),
                        "gross_shareholder_payout": json_number(gross_shareholder_payout),
                        "net_shareholder_payout": json_number(net_shareholder_payout),
                        "payout_mix": {
                            "dividends_share": json_number(safe_divide(dividends, gross_shareholder_payout)),
                            "repurchases_share": json_number(safe_divide(share_repurchases, gross_shareholder_payout)),
                            "sbc_offset_share": json_number(safe_divide(stock_based_compensation, payout_base)),
                        },
                        "meta": capital_returns_meta,
                    },
                    "net_dilution_bridge": {
                        "opening_shares": json_number(opening_shares),
                        "shares_issued": json_number(shares_issued),
                        "shares_issued_proxy": json_number(gross_dilution_proxy_shares if shares_issued is None else None),
                        "shares_repurchased": json_number(shares_repurchased),
                        "other_share_change": json_number(other_share_change),
                        "ending_shares": json_number(ending_shares),
                        "weighted_average_diluted_shares": json_number(weighted_average_diluted_shares),
                        "net_share_change": json_number(net_share_change),
                        "net_dilution_ratio": json_number(net_dilution_ratio),
                        "share_repurchase_cash": json_number(share_repurchases),
                        "stock_based_compensation": json_number(stock_based_compensation),
                        "meta": net_dilution_meta,
                    },
                },
                "provenance": {
                    "formula_version": FORMULA_VERSION,
                    "statement_source": row["source"],
                    "statement_type": row["statement_type"],
                    "official_source_id": "sec_companyfacts",
                },
                "source_statement_ids": row["statement_ids"],
                "quality_flags": sorted(quality_flags),
                "confidence_score": json_number(overall_confidence),
                "last_updated": row["last_updated"],
                "last_checked": row["last_checked"],
            }
        )
        previous_row = row

    return snapshots


def _normalize_financial_rows(financials: list[FinancialStatement]) -> list[dict[str, Any]]:
    grouped: dict[tuple[date, str], list[FinancialStatement]] = defaultdict(list)
    for statement in financials:
        grouped[(statement.period_end, statement.filing_type)].append(statement)

    normalized: list[dict[str, Any]] = []
    for (_period_end, _filing_type), statements in grouped.items():
        sorted_statements = sorted(statements, key=lambda item: (item.last_updated, item.id))
        latest = sorted_statements[-1]
        payload_variants = {str(item.data or {}) for item in sorted_statements}
        quality_flags = ["restatement_detected"] if len(payload_variants) > 1 else []
        normalized.append(
            {
                "statement_ids": [item.id for item in sorted_statements],
                "accession_number": _extract_accession_number(latest.source),
                "period_start": latest.period_start,
                "period_end": latest.period_end,
                "filing_type": latest.filing_type,
                "statement_type": latest.statement_type,
                "source": latest.source,
                "filing_acceptance_at": getattr(latest, "filing_acceptance_at", None),
                "last_updated": latest.last_updated,
                "last_checked": latest.last_checked,
                "quality_flags": quality_flags,
                "data": dict(latest.data or {}),
            }
        )
    normalized.sort(key=lambda item: item["period_end"])
    return normalized


def _build_bucket_rows(data: dict[str, Any], bucket_defs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket_key, label in bucket_defs:
        amount = _abs_number(data.get(bucket_key))
        if amount is None:
            continue
        rows.append({"bucket_key": bucket_key, "label": label, "amount": json_number(amount)})
    return rows


def _bucket_flags(section_key: str, buckets: list[dict[str, Any]], expected_count: int) -> list[str]:
    if not buckets:
        return [f"{section_key}_missing"]
    if len(buckets) < expected_count:
        return [f"{section_key}_partial"]
    return []


def _missing_flags(values: dict[str, float | None], *, prefix: str) -> list[str]:
    missing = [key for key, value in values.items() if value is None]
    if not missing:
        return []
    if len(missing) == len(values):
        return [f"{prefix}_missing"]
    return [f"{prefix}_partial", *[f"{prefix}_{item}_missing" for item in missing]]


def _section_meta(
    as_of: date,
    last_refreshed_at: datetime | None,
    provenance_sources: list[str],
    confidence_flags: list[str],
    present_count: int,
    total_count: int,
) -> dict[str, Any]:
    confidence_score = 0.0 if total_count <= 0 else max(0.0, min(1.0, present_count / total_count))
    return {
        "as_of": as_of,
        "last_refreshed_at": last_refreshed_at,
        "provenance_sources": provenance_sources,
        "confidence_score": json_number(confidence_score),
        "confidence_flags": sorted(set(confidence_flags)),
    }


def _bucket_amount(rows: list[dict[str, Any]], key: str) -> int | float | None:
    match = next((row for row in rows if row.get("bucket_key") == key), None)
    if match is None:
        return None
    return match.get("amount")


def _extract_accession_number(source: str | None) -> str | None:
    if not source:
        return None
    normalized = str(source)
    for segment in normalized.split("/"):
        if len(segment) == 20 and segment.count("-") == 2:
            return segment
    return None


def _present_count(*values: float | None) -> int:
    return sum(1 for value in values if value is not None)


def _sum_non_null(*values: float | None) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _abs_number(value: Any) -> float | None:
    number = _to_float(value)
    if number is None:
        return None
    return abs(number)


def snapshot_effective_at(snapshot: CapitalStructureSnapshot | Any) -> datetime | None:
    acceptance_at = getattr(snapshot, "filing_acceptance_at", None)
    if acceptance_at is not None:
        return _normalize_datetime(acceptance_at)
    period_end = getattr(snapshot, "period_end", None)
    if period_end is None:
        return None
    return datetime.combine(period_end, time.max, tzinfo=timezone.utc)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

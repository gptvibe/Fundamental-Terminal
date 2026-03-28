from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal

import httpx

from app.config import settings
from app.source_registry import infer_source_id

BANK_REGULATORY_STATEMENT_TYPE = "canonical_bank_regulatory"
FDIC_FINANCIALS_SOURCE_ID = "fdic_bankfind_financials"
FEDERAL_RESERVE_Y9C_SOURCE_ID = "federal_reserve_fr_y9c"
_FEDERAL_RESERVE_Y9C_OFFICIAL_URL = "https://www.federalreserve.gov/apps/reportingforms/Report/Index/FR_Y-9C"

_BANK_INDUSTRY_KEYWORDS = (
    "bank",
    "banking",
    "national association",
    "commercial bank",
    "trust company",
    "savings bank",
)
_HOLDING_COMPANY_KEYWORDS = (
    "bancorp",
    "bancshares",
    "bankshares",
    "holding company",
    "holdings",
    "financial group",
    "financial corp",
)
_CORPORATE_SUFFIXES = {
    "and",
    "bank",
    "co",
    "company",
    "corp",
    "corporation",
    "group",
    "inc",
    "llc",
    "ltd",
    "na",
    "national",
    "the",
}
_FDIC_DATE_FORMATS = ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y")
_FDIC_FINANCIAL_LIMIT = 16


@dataclass(frozen=True, slots=True)
class RegulatedEntityClassification:
    issuer_type: Literal["bank", "bank_holding_company"]
    confidence_score: float
    confidence_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RegulatoryFinancialStatement:
    filing_type: str
    period_start: date
    period_end: date
    source: str
    filing_acceptance_at: datetime | None
    data: dict[str, Any]
    selected_facts: dict[str, Any]
    reconciliation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FdicInstitutionMatch:
    cert: str | None
    rssd_id: str | None
    rssdhcr: str | None
    source: str
    confidence_score: float
    confidence_flags: list[str] = field(default_factory=list)


def classify_regulated_entity(company: Any) -> RegulatedEntityClassification | None:
    values = _classification_values(company)
    market_industry = values.get("market_industry") or ""
    market_sector = values.get("market_sector") or ""
    name = values.get("name") or ""
    combined = " ".join(value for value in values.values() if value)

    if "banks" in market_industry:
        issuer_type: Literal["bank", "bank_holding_company"] = "bank"
        confidence_score = 1.0
        flags: list[str] = []
    elif market_sector == "financials" and any(keyword in combined for keyword in _BANK_INDUSTRY_KEYWORDS):
        issuer_type = "bank"
        confidence_score = 0.9
        flags = ["regulated_entity_inferred_from_market_classification"]
    elif any(keyword in combined for keyword in _BANK_INDUSTRY_KEYWORDS):
        issuer_type = "bank"
        confidence_score = 0.78
        flags = ["regulated_entity_inferred_from_name_or_sector"]
    else:
        return None

    if any(keyword in name for keyword in _HOLDING_COMPANY_KEYWORDS):
        issuer_type = "bank_holding_company"
        confidence_score = min(1.0, confidence_score + 0.08)

    return RegulatedEntityClassification(
        issuer_type=issuer_type,
        confidence_score=round(confidence_score, 4),
        confidence_flags=sorted(set(flags)),
    )


def build_regulated_entity_payload(company: Any, financials: list[Any] | None = None) -> dict[str, Any] | None:
    classification = classify_regulated_entity(company)
    if classification is None:
        return None

    reporting_basis = "fdic_call_report" if classification.issuer_type == "bank" else "fr_y9c"
    if financials:
        source_ids = {
            infer_source_id(getattr(statement, "source", None))
            for statement in financials
        }
        if FEDERAL_RESERVE_Y9C_SOURCE_ID in source_ids and FDIC_FINANCIALS_SOURCE_ID in source_ids:
            reporting_basis = "mixed_regulatory"
        elif FEDERAL_RESERVE_Y9C_SOURCE_ID in source_ids:
            reporting_basis = "fr_y9c"
        elif FDIC_FINANCIALS_SOURCE_ID in source_ids:
            reporting_basis = "fdic_call_report"

    return {
        "issuer_type": classification.issuer_type,
        "reporting_basis": reporting_basis,
        "confidence_score": classification.confidence_score,
        "confidence_flags": classification.confidence_flags,
    }


def select_preferred_financials(company: Any, sec_financials: list[Any], regulatory_financials: list[Any]) -> list[Any]:
    classification = classify_regulated_entity(company)
    if classification is None or not regulatory_financials:
        return sec_financials
    return regulatory_financials


def collect_regulated_financial_statements(
    company: Any,
    *,
    sec_financials: list[Any] | None = None,
) -> list[RegulatoryFinancialStatement]:
    classification = classify_regulated_entity(company)
    if classification is None:
        return []

    overlays = _build_sec_overlay_map(sec_financials or [])
    statements: list[RegulatoryFinancialStatement] = []

    with FdicBankFindClient() as client:
        fdic_match = client.resolve_institution(company, classification)
        if classification.issuer_type == "bank" and fdic_match is not None:
            rows, source = client.fetch_financials(fdic_match, issuer_type=classification.issuer_type)
            statements.extend(
                map_fdic_financial_rows(
                    rows,
                    source=source,
                    issuer_type=classification.issuer_type,
                    confidence_score=min(classification.confidence_score, fdic_match.confidence_score),
                    confidence_flags=sorted(set([*classification.confidence_flags, *fdic_match.confidence_flags])),
                    sec_overlays=overlays,
                )
            )

    if classification.issuer_type == "bank_holding_company":
        statements.extend(
            load_federal_reserve_y9c_statements(
                company,
                confidence_score=classification.confidence_score,
                confidence_flags=classification.confidence_flags,
                sec_overlays=overlays,
            )
        )

    return sorted(statements, key=lambda item: (item.period_end, item.filing_type), reverse=True)


def map_fdic_financial_rows(
    rows: list[dict[str, Any]],
    *,
    source: str,
    issuer_type: Literal["bank", "bank_holding_company"],
    confidence_score: float,
    confidence_flags: list[str],
    sec_overlays: dict[date, dict[str, Any]] | None = None,
) -> list[RegulatoryFinancialStatement]:
    statements: list[RegulatoryFinancialStatement] = []
    for row in rows[:_FDIC_FINANCIAL_LIMIT]:
        statement = map_fdic_financial_row(
            row,
            source=source,
            issuer_type=issuer_type,
            confidence_score=confidence_score,
            confidence_flags=confidence_flags,
            sec_overlay=(sec_overlays or {}).get(_parse_report_date(row.get("REPDTE"))),
        )
        if statement is not None:
            statements.append(statement)
    return statements


def map_fdic_financial_row(
    row: dict[str, Any],
    *,
    source: str,
    issuer_type: Literal["bank", "bank_holding_company"],
    confidence_score: float,
    confidence_flags: list[str],
    sec_overlay: dict[str, Any] | None = None,
) -> RegulatoryFinancialStatement | None:
    period_end = _parse_report_date(row.get("REPDTE"))
    if period_end is None:
        return None

    total_assets = _fdic_amount(row.get("ASSET"))
    stockholders_equity = _fdic_amount(_first_non_null(row.get("EQTOT"), row.get("EQ")))
    total_liabilities = None
    if total_assets is not None and stockholders_equity is not None:
        total_liabilities = total_assets - stockholders_equity

    net_interest_income = _fdic_amount(row.get("NIM"))
    noninterest_income = _fdic_amount(row.get("NONII"))
    noninterest_expense = _fdic_amount(row.get("NONIX"))
    pretax_income = _fdic_amount(row.get("PTAXNETINC"))
    provision_for_credit_losses = _derive_fdic_provision(
        net_interest_income=net_interest_income,
        noninterest_income=noninterest_income,
        noninterest_expense=noninterest_expense,
        pretax_income=pretax_income,
    )

    data = {
        "net_income": _fdic_amount(row.get("NETINC")),
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "stockholders_equity": stockholders_equity,
        "cash_and_cash_equivalents": _fdic_amount(row.get("CHBAL")),
        "interest_expense": _fdic_amount(row.get("EINTEXP")),
        "net_interest_income": net_interest_income,
        "noninterest_income": noninterest_income,
        "noninterest_expense": noninterest_expense,
        "pretax_income": pretax_income,
        "provision_for_credit_losses": provision_for_credit_losses,
        "deposits_total": _fdic_amount(row.get("DEP")),
        "core_deposits": _fdic_amount(row.get("COREDEP")),
        "uninsured_deposits": _fdic_amount(row.get("DEPUNINS")),
        "loans_net": _fdic_amount(row.get("LNLSNET")),
        "net_interest_margin": _fdic_ratio(row.get("NIMY")),
        "nonperforming_assets_ratio": _fdic_ratio(row.get("NPERFV")),
        "common_equity_tier1_ratio": _fdic_ratio(row.get("IDT1CER")),
        "tier1_risk_weighted_ratio": _fdic_ratio(row.get("IDT1RWAJR")),
        "total_risk_based_capital_ratio": _fdic_ratio(row.get("RBC1AAJ")),
        "return_on_assets_ratio": _fdic_ratio(row.get("ROA")),
        "return_on_equity_ratio": _fdic_ratio(row.get("ROE")),
        "regulated_bank_source_id": FDIC_FINANCIALS_SOURCE_ID,
        "regulated_bank_reporting_basis": "fdic_call_report",
        "regulated_bank_confidence_score": round(confidence_score, 4),
        "regulated_bank_confidence_flags": sorted(set(confidence_flags + (["holding_company_proxy_from_fdic_subsidiary"] if issuer_type == "bank_holding_company" else []))),
    }
    _apply_sec_overlay(data, sec_overlay)

    if not _has_meaningful_regulated_data(data):
        return None

    return RegulatoryFinancialStatement(
        filing_type="CALL",
        period_start=_quarter_start(period_end),
        period_end=period_end,
        source=source,
        filing_acceptance_at=None,
        data=data,
        selected_facts={
            "regulated_bank": {
                "source_id": FDIC_FINANCIALS_SOURCE_ID,
                "reporting_basis": "fdic_call_report",
                "raw_identifiers": {
                    "cert": row.get("CERT"),
                    "rssd_id": row.get("RSSDID"),
                    "rssdhcr": row.get("RSSDHCR"),
                },
            }
        },
    )


def load_federal_reserve_y9c_statements(
    company: Any,
    *,
    confidence_score: float,
    confidence_flags: list[str],
    sec_overlays: dict[date, dict[str, Any]] | None = None,
) -> list[RegulatoryFinancialStatement]:
    records, source = _load_y9c_records()
    if not records or source is None:
        return []

    normalized_company_name = _normalize_name(getattr(company, "name", None))
    matched: list[dict[str, Any]] = []
    for record in records:
        reporter_names = [
            _normalize_name(record.get("name")),
            _normalize_name(record.get("company_name")),
            _normalize_name(record.get("reporter_name")),
            _normalize_name(record.get("holding_company_name")),
        ]
        if normalized_company_name and any(name and name == normalized_company_name for name in reporter_names):
            matched.append(record)

    statements: list[RegulatoryFinancialStatement] = []
    for record in matched:
        statement = map_federal_reserve_y9c_record(
            record,
            source=_FEDERAL_RESERVE_Y9C_OFFICIAL_URL,
            confidence_score=confidence_score,
            confidence_flags=confidence_flags,
            sec_overlay=(sec_overlays or {}).get(_parse_report_date(_extract_record_value(record, ["report_date", "period_end", "as_of"]))),
        )
        if statement is not None:
            statements.append(statement)
    return sorted(statements, key=lambda item: item.period_end, reverse=True)


def map_federal_reserve_y9c_record(
    record: dict[str, Any],
    *,
    source: str,
    confidence_score: float,
    confidence_flags: list[str],
    sec_overlay: dict[str, Any] | None = None,
) -> RegulatoryFinancialStatement | None:
    period_end = _parse_report_date(_extract_record_value(record, ["report_date", "period_end", "as_of"]))
    if period_end is None:
        return None

    stockholders_equity = _number(_extract_record_value(record, ["stockholders_equity", "total_equity", "BHCK3210", "3210"]))
    total_assets = _number(_extract_record_value(record, ["total_assets", "BHCK2170", "2170"]))
    total_liabilities = _number(_extract_record_value(record, ["total_liabilities", "BHCK2948", "2948"]))
    if total_liabilities is None and total_assets is not None and stockholders_equity is not None:
        total_liabilities = total_assets - stockholders_equity

    data = {
        "net_income": _number(_extract_record_value(record, ["net_income", "BHCK4340", "4340"])),
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "stockholders_equity": stockholders_equity,
        "interest_expense": _number(_extract_record_value(record, ["interest_expense", "BHCK4073", "4073"])),
        "net_interest_income": _number(_extract_record_value(record, ["net_interest_income", "BHCK4074", "4074"])),
        "noninterest_income": _number(_extract_record_value(record, ["noninterest_income", "BHCK4079", "4079"])),
        "noninterest_expense": _number(_extract_record_value(record, ["noninterest_expense", "BHCK4093", "4093"])),
        "pretax_income": _number(_extract_record_value(record, ["pretax_income", "income_before_taxes", "BHCK4301", "4301"])),
        "provision_for_credit_losses": _number(_extract_record_value(record, ["provision_for_credit_losses", "provision_burden_amount", "RIAD4230", "4230"])),
        "deposits_total": _number(_extract_record_value(record, ["deposits_total", "total_deposits", "BHCB2200", "2200"])),
        "core_deposits": _number(_extract_record_value(record, ["core_deposits"])),
        "uninsured_deposits": _number(_extract_record_value(record, ["uninsured_deposits"])),
        "loans_net": _number(_extract_record_value(record, ["loans_net", "net_loans"])),
        "net_interest_margin": _number(_extract_record_value(record, ["net_interest_margin", "nim"])),
        "nonperforming_assets_ratio": _number(_extract_record_value(record, ["nonperforming_assets_ratio", "asset_quality_ratio"])),
        "common_equity_tier1_ratio": _number(_extract_record_value(record, ["common_equity_tier1_ratio", "cet1_ratio"])),
        "tier1_risk_weighted_ratio": _number(_extract_record_value(record, ["tier1_risk_weighted_ratio", "tier1_capital_ratio"])),
        "total_risk_based_capital_ratio": _number(_extract_record_value(record, ["total_risk_based_capital_ratio", "total_capital_ratio"])),
        "regulated_bank_source_id": FEDERAL_RESERVE_Y9C_SOURCE_ID,
        "regulated_bank_reporting_basis": "fr_y9c",
        "regulated_bank_confidence_score": round(confidence_score, 4),
        "regulated_bank_confidence_flags": sorted(set(confidence_flags)),
    }

    if data.get("provision_for_credit_losses") is None:
        data["provision_for_credit_losses"] = _derive_fdic_provision(
            net_interest_income=_number(data.get("net_interest_income")),
            noninterest_income=_number(data.get("noninterest_income")),
            noninterest_expense=_number(data.get("noninterest_expense")),
            pretax_income=_number(data.get("pretax_income")),
        )

    _apply_sec_overlay(data, sec_overlay)
    if not _has_meaningful_regulated_data(data):
        return None

    return RegulatoryFinancialStatement(
        filing_type="FR Y-9C",
        period_start=_quarter_start(period_end),
        period_end=period_end,
        source=source,
        filing_acceptance_at=None,
        data=data,
        selected_facts={
            "regulated_bank": {
                "source_id": FEDERAL_RESERVE_Y9C_SOURCE_ID,
                "reporting_basis": "fr_y9c",
            }
        },
    )


class FdicBankFindClient:
    def __init__(self) -> None:
        headers = {
            "Accept": "application/json",
            "User-Agent": settings.sec_user_agent,
        }
        self._client = httpx.Client(
            base_url=settings.fdic_api_base_url.rstrip("/"),
            follow_redirects=True,
            headers=headers,
            timeout=settings.fdic_timeout_seconds,
        )

    def __enter__(self) -> FdicBankFindClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def resolve_institution(
        self,
        company: Any,
        classification: RegulatedEntityClassification,
    ) -> FdicInstitutionMatch | None:
        company_name = str(getattr(company, "name", "") or "").strip()
        if not company_name:
            return None

        candidates: list[FdicInstitutionMatch] = []
        for query in _fdic_name_queries(company_name):
            payload, request_url = self._request(
                "/institutions",
                params={
                    "filters": query,
                    "limit": 25,
                    "sort_by": "ACTIVE",
                    "sort_order": "DESC",
                },
            )
            for row in _fdic_rows(payload):
                match = _score_fdic_match(
                    company_name,
                    row,
                    source=request_url,
                    classification=classification,
                )
                if match is not None:
                    candidates.append(match)
            if candidates:
                break

        if not candidates:
            return None

        best = max(candidates, key=lambda item: item.confidence_score)
        if best.confidence_score < 0.68:
            return None
        return best

    def fetch_financials(
        self,
        match: FdicInstitutionMatch,
        *,
        issuer_type: Literal["bank", "bank_holding_company"],
    ) -> tuple[list[dict[str, Any]], str]:
        filters = None
        if issuer_type == "bank_holding_company" and match.rssdhcr:
            filters = f'RSSDHCR:{match.rssdhcr}'
        elif match.cert:
            filters = f'CERT:{match.cert}'
        elif match.rssd_id:
            filters = f'RSSDID:{match.rssd_id}'
        if not filters:
            return [], match.source

        payload, request_url = self._request(
            "/financials",
            params={
                "filters": filters,
                "limit": _FDIC_FINANCIAL_LIMIT,
                "sort_by": "REPDTE",
                "sort_order": "DESC",
            },
        )
        return _fdic_rows(payload), request_url

    def _request(self, path: str, *, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json(), str(response.request.url)


def _fdic_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for item in (payload.get("data") or []):
        data = item.get("data") if isinstance(item, dict) else None
        if isinstance(data, dict):
            rows.append(data)
    return rows


def _score_fdic_match(
    company_name: str,
    row: dict[str, Any],
    *,
    source: str,
    classification: RegulatedEntityClassification,
) -> FdicInstitutionMatch | None:
    normalized_company = _normalize_name(company_name)
    primary_name = str(row.get("NAME") or "").strip()
    holding_name = str(row.get("NAMEHCR") or "").strip()
    candidates = [name for name in (primary_name, holding_name) if name]
    if not candidates:
        return None

    similarity = max(SequenceMatcher(None, normalized_company, _normalize_name(name)).ratio() for name in candidates)
    if similarity <= 0:
        return None

    active_bonus = 0.05 if str(row.get("ACTIVE") or "") == "1" else 0.0
    if classification.issuer_type == "bank_holding_company" and holding_name:
        similarity += 0.06
    if classification.issuer_type == "bank" and primary_name:
        similarity += 0.04

    confidence_flags: list[str] = []
    if similarity < 0.8:
        confidence_flags.append("fdic_name_match_not_exact")

    return FdicInstitutionMatch(
        cert=_string_or_none(row.get("CERT")),
        rssd_id=_string_or_none(_first_non_null(row.get("RSSDID"), row.get("FED_RSSD"))),
        rssdhcr=_string_or_none(row.get("RSSDHCR")),
        source=source,
        confidence_score=round(min(1.0, similarity + active_bonus), 4),
        confidence_flags=confidence_flags,
    )


def _fdic_name_queries(company_name: str) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in (company_name, _trim_company_suffixes(company_name)):
        cleaned = candidate.replace('"', '').strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        queries.append(f'NAME:"{cleaned}" OR NAMEHCR:"{cleaned}"')
    return queries


def _load_y9c_records() -> tuple[list[dict[str, Any]], str | None]:
    if settings.federal_reserve_y9c_json_path:
        path = Path(settings.federal_reserve_y9c_json_path)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return _normalize_y9c_payload(payload), path.as_posix()

    if settings.federal_reserve_y9c_json_url:
        with httpx.Client(timeout=settings.federal_reserve_y9c_timeout_seconds, follow_redirects=True, headers={"User-Agent": settings.sec_user_agent}) as client:
            response = client.get(settings.federal_reserve_y9c_json_url)
            response.raise_for_status()
            return _normalize_y9c_payload(response.json()), str(response.request.url)

    return [], None


def _normalize_y9c_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            return [item for item in payload.get("data") if isinstance(item, dict)]
        if isinstance(payload.get("records"), list):
            return [item for item in payload.get("records") if isinstance(item, dict)]
    return []


def _extract_record_value(record: dict[str, Any], aliases: list[str]) -> Any:
    fields = record.get("fields") if isinstance(record.get("fields"), dict) else None
    for alias in aliases:
        if alias in record:
            return record.get(alias)
        if fields and alias in fields:
            return fields.get(alias)
    return None


def _apply_sec_overlay(data: dict[str, Any], sec_overlay: dict[str, Any] | None) -> None:
    if not isinstance(sec_overlay, dict):
        return

    for key in ("goodwill_and_intangibles", "shares_outstanding", "weighted_average_diluted_shares", "eps"):
        if data.get(key) is None and sec_overlay.get(key) is not None:
            data[key] = sec_overlay.get(key)

    stockholders_equity = _number(data.get("stockholders_equity"))
    goodwill = _number(data.get("goodwill_and_intangibles"))
    if stockholders_equity is not None:
        tangible_common_equity = stockholders_equity - (goodwill or 0.0)
        data["tangible_common_equity"] = tangible_common_equity


def _build_sec_overlay_map(sec_financials: list[Any]) -> dict[date, dict[str, Any]]:
    overlays: dict[date, dict[str, Any]] = {}
    for statement in sec_financials:
        period_end = getattr(statement, "period_end", None)
        raw_data = getattr(statement, "data", None)
        if not isinstance(period_end, date) or not isinstance(raw_data, dict):
            continue
        overlays[period_end] = dict(raw_data)
    return overlays


def _has_meaningful_regulated_data(data: dict[str, Any]) -> bool:
    meaningful_keys = (
        "net_interest_income",
        "net_interest_margin",
        "provision_for_credit_losses",
        "deposits_total",
        "common_equity_tier1_ratio",
    )
    return any(_number(data.get(key)) is not None for key in meaningful_keys)


def _derive_fdic_provision(
    *,
    net_interest_income: float | None,
    noninterest_income: float | None,
    noninterest_expense: float | None,
    pretax_income: float | None,
) -> float | None:
    if any(value is None for value in (net_interest_income, noninterest_income, noninterest_expense, pretax_income)):
        return None
    return (net_interest_income or 0.0) + (noninterest_income or 0.0) - (noninterest_expense or 0.0) - (pretax_income or 0.0)


def _classification_values(company: Any) -> dict[str, str]:
    return {
        "name": _normalize_text(getattr(company, "name", None)),
        "sector": _normalize_text(getattr(company, "sector", None)),
        "market_sector": _normalize_text(getattr(company, "market_sector", None)),
        "market_industry": _normalize_text(getattr(company, "market_industry", None)),
    }


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _normalize_name(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", _normalize_text(value))
    parts = [part for part in normalized.split() if part and part not in _CORPORATE_SUFFIXES]
    return " ".join(parts)


def _trim_company_suffixes(value: str) -> str:
    parts = [part for part in re.split(r"\s+", value.strip()) if part]
    while parts and re.sub(r"[^a-z0-9]+", "", parts[-1].lower()) in _CORPORATE_SUFFIXES:
        parts.pop()
    return " ".join(parts)


def _parse_report_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in _FDIC_DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _quarter_start(period_end: date) -> date:
    month = ((period_end.month - 1) // 3) * 3 + 1
    return date(period_end.year, month, 1)


def _fdic_amount(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number * 1000.0


def _fdic_ratio(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number / 100.0


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Literal

from bs4 import BeautifulSoup


EvidenceStatus = Literal["available", "not_available"]

_SUPPORTED_FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K"}
_MILLION = 1_000_000.0
_BILLION = 1_000_000_000.0
_SENSITIVITY_PATTERNS = (
    re.compile(
        r"\$(?P<oil_delta>[\d,.]+)\s+per\s+barrel[^.]{0,220}?(?P<benchmark>Brent|WTI)[^.]{0,220}?(?:after[- ]tax\s+)?earnings[^$]{0,80}?\$(?P<earnings>[\d,.]+)\s*(?P<scale>billion|million)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?P<benchmark>Brent|WTI)[^.]{0,220}?(?:after[- ]tax\s+)?earnings[^$]{0,80}?\$(?P<earnings>[\d,.]+)\s*(?P<scale>billion|million)[^.]{0,160}?\$(?P<oil_delta>[\d,.]+)\s+per\s+barrel",
        flags=re.IGNORECASE,
    ),
)


def collect_company_oil_evidence(
    cik: str,
    *,
    checked_at: datetime,
    client: Any | None = None,
    submissions: dict[str, Any] | None = None,
    companyfacts: dict[str, Any] | None = None,
    filing_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_checked_at = _normalize_datetime(checked_at) or datetime.now(timezone.utc)
    owned_client = False
    sec_client = client
    try:
        if sec_client is None:
            from app.services.sec_edgar import EdgarClient

            sec_client = EdgarClient()
            owned_client = True

        submissions_payload = submissions if isinstance(submissions, dict) else _safe_get_json(sec_client, "submissions", cik)
        companyfacts_payload = companyfacts if isinstance(companyfacts, dict) else _safe_get_json(sec_client, "companyfacts", cik)
        filing_lookup = filing_index if isinstance(filing_index, dict) else _safe_build_filing_index(sec_client, submissions_payload)

        disclosed_sensitivity = _not_available_field(
            reason="No clearly disclosed Brent or WTI oil sensitivity was found in the parsed filing text.",
            provenance_sources=["sec_edgar"],
        )
        realized_price_comparison = {
            **_not_available_field(
                reason="No clearly structured realized-price-versus-benchmark table was found in the parsed filing text.",
                provenance_sources=["sec_edgar"],
            ),
            "benchmark": None,
            "rows": [],
        }

        for metadata in _sorted_supported_filings(filing_lookup):
            document_name = str(getattr(metadata, "primary_document", "") or "").strip()
            if not document_name:
                continue

            try:
                source_url, payload = sec_client.get_filing_document_text(cik, getattr(metadata, "accession_number", ""), document_name)
            except Exception:
                continue

            if disclosed_sensitivity["status"] != "available":
                disclosed_sensitivity = _extract_disclosed_sensitivity(payload, metadata=metadata, source_url=source_url)
            if realized_price_comparison["status"] != "available":
                realized_price_comparison = _extract_realized_vs_benchmark_table(payload, metadata=metadata, source_url=source_url)
            if disclosed_sensitivity["status"] == "available" and realized_price_comparison["status"] == "available":
                break

        diluted_shares = _extract_diluted_shares(companyfacts_payload, cik=cik, filing_index=filing_lookup)
        parser_confidence_flags = sorted(
            {
                *[str(flag) for flag in disclosed_sensitivity.get("confidence_flags") or [] if isinstance(flag, str)],
                *[str(flag) for flag in diluted_shares.get("confidence_flags") or [] if isinstance(flag, str)],
                *[str(flag) for flag in realized_price_comparison.get("confidence_flags") or [] if isinstance(flag, str)],
            }
        )

        available_count = sum(
            1
            for item in (disclosed_sensitivity, diluted_shares, realized_price_comparison)
            if item.get("status") == "available"
        )
        if available_count == 3:
            status = "available"
        elif available_count:
            status = "partial"
        else:
            status = "not_available"

        return {
            "status": status,
            "parser_confidence_flags": parser_confidence_flags,
            "checked_at": normalized_checked_at.isoformat(),
            "disclosed_sensitivity": disclosed_sensitivity,
            "diluted_shares": diluted_shares,
            "realized_price_comparison": realized_price_comparison,
        }
    finally:
        if owned_client and sec_client is not None:
            sec_client.close()


def _safe_get_json(client: Any, kind: str, cik: str) -> dict[str, Any]:
    try:
        if kind == "submissions":
            payload = client.get_submissions(cik)
        else:
            payload = client.get_companyfacts(cik)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_build_filing_index(client: Any, submissions: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = client.build_filing_index(submissions)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sorted_supported_filings(filing_index: dict[str, Any] | None) -> list[Any]:
    candidates: list[Any] = []
    for metadata in (filing_index or {}).values():
        base_form = _base_form(getattr(metadata, "form", None))
        if base_form in _SUPPORTED_FORMS:
            candidates.append(metadata)
    candidates.sort(
        key=lambda item: (
            getattr(item, "filing_date", None) or getattr(item, "report_date", None) or date.min,
            getattr(item, "accession_number", "") or "",
        ),
        reverse=True,
    )
    return candidates


def _extract_disclosed_sensitivity(payload: str, *, metadata: Any, source_url: str) -> dict[str, Any]:
    text = _normalize_text(BeautifulSoup(payload, "html.parser").get_text(" ", strip=True) if "<" in payload else payload)
    matches: list[dict[str, Any]] = []
    for pattern in _SENSITIVITY_PATTERNS:
        for match in pattern.finditer(text):
            oil_delta = _parse_number(match.group("oil_delta"))
            earnings = _parse_number(match.group("earnings"))
            scale = str(match.group("scale") or "").lower()
            benchmark = str(match.group("benchmark") or "").strip().lower()
            if oil_delta is None or oil_delta <= 0 or earnings is None or benchmark not in {"brent", "wti"}:
                continue
            scaled_earnings = earnings * (_BILLION if scale == "billion" else _MILLION)
            matches.append(
                {
                    "benchmark": benchmark,
                    "oil_price_change_per_bbl": oil_delta,
                    "annual_after_tax_earnings_change": scaled_earnings,
                    "annual_after_tax_sensitivity": scaled_earnings / oil_delta,
                }
            )

    unique_matches = {
        (item["benchmark"], round(float(item["annual_after_tax_sensitivity"]), 2), round(float(item["oil_price_change_per_bbl"]), 2))
        for item in matches
    }
    if not unique_matches:
        return _not_available_field(
            reason="No clearly disclosed Brent or WTI oil sensitivity was found in the parsed filing text.",
            provenance_sources=["sec_edgar"],
            confidence_flags=["oil_sensitivity_not_available"],
        )
    if len(unique_matches) > 1:
        return _not_available_field(
            reason="Multiple conflicting oil sensitivity disclosures were found in the filing text.",
            provenance_sources=["sec_edgar"],
            source_url=source_url,
            accession_number=getattr(metadata, "accession_number", None),
            filing_form=getattr(metadata, "form", None),
            confidence_flags=["oil_sensitivity_ambiguous"],
        )

    selected = matches[0]
    return {
        "status": "available",
        "reason": None,
        "benchmark": selected["benchmark"],
        "oil_price_change_per_bbl": selected["oil_price_change_per_bbl"],
        "annual_after_tax_earnings_change": selected["annual_after_tax_earnings_change"],
        "annual_after_tax_sensitivity": selected["annual_after_tax_sensitivity"],
        "metric_basis": "annual_after_tax_earnings_usd",
        "source_url": source_url,
        "accession_number": getattr(metadata, "accession_number", None),
        "filing_form": getattr(metadata, "form", None),
        "confidence_flags": ["oil_sensitivity_disclosed"],
        "provenance_sources": ["sec_edgar"],
    }


def _extract_realized_vs_benchmark_table(payload: str, *, metadata: Any, source_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(payload, "html.parser")
    best_candidate: dict[str, Any] | None = None
    best_score = -1

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [_normalize_text(cell.get_text(" ", strip=True)) for cell in header_cells]
        column_roles = [_classify_realized_table_header(header) for header in headers]
        if "realized_price" not in column_roles or not any(role in {"benchmark_price", "realized_percent"} for role in column_roles):
            continue

        benchmark_label = _benchmark_from_headers(headers)
        parsed_rows: list[dict[str, Any]] = []
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            values = [cell.get_text(" ", strip=True) for cell in cells]
            parsed = _parse_realized_table_row(values, column_roles, benchmark_label)
            if parsed is not None:
                parsed_rows.append(parsed)

        if not parsed_rows:
            continue
        score = len(parsed_rows) * 10
        if any(item.get("benchmark_price") is not None for item in parsed_rows):
            score += 5
        if any(item.get("realized_percent_of_benchmark") is not None for item in parsed_rows):
            score += 3
        if score > best_score:
            best_score = score
            best_candidate = {
                "status": "available",
                "reason": None,
                "benchmark": benchmark_label,
                "rows": parsed_rows,
                "source_url": source_url,
                "accession_number": getattr(metadata, "accession_number", None),
                "filing_form": getattr(metadata, "form", None),
                "confidence_flags": ["realized_vs_benchmark_table_parsed"],
                "provenance_sources": ["sec_edgar"],
            }

    if best_candidate is None:
        return {
            **_not_available_field(
                reason="No clearly structured realized-price-versus-benchmark table was found in the parsed filing text.",
                provenance_sources=["sec_edgar"],
                confidence_flags=["realized_vs_benchmark_not_available"],
            ),
            "benchmark": None,
            "rows": [],
        }
    return best_candidate


def _classify_realized_table_header(header: str) -> str:
    normalized = _normalize_identifier(header)
    if not normalized:
        return "unknown"
    if normalized.startswith(("year", "quarter", "period", "fiscalyear")):
        return "period"
    if "realized" in normalized and "%" in header:
        return "realized_percent"
    if "percentof" in normalized and any(token in normalized for token in ("benchmark", "brent", "wti")):
        return "realized_percent"
    if "realized" in normalized and any(token in normalized for token in ("price", "perbarrel", "perbbl")):
        return "realized_price"
    if any(token in normalized for token in ("benchmark", "brent", "wti")) and "%" not in header:
        return "benchmark_price"
    return "unknown"


def _parse_realized_table_row(values: list[str], column_roles: list[str], benchmark_label: str | None) -> dict[str, Any] | None:
    period_label = None
    realized_price = None
    benchmark_price = None
    realized_percent = None
    for raw_value, role in zip(values, column_roles, strict=False):
        if role == "period" and period_label is None:
            candidate = " ".join(raw_value.split())
            if candidate:
                period_label = candidate
        elif role == "realized_price":
            realized_price = _parse_number(raw_value)
        elif role == "benchmark_price":
            benchmark_price = _parse_number(raw_value)
        elif role == "realized_percent":
            realized_percent = _parse_percent(raw_value)

    if period_label is None or realized_price is None:
        return None
    if benchmark_price is None and realized_percent is None:
        return None
    if realized_percent is None and benchmark_price not in (None, 0):
        realized_percent = (realized_price / benchmark_price) * 100.0
    premium_discount = realized_price - benchmark_price if benchmark_price is not None else None
    return {
        "period_label": period_label,
        "benchmark": benchmark_label,
        "realized_price": realized_price,
        "benchmark_price": benchmark_price,
        "realized_percent_of_benchmark": realized_percent,
        "premium_discount": premium_discount,
    }


def _benchmark_from_headers(headers: list[str]) -> str | None:
    for header in headers:
        normalized = _normalize_identifier(header)
        if "brent" in normalized:
            return "brent"
        if "wti" in normalized:
            return "wti"
    return None


def _extract_diluted_shares(companyfacts: dict[str, Any], *, cik: str, filing_index: dict[str, Any] | None) -> dict[str, Any]:
    facts_root = companyfacts.get("facts") if isinstance(companyfacts, dict) else None
    if not isinstance(facts_root, dict):
        return _not_available_field(
            reason="SEC companyfacts did not include a usable diluted-shares fact.",
            provenance_sources=["sec_companyfacts"],
            confidence_flags=["diluted_shares_not_available"],
        )

    candidates: list[dict[str, Any]] = []
    for metric, tags in (
        ("weighted_average_diluted_shares", [("us-gaap", ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfShareOutstandingBasicAndDiluted"]), ("ifrs-full", ["WeightedAverageNumberOfOrdinarySharesOutstandingDiluted"])]),
        ("shares_outstanding", [("us-gaap", ["CommonStockSharesOutstanding"]), ("dei", ["EntityCommonStockSharesOutstanding"])]),
    ):
        for taxonomy, taxonomy_tags in tags:
            taxonomy_root = facts_root.get(taxonomy)
            if not isinstance(taxonomy_root, dict):
                continue
            for tag in taxonomy_tags:
                fact_payload = taxonomy_root.get(tag)
                if not isinstance(fact_payload, dict):
                    continue
                for observation in _iter_share_observations(fact_payload):
                    value = _parse_companyfacts_value(observation.get("val"))
                    if value is None:
                        continue
                    candidates.append(
                        {
                            "metric": metric,
                            "taxonomy": taxonomy,
                            "tag": tag,
                            "value": value,
                            "accession_number": observation.get("accn"),
                            "filed": _parse_iso_date(observation.get("filed")),
                            "period_end": _parse_iso_date(observation.get("end")),
                            "form": observation.get("form"),
                        }
                    )

    if not candidates:
        return _not_available_field(
            reason="SEC companyfacts did not include a usable diluted-shares fact.",
            provenance_sources=["sec_companyfacts"],
            confidence_flags=["diluted_shares_not_available"],
        )

    latest_filing_accessions = {
        getattr(item, "accession_number", None)
        for item in _sorted_supported_filings(filing_index)
        if getattr(item, "accession_number", None)
    }
    candidates.sort(
        key=lambda item: (
            1 if item["metric"] == "weighted_average_diluted_shares" else 0,
            1 if item.get("accession_number") in latest_filing_accessions else 0,
            item.get("period_end") or date.min,
            item.get("filed") or date.min,
        ),
        reverse=True,
    )
    selected = candidates[0]
    accession_number = selected.get("accession_number")
    source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    if accession_number:
        source_url = f"{source_url}#accn={accession_number}"

    return {
        "status": "available",
        "reason": None,
        "value": selected["value"],
        "unit": "shares",
        "source_url": source_url,
        "accession_number": accession_number,
        "filing_form": selected.get("form"),
        "taxonomy": selected["taxonomy"],
        "tag": selected["tag"],
        "confidence_flags": [
            "weighted_average_diluted_shares_companyfacts"
            if selected["metric"] == "weighted_average_diluted_shares"
            else "shares_outstanding_companyfacts"
        ],
        "provenance_sources": ["sec_companyfacts"],
    }


def _iter_share_observations(fact_payload: dict[str, Any]) -> list[dict[str, Any]]:
    units_root = fact_payload.get("units") if isinstance(fact_payload, dict) else None
    if not isinstance(units_root, dict):
        return []
    observations: list[dict[str, Any]] = []
    for unit, unit_observations in units_root.items():
        if unit != "shares" and not str(unit).endswith(("share", "shares")):
            continue
        if not isinstance(unit_observations, list):
            continue
        for observation in unit_observations:
            if isinstance(observation, dict):
                observations.append(observation)
    return observations


def _not_available_field(
    *,
    reason: str,
    provenance_sources: list[str],
    source_url: str | None = None,
    accession_number: str | None = None,
    filing_form: str | None = None,
    confidence_flags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "not_available",
        "reason": reason,
        "source_url": source_url,
        "accession_number": accession_number,
        "filing_form": filing_form,
        "confidence_flags": sorted(set(confidence_flags or [])),
        "provenance_sources": provenance_sources,
    }


def _base_form(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text[:-2] if text.endswith("/A") else text


def _parse_companyfacts_value(value: Any) -> float | None:
    return _parse_number(value)


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.replace("$", "").replace(",", "").replace("%", "").strip("()")
    match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    numeric = float(match.group(0))
    return -abs(numeric) if negative else numeric


def _parse_percent(value: Any) -> float | None:
    parsed = _parse_number(value)
    return parsed if parsed is None else parsed


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
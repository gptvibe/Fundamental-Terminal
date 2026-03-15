from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Sequence

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, InstitutionalFund, InstitutionalHolding
from app.services.sec_cache import sec_http_cache
from app.services.status_stream import JobReporter

logger = logging.getLogger(__name__)

THIRTEEN_F_BASE_FORMS = {"13F-HR"}
LEGAL_ENTITY_STOP_WORDS = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "holdings",
    "holding",
    "group",
    "plc",
    "ltd",
    "limited",
    "sa",
    "nv",
    "ag",
    "llc",
    "lp",
    "the",
    "class",
    "cl",
    "common",
    "stock",
}

CURATED_13F_MANAGERS: tuple[tuple[str, str], ...] = (
    ("Berkshire Hathaway Inc", "Berkshire Hathaway"),
    ("Bridgewater Associates, LP", "Bridgewater Associates"),
    ("Pershing Square Capital Management, L.P.", "Pershing Square"),
    ("Scion Asset Management, LLC", "Scion Asset Management"),
    ("Appaloosa LP", "Appaloosa"),
    ("Third Point LLC", "Third Point"),
    ("Renaissance Technologies LLC", "Renaissance Technologies"),
    ("D. E. Shaw & Co., L.P.", "D. E. Shaw"),
    ("T. Rowe Price Investment Management, Inc.", "T. Rowe Price"),
    ("Capital World Investors", "Capital World Investors"),
)

CURATED_13F_STRATEGIES: dict[str, str] = {
    "berkshire hathaway": "Concentrated value and quality investing.",
    "bridgewater associates": "Global macro and risk-parity investing.",
    "pershing square": "Concentrated activist value investing.",
    "scion asset management": "Deep-value and contrarian investing.",
    "appaloosa": "Opportunistic value and event-driven investing.",
    "third point": "Event-driven and activist investing.",
    "renaissance technologies": "Quantitative and systematic investing.",
    "d e shaw": "Quantitative multi-strategy investing.",
    "t rowe price": "Long-only growth investing.",
    "capital world investors": "Fundamental long-only global growth investing.",
}


@dataclass(slots=True)
class FundCandidate:
    search_query: str
    manager_name: str


@dataclass(slots=True)
class ResolvedFund:
    fund_cik: str
    fund_name: str
    fund_manager: str


@dataclass(slots=True)
class FilingMetadata:
    accession_number: str
    form: str | None
    filing_date: date | None
    report_date: date | None
    primary_document: str | None


@dataclass(slots=True)
class HoldingSnapshot:
    accession_number: str
    reporting_date: date
    filing_date: date | None
    shares_held: float | None
    market_value: float | None
    change_in_shares: float | None
    percent_change: float | None
    portfolio_weight: float | None
    source: str


class InstitutionalHoldingsClient:
    def __init__(self) -> None:
        self._http = httpx.Client(
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
            timeout=settings.sec_timeout_seconds,
        )
        self._last_request_at = 0.0

    def close(self) -> None:
        self._http.close()

    def resolve_fund(self, candidate: FundCandidate) -> ResolvedFund | None:
        payload = self._get_json(settings.sec_search_base_url, params={"q": f"{candidate.search_query} 13F-HR"})
        hits = ((payload or {}).get("hits") or {}).get("hits") or []

        best_payload: dict[str, Any] | None = None
        best_score = -1
        query_tokens = _name_tokens(candidate.search_query)
        for hit in hits[:20]:
            source = hit.get("_source") or {}
            display_name = " ".join(source.get("display_names") or [])
            cik = ((source.get("ciks") or [None])[0])
            form = str(source.get("form") or "")
            if not display_name or not cik or _base_form(form) not in THIRTEEN_F_BASE_FORMS:
                continue

            display_tokens = _name_tokens(display_name)
            overlap_score = len(query_tokens & display_tokens)
            if overlap_score > best_score:
                best_score = overlap_score
                best_payload = source

        if best_payload is None:
            logger.warning("Unable to resolve 13F fund for query %s", candidate.search_query)
            return None

        raw_display_name = " ".join(best_payload.get("display_names") or [])
        cleaned_name = _clean_display_name(raw_display_name)
        fund_cik = _zero_pad_cik(str((best_payload.get("ciks") or [""])[0]))
        return ResolvedFund(
            fund_cik=fund_cik,
            fund_name=cleaned_name or candidate.manager_name,
            fund_manager=candidate.manager_name,
        )

    def get_submissions(self, cik: str) -> dict[str, Any]:
        return self._get_json(f"{settings.sec_submissions_base_url}/CIK{_zero_pad_cik(cik)}.json")

    def get_filing_index(self, cik: str, accession_number: str) -> dict[str, Any]:
        return self._get_json(_filing_index_url(cik, accession_number))

    def get_text(self, url: str, *, accept: str = "application/xml,text/xml,text/plain,*/*") -> str:
        response = self._request(url, headers={"Accept": accept})
        return response.text

    def _get_json(self, url: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request(url, params=params)
        return response.json()

    def _request(self, url: str, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> httpx.Response:
        cached_response = sec_http_cache.get("GET", url, params=params, headers=headers)
        if cached_response is not None:
            return cached_response

        elapsed = time.monotonic() - self._last_request_at
        wait_seconds = settings.sec_min_request_interval_seconds - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        response = self._http.get(url, params=params, headers=headers)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        sec_http_cache.put("GET", url, response, params=params, headers=headers)
        return response


def refresh_company_institutional_holdings(
    session: Session,
    company: Company,
    *,
    checked_at: datetime,
    reporter: JobReporter,
    force: bool = False,
) -> int:
    client = InstitutionalHoldingsClient()
    try:
        reporter.step("13f", "Resolving major 13F managers...")
        resolved_funds = _resolve_curated_funds(session, client, checked_at, limit=settings.sec_13f_manager_limit)
        session.commit()
        if not resolved_funds:
            reporter.step("13f", "No 13F managers resolved; skipping institutional holdings refresh.")
            _touch_company_institutional_holdings(session, company.id, checked_at)
            return 0

        reporter.step("13f", f"Checking SEC 13F filings across {len(resolved_funds)} managers...")
        normalized_holdings: list[tuple[int, HoldingSnapshot]] = []
        company_tokens = _name_tokens(company.name)
        for fund in resolved_funds:
            try:
                submissions = client.get_submissions(fund.fund_cik)
                filings = _latest_two_13f_filings(submissions)
                if not filings:
                    continue
                snapshots = _collect_fund_company_snapshots(client, fund, company_tokens, filings)
                normalized_holdings.extend((fund.id, snapshot) for snapshot in snapshots)
            except Exception as exc:
                logger.warning("Unable to refresh 13F holdings for %s: %s", fund.fund_name, exc)

        reporter.step("database", "Saving institutional holdings to database...")
        holdings_written = _upsert_institutional_holdings(
            session=session,
            company=company,
            fund_snapshots=normalized_holdings,
            checked_at=checked_at,
        )
        _touch_company_institutional_holdings(session, company.id, checked_at)
        return holdings_written
    finally:
        client.close()


def get_company_institutional_holdings_last_checked(session: Session, company: Company) -> datetime | None:
    if company.institutional_holdings_last_checked is not None:
        return company.institutional_holdings_last_checked

    statement = select(func.max(InstitutionalHolding.last_checked)).where(InstitutionalHolding.company_id == company.id)
    return session.execute(statement).scalar_one_or_none()


def _resolve_curated_funds(
    session: Session,
    client: InstitutionalHoldingsClient,
    checked_at: datetime,
    *,
    limit: int,
) -> list[InstitutionalFund]:
    resolved_rows: list[InstitutionalFund] = []
    for search_query, manager_name in CURATED_13F_MANAGERS[:limit]:
        resolved = client.resolve_fund(FundCandidate(search_query=search_query, manager_name=manager_name))
        if resolved is None:
            continue
        fund = _upsert_institutional_fund(session, resolved, checked_at)
        resolved_rows.append(fund)
    return resolved_rows


def _upsert_institutional_fund(session: Session, resolved: ResolvedFund, checked_at: datetime) -> InstitutionalFund:
    statement = (
        insert(InstitutionalFund)
        .values(
            fund_cik=resolved.fund_cik,
            fund_name=resolved.fund_name,
            fund_manager=resolved.fund_manager,
            last_checked=checked_at,
        )
        .on_conflict_do_update(
            index_elements=[InstitutionalFund.fund_cik],
            set_={
                "fund_name": resolved.fund_name,
                "fund_manager": resolved.fund_manager,
                "last_checked": checked_at,
            },
        )
        .returning(InstitutionalFund.id)
    )
    fund_id = session.execute(statement).scalar_one()
    return session.get(InstitutionalFund, fund_id)


def _latest_two_13f_filings(submissions: dict[str, Any]) -> list[FilingMetadata]:
    recent = submissions.get("filings", {}).get("recent", {})
    rows: list[FilingMetadata] = []
    for form, accession, filing_date, report_date, primary_document in zip(
        recent.get("form", []) or [],
        recent.get("accessionNumber", []) or [],
        recent.get("filingDate", []) or [],
        recent.get("reportDate", []) or [],
        recent.get("primaryDocument", []) or [],
    ):
        if _base_form(form) not in THIRTEEN_F_BASE_FORMS:
            continue
        rows.append(
            FilingMetadata(
                accession_number=str(accession),
                form=form,
                filing_date=_parse_date(filing_date),
                report_date=_parse_date(report_date),
                primary_document=str(primary_document) if primary_document else None,
            )
        )

    rows.sort(key=lambda row: (row.report_date or date.min, row.filing_date or date.min), reverse=True)
    distinct_rows: list[FilingMetadata] = []
    seen_reporting_dates: set[date] = set()
    for row in rows:
        if row.report_date is None or row.report_date in seen_reporting_dates:
            continue
        seen_reporting_dates.add(row.report_date)
        distinct_rows.append(row)
        if len(distinct_rows) >= 2:
            break
    return distinct_rows


def _collect_fund_company_snapshots(
    client: InstitutionalHoldingsClient,
    fund: InstitutionalFund,
    company_tokens: set[str],
    filings: Sequence[FilingMetadata],
) -> list[HoldingSnapshot]:
    parsed_rows: list[tuple[FilingMetadata, HoldingSnapshot | None]] = []
    for filing in filings:
        parsed_rows.append((filing, _extract_company_snapshot(client, fund, company_tokens, filing)))

    if not parsed_rows:
        return []

    latest_filing, latest_snapshot = parsed_rows[0]
    previous_snapshot = parsed_rows[1][1] if len(parsed_rows) > 1 else None

    snapshots: list[HoldingSnapshot] = []
    if latest_snapshot is not None:
        previous_shares = previous_snapshot.shares_held if previous_snapshot is not None else 0.0
        change_in_shares = None
        percent_change = None
        if latest_snapshot.shares_held is not None:
            if previous_snapshot is not None and previous_snapshot.shares_held is not None:
                change_in_shares = latest_snapshot.shares_held - previous_snapshot.shares_held
                if previous_snapshot.shares_held != 0:
                    percent_change = change_in_shares / previous_snapshot.shares_held
            elif latest_filing.report_date is not None:
                change_in_shares = latest_snapshot.shares_held - previous_shares

        snapshots.append(
            HoldingSnapshot(
                accession_number=latest_snapshot.accession_number,
                reporting_date=latest_snapshot.reporting_date,
                filing_date=latest_snapshot.filing_date,
                shares_held=latest_snapshot.shares_held,
                market_value=latest_snapshot.market_value,
                change_in_shares=change_in_shares,
                percent_change=percent_change,
                portfolio_weight=latest_snapshot.portfolio_weight,
                source=latest_snapshot.source,
            )
        )

    if previous_snapshot is not None:
        snapshots.append(previous_snapshot)

    return snapshots


def _extract_company_snapshot(
    client: InstitutionalHoldingsClient,
    fund: InstitutionalFund,
    company_tokens: set[str],
    filing: FilingMetadata,
) -> HoldingSnapshot | None:
    if filing.report_date is None:
        return None

    xml_url, xml_payload = _load_information_table_xml(client, fund.fund_cik, filing)
    if not xml_payload:
        return None

    try:
        root = ET.fromstring(xml_payload)
    except ET.ParseError:
        logger.warning("Unable to parse 13F information table for %s %s", fund.fund_name, filing.accession_number)
        return None

    rows = [element for element in root.iter() if _local_name(element.tag) == "infoTable"]
    if not rows:
        return None

    total_market_value = 0.0
    matched_market_value = 0.0
    matched_shares = 0.0
    matched = False

    for row in rows:
        issuer_name = _child_text(row, "nameOfIssuer")
        market_value = _parse_float(_child_text(row, "value"))
        shares = _parse_float(_child_text(row, "sshPrnamt"))

        actual_market_value = market_value or 0.0
        total_market_value += actual_market_value

        if not issuer_name or not _issuer_matches_company(issuer_name, company_tokens):
            continue

        matched = True
        matched_market_value += actual_market_value
        matched_shares += shares or 0.0

    if not matched:
        return None

    portfolio_weight = (matched_market_value / total_market_value) if total_market_value else None
    return HoldingSnapshot(
        accession_number=filing.accession_number,
        reporting_date=filing.report_date,
        filing_date=filing.filing_date,
        shares_held=matched_shares,
        market_value=matched_market_value,
        change_in_shares=None,
        percent_change=None,
        portfolio_weight=portfolio_weight,
        source=xml_url,
    )


def _load_information_table_xml(
    client: InstitutionalHoldingsClient,
    cik: str,
    filing: FilingMetadata,
) -> tuple[str, str | None]:
    index_payload = client.get_filing_index(cik, filing.accession_number)
    items = index_payload.get("directory", {}).get("item", []) or []
    preferred_names = []
    for item in items:
        name = str(item.get("name") or "")
        lowered = name.lower()
        if lowered.endswith(".xml") and lowered != (filing.primary_document or "").lower():
            preferred_names.append(name)

    preferred_names.sort(key=lambda name: ("info" not in name.lower(), "table" not in name.lower(), len(name)))
    for name in preferred_names:
        url = _filing_document_url(cik, filing.accession_number, name)
        payload = client.get_text(url)
        if "infoTable" in payload or "informationTable" in payload:
            return url, payload

    text_candidates = [str(item.get("name") or "") for item in items if str(item.get("name") or "").lower().endswith(".txt")]
    for name in text_candidates:
        url = _filing_document_url(cik, filing.accession_number, name)
        payload = client.get_text(url, accept="text/plain,*/*")
        xml_fragment = _extract_information_table_fragment(payload)
        if xml_fragment:
            return url, xml_fragment

    return _filing_document_url(cik, filing.accession_number, filing.primary_document or ""), None


def _upsert_institutional_holdings(
    session: Session,
    company: Company,
    *,
    fund_snapshots: Sequence[tuple[int, HoldingSnapshot]],
    checked_at: datetime,
) -> int:
    holdings_written = 0
    for fund_id, snapshot in fund_snapshots:
        statement = (
            insert(InstitutionalHolding)
            .values(
                company_id=company.id,
                fund_id=fund_id,
                accession_number=snapshot.accession_number,
                reporting_date=snapshot.reporting_date,
                filing_date=snapshot.filing_date,
                shares_held=snapshot.shares_held,
                market_value=snapshot.market_value,
                change_in_shares=snapshot.change_in_shares,
                percent_change=snapshot.percent_change,
                portfolio_weight=snapshot.portfolio_weight,
                source=snapshot.source,
                last_checked=checked_at,
            )
            .on_conflict_do_update(
                constraint="uq_institutional_holdings_company_fund_reporting_date",
                set_={
                    "accession_number": snapshot.accession_number,
                    "filing_date": snapshot.filing_date,
                    "shares_held": snapshot.shares_held,
                    "market_value": snapshot.market_value,
                    "change_in_shares": snapshot.change_in_shares,
                    "percent_change": snapshot.percent_change,
                    "portfolio_weight": snapshot.portfolio_weight,
                    "source": snapshot.source,
                    "last_checked": checked_at,
                    "last_updated": checked_at,
                },
            )
        )
        session.execute(statement)
        holdings_written += 1
    return holdings_written


def _touch_company_institutional_holdings(session: Session, company_id: int, checked_at: datetime) -> None:
    session.execute(
        update(Company)
        .where(Company.id == company_id)
        .values(institutional_holdings_last_checked=checked_at)
    )


def _issuer_matches_company(issuer_name: str, company_tokens: set[str]) -> bool:
    issuer_tokens = _name_tokens(issuer_name)
    if not issuer_tokens or not company_tokens:
        return False
    if issuer_tokens == company_tokens:
        return True
    overlap = issuer_tokens & company_tokens
    if len(company_tokens) == 1:
        return bool(overlap)
    return len(overlap) >= max(2, len(company_tokens) - 1)


def _name_tokens(value: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
    return {token for token in cleaned.split() if token and token not in LEGAL_ENTITY_STOP_WORDS and len(token) > 1}


def _clean_display_name(value: str) -> str:
    cleaned = re.sub(r"\s*\([^)]*CIK[^)]*\)", "", value)
    cleaned = re.sub(r"\s*\([^)]*\)", "", cleaned)
    return " ".join(cleaned.split())


def _child_text(node: ET.Element, local_name: str) -> str | None:
    for child in node.iter():
        if _local_name(child.tag) == local_name and child is not node:
            text = (child.text or "").strip()
            return text or None
    return None


def _extract_information_table_fragment(payload: str) -> str | None:
    start = payload.find("<informationTable")
    end = payload.rfind("</informationTable>")
    if start == -1 or end == -1:
        return None
    return payload[start : end + len("</informationTable>")]


def _filing_index_url(cik: str, accession_number: str) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/index.json"


def _filing_document_url(cik: str, accession_number: str, document_name: str) -> str:
    accession_compact = accession_number.replace("-", "")
    numeric_cik = str(int(cik))
    return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{accession_compact}/{document_name}"


def _base_form(value: str | None) -> str:
    if not value:
        return ""
    return value.split("/")[0].upper()


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def _parse_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def _local_name(tag: str) -> str:
    return tag.split("}")[-1]


def _zero_pad_cik(value: str) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    return digits.zfill(10)


def get_institutional_fund_strategy(fund_name: str | None, fund_manager: str | None = None) -> str | None:
    candidates = [fund_manager or "", fund_name or ""]
    for candidate in candidates:
        normalized = re.sub(r"[^a-z0-9 ]+", " ", candidate.lower())
        compact = " ".join(normalized.split())
        for key, strategy in CURATED_13F_STRATEGIES.items():
            if key in compact:
                return strategy
    return None

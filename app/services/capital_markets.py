from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Iterable

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import CapitalMarketsEvent, Company
from app.services.sec_edgar import FilingMetadata

SUPPORTED_CAPITAL_FORMS = {
    "S-1", "S-1/A", "S-3", "S-3/A", "F-3", "F-3/A", "424B1", "424B2", "424B3", "424B4", "424B5", "NT 10-K", "NT 10-Q",
}


@dataclass(slots=True)
class NormalizedCapitalMarketsEvent:
    accession_number: str
    form: str
    filing_date: date | None
    report_date: date | None
    primary_document: str | None
    primary_doc_description: str | None
    source_url: str
    summary: str
    event_type: str | None = None
    security_type: str | None = None
    offering_amount: float | None = None
    shelf_size: float | None = None
    is_late_filer: bool = False


def collect_capital_markets_events(cik: str, filing_index: dict[str, FilingMetadata]) -> list[NormalizedCapitalMarketsEvent]:
    rows: list[NormalizedCapitalMarketsEvent] = []
    for filing in filing_index.values():
        form = (filing.form or "").upper()
        if form not in SUPPORTED_CAPITAL_FORMS:
            continue

        description = _normalize_optional_text(filing.primary_doc_description)
        source_url = _build_filing_document_url(cik, filing.accession_number, filing.primary_document)
        event_type = _event_type(form)
        security_type = _security_type(form, description)
        offering_amount = _extract_dollar_amount(description)
        shelf_size = offering_amount if form in {"S-3", "S-3/A", "F-3", "F-3/A"} else None
        is_late_filer = form in {"NT 10-K", "NT 10-Q"}
        summary = _summary_line(form, description, event_type, security_type, offering_amount, is_late_filer)

        rows.append(
            NormalizedCapitalMarketsEvent(
                accession_number=filing.accession_number,
                form=form,
                filing_date=filing.filing_date,
                report_date=filing.report_date,
                primary_document=_normalize_optional_text(filing.primary_document),
                primary_doc_description=description,
                source_url=source_url,
                summary=summary,
                event_type=event_type,
                security_type=security_type,
                offering_amount=offering_amount,
                shelf_size=shelf_size,
                is_late_filer=is_late_filer,
            )
        )

    rows.sort(key=lambda row: (row.filing_date or row.report_date or datetime.min.date(), row.accession_number), reverse=True)
    return rows


def upsert_capital_markets_events(
    session: Session,
    company: Company,
    events: Iterable[NormalizedCapitalMarketsEvent],
    *,
    checked_at: datetime,
) -> int:
    count = 0
    for event in events:
        statement = (
            insert(CapitalMarketsEvent)
            .values(
                company_id=company.id,
                accession_number=event.accession_number,
                form=event.form,
                filing_date=event.filing_date,
                report_date=event.report_date,
                primary_document=event.primary_document,
                primary_doc_description=event.primary_doc_description,
                source_url=event.source_url,
                summary=event.summary,
                event_type=event.event_type,
                security_type=event.security_type,
                offering_amount=event.offering_amount,
                shelf_size=event.shelf_size,
                is_late_filer=event.is_late_filer,
                last_checked=checked_at,
            )
            .on_conflict_do_update(
                index_elements=[CapitalMarketsEvent.company_id, CapitalMarketsEvent.accession_number],
                set_={
                    "form": event.form,
                    "filing_date": event.filing_date,
                    "report_date": event.report_date,
                    "primary_document": event.primary_document,
                    "primary_doc_description": event.primary_doc_description,
                    "source_url": event.source_url,
                    "summary": event.summary,
                    "event_type": event.event_type,
                    "security_type": event.security_type,
                    "offering_amount": event.offering_amount,
                    "shelf_size": event.shelf_size,
                    "is_late_filer": event.is_late_filer,
                    "last_checked": checked_at,
                    "last_updated": checked_at,
                },
            )
        )
        session.execute(statement)
        count += 1

    company.capital_markets_last_checked = checked_at
    return count


def _event_type(form: str) -> str:
    if form.startswith("S-") or form.startswith("F-"):
        return "Registration"
    if form.startswith("424B"):
        return "Prospectus"
    if form.startswith("NT"):
        return "Late Filing Notice"
    return "Capital Markets"


def _security_type(form: str, description: str | None) -> str | None:
    description_text = (description or "").lower()
    if "preferred" in description_text:
        return "Preferred Equity"
    if "warrant" in description_text:
        return "Warrants"
    if "notes" in description_text or "debt" in description_text:
        return "Debt"
    if form.startswith("S-") or form.startswith("F-") or form.startswith("424B"):
        return "Common Equity"
    return None


def _extract_dollar_amount(description: str | None) -> float | None:
    if not description:
        return None
    match = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d+)?)", description)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _summary_line(
    form: str,
    description: str | None,
    event_type: str | None,
    security_type: str | None,
    offering_amount: float | None,
    is_late_filer: bool,
) -> str:
    if description:
        return description
    bits = [f"{form} {event_type or 'capital markets'} filing"]
    if security_type:
        bits.append(security_type)
    if offering_amount is not None:
        bits.append(f"${offering_amount:,.0f}")
    if is_late_filer:
        bits.append("late-filer notice")
    return "; ".join(bits) + "."


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    numeric_cik = str(int(cik))
    compact_accession = accession_number.replace("-", "")
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{compact_accession}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json#accn={accession_number}"

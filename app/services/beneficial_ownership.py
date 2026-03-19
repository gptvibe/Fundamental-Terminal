from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import html
import re
from typing import Iterable
from xml.etree import ElementTree

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BeneficialOwnershipParty, BeneficialOwnershipReport, Company
from app.services.sec_edgar import EdgarClient, FilingMetadata

SUPPORTED_BENEFICIAL_OWNERSHIP_FORMS = {"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"}


@dataclass(slots=True)
class BeneficialOwnershipNormalizedReport:
    accession_number: str
    form: str
    base_form: str
    filing_date: date | None
    report_date: date | None
    is_amendment: bool
    primary_document: str | None
    primary_doc_description: str | None
    source_url: str
    summary: str
    parties: tuple["BeneficialOwnershipNormalizedParty", ...] = ()


@dataclass(slots=True)
class BeneficialOwnershipNormalizedParty:
    party_name: str
    role: str | None = None
    filer_cik: str | None = None
    shares_owned: float | None = None
    percent_owned: float | None = None
    event_date: date | None = None
    purpose: str | None = None


def collect_beneficial_ownership_reports(
    cik: str,
    filing_index: dict[str, FilingMetadata],
    client: EdgarClient | None = None,
) -> list[BeneficialOwnershipNormalizedReport]:
    rows: list[BeneficialOwnershipNormalizedReport] = []
    for filing in filing_index.values():
        form = (filing.form or "").upper()
        if form not in SUPPORTED_BENEFICIAL_OWNERSHIP_FORMS:
            continue
        base_form = "SC 13D" if form.startswith("SC 13D") else "SC 13G"
        is_amendment = form.endswith("/A")
        source_url = _build_filing_document_url(cik, filing.accession_number, filing.primary_document)
        description = (filing.primary_doc_description or "").strip() or None
        summary = description or (
            "Beneficial ownership amendment filing." if is_amendment else "Beneficial ownership filing."
        )
        parties: tuple[BeneficialOwnershipNormalizedParty, ...] = ()
        if client is not None and filing.primary_document:
            try:
                _, document_payload = client.get_filing_document_text(cik, filing.accession_number, filing.primary_document)
                parties = _extract_parties_from_document(document_payload)
            except Exception:
                parties = ()
        rows.append(
            BeneficialOwnershipNormalizedReport(
                accession_number=filing.accession_number,
                form=form,
                base_form=base_form,
                filing_date=filing.filing_date,
                report_date=filing.report_date,
                is_amendment=is_amendment,
                primary_document=filing.primary_document,
                primary_doc_description=description,
                source_url=source_url,
                summary=summary,
                parties=parties,
            )
        )
    rows.sort(key=lambda row: (row.filing_date or row.report_date or datetime.min.date(), row.accession_number), reverse=True)
    return rows


def upsert_beneficial_ownership_reports(
    session: Session,
    company: Company,
    reports: Iterable[BeneficialOwnershipNormalizedReport],
    *,
    checked_at: datetime,
) -> int:
    count = 0
    for report in reports:
        statement = (
            insert(BeneficialOwnershipReport)
            .values(
                company_id=company.id,
                accession_number=report.accession_number,
                form=report.form,
                base_form=report.base_form,
                filing_date=report.filing_date,
                report_date=report.report_date,
                is_amendment=report.is_amendment,
                primary_document=report.primary_document,
                primary_doc_description=report.primary_doc_description,
                source_url=report.source_url,
                summary=report.summary,
                last_checked=checked_at,
            )
            .on_conflict_do_update(
                index_elements=[BeneficialOwnershipReport.company_id, BeneficialOwnershipReport.accession_number],
                set_={
                    "form": report.form,
                    "base_form": report.base_form,
                    "filing_date": report.filing_date,
                    "report_date": report.report_date,
                    "is_amendment": report.is_amendment,
                    "primary_document": report.primary_document,
                    "primary_doc_description": report.primary_doc_description,
                    "source_url": report.source_url,
                    "summary": report.summary,
                    "last_checked": checked_at,
                    "last_updated": checked_at,
                },
            )
            .returning(BeneficialOwnershipReport.id)
        )
        report_id = session.execute(statement).scalar_one()
        _replace_report_parties(session, report_id, report.parties)
        count += 1

    company.beneficial_ownership_last_checked = checked_at
    return count


def _replace_report_parties(
    session: Session,
    report_id: int,
    parties: tuple[BeneficialOwnershipNormalizedParty, ...],
) -> None:
    session.execute(delete(BeneficialOwnershipParty).where(BeneficialOwnershipParty.report_id == report_id))
    for party in parties:
        if not party.party_name.strip():
            continue
        session.add(
            BeneficialOwnershipParty(
                report_id=report_id,
                party_name=party.party_name.strip(),
                role=(party.role or "").strip() or None,
                filer_cik=party.filer_cik,
                shares_owned=party.shares_owned,
                percent_owned=party.percent_owned,
                event_date=party.event_date,
                purpose=party.purpose,
            )
        )


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    numeric_cik = str(int(cik))
    compact_accession = accession_number.replace("-", "")
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{compact_accession}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json#accn={accession_number}"


def _extract_parties_from_document(document_payload: str) -> tuple[BeneficialOwnershipNormalizedParty, ...]:
    if "<" not in document_payload:
        return ()
    xml_parties = _extract_parties_from_xml(document_payload)
    if xml_parties:
        return xml_parties
    return _extract_parties_from_text(document_payload)


def _extract_parties_from_xml(document_payload: str) -> tuple[BeneficialOwnershipNormalizedParty, ...]:
    try:
        root = ElementTree.fromstring(document_payload)
    except ElementTree.ParseError:
        return ()

    def _tag_matches(element: ElementTree.Element, suffix: str) -> bool:
        tag_name = element.tag.rsplit("}", 1)[-1].lower()
        return tag_name.endswith(suffix)

    names = [
        _clean_text(node.text)
        for node in root.iter()
        if _tag_matches(node, "nameofreportingperson") and _clean_text(node.text)
    ]
    ciks = [
        _normalize_cik(node.text)
        for node in root.iter()
        if _tag_matches(node, "cik") and _normalize_cik(node.text)
    ]
    shares = [
        _parse_number(node.text)
        for node in root.iter()
        if _tag_matches(node, "amountbeneficiallyowned") and _parse_number(node.text) is not None
    ]
    percents = [
        _parse_number(node.text)
        for node in root.iter()
        if _tag_matches(node, "percentofclassrepresentedbyamountinrow11") and _parse_number(node.text) is not None
    ]
    event_date = next(
        (
            _parse_iso_date(node.text)
            for node in root.iter()
            if _tag_matches(node, "dateofeventwhichrequiresfilingofthisstatement")
            and _parse_iso_date(node.text) is not None
        ),
        None,
    )
    purpose = next(
        (
            _truncate_text(_clean_text(node.text), 500)
            for node in root.iter()
            if _tag_matches(node, "purposeoftransaction") and _clean_text(node.text)
        ),
        None,
    )

    parties: list[BeneficialOwnershipNormalizedParty] = []
    for index, party_name in enumerate(dict.fromkeys(name for name in names if name)):
        parties.append(
            BeneficialOwnershipNormalizedParty(
                party_name=party_name,
                role="reporting_person",
                filer_cik=_value_at(ciks, index),
                shares_owned=_value_at(shares, index),
                percent_owned=_value_at(percents, index),
                event_date=event_date,
                purpose=purpose,
            )
        )
    return tuple(parties)


def _extract_parties_from_text(document_payload: str) -> tuple[BeneficialOwnershipNormalizedParty, ...]:
    plain_text = _collapse_document_text(document_payload)
    if not plain_text:
        return ()

    names = _find_name_candidates(plain_text)
    if not names:
        return ()

    filer_cik = _first_match(r"(?i)cik\s*(?:number|no\.|#|:)\s*(\d{5,10})", plain_text, normalize=_normalize_cik)
    shares_owned = _first_match(
        r"(?is)aggregate\s+amount\s+beneficially\s+owned\s+by\s+each\s+reporting\s+person\s*[:\-]?\s*([\d,]+(?:\.\d+)?)",
        plain_text,
        normalize=_parse_number,
    )
    percent_owned = _first_match(
        r"(?is)percent\s+of\s+class\s+represented\s+by\s+amount\s+in\s+row\s*\(?11\)?\s*[:\-]?\s*([\d.]+)\s*%?",
        plain_text,
        normalize=_parse_number,
    )
    event_date = _first_match(
        r"(?is)date\s+of\s+event\s+which\s+requires\s+filing\s+of\s+this\s+statement\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})",
        plain_text,
        normalize=_parse_iso_date,
    )
    purpose = _extract_purpose_from_text(plain_text)

    return tuple(
        BeneficialOwnershipNormalizedParty(
            party_name=name,
            role="reporting_person",
            filer_cik=filer_cik,
            shares_owned=shares_owned,
            percent_owned=percent_owned,
            event_date=event_date,
            purpose=purpose,
        )
        for name in names
    )


def _find_name_candidates(plain_text: str) -> list[str]:
    candidates: list[str] = []
    patterns = [
        r"(?im)^\s*name\s+of\s+reporting\s+person\s*[:\-]\s*(.{3,120})$",
        r"(?im)^\s*reporting\s+person\s*[:\-]\s*(.{3,120})$",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, plain_text):
            name = _clean_text(match.group(1))
            if not name:
                continue
            if any(token in name.lower() for token in ["irs", "identification", "check", "source"]):
                continue
            candidates.append(name)
    if candidates:
        return list(dict.fromkeys(candidates))

    fallback = _first_match(
        r"(?is)item\s*2\.?\s*identity\s+and\s+background\s*[:\-]?\s*([A-Za-z0-9 ,.'()&-]{3,120})",
        plain_text,
    )
    return [fallback] if isinstance(fallback, str) and fallback else []


def _extract_purpose_from_text(plain_text: str) -> str | None:
    match = re.search(r"(?is)item\s*4\.?\s*purpose\s+of\s+transaction\s*(.*?)(?:item\s*5\.|$)", plain_text)
    if not match:
        return None
    return _truncate_text(_clean_text(match.group(1)), 500)


def _collapse_document_text(document_payload: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", document_payload)
    unescaped = html.unescape(no_tags)
    normalized = re.sub(r"\s+", " ", unescaped)
    return normalized.strip()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip(" ;:\n\t")
    return cleaned or None


def _normalize_cik(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def _parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", ""))
    except ValueError:
        return None


def _parse_iso_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    try:
        return date.fromisoformat(cleaned)
    except ValueError:
        return None


def _truncate_text(value: str | None, max_length: int) -> str | None:
    if not value:
        return None
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _first_match(pattern: str, value: str, normalize=None):
    match = re.search(pattern, value)
    if not match:
        return None
    extracted = match.group(1)
    if normalize is None:
        return _clean_text(extracted)
    return normalize(extracted)


def _value_at(values: list, index: int):
    if not values:
        return None
    if index < len(values):
        return values[index]
    return values[0]

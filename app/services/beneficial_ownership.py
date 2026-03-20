from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import html
import os
import re
from typing import Iterable
from xml.etree import ElementTree

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BeneficialOwnershipParty, BeneficialOwnershipReport, Company
from app.services.sec_edgar import EdgarClient, FilingMetadata

_BENEFICIAL_OWNERSHIP_FORM_PATTERN = re.compile(
    r"^(?:SC\s+|SCHEDULE\s+)?(13D|13G)\s*(/A)?$",
    re.IGNORECASE,
)


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
    amendment_chain_key: str | None = None
    previous_accession_number: str | None = None
    amendment_sequence: int | None = None
    amendment_chain_size: int | None = None


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
        normalized_form = _normalize_beneficial_ownership_form(filing.form)
        if normalized_form is None:
            continue
        form, base_form, is_amendment = normalized_form
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
        if client is not None and not parties:
            try:
                _, submission_payload = client.get_filing_document_text(
                    cik,
                    filing.accession_number,
                    f"{filing.accession_number.replace('-', '')}.txt",
                )
                parties = _extract_parties_from_submission_text(submission_payload)
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
    _assign_amendment_chain_history(rows)
    rows.sort(key=lambda row: (row.filing_date or row.report_date or datetime.min.date(), row.accession_number), reverse=True)
    return rows


def _normalize_beneficial_ownership_form(form: str | None) -> tuple[str, str, bool] | None:
    normalized = re.sub(r"\s+", " ", (form or "").strip()).upper()
    match = _BENEFICIAL_OWNERSHIP_FORM_PATTERN.fullmatch(normalized)
    if not match:
        return None

    family = match.group(1).upper()
    is_amendment = bool(match.group(2))
    base_form = f"SC {family}"
    canonical_form = f"{base_form}/A" if is_amendment else base_form
    return canonical_form, base_form, is_amendment


def _assign_amendment_chain_history(reports: list[BeneficialOwnershipNormalizedReport]) -> None:
    chains: dict[str, list[BeneficialOwnershipNormalizedReport]] = {}
    for report in reports:
        chain_key = _build_amendment_chain_key(report)
        report.amendment_chain_key = chain_key
        chains.setdefault(chain_key, []).append(report)

    for chain in chains.values():
        chain.sort(key=lambda item: (item.filing_date or item.report_date or datetime.min.date(), item.accession_number))
        chain_size = len(chain)
        for index, report in enumerate(chain):
            report.amendment_sequence = index + 1
            report.amendment_chain_size = chain_size
            report.previous_accession_number = chain[index - 1].accession_number if index > 0 else None


def _build_amendment_chain_key(report: BeneficialOwnershipNormalizedReport) -> str:
    ciks = sorted({party.filer_cik for party in report.parties if party.filer_cik})
    if ciks:
        return _truncate_chain_key(f"{report.base_form}:cik:{'|'.join(ciks)}")

    names = sorted({_normalize_chain_name(party.party_name) for party in report.parties if party.party_name.strip()})
    names = [name for name in names if name]
    if names:
        return _truncate_chain_key(f"{report.base_form}:name:{'|'.join(names)}")

    document_token = _document_chain_token(report.primary_document)
    if document_token:
        return _truncate_chain_key(f"{report.base_form}:doc:{document_token}")

    accession = report.accession_number.replace("-", "")
    return _truncate_chain_key(f"{report.base_form}:accession:{accession}")


def _normalize_chain_name(value: str) -> str:
    lowered = value.strip().lower()
    normalized = re.sub(r"\s+", " ", lowered)
    return normalized


def _truncate_chain_key(value: str) -> str:
    if len(value) <= 180:
        return value
    return value[:180]


def _document_chain_token(primary_document: str | None) -> str | None:
    if not primary_document:
        return None
    stem, _ = os.path.splitext(primary_document)
    normalized = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if len(normalized) < 4:
        return None
    return normalized[:96]


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
                amendment_chain_key=report.amendment_chain_key,
                previous_accession_number=report.previous_accession_number,
                amendment_sequence=report.amendment_sequence,
                amendment_chain_size=report.amendment_chain_size,
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
                    "amendment_chain_key": report.amendment_chain_key,
                    "previous_accession_number": report.previous_accession_number,
                    "amendment_sequence": report.amendment_sequence,
                    "amendment_chain_size": report.amendment_chain_size,
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


def _extract_parties_from_submission_text(document_payload: str) -> tuple[BeneficialOwnershipNormalizedParty, ...]:
    if not document_payload:
        return ()

    parties: list[BeneficialOwnershipNormalizedParty] = []
    seen_keys: set[tuple[str, str | None]] = set()

    for match in re.finditer(
        r"(?is)FILED\s+BY\s*:\s*.*?COMPANY\s+CONFORMED\s+NAME\s*:\s*(.{2,160}?)\s+CENTRAL\s+INDEX\s+KEY\s*:\s*(\d{5,10})",
        document_payload,
    ):
        name = _clean_text(match.group(1))
        filer_cik = _normalize_cik(match.group(2))
        if not name:
            continue
        key = (name.lower(), filer_cik)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        parties.append(
            BeneficialOwnershipNormalizedParty(
                party_name=name,
                role="reporting_person",
                filer_cik=filer_cik,
            )
        )

    if parties:
        return tuple(parties)

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
        r"(?is)date\s+of\s+event\s+which\s+requires\s+filing\s+of\s+this\s+statement\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})",
        plain_text,
        normalize=_parse_flexible_date,
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
        r"(?is)name\s+of\s+reporting\s+person\s*[:\-]\s*([A-Za-z0-9 ,.'()&-]{3,120})",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, plain_text):
            raw_name = _clean_text(match.group(1))
            if not raw_name:
                continue
            name = re.split(r"\b(?:CIK|IRS|ITEM\s+\d+)\b", raw_name, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ;:,")
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


def _parse_flexible_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None

    iso_date = _parse_iso_date(cleaned)
    if iso_date is not None:
        return iso_date

    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", cleaned)
    if not match:
        return None
    month, day, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(year, month, day)
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

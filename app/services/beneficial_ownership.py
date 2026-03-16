from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BeneficialOwnershipParty, BeneficialOwnershipReport, Company
from app.services.sec_edgar import FilingMetadata

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
    parties: tuple[tuple[str, str | None], ...] = ()


def collect_beneficial_ownership_reports(cik: str, filing_index: dict[str, FilingMetadata]) -> list[BeneficialOwnershipNormalizedReport]:
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
    parties: tuple[tuple[str, str | None], ...],
) -> None:
    session.execute(delete(BeneficialOwnershipParty).where(BeneficialOwnershipParty.report_id == report_id))
    for party_name, role in parties:
        if not party_name.strip():
            continue
        session.add(
            BeneficialOwnershipParty(
                report_id=report_id,
                party_name=party_name.strip(),
                role=(role or "").strip() or None,
            )
        )


def _build_filing_document_url(cik: str, accession_number: str, primary_document: str | None) -> str:
    numeric_cik = str(int(cik))
    compact_accession = accession_number.replace("-", "")
    if primary_document:
        return f"https://www.sec.gov/Archives/edgar/data/{numeric_cik}/{compact_accession}/{primary_document}"
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json#accn={accession_number}"
